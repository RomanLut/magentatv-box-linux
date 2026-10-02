#!/usr/bin/env python3
"""Make RetroArch's own menu see what the retro-run launchers use
(/usr/local/bin/{nes,snes,gb,gba,megadrive,pce,psx,n64,psp,doom,wolf3d,quake2,
scummvm,rick}, installed with the games in START-HERE §4): the cores built for the
box in /usr/local/lib/libretro (Genesis Plus GX, PCSX ReARMed, Mupen64Plus-Next,
PPSSPP, PrBoom, ECWolf, vitaQuake 2, ScummVM, XRick),
the BIOS files in /DATA/Games/bios, and the games in /DATA/Games/<system>.

 - ~/.config/retroarch/cores: links to every core, Debian's and the built ones
 - ~/.config/retroarch/retroarch.cfg: core/info/BIOS/playlist paths plus the
   launchers' settings (/usr/local/share/mrg5-games/retroarch-mrg5.cfg), so a
   game started from the menu runs as it does from a launcher
 - ~/.config/retroarch/playlists/<system>.lpl: one playlist per system whose
   core is installed
 - /DATA/Games/downloads: where RetroArch's Content Downloader saves; its game
   folders are listed with the systems they belong to
 - /DATA/Games/bios/scummvm: a link to ScummVM's themes and engine data in
   /usr/local/share/scummvm (the release empties /DATA)

RetroArch rewrites retroarch.cfg on exit: run this only while it is closed.
Idempotent; rerun after adding games.

usage: retroarch-menu-setup.py
"""
import json
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~/.config/retroarch")
CORES = os.path.join(HOME, "cores")
PLAYLISTS = os.path.join(HOME, "playlists")
CFG = os.path.join(HOME, "retroarch.cfg")
INFO = "/usr/share/libretro/info"
SYS = "/usr/lib/arm-linux-gnueabihf/libretro"
OWN = "/usr/local/lib/libretro"
GAMES = "/DATA/Games"
DOWNLOADS = GAMES + "/downloads"
SCUMMVM_DATA = "/usr/local/share/scummvm"
LAUNCHER_CFG = "/usr/local/share/mrg5-games/retroarch-mrg5.cfg"

# games folder(s), extensions, core (as the launchers choose it), playlist name
SYSTEMS = [
    (["nes"], {".nes"}, "nestopia", "Nintendo - Nintendo Entertainment System"),
    (["snes"], {".sfc", ".smc"}, "bsnes_mercury_performance",
     "Nintendo - Super Nintendo Entertainment System"),
    (["gb"], {".gb", ".gbc"}, "gambatte", "Nintendo - Game Boy"),
    (["gba"], {".gba"}, "mgba", "Nintendo - Game Boy Advance"),
    (["megadrive"], {".md", ".gen", ".smd", ".bin"}, "genesis_plus_gx",
     "Sega - Mega Drive - Genesis"),
    (["pce"], {".pce"}, "mednafen_pce_fast", "NEC - PC Engine - TurboGrafx 16"),
    (["ps1", "psx"], {".cue", ".chd", ".pbp"}, "pcsx_rearmed", "Sony - PlayStation"),
    # the GLES3 build: the GLES2 one hands the frontend a black frame (checks/53 §9 item 13)
    (["n64"], {".z64", ".n64", ".v64"}, "mupen64plus_next_gles3", "Nintendo - Nintendo 64"),
    # PPSSPP, built on the box (games-20260924/build-ppsspp.sh)
    (["psp"], {".iso", ".cso", ".pbp", ".chd"}, "ppsspp", "Sony - PlayStation Portable"),
    # ScummVM: one .scummvm file per game folder (RetroArch's content downloader writes it)
    (["scummvm", "downloads"], {".scummvm"}, "scummvm", "ScummVM"),
]

# games that are a whole folder (games-20260924/build-cores.sh): one entry per
# folder under /DATA/Games/<dir> and /DATA/Games/downloads, the file the core is started
# with, labelled by the folder
FOLDER_GAMES = [
    # prboom.wad is PrBoom's own data file, not a game
    ("doom", r"(?i)(?!prboom\.wad$).*\.(wad|iwad)$", "prboom", "DOOM"),
    ("wolf3d", r"(?i)vswap\.(wl1|wl6|sod|sdm|n3d)$", "ecwolf", "Wolfenstein 3D"),
    ("quake2", r"(?i)pak0\.pak$", "vitaquake2", "Quake II"),
    ("rick", r"(?i)data\.zip$", "xrick", "Rick Dangerous"),
]

