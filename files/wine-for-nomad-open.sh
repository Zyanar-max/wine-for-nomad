#!/bin/sh
# Wine for Nomad Sculpt: starts Nomad from Bottles (optionally with a .nom file), but never a second one.
# Installed by install.sh with the @...@ values filled in.
#
# Bottles Flatpak runs every launch in its own sandbox with its own wineserver. A second launch on
# the same bottle can't see the first one, and the two break each other (Bottles freezes).

CLI='@CLI@'
BOTTLE='@BOTTLE@'
PROGRAM='@PROGRAM@'
PREFIX='@PREFIX@'

winpath() { printf 'Z:%s' "$(realpath -- "$1" | sed 's|/|\\|g')"; }

# Nomad itself, in this bottle
running() {
    for p in $(pgrep -x Nomad.exe); do
        tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep -qxF "WINEPREFIX=$PREFIX" && return 0
    done
    return 1
}

# Bottles is still starting it (a launch younger than 90 s; older leftovers don't count)
starting() {
    for b in $(pgrep -f -- "bottles-cli run -b $BOTTLE -p $PROGRAM"); do
        [ "$(ps -o etimes= -p "$b" 2>/dev/null | tr -d ' ')" -lt 90 ] 2>/dev/null && return 0
    done
    return 1
}

# Bottles Flatpak sometimes leaves a dead session behind: Wine's services (services.exe,
# winedevice.exe, ...) keep running in the old sandbox after its wineserver is gone, and the next
# start on the same bottle can hang without a window. Close such a sandbox, but only if it belongs
# to this bottle, its wineserver is gone, and no program and no Bottles window is left in it.
cleanup_stale() {
    case "$CLI" in flatpak*) ;; *) return 0 ;; esac
    for p in /proc/[0-9]*; do
        info="$p/root/.flatpak-info"
        grep -qxF 'name=com.usebottles.bottles' "$info" 2>/dev/null || continue
        inst=$(sed -n 's/^instance-id=//p' "$info" 2>/dev/null)
        [ -n "$inst" ] || continue
        if tr '\0' '\n' < "$p/environ" 2>/dev/null | grep -qxF "WINEPREFIX=$PREFIX"; then mine=1; else mine=0; fi
        case "$(cat "$p/comm" 2>/dev/null)" in
        services.exe|winedevice.exe|plugplay.exe|svchost.exe|rpcss.exe|lsass.exe|explorer.exe|conhost.exe|tabtip.exe|rundll32.exe)
            kind=service ;;
        bwrap|xdg-dbus-proxy|bottles-cli|start.exe|sh|bash)
            kind=other ;;
        *)  kind=busy ;;         # wineserver, a program, the Bottles window ...
        esac
        echo "$inst $kind $mine"
    done | awk '{ if ($2 == "busy") busy[$1] = 1; if ($2 == "service" && $3 == 1) left[$1] = 1 }
                END { for (i in left) if (!(i in busy)) print i }' |
    while read -r inst; do
        flatpak kill "$inst" 2>/dev/null && sleep 1
    done
    return 0
}

if running || starting; then
    # urgent, so GNOME shows it on top of a fullscreen window too
    if [ -n "$1" ]; then
        notify-send -u critical -i wine-for-nomad "Nomad Sculpt is already running" \
            "Open $(basename -- "$1") from Nomad (Files → Open). Only one Nomad can run at a time."
    else
        notify-send -u critical -i wine-for-nomad "Nomad Sculpt is already running" "Only one Nomad can run at a time."
    fi
    exit 0
fi

if [ -n "$1" ]; then
    # Bottles Flatpak only sees the folders it has access to. Without this check Nomad just
    # starts empty.
    case "$CLI" in
    flatpak*)
        app=${CLI##* }
        if ! flatpak run --command=test "$app" -r "$(realpath -- "$1")" 2>/dev/null; then
            notify-send -u critical -i wine-for-nomad "Nomad can't see this file" \
                "$(basename -- "$1") is in a folder Bottles has no access to. Move it to a drive or folder the bottle can see."
            exit 1
        fi
        ;;
    esac
    file=$(winpath "$1") || exit 1
    cleanup_stale
    exec $CLI run -b "$BOTTLE" -p "$PROGRAM" "$file"
fi
cleanup_stale
exec $CLI run -b "$BOTTLE" -p "$PROGRAM"
