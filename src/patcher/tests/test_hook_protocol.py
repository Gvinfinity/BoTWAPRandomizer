"""Execute the check hook's integer instructions against a byte mailbox.

This bounded interpreter checks the actual source's parser and queue operations;
it does not replace Cemu validation of native calls or the hook addresses.
"""
import re
import struct
from pathlib import Path

import pytest
from src.patcher.core import ROOT
from botw_static.hook import mailbox_assembly, build_seed_hook
from botw_static.protocol import PROTOCOL as P, seed_fingerprint


class PPC:
    def __init__(self, ids):
        self.memory = bytearray(0x200000)
        self.registers = [0] * 32
        self.floats = [0.] * 32
        self.registers[1] = 0x1F0000
        self.link, self.ctr = 0, 0
        self.globals = {}
        self.native_call = lambda address: (_ for _ in ()).throw(AssertionError(f'Unexpected native call {address:X}'))
        self.labels, self.code = {}, []
        self.symbols = {'_AP_Mailbox_Base': 0x10000, '_AP_Is_Injecting': 0x10000 + P['mailbox_size']}
        self.symbols['_AP_Progression_State'] = self.symbols['_AP_Is_Injecting'] + 4
        self.symbols['_AP_Stamina_Constants'] = self.symbols['_AP_Is_Injecting'] + 12
        struct.pack_into('>fff', self.memory, self.symbols['_AP_Stamina_Constants'], 1000., 200., 3000.)
        words = [int(word, 16) for word in re.findall(r'0x[0-9A-F]{8}', mailbox_assembly(ids))]
        self.memory[0x10000:0x10000 + len(words)*4] = struct.pack(f'>{len(words)}I', *words)
        for raw in (ROOT / 'src/hook/patch_Archipelago.asm').read_text().splitlines():
            line = raw.split('#')[0].strip()
            if line.endswith(':'):
                self.labels[line[:-1]] = len(self.code)
            elif line and not line.startswith(('.', '[', 'moduleMatches', '0x')):
                op, _, args = line.partition(' ')
                self.code.append((op, [a.strip() for a in args.split(',') if a.strip()]))

    def word(self, offset, value=None):
        address = self.symbols['_AP_Mailbox_Base'] + offset
        if value is not None:
            struct.pack_into('>I', self.memory, address, value & 0xFFFFFFFF)
        return struct.unpack_from('>I', self.memory, address)[0]

    def reg(self, name):
        return int(name[1:])

    def immediate(self, text):
        if '@' in text:
            name, modifier = text.split('@')
            value = self.symbols[name]
            if modifier == 'ha':
                return (value + 0x8000) >> 16
            value &= 0xFFFF
            return value if value < 0x8000 else value - 0x10000
        return int(text, 0)

    def address(self, text):
        offset, register = text.rstrip(')').split('(')
        return (self.immediate(offset) + self.registers[self.reg(register)]) & 0xFFFFFFFF

    def run(self, label):
        pc, compare = self.labels[label], 0
        r = self.registers
        for _ in range(200000):
            op, a = self.code[pc]
            pc += 1
            if op == 'li': r[self.reg(a[0])] = self.immediate(a[1]) & 0xFFFFFFFF
            elif op == 'lis': r[self.reg(a[0])] = self.immediate(a[1]) << 16
            elif op == 'addi':
                # PPC addi treats rA=0 as literal zero, unlike register arithmetic.
                base = r[self.reg(a[1])] if self.reg(a[1]) else 0
                r[self.reg(a[0])] = (base + self.immediate(a[2])) & 0xFFFFFFFF
            elif op in ('or', 'ori', 'add', 'subf'):
                x = r[self.reg(a[1])]
                y = self.immediate(a[2]) if op == 'ori' else r[self.reg(a[2])]
                value = (x | y) if op in ('or', 'ori') else x+y if op == 'add' else y-x
                r[self.reg(a[0])] = value & 0xFFFFFFFF
            elif op == 'slwi': r[self.reg(a[0])] = (r[self.reg(a[1])] << self.immediate(a[2])) & 0xFFFFFFFF
            elif op == 'clrlwi': r[self.reg(a[0])] = r[self.reg(a[1])] & (0xFFFFFFFF >> self.immediate(a[2]))
            elif op in ('lwz', 'lbz'):
                address = self.address(a[1])
                r[self.reg(a[0])] = (self.globals.get(address, 0) if address >= len(self.memory) else
                                    self.memory[address] if op == 'lbz' else struct.unpack_from('>I', self.memory, address)[0])
            elif op in ('stw', 'stwu'):
                address = self.address(a[1])
                struct.pack_into('>I', self.memory, address, r[self.reg(a[0])])
                if op == 'stwu': r[self.reg(a[1].split('(')[1][:-1])] = address
            elif op in ('cmpwi', 'cmpw', 'cmplwi', 'cmplw'):
                x = r[self.reg(a[0])]
                y = self.immediate(a[1]) if op.endswith('wi') else r[self.reg(a[1])]
                if not op.startswith('cmpl'):
                    x = x if x < 0x80000000 else x - 0x100000000
                    y = y if y < 0x80000000 else y - 0x100000000
                compare = (x > y) - (x < y)
            elif op in ('b', 'beq', 'bne', 'blt', 'ble', 'bgt', 'bge'):
                take = {'b': True, 'beq': compare == 0, 'bne': compare != 0, 'blt': compare < 0,
                        'ble': compare <= 0, 'bgt': compare > 0, 'bge': compare >= 0}[op]
                if take:
                    if a[0].startswith('0x'): return 'native'
                    pc = self.labels[a[0]]
            elif op == 'bl': self.link, pc = pc, self.labels[a[0]]
            elif op == 'blr':
                if self.link == 0: return 'suppressed'
                pc = self.link
            elif op == 'bctr': return 'native'
            elif op == 'mtctr': self.ctr = r[self.reg(a[0])]
            elif op == 'bctrl': self.native_call(self.ctr)
            elif op == 'mflr': r[self.reg(a[0])] = self.link
            elif op == 'mtlr': self.link = r[self.reg(a[0])]
            elif op == 'lfs': self.floats[self.reg(a[0])] = struct.unpack_from('>f', self.memory, self.address(a[1]))[0]
            elif op == 'stfs': struct.pack_into('>f', self.memory, self.address(a[1]), self.floats[self.reg(a[0])])
            elif op == 'fadds': self.floats[self.reg(a[0])] = self.floats[self.reg(a[1])] + self.floats[self.reg(a[2])]
            elif op == 'fmr': self.floats[self.reg(a[0])] = self.floats[self.reg(a[1])]
            elif op == 'fcmpu':
                x, y = self.floats[self.reg(a[1])], self.floats[self.reg(a[2])]
                compare = (x > y) - (x < y)
            elif op in ('sync', 'stfd', 'lfd'): pass
            else: raise AssertionError(f'Unsupported test instruction: {op}')
        raise AssertionError('Hook did not terminate')

    def acquire(self, name):
        self.registers[4] = 0x30000
        struct.pack_into('>I', self.memory, 0x30000, 0x30010)
        encoded = name.encode() + b'\0'
        self.memory[0x30010:0x30010 + len(encoded)] = encoded
        return self.run('_AP_AddItem_Hook')


