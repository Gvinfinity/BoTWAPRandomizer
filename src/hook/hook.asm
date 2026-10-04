[BotW_Archipelago_Multiworld_V208]
moduleMatches = 0x6267bfd0

.origin = codecave

codeCave_AP_Hook:
stwu r1, -0x100(r1)  
mflr r0              
stw r0, 0x104(r1)    
stmw r3, 0x8(r1)     

lis r31, 0x1100

; Update status to 2 and tick_count
li r3, 2
stw r3, 0x08(r31)
lwz r3, 0x1C(r31)
addi r3, r3, 1
stw r3, 0x1C(r31)

; Process incoming items
lwz r4, 0x0C(r31)
lwz r5, 0x10(r31)
cmpw r5, r4
bge endLoop

; Get index: r6 = in_tail % 256
rlwinm r6, r5, 0, 24, 31
slwi r6, r6, 5
addi r6, r6, 0x20
add r6, r31, r6

; Load actSys = *0x105B8C00
lis r3, 0x105B
ori r3, r3, 0x8C00
lwz r3, 0(r3)
cmpwi r3, 0
beq incTail

; Set is_injecting flag (0x0A)
li r7, 1
stb r7, 0x0A(r31)

; r4 = actorName, r5 = quantity
addi r4, r6, 8
lwz r5, 24(r6)

; Call ksys::act::acquireItem (0x03741B20)
lis r12, 0x0374
ori r12, r12, 0x1B20
mtctr r12
bctrl

; Clear is_injecting flag
li r7, 0
stb r7, 0x0A(r31)

incTail:
lwz r5, 0x10(r31)
addi r5, r5, 1
stw r5, 0x10(r31)

endLoop:
lmw r3, 0x8(r1)      
lwz r0, 0x104(r1)    
mtlr r0              
addi r1, r1, 0x100   
stwu r1, -0x20(r1)   
blr                  


codeCave_AcquireItem:
stwu r1, -0x100(r1)
mflr r0
stw r0, 0x104(r1)
stmw r3, 0x8(r1)     

lis r31, 0x1100

; Check status == 2
lwz r7, 0x08(r31)
cmpwi r7, 2
bne acqEnd

; Check is_injecting == 0
lbz r7, 0x0A(r31)
cmpwi r7, 0
bne acqEnd

; Check "Weap" (0x57656170) or "Item" (0x4974656D)
lwz r7, 0(r4)

lis r8, 0x5765
ori r8, r8, 0x6170
cmpw r7, r8
beq doCheck

lis r8, 0x4974
ori r8, r8, 0x656D
cmpw r7, r8
bne acqEnd

doCheck:
lwz r9, 0x14(r31)
rlwinm r10, r9, 0, 24, 31
slwi r10, r10, 4
lis r11, 0
ori r11, r11, 0x2020
add r10, r10, r11
add r10, r10, r31

stw r9, 0(r10)
li r12, 0
stw r12, 4(r10)
lis r12, 0x5000
add r12, r12, r9
stw r12, 8(r10)
li r12, 0
stw r12, 12(r10)

addi r9, r9, 1
stw r9, 0x14(r31)

acqEnd:
lmw r3, 0x8(r1)
lwz r0, 0x104(r1)
mtlr r0
addi r1, r1, 0x100
stwu r1, -0x30(r1)
blr

; --- HOOKS ---
0x03780D7C = bla codeCave_AP_Hook
0x03741B20 = bla codeCave_AcquireItem
