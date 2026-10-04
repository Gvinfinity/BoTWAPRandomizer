# Cemu Installation Guide: BotW Archipelago Multiworld

This guide explains how to install the generated Archipelago patch (which contains the Engine Hook and Static World modifications) into your Cemu emulator. 

The BotW Archipelago mod uses Cemu's **Graphic Packs V3** system to inject ASM, load our custom C++ Hook DLL, and replace the vanilla `.bdrop` map files.

## 1. Prerequisites

> **Game Version:** You must have *The Legend of Zelda: Breath of the Wild* installed in Cemu and updated strictly to **v1.5.0 (v208)**. The ASM memory offsets in the hook will crash your game if used on older versions.

## 2. Locate your Graphic Packs Folder
First, find where Cemu stores its Graphic Packs. 
* **Windows (Portable):** It is the `graphicPacks/` folder located right next to your `Cemu.exe`.
* **Linux / Steam Deck (Native):** Usually located at `~/.local/share/Cemu/graphicPacks/`.
* **Linux (Wine/Proton):** It will be in the `graphicPacks/` folder inside your Wine prefix where Cemu is installed.

## 3. Extract the APWorld Mod
When you generate an Archipelago seed, the `BotW-AP` generator will output a ZIP file containing your personalized Graphic Pack (e.g., `AP_BotW_PlayerName_12345.zip`).

1. Open your `graphicPacks/` folder.
2. Create a new folder named `BotW_Archipelago_Multiworld`.
3. Extract the contents of the ZIP directly into this new folder.

### File Structure Verification
Double-check that the extraction was successful. Your folder structure should look exactly like this:

```text
graphicPacks/
└── BotW_Archipelago_Multiworld/
    ├── rules.txt           # Defines the mod for Cemu's UI
    ├── patches.txt         # Memory hook ASM and code caves
    ├── BotW_AP_Hook.dll    # (Or .so) The compiled C++ Engine Hook
    └── content/            # The modified game files (Patcher output)
        └── Actor/
            └── DropTable/  # Modified .bdrop files (Chests)
        └── Map/
            └── MainField/  # Modified .bshop files (Stores)
```

## 4. Enable the Mod in Cemu

1. Launch Cemu.
2. On the top menu bar, click **Options** > **Graphic Packs**.
3. In the Graphic Packs window, click the **Update latest community graphic packs** button at the bottom right just to be safe.
4. Expand the **The Legend of Zelda: Breath of the Wild** category.
5. Expand the **Mods** subcategory (or look for a dedicated **Archipelago** category depending on `rules.txt`).
6. Find **Archipelago Multiworld Hook** and **Check the box** next to it to enable the mod.
7. Close the Graphic Packs window.

**Note:** To ensure the hook runs cleanly, we recommend disabling any other mods that drastically alter Link's inventory, drop tables, or the Great Plateau sequence (like "Skip the Great Plateau" mods), as they may conflict with AP logic.

## 5. Play and Connect
You are now ready to play! 
1. Boot the game in Cemu.
2. Launch your Archipelago C# Client (`BotWClient`).
3. Connect the client to your AP Server. The client will automatically find the running Cemu process, hook into the Shared Memory Mailbox, and begin synchronizing your multiworld items!
