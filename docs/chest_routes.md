# Chest route research — 0.5.5

All 187 currently AP-bound chest routes are now annotated in
[`chest_routes.json`](../worlds/botw/static/chest_routes.json). Each row includes
its logical map, HashId, AP check ID, original reward actor, position, route,
normal-route requirements and evidence URLs. `check_logic.py` reads these same
requirements; the research is not a separate, unused document. Discovery applies
the corrections again when rebuilding a catalog.

All 187 identities, positions and rewards were checked against the installed v208
maps and their catalog SHA-256 values. The seven duplicate Final Trial variants
were checked too. Walkthrough/landmark matching uses the original reward only as
one identifying clue, together with map geometry and location. It does not use
numbered chest order as a physical binding.

## Corrections established by this research

* `C986043B` and `DE46BD48`: Magnesis retrieves the submerged river chests.
* `B326B249`: Cryonis reaches the wooden chest in the cold pond. Native Plateau
  cold preparation is available; Magnesis does not replace Cryonis here.
* `24A00436`, `53A734A0`, `C3182931`: walk along the southern bank into the
  waterfall cave. These metal chests stand on dry ground; requiring Magnesis
  solely because they are metal would be wrong.
* Three Expansion Pass bonus chests now carry a DLC category instead of appearing
  in a default, DLC-disabled location list.
* The seven chests in `Pack/FinalTrial.pack` belong to the Champions' Ballad's
  fifth Divine Beast, **not** the Trial of the Sword. They now use the `Final Trial`
  region, Champion-song progression and Champions' Ballad option. Individual
  routes cover the rotating plate, fan, water valve, gear catwalk and doorway
  ledges. Their AP IDs and source-map variants remain stable.

The dungeon identification is corroborated by the map's `DgnObj_DLC_Ibutsu*`
mechanisms, English reward labels, and the
[Divine Trial walkthrough](https://zeldauniverse.net/guides/breath-of-the-wild/the-champions-ballad/ex-the-divine-trial/).
The [independent Final Trial guide](https://www.shacknews.com/article/102523/zelda-breath-of-the-wild-champions-ballad-final-trial-walkthrough)
describes the corresponding machinery and rewards. The Diamond doorway ledge is
also described in the [complete walkthrough](https://gamefaqs.gamespot.com/switch/189707-the-legend-of-zelda-breath-of-the-wild/faqs/75420/walkthrough).

Plateau research cross-checks the installed maps against the
[River of the Dead chest list](https://zeldawiki.wiki/wiki/River_of_the_Dead),
[Forest of Spirits chest list](https://zeldawiki.wiki/wiki/Forest_of_Spirits),
[Temple of Time chest list](https://www.zeldawiki.wiki/wiki/Temple_of_Time),
[2017 mountain chest guide](https://www.itechpost.com/articles/90770/20170309/zelda-breath-of-the-wild-guide-to-finding-hidden-treasure-in-the-great-plateau.htm),
and [Plateau walkthrough](https://www.zeldaspalace.com/breathofthewild/soluce.php?p=3).
Source inconsistencies are retained as caveats, including a secondary guide's
incorrect Opal label for the cold-pond chest whose installed actor yields Amber.
The two bog-platform alternative sets retain the player's explicit confirmation.

## Exact scope

The catalog covers **32 Plateau, seven Final Trial and 148 shrine checks**.
The shrine pass matches native reward actors and positions to the individual
walkthrough chest descriptions. Identical rewards are not resolved by numbering:
Mirro Shaz's two hammers were distinguished using the entrance-elevator position
and the distant side trial. Its first hammer and Wahgo Katta's crate-top Amber
need no local Stasis/Magnesis puzzle respectively; their old gates were removed.

The twenty ambiguous initial source matches were cross-checked against additional
guides. Relevant entries retain `identity_note` corrections, including scaled bow
names and Ta'loh Naeg's interior equipment chests incorrectly described as outside.
Voo Lota's independent guides also establish its glider-only chest detour; the
initial source's mandatory-Stasis claim is rejected. Corroborated entries record
`source_review: cross_checked`. Not every secondary guide statement is accepted,
and this does not establish minimum requirements across every possible strategy.
Existing shrine approach/quest requirements are retained unless a specific local
correction is established. Unbound and excluded game chests are outside this
187-check scope. No checks were enabled from keyword matches or chest material.

Requirements represent supported normal routes, not proof of minimal requirements
across all possible strategies. Native combat equipment, food, elixirs, ordinary
climbing and stamina recovery remain available. Parent region, quest and goal
requirements still apply in addition to each local expression.

These are research-established routes, not Cemu playtest results: every entry
retains `gameplay_verified: false`. Cemu verification must test missing required
capabilities and accepted alternatives on the generated pack. Regenerate seeds
and packs for 0.5.5 because the previous Final Trial placements and DLC selection
used the wrong access chain.
