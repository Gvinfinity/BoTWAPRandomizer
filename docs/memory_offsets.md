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
  * This is a less established candidate and is not used by the current patch. The current patch keeps the `0x0313B840` game-thread hook used by the SpawnActors reference, which executes on the regular unpaused gameplay tick.

### GameData & Flags (`ksys::gdt::Manager`)
* **`ksys::gdt::Manager::setBoolByName`**
  * Offset: `0x0321F534`
  * Signature: `void setBoolByName(const char* flagName, bool value)`
* **`ksys::gdt::Manager::getBoolByName`**
  * Offset: `0x0321F5A0`
  * Signature: `bool getBoolByName(const char* flagName)`

### Inventory & UI
* **`ksys::ui::PauseMenuDataMgr::addItem`**: `0x02EB3DF0`
  * Restored full-durability direct-inventory path from before actor spawning. The hook builds a `sead::SafeString`, classifies it with `0x02EAE914`, resolves maximum durability with `0x0308812C` for swords, bows, and shields, calls `addItem` under the manager lock, saves the pouch to GameData, and unlocks. Other types retain their mailbox quantity. The `0x02EB58A8` follow-up is called only for food (type 8); calling it for weapons caused the earlier crash at `0x02EC216C`. This version bypasses the pickup animation.
* **Actor creation entry used by SpawnActors**: `0x037B6040`
  * The restored historical hook only preserves its scratch register and replays the original prologue before returning to `0x037B6044`. It captures no creator context and requests no actor creation. The actor-spawn ring is removed.
* **Unresolved telemetry hook**: `0x03741B20` is restored exactly as in the confirmed-working version. Its wrapper preserves scratch registers and resumes the original function at `0x03741B24`; it does not emit location checks. Incoming delivery uses `PauseMenuDataMgr::addItem` above.
* **Pickup notification / item-get UI**: No verified Wii U v208 function address is recorded in `symbols-wiiu-v208.csv`. The earlier `0x03A00000` placeholder is unverified and must not be called as a function.
* **Chest reward event (reference only)**: The `external/uking/data/uking_functions.csv` Switch symbol map identifies `AI_Action_TreasureBoxBurnedOut::spawnDropActor` (`0x710029B FDC` range; entry `0x710029BFDC`) as the chest action routine that spawns the configured drop actor after the chest opens. `AI_Action_TreasureBoxBurnedOut::enter` is the preceding action entry. This establishes the event chain conceptually, but these are Switch addresses and are **not valid Wii U hook addresses**. The local Wii U v208 symbol sheet does not yet contain a confirmed corresponding entry or calling convention.
* **Outgoing chest-check boundary**: `src/patcher/patch_chests.py` changes a chest's `DropActor` to `AP_Dummy_Check` and writes `AP_LocationID` into the chest actor parameters. The chest reward path therefore reaches the drop-actor spawn, but the current repository has no `AP_Dummy_Check` runtime actor implementation to read that parameter or emit it to the mailbox. Hooking `PauseMenuDataMgr::addItem` alone can observe inventory mutation but cannot reliably determine which chest/location caused it. Resolve the Wii U spawn/action path and parameter propagation before wiring the outgoing queue.
* **Inventory Array / Pouch Content Pointers**
  * Base Pointer: `0x105B8B1C` (LibreVR verified static pointer to Pouch Content)
  * Note: We avoid direct RAM modification and instead use native API calls.

## Hook / Mailbox Addresses

### Mailbox Base Address
The hook allocates the mailbox in the Cemu graphic pack codecave. Its guest address can vary with the loaded patches, so the C# client locates it by scanning writable Cemu memory for the eight-byte signature `APMBBOTW` (`41 50 4D 42 42 4F 54 57`). Hook code accesses it through the `_AP_Mailbox_Base` codecave label.

### Mailbox Layout (Total: 20,512 bytes / 0x5020)
| Offset from Base | Size | Description |
| :--- | :--- | :--- |
| `0x0000` | 32 B | Header (signature, status, queue heads/tails, tick count) |
| `0x0020` | 16,384 B | Incoming Queue (256 × 64-byte items) |
| `0x4020` | 4,096 B | Outgoing Queue (256 × 16-byte checks) |

### Debug Fields
* **`status`** (offset `0x08`): Set to `2` ("In Game") by the hook on its first tick. If `0`, the hook hasn't executed yet.
* **`tick_count`** (offset `0x1C`): Incremented each game tick. Use for liveness monitoring.
