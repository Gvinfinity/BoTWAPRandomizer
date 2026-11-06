# Walkthrough comparison: access and quest gates

Research audit, 2026-11-05. Version 0.5.3 implements the boarding, disguise,
Camera and local quest-stage changes described in [boarding_logic.md](boarding_logic.md).
The original findings and proposals follow. Walkthrough routes identify candidates;
mandatory requirements and alternate solutions still need game-event or physical
verification before changing the generator. Assume a fresh save and no glitches.

## Confirmed gaps in the current logic

### 1. Gerudo Town disguise and the Naboris quest chain

The standard entrance route uses Gerudo Veil, Gerudo Top and Gerudo Sirwal.
The town is distinct from the surrounding desert. The walkthrough enters town
before meeting Riju and starting the stolen-helm quest.
[Gerudo Town walkthrough](https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/gerudo-town/)

There is currently no `Gerudo Town` region. Naboris has a heat-resistance OR
Gerudo-outfit branch, which allows other heat-resistant armor to substitute for
the disguise. With all items except the three Gerudo pieces, the current state
can reach Thunderblight's check. That is an incomplete model of normal boarding.

Propose a separate town/quest entrance with a disguise rule. Route Riju-dependent
progression and future town checks through it. Keep outdoor desert checks and
Daqo Chisay, outside the town gate, outside this restriction.

Do not require exactly the original trio without checking alternatives. The
Thunder Helm can replace the Veil, and Sand Boots or Snow Boots can replace the
Sirwal while preserving the disguise. A candidate expression is:

`Gerudo Top AND (Gerudo Veil OR Thunder Helm) AND (Gerudo Sirwal OR Sand Boots OR Snow Boots)`

