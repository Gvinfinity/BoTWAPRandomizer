# Walkthrough research library

The local collection is at `out/logic-research/README.md`. It contains 227 full-text
articles: all 136 shrine guides (including DLC), shrine quests, story walkthroughs,
Divine Beast guides, and a second 22-chapter story walkthrough. Nintendo's official
introductory PDF and public object-map chest records are also saved.

Sources: [Zelda Central shrines](https://zeldacentral.com/games/breath-of-the-wild/shrines/),
[Zelda Central walkthrough](https://zeldacentral.com/games/breath-of-the-wild/walkthrough/),
[Zelda's Palace walkthrough](https://www.zeldaspalace.com/breathofthewild/soluce.php),
[Nintendo Explorer's Guide](https://assets.nintendo.com/image/upload/v1675114089/Microsites/zelda-breath-of-the-wild/pdf/ExplorersGuide.pdf),
and [ZeldaMods Object Map](https://objmap.zeldamods.org/).

`manifest.json` records URLs, local article text, timestamps and checksums.
`coverage.json` maps references onto 136 shrines and the chest catalog, including
excluded placements. All 187 bound AP chests match public object identities;
148 have a matching shrine guide, while the 32 Plateau and seven Trial chests
now have per-actor research annotations in `worlds/botw/static/chest_routes.json`
(see [the route findings](chest_routes.md)). All 187 bound checks now have per-actor route annotations; source caveats and
entries needing additional corroboration are retained in the route catalog.

`audit-candidates.json` is a queue of capability mentions to inspect against the
compiled rules, region gates, optional methods and other chests in the shrine.
It does not automatically add requirements. In particular, ordinary weapons,
arrows, cooking and elixirs remain usable under the selected logic assumptions.

For each accepted route, record the shrine/quest approach, its individual chest
position/HashId, required AP capabilities, native resources, alternatives and
source passage/image. Then test the route in Cemu with required items withheld
and with each accepted alternative. Only that final stage should be labeled
`gameplay_verified`; collection and static source matching leave it false.

Full articles and game-object datasets remain in ignored `out/`, not in the
APWorld bundle. Screenshots and video are referenced, not mirrored. Direct
Zelda Dungeon/Zelda Universe downloads were blocked; no access-control bypass
was attempted. Downloading these references does not establish a complete
walkthrough-backed route for every overworld chest or gameplay verification of
all existing rules.
