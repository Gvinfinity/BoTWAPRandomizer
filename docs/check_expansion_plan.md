# Shrine, tower and encounter checks

The world now supports independent `shrine_sanity`, `tower_sanity`,
`miniboss_sanity` and `boss_sanity` options. They default on. `chest_sanity`
adds mapped overworld chests; mapped shrine chests remain included. Tower items
reveal maps without locking access to regions or their tower checks. The Plateau
tower check is omitted when its tutorial is skipped. Boss checks required by the
selected goal remain enabled with `boss_sanity` off.

The supported catalog contains 120 base-game shrine completions, fifteen towers,
84 base-game minibosses (40 Talus, 40 Hinox/Stalnox and four Molduga), and six
base-game bosses (four Blights, Calamity Ganon and Dark Beast Ganon). Champions'
Ballad adds Igneo Talus Titan, Molduking and Maz Koshia. DLC options gate those
three encounters. With all mapped chest bindings and options represented, the
live route manifest contains 415 locations. Normal seeds select their enabled
subset, including fourteen towers with the default tutorial skip.

Monk rewards are patched in both `Npc_DungeonPriest001` and the `Demo033_0`
cinematic event. A current-map dispatch replaces only selected base-game Spirit
Orb grants, preserving the original continuation, counters and return behavior.
Untracked and DLC shrine completion rewards retain vanilla behavior. Native
`Clear_DungeonNNN` watches reconcile completed shrine checks through the same
outgoing queue.

Tower checks come from physical terminal activation, never from tower-map flag
polling. Only selected tower placements use the `AP_TowerTerminal` clone. Its
reactivation event works after receiving an AP tower item; original lab, shrine
and Divine Beast terminals remain untouched. An already revealed tower emits its
physical check without replaying the vanilla map-download cinematic.

Encounter checks observe native, save-backed defeat signals. Individual miniboss
placement flags identify each enemy; boss defeat counters/cinematics identify
major bosses. Ability ownership and Divine Beast clear rewards are not defeat
signals. Production packs preserve enemies, combat AI and drops. The watcher
caches native flag indices, invalidates caches when the GameData core changes,
and polls at most 64 entries per gameplay tick. Checks use the existing bounded
queue and persistent client journal, including reconnect deduplication.

Every event/map source has a v208 checksum binding. Base encounters reference
base-game resources and do not require DLC assets. The native watcher adds no
mailbox protocol fields. Regenerate seeds and packs to include the new checks;
previous seeds retain their original location tables.

See [the live test instructions](cemu_integration_tests.md) for item coverage,
physical location routes, assistance, resumability and evidence limits.
