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

## Hook / Mailbox Addresses

### Mailbox Base Address
* **Guest (PPC) Address**: `0x11000000`
* **Host Address Calculation**: `memory_base + 0x11000000`

Cemu reserves a contiguous 4GB (`0x100000000`) virtual address block as `memory_base` for the entire PPC address space. Guest address `X` maps to host address `memory_base + X`. The C# client finds `memory_base` by parsing `/proc/PID/maps` for large (≥512MB) anonymous `rw-p` mappings, then validates the mailbox magic at the computed offset.

### Mailbox Layout (Total: 12,384 bytes / 0x3260)
| Offset from Base | Size | Description |
| :--- | :--- | :--- |
| `0x0000` | 32 B | Header (magic, version, status, heads/tails, tick_count) |
| `0x0020` | 8192 B | Incoming Queue (256 × 32-byte items) |
| `0x2020` | 4096 B | Outgoing Queue (256 × 16-byte checks) |
| `0x3020` | 64 B | Debug message buffer (hook → client) |

### Debug Fields
* **`status`** (offset `0x08`): Set to `2` ("In Game") by the hook on its first tick. If `0`, the hook hasn't executed yet.
* **`tick_count`** (offset `0x1C`): Incremented each game tick. Use for liveness monitoring.
* **`debug_msg`** (offset `0x3020`): 64-byte ASCII string written by the hook with diagnostic messages.
