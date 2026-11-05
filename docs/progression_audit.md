# Progression gate audit

The goal has since been strengthened: all four Blight defeat checks are required,
plus `Trial of the Sword - Completed` when Master Trials is enabled, and the Dark
Beast defeat check. Both generation logic and client goal reporting use these
prerequisites. The measurements below predate that change.

Audited the current open-world rules with default options, solo seeds 1–10,
using Archipelago's restrictive fill and `MultiWorld.get_spheres()`. This is a
logic simulation; it does not verify physical access in Cemu or predict a
multiworld's sphere count. Event locations are included in the sphere sizes.

| Seed | Locations per sphere |
| --- | --- |
| 1 | 32, 74, 37, 127, 109, 11 |
| 2 | 32, 189, 48, 77, 41, 3 |
| 3 | 32, 79, 20, 119, 130, 8, 2 |
| 4 | 32, 86, 45, 112, 109, 6 |
| 5 | 32, 6, 201, 119, 31, 1 |
| 6 | 32, 96, 98, 78, 77, 9 |
| 7 | 32, 91, 197, 69, 1 |
| 8 | 32, 4, 178, 112, 60, 4 |
| 9 | 32, 160, 141, 52, 5 |
| 10 | 32, 74, 25, 5, 6, 12, 86, 36, 73, 40, 1 |

The initial state reaches 32 checks. Adding only the Paraglider reaches 106.
From that state, adding each item independently gives these extra checks:
Magnesis 29, Cryonis 10, Remote Bombs 103, Stasis 11, Revali's Gale 4,
Camera 1, Central Tower 0, Vah Ruta Controls 0. The last figure does not mean
Controls are unused: other requirements must also be met.

## Existing gates to improve first

* Audit shrine and shrine-chest rules against their actual puzzles. The four
  Plateau rune terminals already suppress vanilla rune acquisition. Runes are
  therefore the best existing AP-controlled capabilities to build on. Record
  legitimate alternate solutions and distinguish no-glitch logic from skips.
* Audit Divine Beast access, internal terminals and boss access separately.
  Controls items currently grant flags, but the static patch does not suppress
  every vanilla route to those flags. A delivery implementation alone does not
  establish an enforced AP gate. Patch the appropriate event before relying
  on exclusive Controls ownership.
* Replace broad miniboss assumptions with encounter-specific combat logic.
  Many encounters share Bombs OR Master Sword, so one receipt opens a large
  group. Ordinary weapons remain obtainable in the game; requiring an AP
  sword, bow, armor set or heart total would not be a physical gate by itself.
* Check the inherited Trial of the Sword and final-goal requirements. Heart
  counts, upgraded armor and required abilities can be conservative logic
  assumptions; they should not be presented as enforced game restrictions.

## Optional new gates requiring implementation

| Mechanism | Effect | Required work |
| --- | --- | --- |
| Shrine entry permits, grouped by trial type or tier | Creates several dungeon-access steps while keeping Hyrule traversable | New items, entry-event restrictions, delivery flags, matching entrance rules and checks for alternate entrances/re-entry |
| Separate Divine Beast entry permits and Controls | Separates entry from internal progression | Suppress vanilla permit/control grants and guard the actual entry/control events |
| Progressive rune stages | Splits large ability unlocks into smaller steps | Verify each stage is meaningful for puzzles; existing Bombs/Stasis upgrades alone may not create many new gates |
| Boss completion prerequisites for the final encounter | Adds a late progression chain | Patch final encounter access and expose a goal option; matching logic alone cannot prevent early entry |

These are proposals, not implemented features. More spheres are not guaranteed:
placement and parallel routes can still collect several unlocks in one sphere.
Start with the rune/puzzle audit; add optional shrine permits if a deliberately
more structured randomizer mode is desired. Keep the overworld open.

Tower items now reveal maps without opening regions. Their inherited progression
classification should also be reviewed so the filler does not prioritize map
items that no longer unlock checks.

Nintendo's [rune guide](https://play.nintendo.com/news-tips/tips-tricks/legend-of-zelda-breath-of-the-wild-runes-guide/)
describes the distinct rune capabilities. Its
[Trial of the Sword description](https://www.nintendo.com/en-gb/Games/Nintendo-Switch-games/The-Legend-of-Zelda-Breath-of-the-Wild-1173609.html)
describes the trial as a challenge that powers up the Master Sword; the
repository's additional numerical requirements still need a physical audit.