if subprocess.run(["pgrep", "-x", "retroarch"], capture_output=True).returncode == 0:
    sys.exit("RetroArch is running; close it first (it rewrites its config on exit)")

os.makedirs(CORES, exist_ok=True)
os.makedirs(PLAYLISTS, exist_ok=True)
if not os.path.isdir(DOWNLOADS):
    os.makedirs(DOWNLOADS)
    os.chmod(DOWNLOADS, 0o777)   # like the other game folders: open to the share and admin
link = os.path.join(GAMES, "bios", "scummvm")
if os.path.isdir(SCUMMVM_DATA) and not os.path.lexists(link):
    os.symlink(SCUMMVM_DATA, link)

# 1. cores (and no links left to cores that are gone)
for f in os.listdir(CORES):
    if os.path.islink(os.path.join(CORES, f)) and not os.path.exists(os.path.join(CORES, f)):
        os.remove(os.path.join(CORES, f))
for d in (SYS, OWN):
    for f in sorted(os.listdir(d)):
        if f.endswith("_libretro.so"):
            link = os.path.join(CORES, f)
            if os.path.islink(link) or os.path.exists(link):
                os.remove(link)
            os.symlink(os.path.join(d, f), link)
print("cores:", ", ".join(sorted(f[:-12] for f in os.listdir(CORES) if f.endswith("_libretro.so"))))


def display_name(core):
    try:
        for line in open(os.path.join(INFO, core + "_libretro.info")):
            m = re.match(r'\s*display_name\s*=\s*"(.*)"', line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return core


# 2. config: the launchers' settings, then the paths
settings = {}
for line in open(LAUNCHER_CFG):
    m = re.match(r'\s*(\w+)\s*=\s*"(.*)"', line)
    if m and m.group(1) != "menu_driver":   # keep Debian's xmb (assets installed)
        settings[m.group(1)] = m.group(2)
settings.update({
    "libretro_directory": CORES,
    "libretro_info_path": INFO,
    "system_directory": GAMES + "/bios",
    "playlist_directory": PLAYLISTS,
    "rgui_browser_directory": GAMES,
    "core_assets_directory": DOWNLOADS,
})
lines = open(CFG).read().splitlines() if os.path.exists(CFG) else []
seen = set()
for i, line in enumerate(lines):
    m = re.match(r"\s*(\w+)\s*=", line)
    if m and m.group(1) in settings:
        lines[i] = '%s = "%s"' % (m.group(1), settings[m.group(1)])
        seen.add(m.group(1))
lines += ['%s = "%s"' % (k, v) for k, v in settings.items() if k not in seen]
with open(CFG, "w") as f:
    f.write("\n".join(lines) + "\n")
print("config:", CFG, "(%d settings)" % len(settings))

# 3. playlists
def found_files(dirs, exts):
    """(path, label) of every file with one of exts under the system folders"""
    for d in dirs:
        for root, _, files in os.walk(os.path.join(GAMES, d)):
            for f in sorted(files):
                base, ext = os.path.splitext(f)
                if ext.lower() in exts:
                    yield os.path.join(root, f), base


def found_folders(d, pattern):
    """(path, label) per game folder: the first file matching pattern, labelled by the folder"""
    for top in (os.path.join(GAMES, d), DOWNLOADS):
        for game in sorted(os.listdir(top)) if os.path.isdir(top) else []:
            for root, _, files in os.walk(os.path.join(top, game)):
                hits = sorted(f for f in files if re.fullmatch(pattern, f))
                if hits:
                    yield os.path.join(root, hits[0]), game
                    break


def write_playlist(core, name, found):
    core_path = os.path.join(CORES, core + "_libretro.so")
    items = [{"path": path, "label": label, "core_path": core_path,
              "core_name": display_name(core), "crc32": "DETECT", "db_name": name + ".lpl"}
             for path, label in found]
    lpl = os.path.join(PLAYLISTS, name + ".lpl")
    if not items or not os.path.exists(core_path):
        if os.path.exists(lpl):
            os.remove(lpl)
        return
    with open(lpl, "w") as f:
        json.dump({"version": "1.5", "default_core_path": core_path,
                   "default_core_name": display_name(core), "label_display_mode": 0,
                   "right_thumbnail_mode": 0, "left_thumbnail_mode": 0, "sort_mode": 0,
                   "items": items}, f, indent=2)
    print("playlist: %-45s %d game(s)" % (name, len(items)))


for dirs, exts, core, name in SYSTEMS:
    write_playlist(core, name, found_files(dirs, exts))
for d, pattern, core, name in FOLDER_GAMES:
    write_playlist(core, name, found_folders(d, pattern))
