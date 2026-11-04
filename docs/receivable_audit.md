# Receivable audit

All 179 Manual entries and the additional Paraglider / Arrows (10) entries now have delivery mappings. The previous 43 unsupported entries use shared native profiles in `worlds/botw/data/native_grants.json`, embedded in the client and referenced by the world generator. Existing slot contracts that label these entries `unimplemented` resolve their names through the same profiles.

## Native dispatch

| Receivable | Native path |
| --- | --- |
| Weapons | Classify, read max durability, add and save under the pouch critical section |
| Armor, arrows, materials | Classified pouch add/save; armor IDs matched to message names and ActorInfo base ranks |
| Rupees | `increaseFlag_CurrentRupee`, followed by saved wallet verification; delta issued once |
| Hearts | `PlayerInfo::setMaxHeartValue` |
| Stamina | `PlayerInfo::setStaminaMax` and `setActorStaminaMax` |
| Inventory slots | Native asynchronous GameData s32 setter |
| Runes and sensor | Native ownership flags; separate upgrade tiers; bombs also grant both shape flags; camera grants album and compendium flags |
| Travel Medallion | Native pouch add followed by ownership flag |
| Champion abilities | Native base/upgraded key-item pouch add, ownership flag verification, then native removal of the base key item for upgrades |
| Divine Beast controls | Per-beast app flag and interior-map flag; Medoh download and Rudania window flags mirror the download event |
| Final Trial controls | `IsGet_App_FinalTrial` |
| Divine Beast completion | Corresponding `Clear_Remains*` flag |
| Armor upgrade | `GreatFairy_ArmorRank`, four tiers |
| Progressive Master Sword | Sword grant, then 10/20/30 added power; final tier sets full-power flag |
| One-Hit Obliterator | Native `Weapon_Sword_502` pouch grant and ownership flag |
| Towers | Tower marker and activation flags, then native tower centre/scale loaders and record initialization |

Flag operations use native by-name bool/s32 getters and manager setters. Event-only tower activation flags require the native typed setter's event permission path; both write cores are updated when mirroring is enabled. No raw inventory array writes are used.

## Recovery

The client journals the selected progressive tier before mutating it. Each absolute flag write is read back on a later gameplay tick. A partial grant resumes its selected tier after reconnect; it cannot choose a higher tier merely because its first ownership flag has already changed. Actor grants retain pouch-full handling. Champion upgrades remove the base item only after the upgraded item and ownership flag are confirmed. The removal uses the native signed-count pouch mutation at `0x02eb8180`, with a pointer to `allowEquipped=true`, matching its native caller at `0x02152650`. The callee locks, saves and rebuilds pouch lists. The client checks that the base item is absent before acknowledging the receipt; replay restores the removal name and bool pointer storage, and an executed batch is verified without being reissued. Capped upgrade receipts also clean up base items left by older client versions. Repeated receipts beyond the highest tier are consumed without increasing the cap. Absolute flag writes may be retried safely; the wallet delta remains a separate once-only operation.

## Evidence and verification

- Every native profile's flag name, type and program-write permission was checked against the installed Wii U v208 Bootup GameData.
- The symbol catalog supplies native addresses, calling conventions, tower refresh functions and event permission semantics.
- Installed event flows supplied rune and sensor ownership checks, Divine Beast map download flags, champion upgrade actor names, tower activation/marker operations, and Master Sword power operations (`Demo206_0`, `100enemy` flow).
- Client build and self-tests pass, including all 43 profiles, progression caps, byte-sized big-endian bool outputs, delayed flag commits and reconnect without accidentally granting a second Stasis tier. Champion tests cover all four base-to-upgraded replacements, delayed removal, journal replay before publication, reconnect after execution, and preservation of unrelated pouch items.
- A direct import of the world reference confirms all 181 entries have implemented delivery kinds. All 18 world generation tests pass, including a regression test for delivery coverage.

## Live validation status

The full Cemu delivery-state suite passed on 2026-11-04: 194 receipts covering all 181 item types and 27 categories, including all four champion base-item removals, in 68.82 seconds including startup/shutdown. Independent native flag and pouch observations verified every planned receipt. Live testing corrected the extra GameData core pointer dereference, the event-only typed setter permission register, and active armor counting despite sentinel values. See `docs/cemu_integration_tests.md` for commands and evidence.

These observations do not establish all gameplay effects. Verify immediate rune usability, tower visuals/fast travel, ability activation/cooldowns and icon replacement, equipped Master Sword power refresh, and One-Hit Obliterator behavior outside its vanilla quest. Native pickup banners are still absent from the direct pouch path. The four-hour stability and full-pouch acceptance sessions remain outstanding.
