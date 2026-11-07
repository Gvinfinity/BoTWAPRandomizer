"""Encounter bindings and bounded native completion flag observation."""
from importlib.resources import files
import json
import struct

from .check_logic import apply_check_logic


def catalog():
    data = json.loads(files(__package__).joinpath('combat.json').read_text())
    data['locations'] = [apply_check_logic(entry) for entry in data['locations']]
    return data



def validate_watches(dump, locations):
    """Reject incompatible GameData instead of polling missing names forever."""
    required = {entry['watch_flag']: entry.get('watch_type', 'bool')
                for entry in locations if 'watch_flag' in entry}
    if not required:
        return
    from .resources import binary_modules, decompress, decode_byml
    archive = binary_modules()[0].Sarc(decompress(dump.read('content/Pack/Bootup.pack!GameData/gamedata.ssarc')))
    found = set()
    for member in archive.get_files():
        for kind, rows in decode_byml(bytes(member.data)).items():
            for row in rows:
                if not hasattr(row, 'get'):
                    continue
                name = row.get('DataName')
                if name not in required:
                    continue
                if name in found or kind != required[name] + '_data' or not row.get('IsSave'):
                    raise ValueError('Incompatible native completion flag: ' + name)
                found.add(name)
    if required.keys() - found:
        raise ValueError('GameData lacks completion flags: ' + ', '.join(sorted(required.keys() - found)))


def hook_assembly(locations, all_ids):
    encounters = [e for e in locations if e.get('kind') in {'miniboss', 'boss', 'shrine', 'objective'}]
    if not encounters:
        return ''
    offsets = {value: index * 8 + 0x5054 for index, value in enumerate(sorted(all_ids))}
    names = bytearray(); rows = []
    for entry in encounters:
        name_offset = len(names)
        names.extend(entry['watch_flag'].encode('ascii') + b'\0')
        rows.extend([offsets[entry['id']], name_offset, int(entry.get('watch_type', 'bool') == 's32'),
                     entry.get('watch_threshold', 1), 0, 0xFFFFFFFF, 0, 0])
    names.extend(b'\0' * (-len(names) % 4))
    def words(values):
        return '\n'.join('.int ' + ', '.join(f'0x{v:08X}' for v in values[i:i+8]) for i in range(0, len(values), 8))
    return f'''
_AP_KillData_Count:
.int 0x{len(encounters):08X}
_AP_KillData_Cursor:
.int 0x00000000
_AP_KillData_Records:
{words(rows)}
_AP_KillData_Names:
{words(list(struct.unpack('>' + 'I' * (len(names)//4), names)))}

_AP_PollKillChecks:
    stwu r1, -0x80(r1)
    mflr r0
    stw r0, 0x84(r1)
    lis r12, 0x1047
    lwz r12, -0x2A50(r12)
    cmpwi r12, 0
    beq kill_poll_done
    lwz r10, 0x700(r12)
    cmpwi r10, 0
    beq kill_poll_done
    lwz r10, 0(r10)
    cmpwi r10, 0
    beq kill_poll_done
    stw r10, 0x38(r1)
    lbz r6, 0x704(r12)
    stw r6, 0x3C(r1)
    lis r12, _AP_KillData_Count@ha
    lwz r12, _AP_KillData_Count@l(r12)
    stw r12, 0x40(r1)
    lis r11, _AP_KillData_Cursor@ha
    lwz r11, _AP_KillData_Cursor@l(r11)
    stw r11, 0x44(r1)
    li r0, 64
    cmpwi r12, 64
    bge kill_poll_budget
    addi r0, r12, 0
kill_poll_budget:
    stw r0, 0x48(r1)
kill_poll_loop:
    lwz r0, 0x48(r1)
    cmpwi r0, 0
    beq kill_poll_save
    lwz r11, 0x44(r1)
    slwi r11, r11, 5
    lis r12, _AP_KillData_Records@ha
    addi r12, r12, _AP_KillData_Records@l
    add r12, r12, r11
    stw r12, 0x4C(r1)
    lis r11, _AP_Mailbox_Base@ha
    addi r11, r11, _AP_Mailbox_Base@l
    lwz r0, 0(r12)
    add r11, r11, r0
    stw r11, 0x50(r1)
    lwz r0, 0(r11)
    cmpwi r0, 0
    bne kill_poll_next
    lwz r10, 0x38(r1)
    lwz r0, 0x10(r12)
    cmpw r0, r10
    bne kill_poll_resolve
    lwz r5, 0x14(r12)
    cmpwi r5, -1
    bne kill_poll_read
kill_poll_resolve:
    stw r10, 0x10(r12)
    lwz r0, 4(r12)
    lis r4, _AP_KillData_Names@ha
    addi r4, r4, _AP_KillData_Names@l
    add r4, r4, r0
    stw r4, 0x58(r1)
    lis r0, 0x1026
    ori r0, r0, 0x3910
    stw r0, 0x5C(r1)
    addi r3, r10, 4
    lwz r0, 8(r12)
    cmpwi r0, 0
    beq kill_poll_index
    addi r3, r10, 0x10
kill_poll_index:
    addi r4, r1, 0x58
    li r5, 1
    lis r12, 0x0320
    ori r12, r12, 0xF45C
    mtctr r12
    bctrl
    lwz r12, 0x4C(r1)
    stw r3, 0x14(r12)
kill_poll_read:
    lwz r12, 0x4C(r1)
    lwz r5, 0x14(r12)
    cmpwi r5, -1
    beq kill_poll_next
    li r0, 0
    stw r0, 0x54(r1)
    addi r3, r1, 0x54
    lwz r4, 0x38(r1)
    lwz r6, 0x3C(r1)
    lwz r0, 8(r12)
    cmpwi r0, 0
    bne kill_poll_s32
    addi r4, r4, 4
    lis r12, 0x0323
    ori r12, r12, 0x4A64
    b kill_poll_call
kill_poll_s32:
    addi r4, r4, 0x10
    lis r12, 0x0323
    ori r12, r12, 0x4B08
kill_poll_call:
    mtctr r12
    bctrl
    cmpwi r3, 0
    beq kill_poll_next
    lwz r12, 0x4C(r1)
    lwz r0, 8(r12)
    cmpwi r0, 0
    bne kill_poll_integer
    lbz r3, 0x54(r1)
    b kill_poll_compare
kill_poll_integer:
    lwz r3, 0x54(r1)
kill_poll_compare:
    lwz r0, 0x0C(r12)
    cmpw r3, r0
    blt kill_poll_next
    lwz r11, 0x50(r1)
    li r0, 1
    stw r0, 0(r11)
    .int 0x7C0004AC
kill_poll_next:
    lwz r11, 0x44(r1)
    addi r11, r11, 1
    lwz r0, 0x40(r1)
    cmpw r11, r0
    blt kill_poll_advance
    li r11, 0
kill_poll_advance:
    stw r11, 0x44(r1)
    lwz r7, 0x48(r1)
    addi r7, r7, -1
    stw r7, 0x48(r1)
    b kill_poll_loop
kill_poll_save:
    lis r12, _AP_KillData_Cursor@ha
    lwz r11, 0x44(r1)
    stw r11, _AP_KillData_Cursor@l(r12)
kill_poll_done:
    lwz r0, 0x84(r1)
    mtlr r0
    addi r1, r1, 0x80
    blr
'''
