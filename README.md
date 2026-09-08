# Warcraft II Remastered Runtime Table Editor 1.2.0

Live table editor for **Warcraft II Remastered 1.0.2.2818 x86**. It attaches to the running `Warcraft II.exe`, stages table changes, writes them to process memory, verifies each write, and can restore the attach-time snapshot.

**This edition does not patch or rewrite `Warcraft II.exe` on disk.** Closing/restarting the game removes the runtime changes.

## What you can edit

The editor exposes the verified table surfaces carried forward from the 1.1 editor:

- upgrade step values;
- projectile minimum range, area-effect flags, orders, action sequences, speed, and piercing behavior;
- order/action animation sequences and flags;
- order and spell ranges;
- spell casting costs (16-bit values);
- spell area-effect flags;
- follow/path-adjust/attack-order classification.

Every row shows its current live value and any staged replacement before you apply it.

## Install

1. Install Python 3.10 or newer.
2. Run `Start_Table_Editor.bat`. The launcher installs `pymem` if needed.
3. Start Warcraft II Remastered and enter the game.
4. In the editor click **Auto Attach**.
5. The editor refuses an executable fingerprint other than the supported 1.0.2.2818 x86 build.

## Editing a table

1. Choose a table in the left sidebar.
2. Click a row.
3. Enter a numeric value or choose a named value from the drop-down when one is available.
4. Stage the value. Staging does not change Warcraft yet.
5. Click **Apply Table** to write only that table, or **Apply All Pending** for every staged table.
6. The editor reads the bytes back immediately and reports a verification failure if Warcraft does not contain the requested value.

## Presets

Use **Export Preset** to save the effective table values to JSON. Use **Import Preset** to stage differences from a saved preset. Importing a preset still does not touch the game until you click Apply.

## Restore

When you attach, the editor captures the original live table values. Use **Restore Table Snapshot** or **Restore All Snapshots** to put those values back. Restarting Warcraft also clears all runtime edits.

## Safety / multiplayer

Use this for offline/private testing. Table changes can affect simulation behavior. Multiplayer safety has not been verified, so this project is not marked `M`.

## Source

The complete editable Python implementation is in `src/war2_remastered_table_editor.py`. No compiled EXE is stored in `main`.
