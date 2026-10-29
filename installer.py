#!/usr/bin/env python3
"""Wine for Nomad Sculpt - fixes for Nomad Sculpt (Windows version) running in a Bottles bottle.

  1. Pen stops after the first touch (winex11.so)
  2. Pen cursor is offset on a multi-monitor desktop (wintab32.dll)
  3. Nomad uses Wintab for the pen (Nomad's config.json)
  4. Native GNOME/KDE file dialogs for Open/Import/Save/Export (zbfiledlg, from Wine for ZBrush)
  5. Optional: bigger interface (Nomad's gui_scale, e.g. for 4K)
  6. Menu entry with Nomad's icon, .nom file icons + double-click, never a second Nomad

Usage: sh install.sh [--bottle NAME] [--gui-scale N] [--uninstall] [--yes]
"""
import argparse, base64, glob, hashlib, json, os, re, shutil, struct, subprocess, sys, zlib

BASE_RUNNER = 'kron4ek-11.20-staging'
FIX_RUNNER = 'kron4ek-11.20-staging-nomad'
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = '.wine-for-nomad.json'
WINTAB = 'lib/wine/x86_64-windows/wintab32.dll'

# (file in runner, offset, original bytes, patched bytes)
PATCHES = [
    # 1: no XCloseDevice in update_device_mapping (it deletes the pen's XInput event selections)
    ('lib/wine/x86_64-unix/winex11.so', 0x2cc0e, 'ff25a4422500', 'c39090909090'),
    # 2: the default context reports the whole virtual screen (all monitors), not only the primary one.
    #    WTInfoA/WTInfoW jump to two small routines in the unused end of .text that fill
    #    lcSysOrgX/Y + lcSysExtX/Y with GetSystemMetrics(SM_X/Y/CX/CYVIRTUALSCREEN).
    (WINTAB, 0x190, 'b06d', '0070'),                       # .text VirtualSize 0x6db0 -> 0x7000
    (WINTAB, 0x3da0, '488b1d49e5', 'e95b400000'),          # WTInfoA -> 0x7e00
    (WINTAB, 0x4170, '488b1d79e1', 'e90b3d0000'),          # WTInfoW -> 0x7e80
    (WINTAB, 0x7e00, '00' * 68,
     '488b1de9a40000b94c000000ffd38984241c010000b94d000000ffd389842420010000'
     'b94e000000ffd389842424010000b94f000000ffd389842428010000e953bdffff'),
    (WINTAB, 0x7e80, '00' * 68,
     '488b1d69a40000b94c000000ffd38984240c010000b94d000000ffd389842410010000'
     'b94e000000ffd389842414010000b94f000000ffd389842418010000e963c1ffff'),
]
ORIGINAL_SHA256 = {
    'lib/wine/x86_64-unix/winex11.so': 'bb99e20fd09ad2726a6e6c3aa1c6c83aed8e3033c8792928dbce49686bd8b7a1',
    WINTAB: '83384feb87da77daf16e17ad0647831ca88676ad39f22a39f5c0bc48d1171eb9',
}
CLSIDS = ('DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7',   # FileOpenDialog
          'C0B4E2F3-BA21-4773-8DBA-335EC946EB8B')   # FileSaveDialog
NOMAD_DIR = ('drive_c', 'Program Files', 'Nomad Sculpt')

ASSUME_YES = False


def say(msg=''):
    print(msg, flush=True)


def ok(msg):
    say('  [ok] ' + msg)


def warn(msg):
    say('  [!]  ' + msg)


def die(msg):
    say('\nERROR: ' + msg)
    sys.exit(1)


def ask(question, default=False):
    if ASSUME_YES:
        return True
    hint = '[Y/n]' if default else '[y/N]'
    ans = input(f'{question} {hint} ').strip().lower()
    return default if not ans else ans in ('y', 'yes', 'i', 'igen')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def find_bottles_root():
    for p in ('~/.var/app/com.usebottles.bottles/data/bottles', '~/.local/share/bottles'):
        p = os.path.expanduser(p)
        if os.path.isdir(os.path.join(p, 'bottles')):
            return p
    die('Bottles was not found (neither Flatpak nor native).')


