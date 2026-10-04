import os

asm = """[BotW_Archipelago_Multiworld_V208]
moduleMatches = 0x6267BFD0

.origin = codecave

# =============================================================================
# 1. MAILBOX ALLOCATION
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

for _ in range(161):
    asm += ".int " + ", ".join(["0"] * 32) + "\n"

asm += """
_AP_Is_Injecting:
.int 0x00000000

# =============================================================================
# 2. MAIN LOOP HOOK (Application::calc - Prologue)
# =============================================================================
_AP_MainTick_Hook:
    # Hooked via 'bla', so LR = 0x0303E4C4.
    # Because we are at the very beginning of the function, Volatile FPRs/VRs 
    # are safely dead and won't be corrupted by acquireItem!

    # 1. Standard Stack Frame (0x80 bytes is perfectly EABI compliant)
    stwu r1, -0x80(r1)
    
    # 2. Backup r0 
    stw r0, 0x30(r1)

    # 3. Backup LR inside OUR frame (0x7C)
    mflr r0
    stw r0, 0x7C(r1)

    # 4. Backup all volatile GPRs (Application::calc arguments + scratch)
    stw r3, 0x08(r1)
    stw r4, 0x0C(r1)
    stw r5, 0x10(r1)
    stw r6, 0x14(r1)
    stw r7, 0x18(r1)
    stw r8, 0x1C(r1)
    stw r9, 0x20(r1)
    stw r10, 0x24(r1)
    stw r11, 0x28(r1)
    stw r12, 0x2C(r1)

    # 5. Mailbox Logic
    lis r11, _AP_Mailbox_Base@ha
    addi r11, r11, _AP_Mailbox_Base@l
    
    # Status = 2, Tick++
    li r12, 2
    stw r12, 0x08(r11)
    lwz r12, 0x1C(r11)
    addi r12, r12, 1
    stw r12, 0x1C(r11)

    # Check incoming queue
    lwz r12, 0x10(r11)  # tail
    lwz r10, 0x0C(r11)  # head
    cmpw r12, r10
    bge tick_done

    # We have an item! Setup actSysPtr (r3)
    lis r9, 0x105B
    ori r9, r9, 0x8C00
    lwz r3, 0(r9)
    cmpwi r3, 0
    beq tick_done

    # Set is_injecting flag
    lis r9, _AP_Is_Injecting@ha
    addi r9, r9, _AP_Is_Injecting@l
    li r10, 1
    stw r10, 0(r9)

    # Setup string pointer (r4) and quantity (r5)
    clrlwi r9, r12, 24
    slwi r9, r9, 6
    addi r9, r9, 0x20
    add r9, r11, r9
    addi r4, r9, 8
    lwz r5, 0x38(r9)

    # Zero optional params
    li r6, 0
    li r7, 0
    li r8, 0
    li r9, 0
    li r10, 0

    # Call acquireItem directly!
    lis r12, 0x0374
    ori r12, r12, 0x1B20
    mtctr r12
    bctrl

    # Clear is_injecting flag
    lis r9, _AP_Is_Injecting@ha
    addi r9, r9, _AP_Is_Injecting@l
    li r10, 0
    stw r10, 0(r9)

    # Increment tail
    lis r11, _AP_Mailbox_Base@ha
    addi r11, r11, _AP_Mailbox_Base@l
    lwz r12, 0x10(r11)
    addi r12, r12, 1
    stw r12, 0x10(r11)

tick_done:
    # Restore all GPRs (This perfectly restores the original arguments to Application::calc)
    lwz r3, 0x08(r1)
    lwz r4, 0x0C(r1)
    lwz r5, 0x10(r1)
    lwz r6, 0x14(r1)
    lwz r7, 0x18(r1)
    lwz r8, 0x1C(r1)
    lwz r9, 0x20(r1)
    lwz r10, 0x24(r1)
    lwz r11, 0x28(r1)
    lwz r12, 0x2C(r1)
    
    # Restore LR (0x0303E4C4)
    lwz r0, 0x7C(r1)
    mtlr r0
    
    # Restore r0
    lwz r0, 0x30(r1)

    # Pop stack frame
    addi r1, r1, 0x80

    # Execute original instruction we replaced!
    lis r9, 0x1048

    # Branch using the Link Register seamlessly back to the engine (0x0303E4C4)
    blr

# =============================================================================
# 3. ACQUIRE ITEM HOOK (Outgoing Intercept)
# =============================================================================
_AP_AcquireItem_Hook:
    # Backup registers
    addi r1, r1, -0x30
    stw r9, 0x08(r1)
    stw r10, 0x0C(r1)
    stw r11, 0x10(r1)
    stw r12, 0x14(r1)

    # Prevent loop if we are the ones injecting
    lis r11, _AP_Is_Injecting@ha
    addi r11, r11, _AP_Is_Injecting@l
    lwz r12, 0(r11)
    cmpwi r12, 1
    beq skip_intercept

    lis r11, _AP_Mailbox_Base@ha
    addi r11, r11, _AP_Mailbox_Base@l

    # Write to Outgoing Queue
    lwz r12, 0x14(r11)  # out_head
    clrlwi r10, r12, 24
    slwi r10, r10, 4
    lis r9, 0
    ori r9, r9, 0x4020
    add r10, r10, r9
    add r10, r10, r11
    
    stw r12, 0(r10)
    li r9, 0
    stw r9, 4(r10)
    
    # Send dummy location 5000 + out_head
    lis r9, 0
    ori r9, r9, 5000
    add r9, r9, r12
    stw r9, 8(r10)
    
    li r9, 0
    stw r9, 12(r10)

    addi r12, r12, 1
    stw r12, 0x14(r11)

skip_intercept:
    # Setup long-distance branch target into CTR to be safe
    lis r12, 0x0374
    ori r12, r12, 0x1B24
    mtctr r12

    # Restore registers
    lwz r9, 0x08(r1)
    lwz r10, 0x0C(r1)
    lwz r11, 0x10(r1)
    lwz r12, 0x14(r1)
    addi r1, r1, 0x30

    stwu r1, -0x30(r1)
    
    # Long-distance branch back
    bctr

# --- Hooks ---

# 1. Main Tick Hook (Application::calc - Prologue)
0x0303E4C0 = bla _AP_MainTick_Hook

# 2. AcquireItem Hook
0x03741B20 = b _AP_AcquireItem_Hook
"""

path = os.path.expanduser('~/.local/share/Cemu/graphicPacks/BotW_Archipelago_Multiworld/patch_Archipelago.asm')
with open(path, 'w') as f:
    f.write(asm)
