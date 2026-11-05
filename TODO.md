[ ] Run the four-hour Cemu stability test with loading screens, deaths, and reconnects.
[ ] Measure chest/shop check latency against the 150 ms target; shop checks are not implemented.
[ ] Verify player-visible item banners for actor and native grants in Cemu.
[ ] Verify full-pouch queueing and recovery across save/load.
[ ] Verify the Paraglider AP grant clears Great Plateau containment without the Old Man event.
[ ] Expand physical route coverage to every supported shrine, tower, miniboss, and boss.

The current beta already includes progressive Master Sword and Champion ability
tiers, tower item delivery and physical tower checks, shrine completion checks,
and a complete delivery mapping for all 181 enabled item types. Regression
coverage is in `worlds/botw/test/`, `src/patcher/tests/`, and `tests/cemu/`.
