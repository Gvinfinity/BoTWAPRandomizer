# Resource loading failures: RSTB and DLC

The two failures were isolated on Cemu 2.6, Wii U EU v208, using the previous
diagnostic installation in `/tmp/botw-ap-debug`. Tests used the same game,
settings, and DLC; only the AP overlay changed. The AP hook was absent during
isolation and enabled for the final complete-pack run.

| AP overlay | Result in 30-second startup check |
| --- | --- |
| Empty (rules only) | Survived |
| Previously generated RSTB only (`generated.srsizetable`) | Crashed at PPC `030b1c30`, LR `037edbf4` |
| Rebuilt DLC archive with vanilla diamond drops, no RSTB override | Survived |
| AP `AocMainField.pack` only, no RSTB override | Crashed at PPC `0314db30`, LR `0314eb58` |
| Same AP DLC archive plus corrected RSTB | Survived |
| Complete rebuilt 187-check pack, including hook | Survived |

## Oversized resource allocations

The old generated table added 1,713,862,784 bytes across its allocation budgets,
including large `.pack` entries absent from the vanilla table. Those entries
change the engine's normal archive allocation path. The table alone reproduced
the crash, without maps, custom actors, startup changes, or hook instructions.
Its stack included a request for `Model/Player_Animation.sbfres`; the evidence
points to resource-heap exhaustion, not a corrupt player animation file.
The sum of budgets is not a measurement of simultaneously allocated memory.

The repository already had a partial mitigation excluding absent pack entries.
However, its `max(old_budget, aligned_new_size + 4096)` rule did not preserve
the original parsing allowance when a resource grew. The replacement compares
each changed resource with its original bytes, preserves its existing budget,
and adds twice the positive aligned serialized growth. New AP actor resources
inherit the diamond template's budget and growth. Absent and zero-budget
resources retain the engine's normal allocation behavior. Shared resources
use the largest required budget without accumulating growth for each archive.

## DLC entries were updated in the wrong namespace

Cemu's overlay directory is `aoc/0010`, but the game's resource table keys use
`Aoc/0010/`. The old path conversion discarded the mount, including when
handling members of `AocMainField.pack`. It updated a base-game map allocation
while leaving the actual DLC allocation unchanged.

For `Map/MainField/D-6/D-6_Static.mubin`:

| Value | Bytes |
| --- | ---: |
| Original DLC serialized map | 245,648 |
| Patched DLC serialized map | 245,760 |
| Original DLC RSTB budget | 245,952 |
| Corrected DLC RSTB budget | 246,144 |
| Base-game budget (preserved) | 205,920 |

The patched map consumed the original allocation's parsing allowance. Changing
only the table to grow the correct DLC entry made the same archive survive.
The archive did not need to be disabled, unpacked, or stripped of DLC assets.
The crash stack's `Placement/MainField.bplacement` string was loading context,
not evidence that that file was missing from the archive.

## Fix and verification

`worlds/botw/static/resource_sizes.py` walks the generated resources and their
original nested archive members, retaining the outer DLC mount. `apply_plan`
uses that comparison instead of the builders' flattened size dictionaries.
The corrected complete table adds 3,984,700 bytes across 575 changed entries;
561 entries are the three new resources for each of 187 check actors.

Run the regression suite with:

```sh
.venv-patcher/bin/python -m pytest src/patcher/tests -q
```

All 31 tests pass. One existing pouch test's obsolete Paraglider expectation
was corrected to match the current starting-state implementation and its other
tests; starting inventory behavior was not changed.

Local diagnostic artifacts (temporary, not committed):

- `repro-baseline.log`, `repro-rstb-crash.log`, `repro-dlc-only-crash.log`,
  `repro-dlc-vanilla-actor-pass.log`, `repro-dlc-corrected-pass.log`, and
  `repro-full-fixed-pass.log` under `/tmp/botw-ap-debug`.
- Rebuilt archive: `/tmp/botw-ap-debug/BotW_AP_resource_fix.zip`.
- Installed-file backups: `/tmp/botw-ap-debug/installed-backup-before-resource-fix`.

The installed pack's seed plan matched the rebuilt pack. Only its RSTB and
ActorInfo differed; both were backed up and replaced with the tested outputs.
ActorInfo incorporates an already-existing repository fix that was absent from
the installed artifact. Future packs receive the resource-sizing fixes through
normal `python -m src.patcher apply` generation.

These checks establish reproduction and removal of the two startup crashes.
They do not establish the project's four-hour multiworld stability, loading
transition, item-delivery, or latency acceptance metrics.
