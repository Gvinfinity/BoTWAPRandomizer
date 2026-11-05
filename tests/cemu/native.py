"""Test-pack-only RPC helpers. Never included in production graphic packs.

The defeat aid sets life through the game's actor restore API. Normal actor AI
must then finish its death lifecycle and write the flag observed by the AP hook.
No LocationChecks or death flags are manufactured by this fixture.
"""
ASSEMBLY = '''
_AP_Test_Exports:
.int 0x41505445, _AP_Test_FindActor, _AP_Test_ZeroLife
_AP_Test_FindActor:
    stwu r1, -0x80(r1)
    mflr r0
    stw r0, 0x84(r1)
    stmw r19, 0x40(r1)
    mr r19, r4
    lwz r29, 0(r3)
    li r31, 0
    lis r30, 0x1048
    lwz r30, -0x3DBC(r30)
    cmpwi r30, 0
    beq test_find_done
    addi r3, r30, 0x20
    lis r12, 0x030B
    ori r12, r12, 0xB668
    mtctr r12
    bctrl
    mr r3, r29
    lis r12, 0x030C
    ori r12, r12, 0x5D30
    mtctr r12
    bctrl
    mr r20, r3
    lwz r26, 0x6C(r30)
    li r28, 8192
test_find_tree:
    cmpwi r26, 0
    beq test_find_unlock
    addi r28, r28, -1
    cmpwi r28, 0
    beq test_find_unlock
    lwz r0, 0x0C(r26)
    cmplw r20, r0
    blt test_find_left
    bgt test_find_right
    lwz r4, 0x10(r26)
    mr r5, r29
    li r8, 64
test_find_name:
    lbz r6, 0(r4)
    lbz r7, 0(r5)
    cmplw r7, r6
    blt test_find_left
    bgt test_find_right
    cmpwi r6, 0
    beq test_find_candidate
    addi r4, r4, 1
    addi r5, r5, 1
    addi r8, r8, -1
    cmpwi r8, 0
    bne test_find_name
    b test_find_unlock
test_find_left:
    lwz r26, 0(r26)
    b test_find_tree
test_find_right:
    lwz r26, 4(r26)
    b test_find_tree
test_find_candidate:
    cmpwi r26, 0
    beq test_find_unlock
    lwz r25, 0x1C(r26)
    cmpwi r25, 0
    beq test_find_next_node
    lbz r0, 0x54(r25)
    cmpwi r0, 0
    beq test_find_next_node
    cmpwi r0, 3
    beq test_find_next_node
test_find_match:
    cmpwi r19, 0
    beq test_find_accept
    lis r12, _AP_Test_Radius@ha
    lfs f3, _AP_Test_Radius@l(r12)
    li r4, 0
test_find_distance:
    addi r5, r25, 0x2D4
    lfsx f1, r5, r4
    lfsx f2, r19, r4
    fsubs f0, f1, f2
    .int 0xFC000210
    fcmpu cr0, f0, f3
    bgt test_find_next_node
    addi r4, r4, 4
    cmpwi r4, 12
    blt test_find_distance
test_find_accept:
    lwz r12, 0xE8(r25)
    cmpwi r12, 0
    beq test_find_next_node
    lwz r12, 0x2BC(r12)
    cmpwi r12, 0
    beq test_find_next_node
    mtctr r12
    mr r3, r25
    bctrl
    cmpwi r3, 0
    beq test_find_next_node
    lwz r0, 0(r3)
    cmpwi r0, 0
    ble test_find_next_node
    mr r31, r25
    b test_find_unlock
test_find_next_node:
    lwz r26, 0x24(r26)
    b test_find_candidate
test_find_unlock:
    addi r3, r30, 0x20
    lis r12, 0x030B
    ori r12, r12, 0xB69C
    mtctr r12
    bctrl
test_find_done:
    mr r3, r31
    lmw r19, 0x40(r1)
    lwz r0, 0x84(r1)
    mtlr r0
    addi r1, r1, 0x80
    blr
_AP_Test_Radius:
.int 0x42480000
_AP_Test_ZeroLife:
    cmpwi r3, 0
    beq test_life_reject
    lwz r0, 0x50(r3)
    cmpw r0, r4
    bne test_life_reject
    lbz r0, 0x54(r3)
    cmpwi r0, 3
    beq test_life_reject
    stwu r1, -0x40(r1)
    mflr r0
    stw r0, 0x44(r1)
    li r0, 0
    stw r0, 8(r1)
    li r4, 0
    addi r5, r3, 0x1F8
    li r6, 0
    li r7, 0
    li r8, 0
    li r9, 0
    li r10, 0
    lis r12, 0x0379
    ori r12, r12, 0x8C20
    mtctr r12
    bctrl
    lwz r0, 0x44(r1)
    mtlr r0
    addi r1, r1, 0x40
    li r3, 1
    blr
test_life_reject:
    li r3, 0
    blr
'''
