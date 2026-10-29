# Wine for Nomad Sculpt

Javítások a **Nomad Sculpt** Windows-os változatához, ha Linuxon **Bottles**-ben, rajztáblával használod. Telepítsd a Nomadot egy bottle-be, futtass le egy scriptet, és kész.

> **A saját gépemre készítettem, és úgy osztom meg, ahogy van. Támogatás nincs, kérlek, ne keress meg miatta.** Ha nálad nem működik, a `sh install.sh --uninstall` mindent visszaállít. Mindenki a saját felelősségére használja.
>
> Vibe-coded with [Claude](https://claude.com/claude-code) (Claude Code): a Wine-hibákat Claude-dal közösen kerestük meg és javítottuk ki. A fájlpárbeszéd a [Wine for ZBrush](https://github.com/Zyanar-max/wine-for-zbrush) csomagból jön.

[English: README.md](README.md)

| # | Hiba | Javítás |
|---|------|---------|
| 1 | A toll egy pillanatig működik, aztán a Nomad semmit nem kap tőle (nincs nyomásérzékenység) | Wine-javítás (winex11) |
| 2 | Több monitornál a Nomad ecsetje el van csúszva a tollhoz képest | Wine-javítás (wintab32): a Wintab az egész asztalt jelenti, nem csak a fő monitort |
| 3 | A Nomad nem a Wintabot használja | Bekapcsolja a `use_wintab`-ot a Nomad beállításaiban |
| 4 | Csúnya, Windows-os Megnyitás/Importálás/Mentés/Exportálás ablakok | A saját asztalod (GNOME/KDE) fájlválasztója jön fel |
| 5 | 4K monitoron apró a felület | Választható: beállítja a Nomad felületméretét (`gui_scale`) |
| 6 | Nincs menübejegyzés, a `.nom` fájlok üres lapként látszanak, a második Nomad lefagyasztja a Bottlest | Menübejegyzés a Nomad ikonjával, `.nom` fájlikonok, dupla kattintásra megnyílnak a Nomadban, sosem indul második Nomad |

## Ami kell

- [Bottles](https://usebottles.com) (Flatpak vagy natív)
- A Bottlesben telepített **kron4ek-11.20-staging** runner (*Beállítások → Runnerek*).
  Ezt használd: a soda runnereken a Nomad minden egér/toll mozdulatnál hibára fut (hiányzó `GetPointerInfoHistory`), és a bejelentkező képernyő használhatatlan.
- A Nomad Sculpt Windows-os változata egy bottle-be telepítve (kipróbálva: Nomad 2.13, *Application* környezet)
- X11 asztal vagy XWayland. Kipróbálva: Rocky Linux 9, GNOME X11-en, Xencelabs tábla, két 4K monitor.

## Telepítés

1. Csinálj egy bottle-t (*Application*), állítsd a runnerét **kron4ek-11.20-staging**-re, és telepítsd bele a Nomadot (`Nomad-x.y.exe`).
2. Indítsd el egyszer a Nomadot, jelentkezz be, aztán zárd be. (Ekkor jönnek létre a Nomad beállításfájljai.)
3. Zárd be a Bottlest, és futtasd:
   ```sh
   sh install.sh
   ```
   A script megkeresi azt a bottle-t, amelyikben a `Nomad.exe` van. Ha több ilyen van: `sh install.sh --bottle NÉV`.
   Megkérdezi a felületméretet. Enterrel marad, ahogy van, vagy add meg pl. így: `--gui-scale 1.5`.
4. Indítsd a Nomadot az alkalmazásmenüből (*Nomad Sculpt*).

**Utána ne állítsd át a bottle runnerét a Bottlesben.** Ha mégis, az 1–2. javítás elveszik; ilyenkor csak futtasd újra a scriptet.

**Bottles-frissítés után** a Bottles néha visszaállítja a bottle-t (visszajön a régi Wine-os fájlablak, vagy elromlik a toll). Ilyenkor futtasd újra a scriptet (`sh install.sh --bottle NÉV --yes`). Akárhányszor lefuttathatod.

## Jó tudni

- **A Nomadot az alkalmazásmenüből indítsd** (*Nomad Sculpt*), ne kétszer a Bottlesből. A Bottles (Flatpak) minden indítást külön sandboxban futtat, és ugyanazon a bottle-ön két Nomad tönkreteszi egymást. Az indító (`~/.local/bin/wine-for-nomad`) csak értesítést dob, ha a Nomad már fut, és ha maradt egy halott Bottles-sandbox a bottle-ből, azt bezárja. A Bottles ablakában a ▶ gombbal indított Nomad nincs védve.
- Egy `.nom` fájlra duplán kattintva megnyílik a Nomadban. Ha a Nomad már fut, értesítést kapsz helyette: ilyenkor a Nomadból nyisd meg.
- A táblát hagyd az **egész asztalra** (minden monitorra) leképezve, ez az alapértelmezés Linuxon. A Nomad a tollat az egész asztalra képezi le, ahogy a Windows-os tábladriverek is.
- Ha más lemezekről is akarsz fájlokat megnyitni, add hozzá őket a Bottlesben: *bottle → Beállítások → Meghajtók*.
- Normál használatkor ne kapcsold be a Wine debug naplózást (`WINEDEBUG=+wintab32`), mert akadozni fog tőle a toll.

## Visszaállítás

```sh
sh install.sh --uninstall
```

Visszateszi a régi runnert, az eredeti `wintab32.dll`-t, a Wine fájlablakait és a Nomad `use_wintab` / `gui_scale` értékeit, és eltávolítja a menübejegyzést, az indítót és a fájlikonokat. Utána a `kron4ek-11.20-staging-nomad` runner mappája törölhető.

## Mit javít pontosan

A script lemásolja a runnert (`kron4ek-11.20-staging-nomad`, hardlinkekkel, így nem foglal plusz helyet), és két fájlt módosít benne. Előtte ellenőrzi az SHA-256-jukat, így más buildet sosem javít.

1. **winex11.so**, `update_device_mapping`: minden egér↔toll váltáskor lefut, és az `XCloseDevice` hívása törli azokat az XInput eseményfeliratkozásokat, amelyeket a Wintab a tollra tett. Utána a Wintab nem kap több tolleseményt. A javítás kihagyja az `XCloseDevice`-t (6 bájt). Ugyanez a hiba volt a Wine for ZBrushban is.
2. **wintab32.dll**, `WTInfoA`/`WTInfoW`: az alapértelmezett kontextusban `lcSysOrg = 0,0` volt, az `lcSysExt` pedig a **fő** monitor mérete. A Nomad ezekből számolja ki a tábla koordinátáiból a képernyő-koordinátákat, ezért két monitornál rossz helyre került az ecset. A javítás a virtuális képernyő adatait írja be (`SM_XVIRTUALSCREEN`, `SM_YVIRTUALSCREEN`, `SM_CXVIRTUALSCREEN`, `SM_CYVIRTUALSCREEN`). A kód két kis rutinban van, a `.text` szakasz nem használt végén.

A fájlpárbeszéd (`zbfiledlg.dll` + `zbfiledlg.py`) ugyanaz, mint a Wine for ZBrushban; a forrása az `src/` mappában van.

## Licenc

MIT, lásd: [LICENSE](LICENSE).
