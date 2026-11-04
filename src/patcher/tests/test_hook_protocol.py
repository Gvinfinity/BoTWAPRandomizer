import re
import struct

import pytest
from src.patcher.core import ROOT
from src.patcher.update_hook import upgrade_hook
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

    def float_word(self, offset, value=None):
        address = self.symbols['_AP_Mailbox_Base'] + offset
        if value is not None:
            struct.pack_into('>f', self.memory, address, value)
        return struct.unpack_from('>f', self.memory, address)[0]

    def enqueue_rpc(self, slot, seq_id, target, gprs=(), fprs=()):
        base = P['incoming_offset'] + (slot % P['ring_capacity']) * P['incoming_size']
        for i in range(0, P['incoming_size'], 4):
            self.word(base + i, 0)
        self.word(base, seq_id)
        self.word(base + 4, target)
        for index, val in enumerate(gprs):
            self.word(base + 8 + index * 4, val)
        for index, val in enumerate(fprs):
            self.float_word(base + 40 + index * 4, val)

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
    assert struct.unpack_from('>I', data, P['capabilities_offset'])[0] & P['capabilities']['rpc']
    assert struct.unpack_from('>I', data, P['configured_offset'])[0] == 1
    assert [struct.unpack_from('>I', data, P['location_table_offset'] + i*8)[0] for i in range(2)] == sorted(ids)
    plan['slot_data']['seed_fingerprint'] = '0'*32
    with pytest.raises(ValueError, match='fingerprint'): build_seed_hook(plan)


def test_actual_rpc_hook_dispatches_batch_calls_and_writes_return_values():
    vm = PPC([0xB1234567])
    stack = vm.registers[1]
    vm.registers[3:11] = [0x11111111 + i for i in range(8)]
    saved_caller = list(vm.registers[3:11])
    calls = []

    def native(address):
        injecting = struct.unpack_from('>I', vm.memory, vm.symbols['_AP_Is_Injecting'])[0]
        assert injecting == 1
        calls.append((address, list(vm.registers[3:11]), list(vm.floats[1:5])))
        if address == 0x02EAE914:
            vm.registers[3] = 2
        elif address == 0x02E1AC6C:
            vm.floats[1] = 1400.0
        elif address == 0x02EB3DF0:
            vm.registers[3] = 0xCAFEBABE

    vm.native_call = native
    vm.enqueue_rpc(0, 10, 0x02EAE914, gprs=[0x23450, 0])
    vm.enqueue_rpc(1, 11, 0x02E1AC6C, gprs=[0], fprs=[1200.0, 200.0, 3.0, 4.0])
    vm.enqueue_rpc(2, 12, 0x02EB3DF0, gprs=[1, 2, 3, 4, 5, 6, 7, 8])
    vm.word(12, 3)

    assert vm.run('_AP_MainTick_Hook') == 'native'
    assert vm.registers[1] == stack
    assert vm.registers[3:11] == saved_caller
    assert struct.unpack_from('>I', vm.memory, vm.symbols['_AP_Is_Injecting'])[0] == 0
    assert vm.word(8) == 2
    assert vm.word(P['mailbox_address_offset']) == vm.symbols['_AP_Mailbox_Base']
    assert vm.word(16) == 3
    assert vm.word(P['ack_sequence_offset']) == 12

    assert len(calls) == 3
    assert calls[0][0] == 0x02EAE914 and calls[0][1][:2] == [0x23450, 0]
    assert calls[1][0] == 0x02E1AC6C and calls[1][2] == [1200.0, 200.0, 3.0, 4.0]
    assert calls[2][0] == 0x02EB3DF0 and calls[2][1] == [1, 2, 3, 4, 5, 6, 7, 8]

    assert vm.word(P['incoming_offset'] + 56) == 2
    assert vm.float_word(P['incoming_offset'] + 64 + 60) == 1400.0
    assert vm.word(P['incoming_offset'] + 128 + 56) == 0xCAFEBABE


def test_actual_rpc_hook_counter_wrap_and_corrupt_ring_guard():
    vm = PPC([0xB1234567])
    called = []
    vm.native_call = lambda address: called.append(address)

    vm.word(12, 0x00000001)
    vm.word(16, 0xFFFFFFFF)
    vm.enqueue_rpc(0xFFFFFFFF, 41, 0x030BB668, gprs=[0x40010])
    vm.enqueue_rpc(0, 42, 0x030BB69C, gprs=[0x40010])
    vm.run('_AP_MainTick_Hook')
    assert called == [0x030BB668, 0x030BB69C]
    assert vm.word(16) == 1
    assert vm.word(P['ack_sequence_offset']) == 42

    called.clear()
    vm.word(12, 300)
    vm.word(16, 1)
    vm.run('_AP_MainTick_Hook')
    assert called == []
    assert vm.word(16) == 1


def test_update_hook_upgrades_legacy_seed_hook_to_rpc_layout():
    ids = [0xB1234567]
    fingerprint = seed_fingerprint('legacy', 1, ids)
    legacy_words = [0x41504D42, 0x424F5457] + [0] * 6
    legacy_words += [0] * ((P['extension_offset'] - 32) // 4)
    legacy_words += [0x41505632, P['version'], 1, 1, 1, 0, 0, 0]
    legacy_words += [int(fingerprint[i:i + 8], 16) for i in range(0, 32, 8)]
    for index in range(P['max_locations']):
        legacy_words += [ids[index] if index < len(ids) else 0, 0]
    assert len(legacy_words) * 4 == P['scratch_offset']
    legacy_block = '_AP_Mailbox_Base:\n' + '\n'.join(
        '.int ' + ', '.join(f'0x{w:08X}' for w in legacy_words[i:i + 16])
        for i in range(0, len(legacy_words), 16)) + '\n'
    legacy_source = legacy_block + '_AP_Is_Injecting:\n.int 0\n'
    upgraded = upgrade_hook(legacy_source)
    block = upgraded.split('_AP_Mailbox_Base:\n')[1].split('_AP_Is_Injecting:')[0]
    words = [int(w, 16) for w in re.findall(r'0x[0-9A-F]{8}', block)]
    data = struct.pack(f'>{len(words)}I', *words)
    assert len(data) == P['mailbox_size']
    assert data[P['seed_fingerprint_offset']:P['location_table_offset']].hex() == fingerprint
    assert struct.unpack_from('>I', data, P['capabilities_offset'])[0] & P['capabilities']['rpc']
    assert struct.unpack_from('>I', data, P['location_table_offset'])[0] == 0xB1234567


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