def find_nomad_bottles(root):
    bdir = os.path.join(root, 'bottles')
    return [n for n in sorted(os.listdir(bdir))
            if os.path.isfile(os.path.join(bdir, n, *NOMAD_DIR, 'Nomad.exe'))]


def wine_running():
    out = subprocess.run(['ps', '-eo', 'comm'], capture_output=True, text=True).stdout.split()
    return any(c == 'wineserver' or c.lower() == 'nomad.exe' for c in out)


def read_yaml_value(path, key):
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.startswith(key + ':'):
                return line.split(':', 1)[1].strip().strip("'\"")
    return None


def set_yaml_value(path, key, value):
    with open(path, encoding='utf-8') as f:
        text = f.read()
    text, n = re.subn(r'^%s:.*$' % re.escape(key), '%s: %s' % (key, value), text, count=1, flags=re.M)
    if not n:
        die(f'"{key}" not found in {path}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


# ---- runner ---------------------------------------------------------------

def build_runner(root):
    src = os.path.join(root, 'runners', BASE_RUNNER)
    dst = os.path.join(root, 'runners', FIX_RUNNER)
    if not os.path.isdir(src):
        die(f'Runner {BASE_RUNNER} is not installed. In Bottles: Preferences -> Runners -> install {BASE_RUNNER}.')
    for rel, digest in ORIGINAL_SHA256.items():
        if sha256(os.path.join(src, rel)) != digest:
            die(f'{BASE_RUNNER}/{rel} is not the version these patches were made for. Nothing was changed.')
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    # hard links: the copy costs no disk space; patched files become real copies below
    shutil.copytree(src, dst, symlinks=True, copy_function=os.link)
    for rel in ORIGINAL_SHA256:
        p = os.path.join(dst, rel)
        data = open(p, 'rb').read()
        os.unlink(p)
        with open(p, 'wb') as f:
            f.write(data)
        shutil.copymode(os.path.join(src, rel), p)
    for rel, off, old, new in PATCHES:
        p = os.path.join(dst, rel)
        with open(p, 'r+b') as f:
            f.seek(off)
            if f.read(len(old) // 2) != bytes.fromhex(old):
                die(f'unexpected bytes in {rel} at {off:#x}')
            f.seek(off)
            f.write(bytes.fromhex(new))
    ok(f'runner {FIX_RUNNER} created (patched copy of {BASE_RUNNER})')
    return dst


# ---- registry -------------------------------------------------------------

def set_inproc_server(system_reg, dll):
    with open(system_reg, encoding='utf-8', errors='surrogateescape') as f:
        text = f.read()
    for clsid in CLSIDS:
        pat = re.compile(r'(\[Software\\\\Classes\\\\CLSID\\\\\{%s\}\\\\InprocServer32\][^\[]*?@=")[^"]*(")' % clsid,
                         re.I)
        text, n = pat.subn(lambda m: m.group(1) + 'C:\\\\windows\\\\system32\\\\' + dll + m.group(2), text)
        if not n:
            die(f'file dialog class {clsid} not found in system.reg')
    with open(system_reg, 'w', encoding='utf-8', errors='surrogateescape') as f:
        f.write(text)


# ---- Nomad settings -------------------------------------------------------

def nomad_data(bdir):
    users = os.path.join(bdir, 'drive_c', 'users')
    for u in sorted(os.listdir(users)) if os.path.isdir(users) else ():
        d = os.path.join(users, u, 'AppData', 'Local', 'Nomad Sculpt')
        if os.path.isfile(os.path.join(d, 'config.json')):
            return d
    return None


def edit_json(path, key, value):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    old = data.get(key)
    if not os.path.exists(path + '.bak-wine-for-nomad'):
        shutil.copy2(path, path + '.bak-wine-for-nomad')
    data[key] = value
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    return old


# ---- desktop integration (menu entry, icons, double-click) --------------------

TAG = 'wine-for-nomad'
MIME = 'application/x-nomad-sculpt'
DATA = os.path.expanduser(os.environ.get('XDG_DATA_HOME', '~/.local/share'))
LAUNCHER = os.path.expanduser('~/.local/bin/' + TAG)

def exe_icon_png(path):
    """Largest icon of a Windows .exe as PNG bytes (or None)."""
    d = open(path, 'rb').read()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    opt = pe + 24
    magic = struct.unpack_from('<H', d, opt)[0]
    rsrc_rva = struct.unpack_from('<I', d, opt + (112 if magic == 0x20b else 96) + 2 * 8)[0]
    sec = opt + struct.unpack_from('<H', d, pe + 20)[0]
    for i in range(nsec):
        va, size, raw = struct.unpack_from('<III', d, sec + i * 40 + 12)
        if va <= rsrc_rva < va + max(size, 1):
            base, delta = raw + rsrc_rva - va, va - raw
            break
    else:
        return None

    def entries(off):
        named, ids = struct.unpack_from('<HH', d, base + off + 12)
        for j in range(named + ids):
            name, child = struct.unpack_from('<II', d, base + off + 16 + j * 8)
            yield name, child

    def leaf(child):
        while child & 0x80000000:          # descend to the first language
            child = next(entries(child & 0x7fffffff))[1]
        rva, size = struct.unpack_from('<II', d, base + child)
        return d[rva - delta:rva - delta + size]

    types = dict(entries(0))
    if 14 not in types or 3 not in types:
        return None
    icons = {n: c for n, c in entries(types[3] & 0x7fffffff)}
    group = leaf(next(entries(types[14] & 0x7fffffff))[1])
    best = None
    for j in range(struct.unpack_from('<H', group, 4)[0]):
        w, h, _, _, _, bpp, size, nid = struct.unpack_from('<BBBBHHIH', group, 6 + j * 14)
        key = ((w or 256), bpp)
        if nid in icons and (best is None or key > best[0]):
            best = (key, nid)
    if not best:
        return None
    img = leaf(icons[best[1]])
    if img[:4] == b'\x89PNG':
        return img
    w = best[0][0]
    if struct.unpack_from('<H', img, 14)[0] != 32:
        return None
    px = img[struct.unpack_from('<I', img, 0)[0]:]
    rows = []
    for y in range(w):
        src = px[(w - 1 - y) * w * 4:(w - y) * w * 4]
        row = bytearray(src)
        row[0::4], row[2::4] = src[2::4], src[0::4]
        rows.append(b'\0' + bytes(row))
    chunk = lambda t, b: struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, w, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b''.join(rows), 9)) + chunk(b'IEND', b''))



