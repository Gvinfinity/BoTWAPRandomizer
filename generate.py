import os

asm = """[BotW_Archipelago_Multiworld_V208]
moduleMatches = 0x6267BFD0

.origin = codecave

# =============================================================================
# 1. MAILBOX ALLOCATION (PURE ASM - NO DLL REQUIRED)
# =============================================================================
_AP_Mailbox_Base:
.int 0x41504D42          # [0x00] Magic Header Part 1: APMB
.int 0x424F5457          # [0x04] Magic Header Part 2: BOTW
.int 0x00000000          # [0x08] Status
.int 0x00000000          # [0x0C] In Head
.int 0x00000000          # [0x10] In Tail
.int 0x00000000          # [0x14] Out Head
.int 0x00000000          # [0x18] Out Tail
.int 0x00000000          # [0x1C] Tick Count
"""

# Allocate Mailbox Queues (12KB)
for _ in range(96):
    asm += ".int " + ", ".join(["0"] * 32) + "\n"

asm += """
_AP_Is_Injecting:
.int 0x00000000

# =============================================================================
# 2. MAIN LOOP HOOK (TICKS & RECEIVES ITEMS)
# =============================================================================
_AP_MainTick_Hook:
    # 1. Back up volatile registers safely
    addi r1, r1, -0x40
    stw r3, 0x08(r1)
    stw r4, 0x0C(r1)
    stw r5, 0x10(r1)
    stw r9, 0x14(r1)
    stw r10, 0x18(r1)
    stw r11, 0x1C(r1)
    stw r12, 0x20(r1)

    lis r11, _AP_Mailbox_Base@ha
    addi r11, r11, _AP_Mailbox_Base@l
    
    # Status = 2, Tick++
    li r12, 2
    stw r12, 0x08(r11)
    lwz r12, 0x1C(r11)
    addi r12, r12, 1
    stw r12, 0x1C(r11)

    # Check for incoming items (in_tail < in_head)
    lwz r12, 0x10(r11)  # r12 = in_tail
    lwz r10, 0x0C(r11)  # r10 = in_head
    cmpw r12, r10
    bge tick_done       # No items waiting

    # Check if actSysPtr is ready
    lis r9, 0x105B
    ori r9, r9, 0x8C00
    lwz r3, 0(r9)
    cmpwi r3, 0
    beq tick_done       # Engine not fully booted yet

    # We have an item! We must create a secure stack frame for the bctrl call
    stwu r1, -0x80(r1)
    mflr r0
    stw r0, 0x84(r1)

    # Set is_injecting = 1 (so our outgoing hook ignores this grant)
    lis r9, _AP_Is_Injecting@ha
    addi r9, r9, _AP_Is_Injecting@l
    li r10, 1
    stw r10, 0(r9)

    # Calculate item pointer: base + 0x20 + ( (in_tail % 256) * 32 )
    clrlwi r9, r12, 24
    slwi r9, r9, 5
    addi r9, r9, 0x20
    add r9, r11, r9

    # Set args for ksys::act::acquireItem
    # r3 = actSysPtr (already set above)
    addi r4, r9, 8      # r4 = ActorName string pointer
    lwz r5, 24(r9)      # r5 = Quantity

    # Execute function
    lis r12, 0x0374
    ori r12, r12, 0x1B20
    mtctr r12
    bctrl

    # Restore LR and tear down inner stack frame
    lwz r0, 0x84(r1)
    mtlr r0
    addi r1, r1, 0x80

    # Clear is_injecting flag
    lis r9, _AP_Is_Injecting@ha
    addi r9, r9, _AP_Is_Injecting@l
    li r10, 0
    stw r10, 0(r9)

    # Increment in_tail to acknowledge receipt
    lis r11, _AP_Mailbox_Base@ha
    addi r11, r11, _AP_Mailbox_Base@l
    lwz r12, 0x10(r11)
    addi r12, r12, 1
    stw r12, 0x10(r11)

tick_done:
    lwz r3, 0x08(r1)
    lwz r4, 0x0C(r1)
    lwz r5, 0x10(r1)
    lwz r9, 0x14(r1)
    lwz r10, 0x18(r1)
    lwz r11, 0x1C(r1)
    lwz r12, 0x20(r1)
    addi r1, r1, 0x40

    cmpwi r3, 0x0
    b 0x0313B844

# =============================================================================
# 3. ACQUIRE ITEM HOOK (INTERCEPTS VANILLA CHESTS TO SEND TO AP)
# =============================================================================
_AP_AcquireItem_Hook:
    addi r1, r1, -0x40
    stw r3, 0x08(r1)
    stw r4, 0x0C(r1)
    stw r9, 0x10(r1)
    stw r10, 0x14(r1)
    stw r11, 0x18(r1)
    stw r12, 0x1C(r1)

    # Check is_injecting. If 1, this item came from AP, don't echo it back!
    lis r11, _AP_Is_Injecting@ha
    addi r11, r11, _AP_Is_Injecting@l
    lwz r12, 0(r11)
    cmpwi r12, 1
    beq skip_intercept

    # Write to Outgoing Queue
    lis r11, _AP_Mailbox_Base@ha
    addi r11, r11, _AP_Mailbox_Base@l
    
    lwz r12, 0x14(r11)  # r12 = out_head
    clrlwi r10, r12, 24
    
    # offset = base + 0x2020 + (r10 * 16)
    slwi r10, r10, 4
    lis r9, 0
    ori r9, r9, 0x2020
    add r10, r10, r9
    add r10, r10, r11
    
    # Write SeqID = out_head
    stw r12, 0(r10)
    
    # Write AP_LocationID = 5000 + out_head (High bits 0)
    li r9, 0
    stw r9, 4(r10)
    lis r9, 0
    ori r9, r9, 5000
    add r9, r9, r12
    stw r9, 8(r10)
    
    # Write isShop = 0
    li r9, 0
    stw r9, 12(r10)

    # out_head++
    addi r12, r12, 1
    stw r12, 0x14(r11)

skip_intercept:
    lwz r3, 0x08(r1)
    lwz r4, 0x0C(r1)
    lwz r9, 0x10(r1)
    lwz r10, 0x14(r1)
    lwz r11, 0x18(r1)
    lwz r12, 0x1C(r1)
    addi r1, r1, 0x40

    stwu r1, -0x30(r1)
    b 0x03741B24

0x0313B840 = b _AP_MainTick_Hook
0x03741B20 = b _AP_AcquireItem_Hook
"""

path = os.path.expanduser('~/.local/share/Cemu/graphicPacks/BotW_Archipelago_Multiworld/patch_Archipelago.asm')
with open(path, 'w') as f:
    f.write(asm)
