The JSON under `manual/` is reference data extracted from JDLKMR/BotW-APManual
v1.1.0 (`manual_breathofthewild_jd.apworld`), downloaded from:
https://github.com/JDLKMR/BotW-APManual/releases/tag/v1.1.0

The repository submodule itself contains only a README. Its release carries
the data. Original names, counts, categories, and requirement expressions are
preserved here for attribution and review. These are community logic data;
no game binaries are bundled in the APWorld.

`chests.json` is generated from a legally extracted Wii U v208 game using
`python -m src.patcher discover`. It contains paths, actor HashIds, original
loot names, coordinates, source checksums, and the binding provenance. It does
not contain Nintendo binary resources. Unbound or deliberately excluded chests
are recorded explicitly and are not AP checks.
