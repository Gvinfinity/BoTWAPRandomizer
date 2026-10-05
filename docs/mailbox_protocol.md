# Shared Memory Mailbox Protocol

This protocol defines the structure of the Shared Memory Mailbox used for IPC (Inter-Process Communication) between the C++ Engine Hook (running inside Cemu) and the C# .NET Network Client.

## 1. Memory Layout (C++ & C# Shared Definition)

The mailbox is designed as a thread-safe, lock-free (using monotonically increasing sequence IDs) memory block.

### 1.1 Header Structure (Size: 32 bytes)

| Offset | Type | Name | Description |
| :--- | :--- | :--- | :--- |
| `0x00` | `char[8]` | `Magic` | Must be `APMBBOTW` (`41 50 4D 42 42 4F 54 57`). Validates mapping. |
| `0x08` | `uint32_t` | `Status` | `0` = Not Ready, `1` = Main Menu, `2` = In Game, `3` = Paused. |
| `0x0C` | `uint32_t` | `In_Head` | Next incoming entry written by the client. |
| `0x10` | `uint32_t` | `In_Tail` | Next incoming entry consumed by the hook. |
| `0x14` | `uint32_t` | `Out_Head` | Sequence ID of the last check *written* by Hook. |
| `0x18` | `uint32_t` | `Out_Tail` | Sequence ID of the last check *processed* by Client. |
| `0x1C` | `uint32_t` | `Tick_Count` | Incremented by the hook each game tick. |

### 1.2 Incoming Queue (Client -> Hook) (Size: 256 * 64 = 16,384 bytes)
Ring buffer of items the player has received from AP.

**Incoming Item Structure (Size: 64 bytes)**:
* `uint32_t SeqID`: Unique monotonically increasing ID.
* `uint32_t AP_ItemID`: Archipelago Item ID.
* `char ActorName[48]`: Native BotW actor name (e.g., `Weapon_Sword_001`), null-terminated.
* `uint32_t Quantity`: Number of items to grant.
* `uint32_t Flags`: Delivery hints (e.g., skip banner, force drop).

The hook is restored to the full-durability direct-inventory version from before actor spawning was introduced. It resolves maximum durability through `0x0308812C` for swords, bows, and shields; other item types use mailbox `Quantity` as the native item value. It does not trigger the pickup animation. `Flags` are ignored. Entries are consumed after processing, including when the pouch manager is unavailable or the name is invalid, matching that historical version.

### 1.3 Outgoing Queue (Hook -> Client) (Size: 256 * 16 = 4096 bytes)
Ring buffer of checks the player has completed in-game.

**Outgoing Check Structure (Size: 16 bytes)**:
* `uint32_t SeqID`: Unique monotonically increasing ID.
* `uint64_t AP_LocationID`: Archipelago Location ID collected.
* `uint32_t IsShop`: 1 if from a store, 0 if chest/event.

The mailbox is a 20,512-byte codecave allocation. The incoming queue begins at `0x20`; the outgoing queue begins at `0x4020`. The client locates the allocation by scanning Cemu memory for the `APMBBOTW` signature.

## 2. Synchronization Mechanism

* **Client Sending Item**:
  1. Checks if `(In_Head - In_Tail) < 256` (Buffer not full).
  2. Writes Item struct to `Incoming_Queue[In_Head % 256]`.
  3. Increments `In_Head`.
* **Hook Receiving Item**:
  1. Checks if `In_Tail < In_Head` (New items available).
  2. Reads `Incoming_Queue[In_Tail % 256]`.
  3. Classifies and inserts the named item through `PauseMenuDataMgr::addItem`, saves the pouch to GameData, then increments `In_Tail`.
* **Hook Sending Check**:
  1. Writes Check struct to `Outgoing_Queue[Out_Head % 256]`.
  2. Increments `Out_Head`.
* **Client Processing Check**:
  1. Checks if `Out_Tail < Out_Head`.
  2. Reads `Outgoing_Queue[Out_Tail % 256]`.
  3. Dispatches via AP WebSocket. On success, increments `Out_Tail`.
