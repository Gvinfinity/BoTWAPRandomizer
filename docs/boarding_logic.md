# Boarding and quest logic — 0.5.3

Beast boarding now has its own region between the surrounding overworld and the
Beast interior. Receiving a Controls item does not grant access through the
boarding route. Interiors also retain their own puzzle/Controls requirements.

| Beast | Normal boarding route in logic | Native supplies included in that route |
| --- | --- | --- |
| Vah Ruta | Paraglider, Zora Armor and Cryonis | Bows and 20 Shock Arrows can be gathered on the Zora approach without defeating the Lynel |
| Vah Medoh | Paraglider, Flight Range preparation and cold protection | A bow is available at the Flight Range; Teba provides Bomb Arrows; cold food/elixir ingredients remain obtainable |
| Vah Rudania | Paraglider, Remote Bombs for cannons, Stasis for route clearance, and fire protection | Foothill Stable's Fireproof Elixirs remain purchasable with renewable vanilla rupees |
| Vah Naboris | Paraglider, Gerudo Town disguise, the existing AP Thunder Helm gate, and Magnesis for Kohga/helm recovery | Riju supplies Bomb Arrows; ordinary bows and sand-seal rental/shields remain available through the native route |

Gerudo Town uses `Gerudo Top AND (Gerudo Veil OR Thunder Helm) AND
(Gerudo Sirwal OR Sand Boots OR Snow Boots)`. The surrounding desert and Daqo
Chisay remain accessible without the disguise. Naboris additionally requires the
helm-recovery milestone; wearing a disguise alone cannot satisfy boarding.
The AP wearable Thunder Helm requirement is retained as requested. It is distinct
from recovering and returning the native quest helm: the player must still do
that quest in-game.

Supply events represent renewable, unmodified vanilla sources, not extra AP
items. Receipt counts of consumable arrow bundles are not used as a proxy for
remaining ammunition. These assumptions depend on the current patcher leaving
those native weapon placements, enemy drops, vendors and quest gifts available.
Future shop/loot randomization must revisit these sources before removing them.

## Other implemented prerequisites

* Camera is required by both the Lakna Rokee chest and monk checks, through
  the prerequisite quest chain's fountain photograph.
* Local `Freed Vah ...` events require reaching the Beast interior with the
  capability to complete its boss and final-terminal quest route. Receiving a
  Champion ability or AP Cleared item cannot directly grant these local events.
* Champions' Ballad access requires all four local Beast completions. The four
  Obliterator shrines precede the twelve Champion-song shrines, and completing
  all four songs precedes the Final Trial. Champion ability upgrades no longer
  substitute for these quest milestones. Native rematches supply their equipment.
* The Beginning Trials completion event gates Middle Trials; Middle completion
  gates Final Trials. AP Master Sword upgrades do not count as trial completions.
  Existing 13/19/25-heart thresholds are retained as conservative difficulty
  assumptions; this release does not claim those are native entry checks.

Local events are the generator's model of quests a player can complete with
available resources. They have no network addresses, grant no extra randomized
items, and do not write or poll native flags. The native game still requires the
actual quests, equipped clothing, and live ammunition at boarding. The existing
native boss/trial check watchers and client Victory prerequisites remain in use.
This release updates generation logic rather than bypassing boarding events.

## Evidence and verification

The walkthrough sources and candidate-rule analysis are recorded in
[the audit](walkthrough_logic_audit.md). Read-only inspection of installed v208
event flows also confirmed:

* `Water_Relic` Events 488/779/859 check Zora upper-body equipment; Events
  642/1031 check 20 `ElectricArrow`.
* `Wind_Relic` Event 801 checks pouch capacity for the 20-Bomb-Arrow quest gift;
  the flow also contains weapon-category and Bomb Arrow inventory checks.
* `Electric_Relic` Events 539/872 check the Gerudo clothing series and the flow
  checks boarding supplies; Riju's outfit, inventory and supply events remain
  untouched by this update.

Generation tests cover missing boarding requirements, accepted disguise
substitutes, native supplies without AP arrow/bow receipts, Controls alone,
Camera gating, DLC stage ordering and trial sequencing. Three four-player BotW
seeds with mixed goal/DLC/check settings were filled and all selected locations
were reachable. Fresh generated patches were validated against the catalogs.
This is not a physical playthrough of all four boarding quests in Cemu.

## Explore logic for a player YAML

Run `python tools/visualize_logic.py --interactive --yaml /path/to/player.yaml --archipelago /path/to/Archipelago` to open the searchable logic viewer using that YAML's BotW options. This regenerates and verifies the graph using the local world and the Archipelago checkout; it may take a moment. PyYAML and the checkout's Python dependencies must be installed in the Python environment used to run the command. Omit `--interactive` to render an SVG, or add `--full` to render every node.

The YAML must specify `game: Breath of the Wild` and fixed option values. Weighted choices are accepted when exactly one choice has a positive weight. Choices with multiple positive weights and random settings are rejected because their actual values are only known after generation. The graph represents logic and options, not the seed's randomized item placements.

Item and location configuration (including starting inventory, placement, exclusions, hints, and item links) is ignored by this viewer; its starting inventory therefore may differ from the player YAML.

In the interactive viewer, select the **Graph** tab to see the selected node's prerequisites. Set the depth and press Refresh to expand more levels, use the zoom buttons and scrollbars to navigate, and click a named node to make it the new focus. This view requires Graphviz's `dot` executable.
