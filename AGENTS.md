# AGENTS.md — Breath of the Wild Archipelago Multiworld (BotW-AP)

## 1. Project Goal
Build a stable, automated, crash-free Archipelago Multiworld integration for *The Legend of Zelda: Breath of the Wild* (Wii U v1.5.0 / v208 running on Cemu). 

Instead of relying on unstable external RAM injection into Link's inventory array, this project uses a hybrid **Engine Hook + Shared Memory Mailbox Architecture**:
1. **Engine Hook (`src/hook/`)**: A Cemu V3 Graphics Pack (PowerPC ASM) paired with an injected C++ DLL (forked from `S41L0R/SpawnActors` and compiled against `leoetlino/uking` headers) that executes native `ksys` game functions during active gameplay ticks.
2. **Static World Patcher (`src/patcher/`)**: A Python pipeline using `roead` / `byml-v2` (modeled after `MelonSpeedruns/BotwRandomizer` and UKMM) that replaces vanilla `.bdrop` (chests) and `.bshop` (stores) loot with a single reusable `AP_Dummy_Check` actor prior to launch.
3. **External Network Client (`src/client/`)**: A C# (.NET 8) client using `Archipelago.MultiClient.Net` that connects to the Archipelago server and communicates with the C++ Engine Hook exclusively via a thread-safe Shared Memory Mailbox.
4. **APWorld Generator (`worlds/botw/`)**: A Python `.apworld` module seeded with location, item, and region logic from `JDLKMR/BotW-APManual` that generates seeds and packages the player's custom Cemu Graphic Pack.

---

## 2. Success Rubric & Acceptance Metrics
An implementation task or milestone is only considered complete when it satisfies the following criteria:

| Metric | Target Requirement | Verification Method |
| :--- | :--- | :--- |
| **Emulator Stability** | 0 crashes across a 4-hour continuous multiworld session (including cutscenes, fast travel, deaths, and save/loads). | Automated stress test queuing 100 consecutive items across loading screens. |
| **Check Latency** | Opening a chest or purchasing a shop check dispatches a `LocationCheck` packet to the AP server in under 150ms. | Client console timestamp logging from ASM hook trigger to WebSocket dispatch. |
| **Delivery Accuracy** | 100% of received items trigger native UI banners and enter Link's inventory without overwriting existing slots. | Send weapons while pouch is full; verify queue holds item until a slot opens. |
| **Vanilla Isolation** | 0 vanilla progression items obtained from AP-tracked chests or shops. | Inspect generated Graphic Pack `.bdrop` and `.bshop` files via unit tests. |
| **Barrier Bypass** | Receiving the Paraglider from AP immediately disables the Great Plateau death fog without triggering the Old Man cutscene. | Grant Paraglider on a fresh save and glide off the Great Plateau tower. |
| **Seed Generation** | `Generate.py` produces valid solo and multiworld seeds and outputs a ready-to-enable Cemu Graphic Pack `.zip`. | Run Archipelago seed generator test suite (`pytest worlds/botw/test/`). |

---

## 3. Repository Structure
```text
/
├── AGENTS.md                 # Master architectural spec and agent instructions
├── docs/
│   └── mailbox_protocol.md   # Byte layout for Incoming/Outgoing shared memory
├── external/                 # Read-only reference submodules (DO NOT modify)
│   ├── sead/                 # open-ead/sead standard library headers
│   ├── SpawnActors/          # S41L0R/SpawnActors ASM + DLL hook base
│   └── BotW-APManual/        # JDLKMR/BotW-APManual JSON logic & location lists
├── src/
│   ├── hook/                 # C++ DLL payload & Cemu V3 patches.txt / rules.txt
│   ├── client/               # C# (.NET 8) Archipelago client & Mailbox poller
│   └── patcher/              # Python scripts for .byml, .bdrop, .bshop, and .msbt modding
└── worlds/
    └── botw/                 # Python Archipelago .apworld implementation
