# Wii U v208 hook offsets

The active graphic pack matches RPX module CRC `0x6267BFD0` (Wii U v1.5.0/v208).
Addresses below come from the existing core hook, SpawnActors reference, and
`src/symbols-wiiu-v208.csv`. Switch addresses in `external/uking` establish engine
relationships but must never be called as Wii U addresses. New measurement and
acknowledgement behavior still needs validation in Cemu.

## Active entrypoints and native calls

| Address | Use |
| :--- | :--- |
| `0x0313B840` | Unpaused gameplay tick from SpawnActors; replay `cmpwi r3,0`, resume `0x0313B844` |
| `0x02EB3DF0` | `PauseMenuDataMgr::addItem`, void return; marker interception; ordinary path replays `stwu r1,-0x50(r1)`, resumes `0x02EB3DF4` |
| `0x037B6040` | Existing actor-spawn prologue passthrough; replay `stwu r1,-0x38(r1)`, resume `0x037B6044` |
| `0x10469978` | Pointer to the pouch manager singleton |
| `0x10263910` | Wii U SafeString vtable; object layout `{text pointer, vtable pointer}` |
| `0x030BB668` | Lock the manager critical section at manager + `0x10` |
| `0x030BB69C` | Unlock that critical section |
| `0x02EAE914` | Classify pouch actor: `(&SafeString, 0)` |
| `0x0308812C` | Resolve maximum durability for sword/bow/shield: `(&SafeString)` |
| `0x02EB58A8` | Food-only post-add call: `(manager, &SafeString)`; do not use for weapons |
| `0x02EB3764` | Save pouch to GameData: `(manager, manager + 0x4C)` |

Native add arguments are `(manager, &SafeString, type, manager + 0x4C, value, 0, 0, 0)`.
Sword/bow/shield types 0/1/3 use full durability; other supported actors use the
remaining quantity. Type 8 receives the food post-add call. A void return is not
proof of delivery: the hook measures live named entries before and after the add.

## Measurement layout

The `sead::OffsetList` at manager + `0x4C` contains sentinel `prev`/`next` pointers,
count, and node offset. See `external/sead/include/container/seadListImpl.h` and
`seadOffsetList.h`. The next pointer is at manager + `0x50`, node offset at +`0x58`.
A linked node's next pointer is +4; subtract the list's node offset to obtain its
PouchItem. The v208 sheet identifies PouchItem `mType` at +8, `mValue` at +`0x10`,
and `mName.text` at +`0x18`. Zero-value entries are inactive. Traversal is bounded
at 420 nodes and runs while holding the native manager lock.

## Checks and mailbox

The reserved raw actor format is `AP_Check_` plus exactly eight uppercase hex
digits. The ID must appear in the compiled seed table. Unknown/malformed reserved
markers are suppressed without reporting an invented ID. Valid markers become
pending; gameplay ticks flush them into the outgoing ring. A full ring keeps the
pending state. Duplicate pickups are suppressed within the running Cemu lifetime.
`_AP_Is_Injecting` prevents incoming grants from producing outgoing checks.

The dynamic codecave label `_AP_Mailbox_Base` owns a `0xD050` byte allocation.
The client scans for `APMBBOTW`, then validates the `APV2` extension, configured
state, fingerprint and location table. See [mailbox_protocol.md](mailbox_protocol.md)
for every field and ownership rule. `status` at +8 stays 2 after the first tick;
`tick_count` at +`0x1C` is the gameplay heartbeat.

## Unimplemented native features

Pickup banners, GameData flag delivery, progression upgrades, Plateau fog bypass,
and victory detection are not wired into this mailbox. Earlier placeholder UI
and GameData function addresses are intentionally not presented as callable APIs.
Candidate native flags and functions must be checked against the v208 symbol
sheet and validated at runtime before adding new capability/command types.
