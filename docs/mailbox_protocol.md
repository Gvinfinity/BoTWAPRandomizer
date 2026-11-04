# BotW AP mailbox protocol v2

The active implementation is a PowerPC hook in a Cemu graphic pack and a Linux
.NET client reading `/proc/<Cemu pid>/mem`. No DLL mailbox adapter is used in this
path. The shared schema is `worlds/botw/static/protocol.json`; Python loads it and
C# embeds that exact file. All integers in guest memory are **big endian**.

## Seed identity and check actors

Each chest drops `AP_Check_XXXXXXXX`, encoding its nonzero unsigned 32-bit AP
**location ID** in exactly eight uppercase hexadecimal digits. Its localized
label, `Archipelago Item [XXXXXXXX]`, is display text. A placed item's ID or owner
never determines the local check ID.

The patcher bundles the core ASM with an immutable seed location table. Slot data
contains protocol version, player, seed name, fingerprint, location names and item
delivery metadata. The fingerprint is the first 16 SHA-256 bytes of compact,
key-sorted JSON containing `seed` (string), `player` (integer), and `locations`
(sorted integer IDs). New seeds also include the canonical `starting_state`
object in that JSON identity. Legacy seeds without a starting-state object
retain their original fingerprint calculation. The client compares slot data, server locations, and the
resident hook table before writing any items or sending any checks.

Enable the generated pack as the **only** AP hook pack. The source hook's empty
table is an unconfigured template and cannot attach as a playable seed.
Protocol v1 packs and slot data must be regenerated.

## Layout

Total allocation: **53,584 bytes (`0xD150`)**. Both rings have 256 entries.
Offsets are relative to `_AP_Mailbox_Base`.

| Offset | Size | Meaning / writer |
| :--- | :--- | :--- |
| `0x0000` | 8 | `APMBBOTW` |
| `0x0008` | 4 | Status: initially 0, hook sets 2 on a gameplay tick |
| `0x000C` | 4 | Incoming head: next producer position / client |
| `0x0010` | 4 | Incoming tail: next consumer position / hook |
| `0x0014` | 4 | Outgoing head: next producer position / hook |
| `0x0018` | 4 | Outgoing tail: next consumer position / client |
| `0x001C` | 4 | Gameplay tick counter / hook |
| `0x0020` | `0x4000` | Incoming ring, 256 × 64 bytes |
| `0x4020` | `0x1000` | Outgoing ring, 256 × 16 bytes |
| `0x5020` | 4 | `APV2` extension signature |
| `0x5024` | 4 | Protocol version: 2 |
| `0x5028` | 4 | Capability bits: `0x1` pouch actors, `0x2` progression, `0x4` RPC |
| `0x502C` | 4 | Configured: 1 for a seed pack |
| `0x5030` | 4 | Location table count (1–4096) |
| `0x5034` | 4 | Guest address of the mailbox / hook |
| `0x5038` | 4 | Sequence of the last completed RPC / hook |
| `0x503C` | 4 | Client-assigned Cemu lifetime nonce; initially zero |
| `0x5040` | 16 | Seed/player fingerprint |
| `0x5050` | `0x8000` | 4096 entries: u32 location ID, u32 check state |
| `0xD050` | `0x100` | Client scratch space for guest-visible arguments |

Status stays at 2 after the first gameplay tick; it is not a current pause/loading
indicator. Pausing stops tick advancement and consumption. Unused table entries
are zero. Check states: 0 unseen, 1 pending, 2 published to the outgoing ring.

### Incoming RPC entry (64 bytes)

The client writes one call per entry. Addresses and pointer arguments are Wii U
guest addresses. The hook loads the argument registers and calls the address on
the gameplay thread. Floating-point values are IEEE 754 single precision.

| Offset | Size | Meaning |
| :--- | :--- | :--- |
| `0x00` | 4 | Nonzero RPC sequence ID |
| `0x04` | 4 | Guest function address |
| `0x08`–`0x24` | 32 | Integer/pointer arguments `r3`–`r10`, in register order |
| `0x28`–`0x34` | 16 | Floating-point arguments `f1`–`f4`, in register order |
| `0x38` | 4 | Returned `r3`, written by the hook |
| `0x3C` | 4 | Returned `f1`, written by the hook |

