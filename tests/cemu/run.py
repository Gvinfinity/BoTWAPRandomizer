"""Real-game smoke test. Run with the patcher's Python; see docs/cemu_integration_tests.md."""
from pathlib import Path
import argparse
import ctypes
import hashlib
import fcntl
import json
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def patch_save(data, position, angle, chest_hash):
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
    write(f'MainField_TBox_Field_Stone_{chest_hash}', [0], 'I')
    for name, value in [('PlayerSavePosMapType', 'MainField'), ('PlayerSavePosMapName', 'D-6')]:
        locs = offsets(name)
        encoded = value.encode().ljust(len(locs)*4, b'\0')
        if len(encoded) != len(locs)*4:
            raise ValueError('Map name exceeds save field')
        for index, at in enumerate(locs): data[at:at+4] = encoded[index*4:index*4+4]
    return data


def prepare(args, run):
    from src.patcher.core import ROOT as _
    from botw_static.resources import GameDump
    from botw_static.protocol import seed_fingerprint
    from botw_static.apply import apply_plan
    titles = args.cemu_data / 'mlc01/usr/title'
    title = '101c9500'
    dump = GameDump(titles/f'00050000/{title}/content', titles/f'0005000e/{title}/content',
                    titles/f'0005000c/{title}/content')
    chest = next(c for c in json.loads(args.catalog.read_text())['locations'] if c['hash_id'] == 2009260213)
    location, item = chest['id'], 4000000001
    fingerprint = seed_fingerprint('test', 1, [location])
    slot = dict(protocol_version=2, player=1, seed='test', seed_fingerprint=fingerprint,
                check_actor_prefix='AP_Check_', locations={str(location):f'AP_Check_{location:08X}'},
                items={str(item):dict(kind='actor', actor='Item_Fruit_A', quantity=1)})
    plan = dict(version=1, game='Breath of the Wild', player=1, seed='test', locations=[chest], slot_data=slot)
    (run/'plan.json').write_text(json.dumps(plan, indent=2))
    config, data = run/'config/Cemu', run/'data/Cemu'
    config.mkdir(parents=True); data.mkdir(parents=True)
    pack = data/'graphicPacks/APTest'
    apply_plan(plan, dump, str(run/'pack.zip'))
    with zipfile.ZipFile(run/'pack.zip') as archive:
        archive.extractall(pack)
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
        x,y,z = chest['position']
        # Unrotated stone chest faces +Z; face it from the front.
        edited = patch_save(original, [x,y+0.1,z+1.7], 180.0, chest['hash_id'])
        (save/'0/game_data.sav').write_bytes(edited)
        for filename in ('caption.sav','caption.jpg'):
            (save/'0'/filename).write_bytes(archive.read(prefix+'0/'+filename))
        (save/'option.sav').write_bytes(archive.read(prefix+'option.sav'))
    (run/'fixture.json').write_text(json.dumps(dict(source_sha256=hashlib.sha256(original).hexdigest(),
        save_sha256=hashlib.sha256(edited).hexdigest(), position=[x,y+0.1,z+1.7], fingerprint=fingerprint), indent=2))
    tree = ET.parse(args.cemu_config/'settings.xml'); root = tree.getroot()
    for name, value in [('mlc_path', str(mlc)), ('check_update','false'), ('fullscreen','false')]:
        element = root.find(name)
        if element is None: element = ET.SubElement(root,name)
        element.text = value
    root.find('Graphic/api').text = '1' if args.display else '0'
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
        ET.SubElement(preset,'preset').text='320x180'
    tree.write(config/'settings.xml', encoding='utf-8', xml_declaration=True)
    controller = ET.Element('emulated_controller')
    ET.SubElement(controller,'type').text = 'Wii U Pro Controller'
    ctrl = ET.SubElement(controller,'controller')
    for name,value in [('api','Keyboard'),('uuid','keyboard'),('display_name','Keyboard')]:
        ET.SubElement(ctrl,name).text = value
    mappings = ET.SubElement(ctrl,'mappings')
    for mapping,key in [(1,ord('e')),(2,ord('q')),(9,ord('p')),(12,65362),(13,65364),
                        (18,ord('w')),(19,ord('s')),(20,ord('a')),(21,ord('d'))]:
        entry=ET.SubElement(mappings,'entry')
        ET.SubElement(entry,'mapping').text=str(mapping); ET.SubElement(entry,'button').text=str(key)
    (config/'controllerProfiles').mkdir()
    ET.ElementTree(controller).write(config/'controllerProfiles/controller0.xml')
    scenario = dict(slot_data=slot, location=location, item=item, actor='Item_Fruit_A',
                    timeout_seconds=args.timeout, state_directory=str(run/'journal'), result_path=str(run/'probe.json'))
    (run/'scenario.json').write_text(json.dumps(scenario,indent=2))
    return titles/f'00050000/{title}/code/U-King.rpx', mlc


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cemu-data',type=Path,default=Path.home()/'.local/share/Cemu')
    parser.add_argument('--cemu-config',type=Path,default=Path.home()/'.config/Cemu')
    parser.add_argument('--save-source',type=Path,default=ROOT/'out/botw-save-backup-20261005-014705.zip')
    parser.add_argument('--catalog',type=Path,default=ROOT/'out/chests-dlc-fixed.json')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=600)
    parser.add_argument('--display', help='Existing X display for hardware rendering; default creates private Xvfb')
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    lease=open('/tmp/botw-cemu-integration.lock','a')
    try: fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: parser.error('Another integration runner is active')
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
        # Allocate a private display without touching the user's active desktop.
        if args.display:
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
        window=None
        while time.monotonic()-started<args.timeout:
            if cemu.poll() is not None: raise RuntimeError('Cemu exited during startup')
            found=subprocess.run(['xdotool','search','--onlyvisible','--pid',str(cemu.pid),'--name','Cemu'],env=env,capture_output=True,timeout=10).stdout.splitlines()
            if found: window=found[-1].decode();break
            time.sleep(.5)
        if window is None: raise TimeoutError('Cemu window')
        command('xdotool','windowfocus',window)
        # Press A through title/Continue/save confirmation. The probe establishes gameplay readiness.
        probe=None;last_capture=0
        while time.monotonic()-started<args.timeout:
            if cemu.poll() is not None: raise RuntimeError('Cemu exited')
            command('xdotool','keydown','e');time.sleep(.5);command('xdotool','keyup','e')
            if time.monotonic()-started>25 and probe is None:
                probe=launch(['dotnet',str(ROOT/'src/client/bin/Debug/net10.0/BotWClient.dll'),
                              '--cemu-test',str(run/'scenario.json')],'client',env)
            if probe is not None and probe.poll() is not None:
                command('import','-window',window,str(run/'screen.png'))
                if probe.returncode: raise RuntimeError('Live probe failed; see client.log')
                result=json.loads((run/'probe.json').read_text());return 0
            if time.monotonic()-last_capture>10:
                command('import','-window',window,str(run/'screen.png'));last_capture=time.monotonic()
            time.sleep(1)
        raise TimeoutError('End-to-end deadline exceeded')
    except Exception as error:
        result['error']=str(error);print(error,file=sys.stderr);return 1
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
        for log in logs:log.close()
        result['elapsed_seconds']=time.monotonic()-started
        (run/'result.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__':sys.exit(main())
