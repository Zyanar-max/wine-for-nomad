# Wine for Nomad Sculpt

Fixes for running the Windows version of **Nomad Sculpt** on Linux in **Bottles**, with a pen tablet. Install Nomad in a bottle, run one script, and you're done.

> **I made this for my own setup and I'm sharing it as is. There's no support, so please don't contact me about it.** If it doesn't work on your system, `sh install.sh --uninstall` puts everything back. Use it at your own risk.
>
> Vibe-coded with [Claude](https://claude.com/claude-code) (Claude Code): the Wine bugs were tracked down and patched in conversation with Claude. The file dialog comes from [Wine for ZBrush](https://github.com/Zyanar-max/wine-for-zbrush).

[Magyar leírás: README_HU.md](README_HU.md)

| # | Problem | Fix |
|---|---------|-----|
| 1 | The pen works for a moment, then Nomad gets nothing from it (no pressure) | Wine patch (winex11) |
| 2 | With more than one monitor, Nomad's brush is offset from the pen | Wine patch (wintab32): Wintab reports the whole desktop, not only the main monitor |
| 3 | Nomad doesn't use Wintab | Sets `use_wintab` in Nomad's settings |
| 4 | Ugly Windows-style Open/Import/Save/Export windows | Uses your desktop's own file chooser (GNOME/KDE) |
| 5 | The interface is tiny on a 4K screen | Optional: sets Nomad's interface scale (`gui_scale`) |
| 6 | No menu entry, `.nom` files show a blank page, a second Nomad freezes Bottles | Menu entry with Nomad's icon, `.nom` file icons, double-click opens them in Nomad, never a second Nomad |

## Requirements

- [Bottles](https://usebottles.com) (Flatpak or native)
- Runner **kron4ek-11.20-staging** installed in Bottles (*Preferences → Runners*).
  Use this one: on the soda runners, Nomad crashes on every mouse/pen event (missing `GetPointerInfoHistory`) and the login screen can't be used.
- Nomad Sculpt for Windows installed in a bottle (tested: Nomad 2.13, environment *Application*)
- An X11 desktop or XWayland. Tested on Rocky Linux 9 with GNOME on X11, Xencelabs tablet, two 4K monitors.

## Install

1. Create a bottle (*Application*), switch its runner to **kron4ek-11.20-staging**, and install Nomad (`Nomad-x.y.exe`) in it.
2. Start Nomad once, log in, then close it. (This creates Nomad's settings files.)
3. Close Bottles and run:
   ```sh
   sh install.sh
   ```
   The script finds the bottle that has `Nomad.exe` in it. If you have more than one, use `sh install.sh --bottle NAME`.
   It asks for the interface scale. Press Enter to leave it, or give e.g. `--gui-scale 1.5`.
4. Start Nomad from the app menu (*Nomad Sculpt*).

**Don't change the bottle's runner in Bottles afterwards.** If you do, fixes 1–2 are lost; just run the script again.

**After a Bottles update**, Bottles sometimes resets the bottle (the old Wine file dialog comes back, or the pen breaks). Just run the script again (`sh install.sh --bottle NAME --yes`). You can run it as many times as you like.

## Good to know

- **Start Nomad from the app menu** (*Nomad Sculpt*), not twice from Bottles. Bottles (Flatpak) runs every launch in its own sandbox, and two Nomads on the same bottle break each other. The launcher (`~/.local/bin/wine-for-nomad`) only shows a notification if Nomad is already running, and it closes a dead Bottles sandbox of the bottle if one was left behind. Starting Nomad with the ▶ button in the Bottles window isn't protected.
- Double-clicking a `.nom` file opens it in Nomad. If Nomad is already running, you get a notification instead: open the file from Nomad.
- Leave your tablet mapped to the **whole desktop** (all monitors), which is the default on Linux. Nomad maps the pen to the whole desktop, like the Windows tablet drivers do.
- To open files from other disks, add them in Bottles: *bottle → Settings → Drives*.
- Don't turn on Wine debug logging (`WINEDEBUG=+wintab32`) for normal use: it makes the pen lag.

## Undo

```sh
sh install.sh --uninstall
```

This puts back the old runner, the original `wintab32.dll`, the Wine file dialogs, and Nomad's `use_wintab` / `gui_scale` values, and removes the menu entry, the launcher and the file icons. The runner folder `kron4ek-11.20-staging-nomad` can then be deleted.

## What exactly is patched

The script makes a copy of the runner (`kron4ek-11.20-staging-nomad`, hard links, so it takes no extra space) and changes two files in it. It checks their SHA-256 first, so it never patches a different build.

1. **winex11.so**, `update_device_mapping`: it runs every time X switches between the mouse and the pen, and its `XCloseDevice` deletes the XInput event selections Wintab made for the pen. After that, Wintab gets no more pen events. The patch skips the `XCloseDevice` (6 bytes). This is the same bug as in Wine for ZBrush.
2. **wintab32.dll**, `WTInfoA`/`WTInfoW`: the default context had `lcSysOrg = 0,0` and `lcSysExt` = the size of the **primary** monitor. Nomad uses these values to turn tablet coordinates into screen coordinates, so with two monitors the brush ended up in the wrong place. The patch fills them in with the virtual screen (`SM_XVIRTUALSCREEN`, `SM_YVIRTUALSCREEN`, `SM_CXVIRTUALSCREEN`, `SM_CYVIRTUALSCREEN`). The code is in two small routines in the unused end of the `.text` section.

The file dialog (`zbfiledlg.dll` + `zbfiledlg.py`) is the same as in Wine for ZBrush; its source is in `src/`.

## License

MIT, see [LICENSE](LICENSE).