def test_actual_hook_hex_parser_seed_table_and_deduplication():
    vm = PPC([0xB1234567])
    stack = vm.registers[1]
    for name in ['AP_Check_b1234567', 'AP_Check_B1234567_extra', 'AP_Check_00000000',
                 'AP_Check_B123456', 'AP_Check_B1234568', 'AP_Check_G1234567']:
        assert vm.acquire(name) == 'suppressed'
        assert vm.word(P['location_table_offset'] + 4) == 0
        assert vm.registers[1] == stack
    assert vm.acquire('AP_Check_B1234567') == 'suppressed'
    assert vm.word(P['location_table_offset'] + 4) == 1
    vm.run('_AP_FlushPendingChecks')
    assert vm.word(20) == 1
    assert vm.word(P['outgoing_offset'] + 8) == 0xB1234567
    assert vm.word(P['outgoing_offset'] + 4) == 0
    assert vm.word(P['location_table_offset'] + 4) == 2
    vm.acquire('AP_Check_B1234567')
    vm.run('_AP_FlushPendingChecks')
    assert vm.word(20) == 1
    assert PPC([]).acquire('Item_Ore_A') == 'native'


def test_actual_hook_keeps_pending_checks_when_ring_is_full():
    ids = list(range(0xB0000001, 0xB0000001 + 300))
    vm = PPC(ids)
    for index in range(300): vm.word(P['location_table_offset'] + index*8 + 4, 1)
    vm.run('_AP_FlushPendingChecks')
    assert vm.word(20) == 256
    assert vm.word(P['location_table_offset'] + 256*8 + 4) == 1
    vm.word(24, 256)
    vm.run('_AP_FlushPendingChecks')
    assert vm.word(20) == 300
    assert all(vm.word(P['location_table_offset'] + index*8 + 4) == 2 for index in range(300))


