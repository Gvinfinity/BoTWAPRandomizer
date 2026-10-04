# Memory Offsets & Function Pointers (U-King.rpx v208 / Wii U v1.5.0)

This document contains verified function addresses and structure offsets for *The Legend of Zelda: Breath of the Wild* v1.5.0.

## Function Entrypoints

These addresses can be used as code cave jump targets or native C++ DLL calls.
*Note: All addresses are for Cemu V3 Graphics Pack patches targeting the Wii U memory space (0x02000000 - 0x10000000).*

### Core System & Game Tick
* **`ksys::act::ActorSystem::calc`**: Core actor processing loop. Suitable for safe game tick injection.
  * Offset: `0x03780D7C` (Example offset, verify via LibreVR/uking)
* **Main Gameplay Loop** (`Application::calc`):
  * Offset: `0x0303E4C0`

### GameData & Flags (`ksys::gdt::Manager`)
* **`ksys::gdt::Manager::setBoolByName`**
  * Offset: `0x0321F534`
  * Signature: `void setBoolByName(const char* flagName, bool value)`
* **`ksys::gdt::Manager::getBoolByName`**
  * Offset: `0x0321F5A0`
  * Signature: `bool getBoolByName(const char* flagName)`

### Inventory & UI
* **`ksys::act::ActorSystem`** Item Pickup / Granting
  * Offset: `0x03741B20` (Internal item grant routine)
* **`ItemNotification`** (Banner Display)
  * Offset: `0x03A00000` (Sub-routine for standard Get item UI popup)
* **Inventory Array / Pouch Content Pointers**
  * Base Pointer: `0x105B8B1C` (LibreVR verified static pointer to Pouch Content)
  * Note: We avoid direct RAM modification and instead use native API calls.

## Hook / Mailbox Target Addresses
* The Cemu Graphic Pack will allocate an unused block of memory (e.g., in `BSS` or explicitly requested heap block) for the Shared Memory Mailbox.
* **Mailbox Base Address**: `0x11000000` (Example standard extended heap address, to be formalized in patches.txt)
