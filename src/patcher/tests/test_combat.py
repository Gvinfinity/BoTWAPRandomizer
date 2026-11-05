import struct

from src.patcher.core import ROOT
from botw_static.combat import catalog
from botw_static.hook import build_seed_hook
from botw_static.protocol import seed_fingerprint, PROTOCOL as P
from test_hook_protocol import PPC


def watch_vm(count=2, kind=None):
    entries = [dict(id=0xC1000000+i, kind=kind or ('miniboss' if i % 2 == 0 else 'boss'),
                    watch_flag=f'PhysicalDeath{i}', watch_type='bool' if i % 2 == 0 else 's32', watch_threshold=1)
               for i in range(count)]
    ids = [e['id'] for e in entries]
    plan = dict(seed='test', player=1, locations=entries,
                slot_data=dict(seed_fingerprint=seed_fingerprint('test', 1, ids)))
    vm = PPC(ids, build_seed_hook(plan).decode())
    vm.globals[0x1046D5B0] = 0x60000
    struct.pack_into('>I', vm.memory, 0x60700, 0x61000)
    struct.pack_into('>I', vm.memory, 0x61000, 0x62000)
    vm.values = {}; vm.calls = []
    def native(address):
        vm.calls.append(address); r = vm.registers
        if address == 0x0320F45C:
            assert r[3] in (0x62004, 0x62010, 0x64004, 0x64010)
            ptr, vtable = struct.unpack_from('>II', vm.memory, r[4])
            assert vtable == 0x10263910 and r[5] == 1
            end = vm.memory.index(0, ptr)
            name = vm.memory[ptr:end].decode()
            result = int(name.removeprefix('PhysicalDeath'))
        else:
            assert address in (0x03234A64, 0x03234B08)
            index = r[5]; value = vm.values.get(index, 0)
            if address == 0x03234A64:
                assert r[4] in (0x62004, 0x64004)
                vm.memory[r[3]] = int(bool(value))
            else:
                assert r[4] in (0x62010, 0x64010)
                struct.pack_into('>I', vm.memory, r[3], value)
            result = 1
        for i in range(3, 13): r[i] = 0xDEADBEEF
        r[3] = result
    vm.native_call = native
    return vm


def test_native_goal_objective_waits_for_its_completion_flag():
    vm = watch_vm(count=1, kind='objective')
    vm.run('_AP_PollKillChecks'); vm.run('_AP_FlushPendingChecks')
    assert vm.word(20) == 0
    vm.values[0] = 1
    vm.run('_AP_PollKillChecks'); vm.run('_AP_FlushPendingChecks')
    assert vm.word(20) == 1
    assert vm.word(P['outgoing_offset'] + 8) == 0xC1000000


def test_native_death_watches_cache_indices_and_ignore_unrelated_progression():
    vm = watch_vm()
    vm.run('_AP_PollKillChecks')
    assert vm.calls.count(0x0320F45C) == 2
    vm.run('_AP_PollKillChecks')
    assert vm.calls.count(0x0320F45C) == 2
    assert vm.word(P['location_table_offset'] + 4) == 0
    assert vm.word(P['location_table_offset'] + 12) == 0
    # Only the death counter changes; no map-clear/ability grant is watched.
    vm.values[1] = 1
    vm.run('_AP_PollKillChecks'); vm.run('_AP_FlushPendingChecks')
    assert vm.word(P['outgoing_offset'] + 8) == 0xC1000001
    assert vm.word(P['location_table_offset'] + 4) == 0
    calls = len(vm.calls)
    vm.run('_AP_PollKillChecks'); vm.run('_AP_FlushPendingChecks')
    assert vm.word(20) == 1
    assert len(vm.calls) == calls + 1  # only the unfinished bool check is polled


def test_watches_resolve_again_after_core_change_and_preserve_stack():
    vm = watch_vm(); stack = vm.registers[1]
    vm.run('_AP_PollKillChecks')
    struct.pack_into('>I', vm.memory, 0x61000, 0x64000)
    vm.run('_AP_PollKillChecks')
    assert vm.calls.count(0x0320F45C) == 4
    assert vm.registers[1] == stack


def test_poll_budget_wrap_and_exactly_once_pending_checks():
    vm = watch_vm(65); vm.values = {i: 1 for i in range(65)}
    vm.run('_AP_PollKillChecks')
    assert sum(vm.word(P['location_table_offset']+i*8+4) == 1 for i in range(65)) == 64
    vm.run('_AP_PollKillChecks'); vm.run('_AP_FlushPendingChecks')
    assert vm.word(20) == 65
    calls = len(vm.calls)
    vm.run('_AP_PollKillChecks'); vm.run('_AP_FlushPendingChecks')
    assert len(vm.calls) == calls and vm.word(20) == 65


def test_combat_catalog_uses_death_signals_and_unique_physical_identities():
    entries = catalog()['locations']
    assert len({e['id'] for e in entries}) == len(entries)
    assert len({e['watch_flag'] for e in entries}) == len(entries)
    assert sum(e['kind'] == 'miniboss' and "The Champions' Ballad DLC" not in e['category'] for e in entries) == 84
    assert sum(e['kind'] == 'boss' for e in entries) == 7
    assert not any(e['watch_flag'].startswith(('Clear_Remains', 'IsGet_Obj_HeroSoul', 'MapTower_')) for e in entries)
    assert all(e['watch_type'] in {'bool', 's32'} and e['watch_threshold'] == 1 for e in entries)


def test_base_encounters_do_not_require_dlc_resources():
    for entry in catalog()['locations']:
        if "The Champions' Ballad DLC" not in entry['category']:
            assert entry['resource'].startswith('content/')
        assert len(entry['map_sha256']) == 64
        assert len(entry['position']) == 3


def test_pack_rejects_missing_wrongly_typed_or_unsaved_native_flags():
    import oead
    import pytest
    from botw_static.combat import validate_watches
    def dump(kind='bool_data', saved=True, name='RealDefeat'):
        writer = oead.SarcWriter(endian=oead.Endianness.Big)
        writer.files['flags.bgdata'] = oead.byml.to_binary(oead.byml.Hash({kind: oead.byml.Array([oead.byml.Hash(dict(DataName=name, IsSave=saved))])}), big_endian=True)
        class Dump:
            def read(self, path):
                assert path == 'content/Pack/Bootup.pack!GameData/gamedata.ssarc'
                return bytes(writer.write()[1])
        return Dump()
    location = dict(watch_flag='RealDefeat', watch_type='bool')
    validate_watches(dump(), [location])
    for invalid in [dump('s32_data'), dump(saved=False), dump(name='OtherFlag')]:
        with pytest.raises(ValueError): validate_watches(invalid, [location])