def test_actual_hook_outgoing_counter_wrap():
    vm = PPC([0xB1234567])
    vm.word(20, 0xFFFFFFFF); vm.word(24, 0xFFFFFFFF)
    vm.acquire('AP_Check_B1234567'); vm.run('_AP_FlushPendingChecks')
    assert vm.word(20) == 0
    offset = P['outgoing_offset'] + 255*P['outgoing_size']
    assert vm.word(offset) == 0xFFFFFFFF
    assert vm.word(offset + 8) == 0xB1234567


def test_actual_pouch_measurement_uses_offset_list_and_live_values():
    vm = PPC([])
    mgr, name = 0x40000, 0x50000
    vm.registers[3], vm.registers[4] = mgr, name
    vm.memory[name:name+11] = b'Item_Ore_A\0'
    def write(address, value): struct.pack_into('>I', vm.memory, address, value)
    write(mgr+0x50, mgr+0x100+0x30); write(mgr+0x58, 0x30)
    for index, value in enumerate([5, 7, 0]):
        entry = mgr+0x100+index*0x100
        write(entry+0x18, name); write(entry+0x10, value)
        write(entry+0x34, entry+0x100+0x30 if index < 2 else mgr+0x4C)
    stack = vm.registers[1]
    vm.run('_AP_MeasureNamedPouch')
    assert vm.registers[3:5] == [12, 2]
    assert vm.registers[1] == stack


def test_seed_hook_table_and_fingerprint_are_the_apworld_contract():
    ids = [0xB1234567, 0xB7654321]
    fingerprint = seed_fingerprint('test', 2, ids)
    plan = {'seed': 'test', 'player': 2, 'locations': [{'id': value} for value in ids],
            'slot_data': {'seed_fingerprint': fingerprint}}
    hook = build_seed_hook(plan).decode()
    block = hook.split('_AP_Mailbox_Base:\n')[1].split('_AP_Is_Injecting:')[0]
    words = [int(word, 16) for word in re.findall(r'0x[0-9A-F]{8}', block)]
    data = struct.pack(f'>{len(words)}I', *words)
    assert len(data) == P['mailbox_size']
    assert data[P['seed_fingerprint_offset']:P['location_table_offset']].hex() == fingerprint
    assert struct.unpack_from('>I', data, P['version_offset'])[0] == P['version']
    assert struct.unpack_from('>I', data, P['configured_offset'])[0] == 1
    assert [struct.unpack_from('>I', data, P['location_table_offset'] + i*8)[0] for i in range(2)] == sorted(ids)
    plan['slot_data']['seed_fingerprint'] = '0'*32
    with pytest.raises(ValueError, match='fingerprint'): build_seed_hook(plan)


