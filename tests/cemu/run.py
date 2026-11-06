"""Real-game smoke test. Run with the patcher's Python; see docs/cemu_integration_tests.md."""
from pathlib import Path
import argparse
import ctypes
import hashlib
import fcntl
import json
import math
import os
import shutil
import signal
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from items import scenarios, reset_delivery_state, physical_check, world_reference, set_save_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def patch_save(data, position, angle, chest_hash, map_type="MainField", map_name="D-6", chest_actor="TBox_Field_Stone"):
    """Edit existing v208 big-endian hash/value records, preserving their layout."""
    data = bytearray(data)
    if len(data) not in (1027208, 1027248) or struct.unpack_from('>I', data)[0] != 0x471b:
        raise ValueError('Expected a Wii U v208 game_data.sav')
    def offsets(name):
        key = zlib.crc32(name.encode())
        found = [i + 4 for i in range(12, len(data) - 4, 8)
                 if struct.unpack_from('>I', data, i)[0] == key]
        if not found:
            raise ValueError(f'Save lacks required field {name}')
        return found
    def write(name, values, fmt):
        locations = offsets(name)
        if len(locations) != len(values):
            raise ValueError(f'Unexpected field size for {name}')
        for at, value in zip(locations, values):
            struct.pack_into('>' + fmt, data, at, value)
    write('PlayerSavePos', position, 'f')
    write('PlayerSavePosAngleYDegree', [angle], 'f')
    if chest_hash is not None:
        write(f'{map_type}_{chest_actor}_{chest_hash}', [0], 'I')
    for name, value in [('PlayerSavePosMapType', map_type), ('PlayerSavePosMapName', map_name)]:
        locs = offsets(name)
        encoded = value.encode().ljust(len(locs)*4, b'\0')
        if len(encoded) != len(locs)*4:
            raise ValueError('Map name exceeds save field')
        for index, at in enumerate(locs): data[at:at+4] = encoded[index*4:index*4+4]
    return data