Verify the guard-event conditions before adopting that expression.
[Disguise mechanic](https://zeldawiki.wiki/wiki/Disguise_%28Mechanic%29)

### 2. Lakna Rokee needs Camera access through its prerequisite quests

The shrine quest follows Find the Fairy Fountain, Flown the Coop and By Firefly's
Light. The fountain quest requires taking a photograph.
[Lakna Rokee guide](https://www.zeldadungeon.net/wiki/Lakna_Rokee_Shrine),
[Find the Fairy Fountain walkthrough](https://zeldauniverse.net/guides/breath-of-the-wild/walkthrough/chapter-8-find-the-fairy-fountain/)

Both the bound chest and shrine completion currently require combat/armor items
but omit Camera. A state with all items except Camera can reach both checks.
Add Camera to both access rules. Ideally represent the prerequisite quest chain
as local events; do not invent AP items for freely obtainable fireflies/cucco
interactions. Keep the shared prerequisite consistent across chest and monk.

## Further changes worth investigating

### 3. Distinguish story objectives from their randomized rewards

Naboris boarding follows recovery and return of the stolen Thunder Helm; Riju
uses it during the assault. Link's wearable helm is a later reward available
after Naboris. The current AP `Thunder Helm` maps to wearable armor, so its new
region requirement is a custom AP gate, not a complete recreation of that quest.
[Naboris entrance](https://www.zeldadungeon.net/wiki/Divine_Beast_Vah_Naboris),
[wearable Thunder Helm](https://www.zeldadungeon.net/wiki/Thunder_Helm)

Keep the requested AP gate if desired, but model `Helm Returned / Riju Ready`
separately. Inspect which quest flags receiving the AP armor actually changes;
armor ownership alone should not be assumed to advance the native quest.

Likewise, a Blight defeat, activating a Beast's final terminal, reporting to its
elder, owning a Champion ability, and receiving an AP `Vah ... Cleared` item are
different events. The current cleared-item profiles write `Clear_Remains...`;
they do not prove that every dependent native quest stage is satisfied.
[Free the Divine Beasts quest](https://www.zeldadungeon.net/wiki/Free_the_Divine_Beasts)

### 4. Champions' Ballad progression

The DLC begins after the four Divine Beast quests are completed. The final
dungeon follows completion of all four Champion songs.
[start requirements](https://www.zeldadungeon.net/wiki/index.php?title=EX_The_Champions%27_Ballad),
[final dungeon walkthrough](https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/the-champions-ballad/)

Current regions use possession of four progressive Champion abilities for the
Obliterator stage, and two copies of each for the Final Trial. Receiving those
items is not evidence of completing their native quest chains. Propose explicit
local story milestones for entry, four song completions, and final-dungeon access,
or deliberately make AP items unlock those stages through verified event patches.

### 5. Trial of the Sword sequencing

The Beginning, Middle and Final Trials are completed in order.
[Trial quest guide](https://www.zeldadungeon.net/wiki/EX_Trial_of_the_Sword)

Current trial regions instead use separate 13/19/25 Heart Container requirements,
Master Sword ownership and runes. There is no local completion dependency between
the three trial regions. Propose Beginning Clear -> Middle Access -> Middle Clear
-> Final Access, using save-backed events. Review the numerical health thresholds
as difficulty assumptions rather than treating them as substitutes for clears.
Ensure received sword upgrades cannot manufacture completion milestones.

### 6. Beast boarding and terminal puzzles

Ruta's standard assault requires Zora Armor and Shock Arrows. Medoh's approach
uses a bow and Bomb Arrows; Teba supplies resources. Rudania's cannon route uses
round bombs. The existing regions capture some requirements (Ruta armor and
Cryonis, Rudania bombs), but not the complete distinction between boarding,
obtaining controls, solving terminals and reaching the boss.
[Ruta](https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/zoras-domain/),
[Medoh](https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/rito-village/),
[Rudania](https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/goron-city/)

Audit those stages independently. Do not require receiving a particular AP bow
or an arbitrary number of arrow bundles when the native quest supplies them.
AP receipt counts do not measure remaining ammunition. Any new inventory gate
needs a verified resource source and a decision about vanilla acquisition.

## Gates already represented

* Voo Lota's chest and completion require `Vah Medoh Cleared`. The walkthrough
  confirms Medoh is a prerequisite for the sisters' shrine quest. A state missing
  that item cannot reach the completion check.
  [Recital at Warbler's Nest](https://www.zeldadungeon.net/wiki/Recital_at_Warbler%27s_Nest)
* Raqa Zunzo's chest and completion require `Vah Naboris Cleared`. The race opens
  after Naboris. A state missing that item cannot reach the completion check.
  [The Undefeated Champ](https://www.zeldadungeon.net/wiki/The_Undefeated_Champ)
* Camera is already required at Kah Yah and Shoqa Tatone. The dragon-scale
  checks at Shae Katha, Tutsuwa Nima and Jitan Sa'mi also already include their
  respective scales. These observations come from the bound chest/completion
  catalogs; they do not establish complete physical route coverage.

## Avoid adding misleading region locks

Climate requirements belong to exposed routes/subregions, with appropriate
alternatives. For example, the Goron City walkthrough explicitly uses Fireproof
Elixirs. Requiring only a specific armor set would exclude that ordinary route.
[Goron City walkthrough](https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/goron-city/)

Keep disguise checks separate from heat protection. Sand/Snow Boots, climbing
gear, upgraded armor and recommended heart totals should not become mandatory
just because a walkthrough recommends them. A shrine quest appearing in the log
also does not always mean starting that quest is necessary to reveal the shrine;
verify the actual pedestal/event before adding a prerequisite.

Suggested order: town/disguise + Lakna Rokee first, then native quest milestone
semantics, Champions' Ballad stages, Trial sequencing, and per-dungeon boarding
and puzzle routes. Apply shared shrine access changes to both chests and monk
checks; the current requirements are duplicated across the reference and bound
catalogs. Add generation tests for missing prerequisites and legitimate alternate
equipment, followed by physical checks of changed native event behavior.