@pytest.mark.parametrize('failure,error', [('manager', 3), ('actor', 1), ('full', 4), ('flags', 2)])
def test_actual_incoming_hook_retains_failed_native_grants(failure, error):
    vm, calls = incoming_vm(failure)
    vm.run('_AP_MainTick_Hook')
    assert vm.word(16) == 0
    assert vm.word(P['ack_sequence_offset']) == 0
    assert vm.word(P['delivery_error_offset']) == error
    if failure in ('actor', 'full'):
        assert calls.count(0x030BB668) == calls.count(0x030BB69C) == 1


def incoming_vm(failure=None, quantity=1, per_call_cap=None):
    vm, calls = PPC([0xB1234567]), []
    mgr, entry = 0x40000, 0x40100
    vm.globals[0x10469978] = 0 if failure == 'manager' else mgr
    def write(address, value): struct.pack_into('>I', vm.memory, address, value)
    write(mgr+0x50, entry+0x30); write(mgr+0x58, 0x30); write(entry+0x34, mgr+0x4C)
    name = vm.symbols['_AP_Mailbox_Base'] + P['incoming_offset'] + 8
    write(entry+0x18, name)
    vm.word(12, 1); vm.word(P['incoming_offset'], 17)
    vm.word(P['incoming_offset'] + 56, quantity)
    vm.word(P['incoming_offset'] + 60, 99 if failure == 'flags' else 0)
    vm.memory[name:name+12] = b'NormalArrow\0'
    def native(address):
        calls.append(address)
        if address == 0x02EAE914: vm.registers[3] = 0xFFFFFFFF if failure == 'actor' else 2
        elif address == 0x02EB3DF0 and failure != 'full':
            value = struct.unpack_from('>I', vm.memory, entry+0x10)[0]
            write(entry+0x10, value + min(vm.registers[7], per_call_cap or vm.registers[7]))
            vm.registers[3] = 0xDEADBEEF  # void return is deliberately unusable as an acknowledgement
        elif address not in (0x030BB668, 0x030BB69C, 0x02EB3764, 0x02EB3DF0):
            raise AssertionError(f'Unexpected native call {address:X}')
    vm.native_call = native
    return vm, calls


def test_actual_incoming_hook_acknowledges_only_a_measured_native_change():
    vm, calls = incoming_vm(quantity=10, per_call_cap=3)
    for outstanding in (7, 4, 1):
        vm.run('_AP_MainTick_Hook')
        assert vm.word(16) == 0
        assert vm.word(P['ack_sequence_offset']) == 0
        assert vm.word(P['incoming_offset']+56) == outstanding
    vm.run('_AP_MainTick_Hook')
    assert vm.word(16) == 1
    assert vm.word(P['ack_sequence_offset']) == 17
    assert vm.word(P['delivery_error_offset']) == 0
    assert calls.count(0x02EB3764) == calls.count(0x030BB69C) == 4


def test_patch_plan_requires_matching_protocol_seed_and_location_data():
    import copy
    from botw_static.plan import validate_plan
    location = {'id': 0xB1234567, 'resource': 'content/Map/MainField/A-1/A-1_Static.smubin',
                'hash_id': 123, 'map_sha256': '0'*64}
    slot = {'protocol_version': P['version'], 'player': 1, 'seed': 'test',
            'check_actor_prefix': 'AP_Check_', 'locations': {str(location['id']): 'AP_Check_B1234567'},
            'seed_fingerprint': seed_fingerprint('test', 1, [location['id']])}
    plan = {'version': 1, 'game': 'Breath of the Wild', 'player': 1, 'seed': 'test',
            'locations': [location], 'slot_data': slot}
    assert validate_plan(plan) is plan
    for field, value in [('protocol_version', 1), ('player', 2), ('seed', 'other'), ('locations', {}),
                         ('seed_fingerprint', '0'*32)]:
        bad = copy.deepcopy(plan); bad['slot_data'][field] = value
        with pytest.raises(ValueError, match='disagree'): validate_plan(bad)