def find_program(yml):
    """Name of the Nomad program entry in bottle.yml."""
    text = open(yml, encoding='utf-8').read()
    for block in re.split(r'\n    [0-9a-f-]{36}:\n', text):
        if re.search(r'executable: .*\bNomad\.exe\s*$', block, re.I | re.M):
            m = re.search(r'^        name: (.+)$', block, re.M)
            if m:
                return m.group(1).strip().strip("'\"")
    return None


def icon_theme_dirs():
    """mimetypes folders of the active icon theme if it lives in the user's home.
    Themes with a generic file icon (e.g. Papirus) win over hicolor otherwise."""
    try:
        theme = subprocess.run(['gsettings', 'get', 'org.gnome.desktop.interface', 'icon-theme'],
                               capture_output=True, text=True).stdout.strip().strip("'")
    except OSError:
        return None, []
    root = os.path.join(DATA, 'icons', theme)
    if not theme or theme == 'hicolor' or not os.path.isdir(root):
        return None, []
    return root, glob.glob(os.path.join(root, '*', 'mimetypes'))


def menu_entries(bottle, program):
    """Existing .desktop files (yours or Bottles') that start Nomad from this bottle."""
    apps = os.path.join(DATA, 'applications')
    found = []
    for f in sorted(os.listdir(apps)) if os.path.isdir(apps) else ():
        p = os.path.join(apps, f)
        if not f.endswith('.desktop') or f.startswith(TAG) or not os.path.isfile(p):
            continue
        m = re.search(r'^Exec=(.*)$', open(p, encoding='utf-8', errors='replace').read(), re.M)
        if not m:
            continue
        ex = m.group(1)
        if (re.search(r'(-b|--bottle)\s+["\']?%s["\']?(\s|$)' % re.escape(bottle), ex) and
                re.search(r'(-p|--program)\s+["\']?%s["\']?(\s|$)' % re.escape(program), ex)) or \
                ex.split()[0] == LAUNCHER:
            found.append(p)
    return found