def prepare(args, run):
    from src.patcher.core import ROOT as _
    from botw_static.resources import GameDump, decode_byml, decompress, replace_members
    from botw_static.protocol import seed_fingerprint
    from botw_static.apply import apply_plan
    from botw_static.runes import catalog as rune_catalog
    titles = args.cemu_data / 'mlc01/usr/title'
    title = '101c9500'
    dump = GameDump(titles/f'00050000/{title}/content', titles/f'0005000e/{title}/content',
                    titles/f'0005000c/{title}/content')
    chest = next(c for c in json.loads(args.catalog.read_text())['locations'] if c['hash_id'] == 2009260213)
    completion = physical_check(args.completion) if args.completion else None
    rune_test = None
    if args.rune_terminal:
        if completion or args.location_id is not None: raise ValueError('--rune-terminal cannot be combined with another physical check')
        rune_test = next((entry for entry in rune_catalog()['locations'] if entry['dungeon'] == args.rune_terminal), None)
        if rune_test is None: raise ValueError('Unknown rune terminal dungeon')
        completion = next(entry for entry in world_reference().load_completions()
                          if entry.get('dungeon') == args.rune_terminal)
    if args.location_id is not None:
        from botw_static.combat import catalog as combat_catalog
        available = [*world_reference().load_chests(), *world_reference().load_completions(), *combat_catalog()['locations']]
        completion = next((e for e in available if e['id'] == args.location_id), None)
        if completion is None: raise ValueError('Unknown production location ID')
        completion = dict(completion, kind=completion.get('kind', 'chest'))
    cases = scenarios(args.items)
    if rune_test:
        rune_reward = args.reward or rune_test['item']
        cases = [case for case in scenarios('full') if case['name'] == rune_reward][:1]
    elif completion:
        name = args.reward or ('Dueling Peaks Tower' if args.completion == 'tower' else 'Arrows (10)')
        cases = [c for c in scenarios('full') if c['name'] == name]
        if not cases: raise ValueError('Unknown reward item: ' + name)
    location, item = (completion or chest)['id'], cases[0]["item"]
    locations = [completion or chest]
    if args.watch_combat:
        from botw_static.combat import catalog as combat_catalog
        locations.extend(e for e in combat_catalog()['locations'] if e['id'] != location)
    if args.all_checks:
        from botw_static.combat import catalog as combat_catalog
        known = {entry['id'] for entry in locations}
        locations.extend(entry for entry in [*world_reference().load_chests(), *world_reference().load_completions(),
                                             *combat_catalog()['locations']] if entry['id'] not in known)
    fingerprint = seed_fingerprint('test', 1, [e['id'] for e in locations])
    slot = dict(protocol_version=2, player=1, seed='test', seed_fingerprint=fingerprint,
                check_actor_prefix='AP_Check_', locations={str(e['id']):f'AP_Check_{e["id"]:08X}' for e in locations},
                items={str(case['item']): case['delivery'] for case in cases})
    planned_locations = [dict(entry, placed_item=dict(
        name=cases[0]['name'], id=cases[0]['item'], player=1, player_name='Test'))
        if entry['id'] == location else dict(entry) for entry in locations]
    plan = dict(version=1, game='Breath of the Wild', player=1, player_name='Test', seed='test',
                locations=planned_locations, slot_data=slot)
    (run/'plan.json').write_text(json.dumps(plan, indent=2))
    config, data = run/'config/Cemu', run/'data/Cemu'
    config.mkdir(parents=True); data.mkdir(parents=True)
    pack = data/'graphicPacks/APTest'
    apply_plan(plan, dump, str(run/'pack.zip'))
    with zipfile.ZipFile(run/'pack.zip') as archive:
        archive.extractall(pack)
    if args.assisted_combat:
        from native import ASSEMBLY
        hook = pack/'BotW_AP_P1/patch_Archipelago.asm'
        hook.write_text(hook.read_text().replace('_AP_Is_Injecting:', ASSEMBLY + '\n_AP_Is_Injecting:', 1))
    if args.fast_fixtures and completion and completion['kind'] == 'shrine':
        # Physical A interaction still starts the real monk event. In test packs,
        # enter at the patched reward node to omit the long decorative cinematic.
        import evfl, io, oead
        from evfl.util import make_index
        event_path = pack/'BotW_AP_P1/content/Event/Demo033_0.sbeventpack'
        raw = event_path.read_bytes()
        archive = oead.Sarc(decompress(raw))
        member = 'EventFlow/Demo033_0.bfevfl'
        document = evfl.EventFlow(); document.read(bytes(archive.get_file(member).data))
        entry = next(e for e in document.flowchart.entry_points if e.name == 'Demo033_0')
        entry.main_event = make_index(next(e for e in document.flowchart.events if e.name == 'Event204'))
        stream = io.BytesIO(); assert document.write(stream)
        event_path.write_bytes(replace_members(raw, {member: stream.getvalue()}))
    mlc = run/'mlc'
    for kind in ('00050000','0005000e','0005000c'):
        parent = mlc/'usr/title'/kind
        parent.mkdir(parents=True, exist_ok=True)
        (parent/title).symlink_to(titles/kind/title, target_is_directory=True)
    save = mlc/f'usr/save/00050000/{title}/user/80000001'
    (save/'0').mkdir(parents=True)
    with zipfile.ZipFile(args.save_source) as archive:
        prefix = f'00050000/{title}/user/80000001/'
        original = archive.read(prefix+'0/game_data.sav')
        map_type, map_name = 'MainField', 'D-6'
        angle = 180.0
        if completion and completion['kind'] == 'tower':
            binding = completion['terminals'][0]
            obj = next(o for o in decode_byml(dump.read(binding['resource']))['Objs']
                       if int(o['HashId']) == binding['hash_id'])
            x,y,z = map(float, obj['Translate'])
            rotation = obj.get('Rotate', 0)
            yaw = float(rotation[1]) if hasattr(rotation, '__len__') else float(rotation)
            x += math.sin(yaw) * 1.6; z += math.cos(yaw) * 1.6; y += .1
            angle = math.degrees(yaw) + 180
            map_name = binding['resource'].split('/')[-1].split('_')[0]
        elif completion and completion['kind'] == 'shrine':
            dungeon = completion['dungeon']; map_type, map_name = 'CDungeon', dungeon
            doc = decode_byml(dump.read(f'content/Pack/{dungeon}.pack!Map/CDungeon/{dungeon}/{dungeon}_Static.smubin'))
            if rune_test:
                terminal = next(o for o in doc['Objs'] if int(o['HashId']) == rune_test['hash_id'])
                yaw = float(terminal.get('Rotate', 0))
                x,y,z = map(float, terminal['Translate'])
                # Start inside the terminal's interaction radius so a single A
                # press can test its action without walking Link across the room.
                x += math.sin(yaw)*.9; z += math.cos(yaw)*.9; y += .1
                angle = math.degrees(yaw)+180
            else:
                anchor = next(o for o in doc['Objs'] if o['UnitConfigName'] == 'DestinationAnchor')
                x,y,z = map(float, anchor['Translate']); y += .1
                angle = math.degrees(float(anchor.get('Rotate', 0)))
        elif completion:
            if 'position' not in completion:
                raise ValueError('Physical fixture needs a scene-specific boss spawn; location cannot be marked visited')
            x,y,z = completion['position']; y += .1; z += 1.7
            logical = completion['logical_map'].split('/')
            map_type, map_name = logical[1], logical[2]
        else:
            x,y,z = chest['position']; y += .1; z += 1.7
        target = completion or chest
        chest_actor, chest_hash = 'TBox_Field_Stone', chest['hash_id']
        if completion:
            chest_hash = None
            if completion['kind'] == 'chest':
                obj = next(o for o in decode_byml(dump.read(completion['resource']))['Objs']
                           if int(o['HashId']) == completion['hash_id'])
                chest_actor, chest_hash = str(obj['UnitConfigName']), completion['hash_id']
                rotation = obj.get('Rotate', 0)
                yaw = float(rotation[1]) if hasattr(rotation, '__len__') else float(rotation)
                x,y,z = map(float, obj['Translate'])
                x += math.sin(yaw)*1.7; z += math.cos(yaw)*1.7; y += .1
                angle = math.degrees(yaw)+180
        if completion and completion.get('actor') == 'Enemy_Giant_Bone':
            angle = 0.0  # Stalnox cannot materialize while its spawn point is in view.
        edited = patch_save(original, [x,y,z], angle, chest_hash, map_type, map_name, chest_actor)
        edited = reset_delivery_state(edited)
        if completion:
            # Physical checks outside the Plateau require its exit prerequisite.
            # Set this only in the isolated fixture, before the player is spawned.
            from botw_static.starting import PLATEAU_FLAGS
            edited = set_save_values(edited, {'IsGet_PlayerStole2': 1, 'Location_MapTower07': 1, **{name: 1 for name in PLATEAU_FLAGS}})
        if completion and completion.get('actor') == 'Enemy_Giant_Bone':
            edited = set_save_values(edited, {'MaxHartValue': 120, 'CurrentHart': 120, 'WM_Time': struct.unpack('>I', struct.pack('>f', 330.0))[0],
                'WM_TimeDivision': 6, 'WM_NighttimeFlag': 1, 'WM_DaytimeFlag': 0})
        if completion and completion['kind'] == 'boss':
            scene = completion['scene']
            if scene.startswith('Remains'):
                element = scene.removeprefix('Remains')
                control_item = {'Wind': 'Vah Medoh Controls', 'Fire': 'Vah Rudania Controls', 'Water': 'Vah Ruta Controls', 'Electric': 'Vah Naboris Controls'}[element]
                control_flags = world_reference().native_grants[control_item]['Tiers'][0]['Writes']
                edited = set_save_values(edited, {flag['Name']: flag['Value'] for flag in control_flags})
                edited = set_save_values(edited, {f'Appear_PGanon{element}': 1, f'Die_PGanon{element}': 0,
                    f'MainFieldDungeon_{completion["actor"]}_{completion["hash_id"]}': 0})
            elif completion['actor'] == 'Enemy_Ganon':
                edited = set_save_values(edited, {'MainField_Enemy_Ganon_108794243': 0,
                    'LastBossGanonBeastGenerateFlag': 0, 'IsGanonLiving': 1, 'GanonQuest_Finished': 0})
            elif completion['actor'] == 'Enemy_GanonBeast':
                edited = set_save_values(edited, {'LastBossGanonBeastGenerateFlag': 1,
                    'IsGanonLiving': 1, 'GanonQuest_Finished': 0})
            elif scene == 'FinalTrial':
                edited = set_save_values(edited, {'Appear_Boss_FinalTrial': 1, 'Die_Boss_FinalTrial': 0,
                    'FinalTrial_Open_DoorBoss': 1})
        if completion and completion['kind'] == 'tower' and args.location_id is not None:
            edited = set_save_values(edited, {f'MapTower_{completion["tower"]:02}': 1, f'Location_MapTower{completion["tower"]:02}': 1})
        if completion and completion['kind'] == 'shrine':
            key = zlib.crc32(('Clear_' + completion['dungeon']).encode())
            found = False
            for at in range(12,len(edited)-4,8):
                if struct.unpack_from('>I',edited,at)[0] == key:
                    struct.pack_into('>I',edited,at+4,0); found = True
            if not found: raise ValueError('Save lacks shrine completion flag')
        if rune_test:
            # This flag selects the first-entry greeting when true. Keep it
            # clear in the isolated fixture so the terminal test starts without
            # Owa Daim's intro event consuming the interaction inputs.
            activation_flag = rune_test['activation_flag']
            edited = set_save_values(edited, {activation_flag: 0, 'Npc_DungeonPriest_First': 0,
                                               f'Open_{rune_test["dungeon"]}': 1})
        (save/'0/game_data.sav').write_bytes(edited)
        for filename in ('caption.sav','caption.jpg'):
            (save/'0'/filename).write_bytes(archive.read(prefix+'0/'+filename))
        (save/'option.sav').write_bytes(archive.read(prefix+'option.sav'))
    overlay = pack/'BotW_AP_P1'
    overlay_hashes = {}
    for path in sorted(overlay.rglob('*')):
        if path.is_file():
            with path.open('rb') as stream:
                overlay_hashes[path.relative_to(overlay).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    # Keep an exact, reviewable delta for test-only overrides even when the route
    # prunes successful emulator profiles. pack.zip remains the production pack.
    with zipfile.ZipFile(run/'pack.zip') as production, zipfile.ZipFile(run/'fixture-overrides.zip', 'w', zipfile.ZIP_DEFLATED) as overrides:
        for relative, digest in overlay_hashes.items():
            name = 'BotW_AP_P1/' + relative
            if name not in production.namelist() or hashlib.sha256(production.read(name)).hexdigest() != digest:
                overrides.write(overlay/relative, name)
    (run/'fixture.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256(original).hexdigest(),
        save_sha256=hashlib.sha256(edited).hexdigest(), position=[x,y,z], fingerprint=fingerprint,
        runtime_overlay_sha256=overlay_hashes, assisted_native_defeat=args.assisted_combat,
        assisted_fast_events=args.fast_fixtures), indent=2))
    tree = ET.parse(args.cemu_config/'settings.xml'); root = tree.getroot()
    for name, value in [('mlc_path', str(mlc)), ('check_update','false'), ('fullscreen','false')]:
        element = root.find(name)
        if element is None: element = ET.SubElement(root,name)
        element.text = value
    root.find('Graphic/api').text = '0' if args.headless else '1'
    old = root.find('GraphicPack')
    if old is not None: root.remove(old)
    gp = ET.SubElement(root,'GraphicPack')
    ET.SubElement(gp,'Entry',filename='graphicPacks/APTest/BotW_AP_P1/rules.txt')
    graphics = args.cemu_data/'graphicPacks/downloadedGraphicPacks/BreathOfTheWild/Graphics'
    if graphics.is_dir():
        shutil.copytree(graphics, data/'graphicPacks/TestGraphics')
        entry = ET.SubElement(gp,'Entry',filename='graphicPacks/TestGraphics/rules.txt')
        preset = ET.SubElement(entry,'Preset')
        ET.SubElement(preset,'category').text='Resolution'
        ET.SubElement(preset,'preset').text=args.resolution
    tree.write(config/'settings.xml', encoding='utf-8', xml_declaration=True)
    controller = ET.Element('emulated_controller')
    ET.SubElement(controller,'type').text = 'Wii U Pro Controller'
    ctrl = ET.SubElement(controller,'controller')
    for name,value in [('api','Keyboard'),('uuid','keyboard'),('display_name','Keyboard')]:
        ET.SubElement(ctrl,name).text = value
    mappings = ET.SubElement(ctrl,'mappings')
    for mapping,key in [(1,ord('e')),(2,ord('q')),(3,ord('x')),(4,ord('f')),(9,ord('p')),(12,65362),(13,65364),
                        (18,ord('w')),(19,ord('s')),(20,ord('a')),(21,ord('d')),
                        (22,ord('i')),(23,ord('k')),(24,ord('j')),(25,ord('l'))]:
        entry=ET.SubElement(mappings,'entry')
        ET.SubElement(entry,'mapping').text=str(mapping); ET.SubElement(entry,'button').text=str(key)
    (config/'controllerProfiles').mkdir()
    ET.ElementTree(controller).write(config/'controllerProfiles/controller0.xml')
    scenario = dict(slot_data=slot, location=location, cases=cases, mode=args.items,
                    item_timeout_seconds=args.item_timeout, progress_path=str(run/'progress.json'),
                    timeout_seconds=args.timeout, state_directory=str(run/'journal'), result_path=str(run/'probe.json'))
    scenario['watch_combat'] = args.watch_combat
    scenario['assisted_combat'] = args.assisted_combat
    scenario['fast_fixtures'] = args.fast_fixtures
    scenario['delivery_after_check'] = args.location_id is not None
    if rune_test:
        scenario['rune_terminal_test'] = dict(dungeon=rune_test['dungeon'], flag=
            rune_test['flag'], activation_flag=rune_test['activation_flag'])
        scenario['rune_interaction_path'] = str(run/'rune-interaction.json')
        scenario['delivery_after_check'] = True
    if completion:
        scenario['physical_check'] = completion
        scenario['expected_position'] = [x,y,z]
    (run/'scenario.json').write_text(json.dumps(scenario,indent=2))
    return titles/f'00050000/{title}/code/U-King.rpx', mlc


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cemu-data',type=Path,default=Path.home()/'.local/share/Cemu')
    parser.add_argument('--cemu-config',type=Path,default=Path.home()/'.config/Cemu')
    parser.add_argument('--save-source',type=Path,default=ROOT/'out/botw-save-backup-20261005-014705.zip')
    parser.add_argument('--catalog',type=Path,default=ROOT/'out/chests-dlc-fixed.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fast-fixtures', action='store_true', help='Test-pack-only omission of decorative monk cinematics; still requires physical interaction')
    parser.add_argument('--all-checks', action='store_true', help='Load the complete production check overlay and native watch table')
    parser.add_argument('--assisted-combat', action='store_true', help='Test-only native zero-life assistance; requires the real enemy death lifecycle to generate the check')
    parser.add_argument('--location-id', type=lambda value: int(value, 0), help='Visit and physically collect a production location before its reward is sent')
    parser.add_argument('--reward', help='Production item name to verify after the location check')
    parser.add_argument('--rune-terminal', choices=('Dungeon009','Dungeon038','Dungeon041','Dungeon065'),
                        help='Verify a Plateau terminal cannot grant its rune outside AP; then exercise the AP grant')
    parser.add_argument('--watch-combat', action='store_true', help='Include all native death watches and assert incoming grants do not trigger them')
    parser.add_argument('--completion', choices=('shrine', 'tower'),
                        help='Validate a physical monk/tower check; tower mode first tests that an AP grant emits no check')
    parser.add_argument('--items', choices=('simplified', 'partial', 'full'), default='simplified',
                        help='One item, one item type per delivery category (all its tiers), or every item and tier')
    parser.add_argument('--item-timeout', type=int, default=15, help='Maximum seconds per receipt; advances immediately on success')
    parser.add_argument('--resolution', default='320x180', help='Community Graphics pack resolution preset')
    parser.add_argument('--capture-pickup-frames', action='store_true', help='Capture chest interaction frames for visual review')
    parser.add_argument('--timeout',type=int,default=600)
    parser.add_argument('--display', default=os.environ.get('DISPLAY'),
                        help='X display to use (defaults to DISPLAY; Vulkan acceleration is enabled)')
    parser.add_argument('--headless', action='store_true',
                        help='Use private Xvfb with OpenGL software rendering')
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    lease=open('/tmp/botw-cemu-integration.lock','a')
    try: fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: parser.error('Another integration runner is active')
    if not args.display and not args.headless and not args.prepare_only:
        parser.error('No X display found; set DISPLAY or pass --headless')
    if not 1 <= args.item_timeout <= 120: parser.error('--item-timeout must be between 1 and 120 seconds')
    if not 30 <= args.timeout <= 1800: parser.error('--timeout must be between 30 and 1800 seconds')
    run=args.output.resolve(); run.mkdir(parents=True,exist_ok=False)
    children=[]; logs=[]; started=time.monotonic(); result={'passed':False}
    def interrupted(signum, frame): raise RuntimeError(f'Interrupted by signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    def launch(command, name, env):
        log=open(run/(name+'.log'),'w'); logs.append(log)
        def allow_test_client():
            # Yama otherwise prohibits the sibling .NET client from attaching.
            if ctypes.CDLL(None, use_errno=True).prctl(0x59616d61, ctypes.c_ulong(-1).value, 0, 0, 0) != 0:
                raise OSError(ctypes.get_errno(), "PR_SET_PTRACER failed")
        p=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
                           preexec_fn=allow_test_client if name == 'cemu' else None)
        children.append(p); return p
    try:
        if not args.prepare_only:
            with open(run/'build.log','w') as build_log:
                subprocess.run(['dotnet','build',str(ROOT/'src/client'),'--no-restore'],
                               stdout=build_log,stderr=subprocess.STDOUT,check=True,timeout=120)
        game,mlc=prepare(args,run)
        if args.prepare_only:
            result={'prepared':True,'passed':False}; return 0
        env=os.environ.copy();env.update(XDG_CONFIG_HOME=str(run/'config'),XDG_DATA_HOME=str(run/'data'),
                                        XDG_CACHE_HOME=str(run/'cache'),GDK_BACKEND='x11')
        # Use the user's accelerated display unless headless mode was requested.
        if args.display and not args.headless:
            env['DISPLAY']=args.display
        else:
            read_fd,write_fd=os.pipe()
            log=open(run/'xvfb.log','w');logs.append(log)
            xvfb=subprocess.Popen(['Xvfb','-displayfd',str(write_fd),'-screen','0','1280x720x24'],
                pass_fds=(write_fd,),stdout=log,stderr=log,start_new_session=True)
            children.append(xvfb);os.close(write_fd)
            import select
            if not select.select([read_fd],[],[],10)[0]: raise TimeoutError('Xvfb startup')
            env['DISPLAY']=':'+os.read(read_fd,32).decode().strip();os.close(read_fd)
        cemu=launch(['Cemu','-m',str(mlc),'-g',str(game)],'cemu',env)
        scenario=json.loads((run/'scenario.json').read_text());scenario['cemu_pid']=cemu.pid
        (run/'scenario.json').write_text(json.dumps(scenario))
        def command(*parts): return subprocess.run(parts,env=env,check=True,capture_output=True,timeout=10).stdout
        probe=launch(['dotnet',str(ROOT/'src/client/bin/Debug/net10.0/BotWClient.dll'),
                      '--cemu-test',str(run/'scenario.json')],'client',env)
        def capture(filename='screen.png'):
            try: subprocess.run(['import','-window',window,str(run/filename)], env=env,
                                capture_output=True, timeout=2, check=False)
            except (subprocess.TimeoutExpired, OSError): pass
        def check_pack():
            log_path = run/'data/Cemu/log.txt'
            if log_path.exists():
                log = log_path.read_text(errors='replace')
                if 'No patches for this graphic pack will be applied' in log:
                    raise RuntimeError('Cemu rejected the generated hook; see data/Cemu/log.txt')
        window=None
        while time.monotonic()-started<args.timeout:
            check_pack()
            if cemu.poll() is not None: raise RuntimeError('Cemu exited during startup')
            found=subprocess.run(['xdotool','search','--onlyvisible','--pid',str(cemu.pid),'--name','Cemu'],env=env,capture_output=True,timeout=10).stdout.splitlines()
            if found: window=found[-1].decode();break
            time.sleep(.5)
        if window is None: raise TimeoutError('Cemu window')
        command('xdotool','windowfocus',window)
        # Press A through title/Continue/save confirmation. The probe establishes gameplay readiness.
        last_capture=0; last_press=0; last_pack_check=0; rune_interaction_sent=False; chest_captured=False
        last_pickup_capture=0; pickup_frame=0
        while time.monotonic()-started<args.timeout:
            if time.monotonic()-last_pack_check > 1:
                check_pack(); last_pack_check=time.monotonic()
            if cemu.poll() is not None:
                if (run/'probe.json').exists(): result=json.loads((run/'probe.json').read_text())
                raise RuntimeError('Cemu exited; see client.log and data/Cemu/log.txt')
            progress_path = run/'progress.json'
            try: progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
            except (ValueError, OSError): progress = {}
            if (args.capture_pickup_frames and progress.get('stage') == 'chest acquisition and AP LocationChecks'
                    and time.monotonic()-last_pickup_capture >= .5):
                capture(f'pickup-{pickup_frame:03}.png')
                pickup_frame += 1; last_pickup_capture=time.monotonic()
            if progress.get('chest_checked') and not chest_captured:
                capture('chest_reward.png'); chest_captured=True
            allow_input = progress.get('input_allowed', True) if (args.completion or args.location_id is not None or args.rune_terminal) else (not progress.get('chest_checked') or progress.get('completed', 0) == 0)
            stage = progress.get('stage', '')
            if args.rune_terminal and progress.get('input_allowed') and stage == 'native observation RPC':
                allow_input = not rune_interaction_sent
            press_interval = 1.5 if args.rune_terminal else .7
            if allow_input and time.monotonic()-last_press >= press_interval:
                command('xdotool','windowfocus',window)
                command('xdotool','keydown','e');time.sleep(.08);command('xdotool','keyup','e')
                last_press=time.monotonic()
                if args.rune_terminal and progress.get('input_allowed') and stage == 'native observation RPC':
                    (run/'rune-interaction.json').write_text(json.dumps({'pressed': True, 'key': 'A'}))
                    rune_interaction_sent=True
            if probe is not None and probe.poll() is not None:
                result=json.loads((run/'probe.json').read_text())
                if probe.returncode: return 1
                capture();return 0
            if time.monotonic()-last_capture>10:
                capture();last_capture=time.monotonic()
            time.sleep(.1)
        raise TimeoutError('End-to-end deadline exceeded')
    except Exception as error:
        result['error']=str(error);print(error,file=sys.stderr);return 1
    finally:
        for child in reversed(children):
            # Signal the whole group even if its leader exited; Cemu can leave
            # renderer/helper children behind after its main process terminates.
            try: os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: pass
            try: os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            try: child.wait(timeout=1)
            except subprocess.TimeoutExpired: pass
        for log in logs:log.close()
        result['elapsed_seconds']=time.monotonic()-started
        (run/'result.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__':sys.exit(main())