@pytest.mark.parametrize('command,handle,initial,delta,cap', [
    (1, 0x10466AD4, 12, 4, 120), (2, None, 1000., 200., 3000.),
    (3, 0x10467B04, 8, 1, 20), (4, 0x10464480, 5, 1, 14), (5, 0x104678CC, 4, 1, 20),
])
@pytest.mark.parametrize('at_cap', [False, True])
def test_progression_waits_for_saved_value_without_repeating_setter(command, handle, initial, delta, cap, at_cap):
    vm = PPC([0xB1234567])
    vm.globals.update({0x1046D5B0: 0x50000, 0x10463F38: 0x60000})
    struct.pack_into('>I', vm.memory, 0x60030, 0x70000)
    if handle: vm.globals[handle] = 77
    saved = cap if at_cap else initial
    pending, calls = [], []
    def native(address):
        calls.append(address)
        if address == 0x02E146A4:
            assert vm.registers[3:5] == [77, 0]
            vm.registers[3] = saved
        elif address == 0x02E1AC6C: vm.floats[1] = saved
        elif address == 0x02D4992C:
            assert vm.registers[3] == 0x60000
            pending.append(vm.registers[4])
        elif address == 0x02E14848:
            assert vm.registers[4:6] == [77, 0]
            pending.append(vm.registers[3])
        elif address == 0x02D49DFC:
            assert vm.registers[3] == 0x60000
            pending.append(vm.floats[1])
        elif address == 0x02D49E88:
            assert vm.registers[3] == 0x60000 and vm.floats[1] == pending[-1]
        else: raise AssertionError(f'Unexpected progression native call {address:X}')
    vm.native_call = native
    vm.word(12, 1); vm.word(P['incoming_offset'], 22)
    vm.word(P['incoming_offset']+56, 1); vm.word(P['incoming_offset']+60, command)
    vm.run('_AP_MainTick_Hook')
    if at_cap:
        assert not pending and vm.word(16) == 1 and vm.word(P['ack_sequence_offset']) == 22
        return
    assert pending == [initial+delta]
    for _ in range(5):
        vm.run('_AP_MainTick_Hook')
        assert pending == [initial+delta]  # setter is never repeated during async propagation
        assert vm.word(16) == 0 and vm.word(P['ack_sequence_offset']) == 0
        assert vm.word(P['delivery_error_offset']) == 5
    saved = pending[0]
    vm.run('_AP_MainTick_Hook')
    assert vm.word(16) == 1 and vm.word(P['ack_sequence_offset']) == 22
    assert vm.word(P['delivery_error_offset']) == 0
    # Another receipt increments from the new saved value, once.
    vm.word(12, 2); vm.word(P['incoming_offset']+64, 23)
    vm.word(P['incoming_offset']+64+56, 1); vm.word(P['incoming_offset']+64+60, command)
    vm.run('_AP_MainTick_Hook')
    assert pending == [initial+delta, initial+2*delta]
    assert vm.word(16) == 1


@pytest.mark.parametrize('command', [1, 2, 3, 4, 5])
def test_progression_without_game_data_retains_receipt(command):
    vm = PPC([0xB1234567])
    vm.word(12, 1); vm.word(P['incoming_offset'], 22)
    vm.word(P['incoming_offset']+56, 1); vm.word(P['incoming_offset']+60, command)
    vm.run('_AP_MainTick_Hook')
    assert vm.word(16) == 0 and vm.word(P['ack_sequence_offset']) == 0
    assert vm.word(P['delivery_error_offset']) == 3