def install_desktop(root, bottle, bdir, state):
    program = find_program(os.path.join(bdir, 'bottle.yml'))
    if not program:
        warn('no Nomad program entry in Bottles, skipped (add Nomad.exe as a program in Bottles, then run again)')
        return
    try:
        png = exe_icon_png(os.path.join(bdir, *NOMAD_DIR, 'Nomad.exe'))   # Nomad's own app icon
    except (OSError, struct.error, StopIteration):
        png = None
    size = struct.unpack_from('>I', png, 16)[0] if png else 256

    # launcher: files/wine-for-nomad-open.sh with this bottle's values filled in
    flatpak = '/.var/app/com.usebottles.bottles/' in root
    cli = 'flatpak run --command=bottles-cli com.usebottles.bottles' if flatpak else 'bottles-cli'
    os.makedirs(os.path.dirname(LAUNCHER), exist_ok=True)
    script = open(os.path.join(HERE, 'files', 'wine-for-nomad-open.sh')).read()
    for key, value in (('CLI', cli), ('BOTTLE', bottle), ('PROGRAM', program), ('PREFIX', bdir)):
        script = script.replace('@%s@' % key, value.replace("'", "'\\''"))
    with open(LAUNCHER, 'w') as f:
        f.write(script)
    os.chmod(LAUNCHER, 0o755)

    # icons: app icon + .nom file icon (hicolor PNG, plus SVG wrappers in a user-installed icon theme)
    theme_root, theme_dirs = icon_theme_dirs()
    if png:
        for sub, name in (('apps', TAG), ('mimetypes', MIME.replace('/', '-'))):
            d = os.path.join(DATA, 'icons', 'hicolor', f'{size}x{size}', sub)
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, name + '.png'), 'wb').write(png)
        b64 = base64.b64encode(png).decode()
        for d in theme_dirs:
            m = re.match(r'(\d+)x\d+', os.path.basename(os.path.dirname(d)))
            dim = int(m.group(1)) if m else 256
            open(os.path.join(d, MIME.replace('/', '-') + '.svg'), 'w').write(
                f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'width="{dim}" height="{dim}" viewBox="0 0 {size} {size}"><image width="{size}" height="{size}" '
                f'xlink:href="data:image/png;base64,{b64}"/></svg>\n')
        for t in filter(None, (os.path.join(DATA, 'icons', 'hicolor'), theme_root)):
            subprocess.run(['gtk-update-icon-cache', '-f', '-t', t], capture_output=True)
    icon = TAG if png else 'applications-graphics'

    # file type
    mime_dir = os.path.join(DATA, 'mime', 'packages')
    os.makedirs(mime_dir, exist_ok=True)
    with open(os.path.join(mime_dir, TAG + '.xml'), 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">\n'
                f'  <mime-type type="{MIME}">\n    <comment>Nomad Sculpt project</comment>\n'
                '    <glob pattern="*.nom" case-sensitive="false"/>\n  </mime-type>\n</mime-info>\n')
    subprocess.run(['update-mime-database', os.path.join(DATA, 'mime')], capture_output=True)

    # menu entry: keep the user's own entry (and its place in the dock), only route it through the
    # launcher; otherwise create one
    apps = os.path.join(DATA, 'applications')
    os.makedirs(apps, exist_ok=True)
    own = os.path.join(apps, TAG + '.desktop')
    existing = menu_entries(bottle, program)
    for p in existing:
        if not os.path.exists(p + '.bak-' + TAG):
            shutil.copy2(p, p + '.bak-' + TAG)
        state.setdefault('menu', [])
        if p not in state['menu']:
            state['menu'].append(p)
        text = open(p, encoding='utf-8').read()
        text = re.sub(r'^Exec=.*$', 'Exec=' + LAUNCHER, text, count=1, flags=re.M)
        open(p, 'w', encoding='utf-8').write(text)
        ok('menu entry %s now starts Nomad through the launcher' % os.path.basename(p))
    if existing:
        if os.path.exists(own):
            os.unlink(own)
    else:
        with open(own, 'w') as f:
            f.write('[Desktop Entry]\nType=Application\nName=Nomad Sculpt\n'
                    f'Comment=Nomad Sculpt ({bottle} bottle)\nExec={LAUNCHER}\n'
                    f'Icon={icon}\nCategories=Graphics;3DGraphics;\nStartupNotify=true\n'
                    'StartupWMClass=nomad.exe\n')
        ok('menu entry "Nomad Sculpt" created (with Nomad\'s own icon)')

    # double-click handler (hidden from the menu)
    with open(os.path.join(apps, TAG + '-open.desktop'), 'w') as f:
        f.write('[Desktop Entry]\nType=Application\nName=Nomad Sculpt\n'
                f'Comment=Open in Nomad Sculpt ({bottle} bottle)\nExec={LAUNCHER} %f\n'
                f'Icon={icon}\nNoDisplay=true\nStartupWMClass=nomad.exe\nMimeType={MIME};\n')
    subprocess.run(['update-desktop-database', apps], capture_output=True)
    subprocess.run(['xdg-mime', 'default', TAG + '-open.desktop', MIME], capture_output=True)
    ok('.nom files get Nomad\'s icon, double-click opens them in Nomad')
    ok('a second Nomad can\'t be started by accident (you get a notification instead)')
    say('       Files must be on a drive or folder the bottle can see.')