The client publishes a batch by writing every entry, then advancing incoming
head once. On a gameplay tick the hook snapshots head and executes the available
calls in order. For each call it writes the results and acknowledgement sequence,
then advances tail. Calls published after the snapshot wait for a later tick.
The client waits for the whole batch to be consumed and checks the last sequence
before reading results. Completion means the function returned; it does not prove
that an item was granted or that an asynchronous game state change was saved.

The hook calls the supplied address directly; it does not validate the function,
arguments, or pointers. The client must use correct v208 addresses and the native
calling convention. Actor calls use a `sead::SafeString` in scratch space: a guest
text pointer, a vtable pointer, then a NUL-terminated ASCII actor name. Scratch
arguments must remain valid until all calls using them finish.

For item delivery, the client classifies the actor and, for weapons, queries its
maximum durability. It queues native lock, add, optional food post-add, save and
unlock calls. The client compares stable pouch observations before and after the
batch, retries an unchanged/full pouch, and tracks partial stack grants. An already
owned unique key item is treated as delivered. Progression grants use native
getters and setters, then poll for the target value. These checks and retries are
client behavior, not RPC-level guarantees.

### Outgoing entry (16 bytes)

| Offset | Size | Meaning |
| :--- | :--- | :--- |
| `0x00` | 4 | Outgoing ring producer position |
| `0x04` | 8 | AP location ID; high word zero for this catalog |
| `0x0C` | 4 | IsShop; currently zero (chests only) |

## Ownership, backpressure, and recovery

Each ring has one producer and one consumer. Counter subtraction wraps as u32;
`head == tail` is empty and `head - tail == 256` is full. Publish the payload
before advancing head. The ASM uses `sync` before publication. Client operations
run on one polling loop and attachment acquires a per-Cemu producer lease.

The acquisition hook suppresses every reserved marker before pouch insertion.
Only exact, seed-listed IDs become pending. Tick processing flushes pending checks;
a full outgoing ring retains their table state. Repeated acquisitions are
idempotent within the Cemu lifetime. Ordinary actors continue through native
`addItem`; incoming grants cannot use marker names.

The client durably journals a check **before** releasing its outgoing slot. The
journal retains the complete checked set and resends it on login; AP checks are
idempotent. A network failure does not lose a freed ring entry. One received item
is in flight at a time. The client saves its intent before publication and advances
the AP history index only after the grant-specific verification succeeds. RPC
sequences identify calls, independently of AP history indices.
The journal lock prevents concurrent access to that seed/player state.

For seeds with a starting-state profile, `starting_inventory` lists the exact
counts already applied to a fresh save by the static pack. Received-item records
retain both item ID and source location. The client acknowledges only those
counts with AP's precollected source location `-2`, saves their applied counters
in the journal, and advances the history index without a second native grant.
Later chest/cheat rewards with the same item ID still follow native delivery.
RPC sequences are assigned separately from AP history indices.

A Cemu restart during an outstanding grant is detected through the lifetime nonce
and requires reconciliation rather than guessing whether delivery happened.
Keep the state directory with the corresponding game save. Loading an older save,
deleting the journal, switching saves, or restarting between a native grant and
its acknowledgement does not have automatic recovery. Checks still in guest RAM
before the client journals them are not durable across a Cemu crash.

## Current limits

The client supports AP login, received-item history, checks, reconnection, actor
grants, and selected heart, stamina, and pouch-slot progression grants. Unsupported
`kind: unimplemented` grants block later history entries with a visible reason.
Legacy seeds without applied-starting metadata can block on reference precollects.
Pickup banners, shop checks, live Paraglider flag delivery, and victory reporting
remain unfinished. The Plateau skip sets its containment flag and pouch statically
on a fresh save.

Pouch observation reads guest memory from the client and uses repeated reads for
stability; it does not hold the game lock while measuring. The native call batch
locks around the add and save. Source interpreter tests and assembly compilation
do not establish emulator stability, latency, save behavior, or correct runtime
native offsets. Test these in Cemu before relying on them.

## SDK references

The [SDK received-item helper](https://github.com/ArchipelagoMW/Archipelago.MultiClient.Net/blob/main/Archipelago.MultiClient.Net/Helpers/ReceivedItemsHelper.cs)
exposes replayable history separately from its dequeue queue. The
[location-check helper](https://github.com/ArchipelagoMW/Archipelago.MultiClient.Net/blob/main/Archipelago.MultiClient.Net/Helpers/LocationCheckHelper.cs)
also maintains local checked state. This client uses its own durable ownership
journal and awaits the socket packet send directly.
