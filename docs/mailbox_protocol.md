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
(sorted integer IDs). The client compares slot data, server locations, and the
resident hook table before writing any items or sending any checks.

Enable the generated pack as the **only** AP hook pack. The source hook's empty
table is an unconfigured template and cannot attach as a playable seed.
Protocol v1 packs and slot data must be regenerated.

## Layout

Total allocation: **53,328 bytes (`0xD050`)**. Both rings have 256 entries.

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
| `0x5028` | 4 | Capability bits: bit 0 = native pouch actor command |
| `0x502C` | 4 | Configured: 1 for a seed pack |
| `0x5030` | 4 | Location table count (1–4096) |
| `0x5034` | 4 | Current native delivery error / hook |
| `0x5038` | 4 | Last completed incoming delivery token / hook |
| `0x503C` | 4 | Client-assigned Cemu lifetime nonce; initially zero |
| `0x5040` | 16 | Seed/player fingerprint |
| `0x5050` | `0x8000` | 4096 entries: u32 location ID, u32 check state |

Status stays at 2 after the first gameplay tick; it is not a current pause/loading
indicator. Pausing stops tick advancement and consumption. Unused table entries
are zero. Check states: 0 unseen, 1 pending, 2 published to the outgoing ring.

### Incoming entry (64 bytes)

| Offset | Size | Meaning |
| :--- | :--- | :--- |
| `0x00` | 4 | Token: received-item history index + 1 (nonzero) |
| `0x04` | 4 | AP item ID (metadata; native action uses actor name) |
| `0x08` | 48 | ASCII native actor name with NUL terminator; maximum 47 bytes |
| `0x38` | 4 | Outstanding quantity, 1–`INT_MAX` |
| `0x3C` | 4 | Command flags; currently **must be zero** |

Weapons use native maximum durability and one actor per command. Stack quantities
are measured before/after the native add. A partial add updates the outstanding
quantity and retains the entry. Already owned unique key items acknowledge
idempotently. The hook saves changed pouch data through the native function.

`addItem` returns void. The hook acknowledges only after observing an increased
live entry count or value sum under the pouch manager lock. An unavailable
manager, invalid actor, unsupported command, or unchanged/full pouch leaves the
entry queued. Errors: 0 none, 1 invalid actor, 2 unsupported command, 3 manager
unavailable, 4 pouch unchanged/full. Nonzero errors are diagnostic, not success.

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
the AP history index only after both native tail advancement and matching token.
The journal lock prevents concurrent access to that seed/player state.

A Cemu restart during an outstanding grant is detected through the lifetime nonce
and requires reconciliation rather than guessing whether delivery happened.
Keep the state directory with the corresponding game save. Loading an older save,
deleting the journal, switching saves, or restarting between a native grant and
its acknowledgement does not have automatic recovery. Checks still in guest RAM
before the client journals them are not durable across a Cemu crash.

## Current limits

The client implements real AP login, history delivery, check submission, and
reconnection. Unsupported `kind: unimplemented` grants remain at the front of the
history with a visible reason; later items wait. Reference precollects can therefore
block delivery until their native grants exist. Native flags, towers, runes,
progressive equipment, pouch/heart/stamina upgrades, pickup banners, Plateau fog
bypass, shop resources, and actual victory reporting remain unfinished.

The pouch measurement uses the v208 symbol sheet and sead list layout. Source
interpreter tests and assembly compilation do not establish emulator stability,
latency, save behavior, or correct runtime native offsets.

## SDK references

The [SDK received-item helper](https://github.com/ArchipelagoMW/Archipelago.MultiClient.Net/blob/main/Archipelago.MultiClient.Net/Helpers/ReceivedItemsHelper.cs)
exposes replayable history separately from its dequeue queue. The
[location-check helper](https://github.com/ArchipelagoMW/Archipelago.MultiClient.Net/blob/main/Archipelago.MultiClient.Net/Helpers/LocationCheckHelper.cs)
also maintains local checked state. This client uses its own durable ownership
journal and awaits the socket packet send directly.