def uninstall_desktop(state):
    for p in state.get('menu', []):
        if os.path.exists(p + '.bak-' + TAG):
            shutil.move(p + '.bak-' + TAG, p)
            ok('menu entry %s restored' % os.path.basename(p))
    paths = [os.path.join(DATA, 'mime', 'packages', TAG + '.xml'),
             os.path.join(DATA, 'applications', TAG + '.desktop'),
             os.path.join(DATA, 'applications', TAG + '-open.desktop'), LAUNCHER]
    paths += glob.glob(os.path.join(DATA, 'icons', '*', '*', 'mimetypes', MIME.replace('/', '-') + '.*'))
    paths += glob.glob(os.path.join(DATA, 'icons', 'hicolor', '*', 'apps', TAG + '.png'))
    for p in paths:
        if os.path.exists(p):
            os.unlink(p)
    subprocess.run(['update-mime-database', os.path.join(DATA, 'mime')], capture_output=True)
    subprocess.run(['update-desktop-database', os.path.join(DATA, 'applications')], capture_output=True)
    ok('menu entry, launcher, file icons and double-click handler removed')


# ---- install / uninstall --------------------------------------------------

def install(root, bottle, gui_scale):
    bdir = os.path.join(root, 'bottles', bottle)
    yml = os.path.join(bdir, 'bottle.yml')
    sys32 = os.path.join(bdir, 'drive_c', 'windows', 'system32')
    state_path = os.path.join(bdir, STATE)
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}

    say('\n1-2. Pen (patched Wine runner)')
    runner = build_runner(root)
    old_runner = read_yaml_value(yml, 'Runner')
    if old_runner != FIX_RUNNER:
        state.setdefault('runner', old_runner)
    shutil.copy2(yml, yml + '.bak-wine-for-nomad')
    set_yaml_value(yml, 'Runner', FIX_RUNNER)
    ok(f'bottle "{bottle}" now uses {FIX_RUNNER} (was {old_runner})')
    wt = os.path.join(sys32, 'wintab32.dll')
    if os.path.exists(wt) and not os.path.exists(wt + '.orig'):
        shutil.copy2(wt, wt + '.orig')
    shutil.copy2(os.path.join(runner, WINTAB), wt)
    ok('patched wintab32.dll copied into the bottle')

    say('\n3. Nomad uses Wintab for the pen')
    data = nomad_data(bdir)
    if not data:
        warn('Nomad\'s settings were not found. Start Nomad once, close it, then run this script again.')
    else:
        old = edit_json(os.path.join(data, 'config.json'), 'use_wintab', 1)
        state.setdefault('use_wintab', old)
        ok('use_wintab = 1 (was %s)' % old)

    say('\n4. Native file dialogs')
    for f in ('zbfiledlg.dll', 'zbfiledlg.py'):
        shutil.copy2(os.path.join(HERE, 'files', f), os.path.join(sys32, f))
    system_reg = os.path.join(bdir, 'system.reg')
    if not os.path.exists(system_reg + '.bak-wine-for-nomad'):
        shutil.copy2(system_reg, system_reg + '.bak-wine-for-nomad')
    set_inproc_server(system_reg, 'zbfiledlg.dll')
    ok('Open/Import/Save/Export now use the desktop file chooser')

    say('\n5. Optional: interface size')
    settings = os.path.join(data, 'data', 'settings.json') if data else None
    if not settings or not os.path.isfile(settings):
        warn('skipped (settings.json not found yet)')
    else:
        if gui_scale is None and not ASSUME_YES:
            ans = input('  Interface scale (1 = Nomad default, 1.5 is good for 4K, Enter = leave as it is): ').strip()
            gui_scale = float(ans.replace(',', '.')) if ans else None
        if gui_scale is None:
            ok('left as it is')
        else:
            old = edit_json(settings, 'gui_scale', gui_scale)
            state.setdefault('gui_scale', old)
            ok(f'gui_scale = {gui_scale} (was {old if old is not None else "default"})')

    say('\n6. Menu entry, file icons and double-click')
    install_desktop(root, bottle, bdir, state)

    with open(state_path, 'w') as f:
        json.dump(state, f)
    say('\nDone. Start Nomad from the app menu (or from Bottles).')
    say('Do not change the bottle\'s runner in Bottles, or fixes 1-2 are lost (run this script again).')


def uninstall(root, bottle):
    bdir = os.path.join(root, 'bottles', bottle)
    yml = os.path.join(bdir, 'bottle.yml')
    sys32 = os.path.join(bdir, 'drive_c', 'windows', 'system32')
    state_path = os.path.join(bdir, STATE)
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}

    if read_yaml_value(yml, 'Runner') == FIX_RUNNER:
        set_yaml_value(yml, 'Runner', state.get('runner') or BASE_RUNNER)
        ok('runner restored to ' + (state.get('runner') or BASE_RUNNER))
    wt = os.path.join(sys32, 'wintab32.dll')
    if os.path.exists(wt + '.orig'):
        shutil.move(wt + '.orig', wt)
        ok('original wintab32.dll restored')
    set_inproc_server(os.path.join(bdir, 'system.reg'), 'comdlg32.dll')
    for f in ('zbfiledlg.dll', 'zbfiledlg.py'):
        p = os.path.join(sys32, f)
        if os.path.exists(p):
            os.unlink(p)
    ok('Wine file dialogs restored')
    data = nomad_data(bdir)
    if data:
        for key, rel in (('use_wintab', 'config.json'), ('gui_scale', os.path.join('data', 'settings.json'))):
            if key in state:
                p = os.path.join(data, rel)
                with open(p, encoding='utf-8') as f:
                    d = json.load(f)
                if state[key] is None:
                    d.pop(key, None)
                else:
                    d[key] = state[key]
                with open(p, 'w', encoding='utf-8') as f:
                    json.dump(d, f, indent=4)
                ok(f'{key} restored')
    uninstall_desktop(state)
    if os.path.exists(state_path):
        os.unlink(state_path)
    say(f'\nDone. The runner folder {FIX_RUNNER} can be deleted in Bottles if no other bottle uses it.')


def main():
    global ASSUME_YES
    ap = argparse.ArgumentParser(description='Wine for Nomad Sculpt fixes for Bottles')
    ap.add_argument('--bottle', help='bottle name (default: the one with Nomad.exe)')
    ap.add_argument('--gui-scale', type=float, help='Nomad interface scale, e.g. 1.5')
    ap.add_argument('--uninstall', action='store_true')
    ap.add_argument('--yes', action='store_true', help='answer yes to questions')
    a = ap.parse_args()
    ASSUME_YES = a.yes

    say('Wine for Nomad Sculpt')
    root = find_bottles_root()
    bottle = a.bottle
    if not bottle:
        found = find_nomad_bottles(root)
        if not found:
            die('no bottle with Nomad.exe found. Install Nomad Sculpt in a Bottles bottle first, or use --bottle NAME.')
        if len(found) > 1:
            die('several Nomad bottles found: %s. Choose one with --bottle NAME.' % ', '.join(found))
        bottle = found[0]
    if not os.path.isfile(os.path.join(root, 'bottles', bottle, 'bottle.yml')):
        die(f'bottle "{bottle}" not found in {root}/bottles')
    say(f'Bottle: {bottle}  ({root})')

    if wine_running():
        die('a Windows program / Wine is still running. Close Nomad and Bottles, then run this again.')

    if a.uninstall:
        uninstall(root, bottle)
    else:
        install(root, bottle, a.gui_scale)


if __name__ == '__main__':
    main()
