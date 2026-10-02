#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Roman Lut
"""quake-shareware-setup (checks/41, "Quake"): install Quake's shareware data on first use.

The release images carry the Quakespasm engine but no Quake game data. When `quake` starts and
finds none, it runs this. It offers to download id Software's original shareware archive,
quake106.zip (Quake 1.06, episode 1), from mirrors of id's own "idstuff" file area (the sources
Debian's game-data-packager uses, plus the idgames archive), checks it against pinned SHA-256
sums, unpacks it, shows id's licence from inside the archive and installs the data and the
licence only when the licence is accepted:

    /usr/local/share/games/quake/id1/pak0.pak
    /usr/local/share/games/quake/slicnse.txt, licinfo.txt      (id's licence and its summary)
    /usr/local/share/games/quake/quakespasm.pak -> the engine's own file
    /usr/local/share/games/quake/INSTALLED                      (source, date, checksums)

Afterwards `quake` starts Quakespasm from there, offline. Cancelling, declining the licence or a
failure leaves nothing installed and nothing in the temporary folder.

    quake-shareware-setup.py [--gui | --tty]       default: --gui with a display, else --tty
    quake-shareware-setup.py --check               exit 0 if the data is installed

Exit status: 0 installed, 1 cancelled or declined, 2 failed. Needs root (it writes under
/usr/local). MRG5_QUAKE_DIR overrides the folder, MRG5_QUAKE_SOURCES (space-separated URLs) the
download sources; both for tests only.
"""
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile

DEST = os.environ.get("MRG5_QUAKE_DIR", "/usr/local/share/games/quake")
ENGINE_PAK = "/usr/share/games/quake/quakespasm.pak"

# quake106.zip as Debian's game-data-packager (73) knows it: quake.sha256sums, quake.groups
ZIP_NAME = "quake106.zip"
ZIP_SIZE = 9094045
ZIP_SHA256 = "ec6c9d34b1ae0252ac0066045b6611a7919c2a0d78a3a66d9387a8f597553239"
RES_NAME = "resource.1"                     # an LHA archive inside the zip
RES_SIZE = 9086574
RES_SHA256 = "c192c9c71bee41750dd7d14c99378766d61e077977b9d13d1a457b8d9eabe34a"
FILES = {                                   # what is taken from resource.1
    "id1/pak0.pak": (18689235, "35a9c55e5e5a284a159ad2a62e0e8def23d829561fe2f54eb402dbc0a9a946af"),
    "slicnse.txt": (10036, "070cdf6a6410adef8fb5f83a4e5ccdb9e2301d2e48d460bb3a67a0f5ba9d70a8"),
    "licinfo.txt": (9311, "8d654834d085c088d603fb6879a874799e8b4cc6ae9317bbf826afd83bc72e31"),
}
# mirrors of id Software's "idstuff" file area (ftp.idsoftware.com, now offline), in order:
# the idgames archive's own site, the mirror in Debian's game-data-packager
# (/etc/game-data-packager/idstuff-mirrors), an idgames mirror. Every file is checked against
# ZIP_SHA256, whichever source it comes from.
SOURCES = [
    "https://www.gamers.org/pub/idgames/idstuff/quake/quake106.zip",
    "ftp://ftp.fu-berlin.de/pc/msdos/games/idgames/idstuff/quake/quake106.zip",
    "https://youfailit.net/pub/idgames/idstuff/quake/quake106.zip",
]
if os.environ.get("MRG5_QUAKE_SOURCES"):
    SOURCES = os.environ["MRG5_QUAKE_SOURCES"].split()
TIMEOUT = 30                                # seconds without data before a source is given up

OFFER = ("Quake needs its game data, which is not part of this system.\n\n"
         "The free shareware version (the first episode) can be downloaded now, 9 MB. "
         "You will see id Software's licence before anything is installed.\n\n"
         "Afterwards Quake starts without an internet connection.")


class Cancelled(Exception):
    pass


class SetupError(Exception):
    pass


def installed(dest=DEST):
    return os.path.isfile(os.path.join(dest, "id1", "pak0.pak"))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def host(url):
    return url.split("/")[2] or url


def download(url, path, progress, cancel):
    """One source into path; progress(done, total); raises Cancelled, SetupError."""
    req = urllib.request.Request(url, headers={"User-Agent": "mrg5-quake-shareware-setup"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(path, "wb") as out:
            done = 0
            while True:
                if cancel.is_set():
                    raise Cancelled()
                block = r.read(64 * 1024)
                if not block:
                    break
                done += len(block)
                if done > ZIP_SIZE:
                    raise SetupError("%s: larger than the expected %d bytes" % (host(url), ZIP_SIZE))
                out.write(block)
                progress(done, ZIP_SIZE)
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise SetupError("%s: %s" % (host(url), reason))
    if os.path.getsize(path) != ZIP_SIZE:
        raise SetupError("%s: incomplete download (%d of %d bytes)"
                         % (host(url), os.path.getsize(path), ZIP_SIZE))
    if sha256(path) != ZIP_SHA256:
        raise SetupError("%s: the downloaded file is damaged" % host(url))


def fetch(work, status, progress, cancel):
    """quake106.zip from the first source that delivers it intact; returns (path, url)."""
    path = os.path.join(work, ZIP_NAME)
    errors = []
    for url in SOURCES:
        status("Downloading from %s ..." % host(url))
        try:
            download(url, path, progress, cancel)
            return path, url
        except SetupError as e:
            errors.append(str(e))
            if os.path.exists(path):
                os.remove(path)
    raise SetupError("The download failed from every source:\n" + "\n".join(errors))


def unpack(work, zpath):
    """resource.1 from the zip, the three files from resource.1, all checked; returns a dir."""
    try:
        with zipfile.ZipFile(zpath) as z:
            z.extract(RES_NAME, work)
    except (zipfile.BadZipFile, KeyError, OSError) as e:
        raise SetupError("The archive cannot be unpacked: %s" % e)
    res = os.path.join(work, RES_NAME)
    if os.path.getsize(res) != RES_SIZE or sha256(res) != RES_SHA256:
        raise SetupError("The downloaded game data is damaged")
    out = os.path.join(work, "out")
    os.mkdir(out)
    try:
        r = subprocess.run(["lha", "xqw=" + out, res] + list(FILES), capture_output=True,
                           text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        raise SetupError("lha (package lhasa) is needed to unpack the data: %s" % e)
    if r.returncode != 0:
        raise SetupError("Unpacking %s failed: %s" % (RES_NAME, (r.stderr or r.stdout).strip()))
    for name, (size, digest) in FILES.items():
        p = os.path.join(out, name)
        if not os.path.isfile(p) or os.path.getsize(p) != size or sha256(p) != digest:
            raise SetupError("The downloaded game data is damaged")
    return out


def licence_text(out):
    def read(name):
        with open(os.path.join(out, name), "rb") as f:
            return f.read().decode("cp437").replace("\r\n", "\n").replace("\t", "        ")
    return read("slicnse.txt").rstrip() + "\n\n\n" + read("licinfo.txt").rstrip() + "\n"


def install(out, url, dest=DEST):
    """Licence files first, pak0.pak last (its presence means installed), each by rename."""
    os.makedirs(os.path.join(dest, "id1"), exist_ok=True)
    for name in ("slicnse.txt", "licinfo.txt", "id1/pak0.pak"):
        target = os.path.join(dest, name)
        shutil.copyfile(os.path.join(out, name), target + ".part")
        os.chmod(target + ".part", 0o644)
        os.replace(target + ".part", target)
    link = os.path.join(dest, "quakespasm.pak")
    if os.path.exists(ENGINE_PAK) and not os.path.lexists(link):
        os.symlink(ENGINE_PAK, link)
    with open(os.path.join(dest, "INSTALLED"), "w") as f:
        f.write("Quake shareware 1.06, installed by quake-shareware-setup on %s\n"
                "source: %s\n%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), url, ZIP_SHA256, ZIP_NAME))
        for name, (_size, digest) in FILES.items():
            f.write("%s  %s\n" % (digest, name))
    subprocess.run(["sync"])


def workdir():
    # in RAM (/tmp is a tmpfs on these systems): ~45 MB at most, removed in every case
    return tempfile.mkdtemp(prefix="quake-shareware-", dir="/tmp")


# ----------------------------------------------------------------------------- text mode
def run_tty():
    try:
        return _run_tty()
    except KeyboardInterrupt:
        print("\nCancelled; nothing was installed.")
        return 1


def _run_tty():
    print("\n== Quake shareware data ==\n")
    print(OFFER + "\n")
    if not ask("Download the shareware version now?"):
        print("Cancelled; nothing was installed.")
        return 1
    work = workdir()
    cancel = threading.Event()
    try:
        last = [0.0]

        def progress(done, total):
            now = time.monotonic()
            if now - last[0] > 0.5 or done == total:
                last[0] = now
                sys.stdout.write("\r  %5.1f of %.1f MB" % (done / 1e6, total / 1e6))
                sys.stdout.flush()
        zpath, url = fetch(work, lambda s: print("\n" + s), progress, cancel)
        print("\nUnpacking ...")
        out = unpack(work, zpath)
        text = licence_text(out)
        pager = shutil.which("less") or shutil.which("more")
        print("\nid Software's licence follows%s.\n" % (" (q to close the pager)" if pager else ""))
        time.sleep(1)
        if pager and sys.stdout.isatty():
            subprocess.run([pager], input=text, text=True)
        else:
            print(text)
        if not ask("Do you accept id Software's licence?"):
            print("Licence declined; nothing was installed.")
            return 1
        install(out, url)
        print("Installed in %s." % DEST)
        return 0
    except SetupError as e:
        print("\nERROR: %s\nNothing was installed." % e)
        return 2
    finally:
        shutil.rmtree(work, ignore_errors=True)


def ask(question):
    try:
        return input(question + " [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


# ----------------------------------------------------------------------------- TV mode
QML = r'''
import QtQuick 2.15
import QtQuick.Window 2.15

Window {
    id: win
    width: 1920; height: 1080
    visible: true
    visibility: Window.FullScreen
    flags: Qt.FramelessWindowHint
    color: "#0b2a14"
    title: "Quake shareware setup"
    readonly property color accent: "#b9f23f"
    readonly property string face: "Quicksand"
    // offer, working, licence, error, done
    property string page: "offer"
    property int sel: 0

    function buttons() {
        if (page === "offer") return ["Download", "Cancel"]
        if (page === "working") return ["Cancel"]
        if (page === "licence") return ["Accept", "Decline"]
        if (page === "error") return backend.canRetry ? ["Try again", "Close"] : ["Close"]
        return []
    }
    function activate(i) {
        var b = buttons()[i]
        if (b === "Download" || b === "Try again") { page = "working"; sel = 0; backend.start() }
        else if (b === "Accept") { page = "working"; sel = 0; backend.accept() }
        else backend.cancel()
    }
    Connections {
        target: backend
        function onLicenceReady() { win.page = "licence"; win.sel = 0; flick.contentY = 0 }
        function onFailed() { win.page = "error"; win.sel = 0 }
        function onFinished() { win.page = "done" }
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#1f5a1c" }
            GradientStop { position: 1.0; color: "#0a2a12" }
        }
    }
    Rectangle { x: 88; y: 64; width: 8; height: 52; radius: 4; color: win.accent }
    Text {
        x: 116; y: 58
        text: "Quake"
        font.family: win.face; font.bold: true; font.pixelSize: 50; color: "white"
    }

    Item {
        id: body
        x: 116; y: 170; width: parent.width - 232; height: 700

        Text {
            visible: win.page === "offer"
            width: parent.width
            text: backend.offer
            wrapMode: Text.WordWrap
            font.family: win.face; font.pixelSize: 36; color: "#e8ffffff"
            lineHeight: 1.15
        }
        Column {
            visible: win.page === "working" || win.page === "done"
            width: parent.width; spacing: 40
            Text {
                text: win.page === "done" ? "Installed. Starting Quake ..." : backend.status
                width: parent.width; wrapMode: Text.WordWrap
                font.family: win.face; font.bold: true; font.pixelSize: 38; color: "white"
            }
            Rectangle {
                visible: win.page === "working" && backend.progress >= 0
                width: parent.width; height: 28; radius: 14
                color: "#40000000"; border.width: 2; border.color: "#40ffffff"
                Rectangle {
                    width: Math.max(28, parent.width * backend.progress); height: parent.height
                    radius: 14; color: win.accent
                }
            }
            Text {
                visible: win.page === "working" && backend.progress >= 0
                text: backend.progressText
                font.family: win.face; font.pixelSize: 30; color: "#b3ffffff"
            }
        }
        Column {
            visible: win.page === "licence"
            width: parent.width; spacing: 20
            Text {
                text: "Licence: read id Software's terms (arrows scroll), then accept or decline."
                width: parent.width; wrapMode: Text.WordWrap
                font.family: win.face; font.bold: true; font.pixelSize: 32; color: "white"
            }
            Rectangle {
                width: parent.width; height: 600; radius: 18
                color: "#99000000"; border.width: 2; border.color: "#40ffffff"
                Flickable {
                    id: flick
                    anchors.fill: parent; anchors.margins: 24
                    clip: true
                    contentWidth: width; contentHeight: lic.height
                    Text {
                        id: lic
                        width: flick.width
                        text: backend.licence
                        wrapMode: Text.WordWrap
                        font.family: "DejaVu Sans Mono"; font.pixelSize: 24; color: "#e8ffffff"
                    }
                }
                Rectangle {   // scroll position
                    anchors.right: parent.right; anchors.rightMargin: 6
                    y: 24 + (parent.height - 48 - height) * (flick.contentHeight > flick.height ?
                         flick.contentY / (flick.contentHeight - flick.height) : 0)
                    width: 8; height: 80; radius: 4; color: "#80ffffff"
                    visible: flick.contentHeight > flick.height
                }
            }
        }
        Text {
            visible: win.page === "error"
            width: parent.width
            text: backend.error + "\n\nNothing was installed."
            wrapMode: Text.WordWrap
            font.family: win.face; font.pixelSize: 34; color: "#ffd0c8"
        }
    }

    Row {
        x: 116; y: 920; spacing: 40
        Repeater {
            model: win.buttons()
            Rectangle {
                property bool on: index === win.sel
                width: label.implicitWidth + 100; height: 84; radius: 42
                color: on ? "#33ffffff" : "#80000000"
                border.width: on ? 4 : 2; border.color: on ? win.accent : "#40ffffff"
                Text {
                    id: label
                    anchors.centerIn: parent
                    text: modelData
                    font.family: win.face; font.bold: true; font.pixelSize: 34; color: "white"
                }
            }
        }
    }
    Text {
        x: 116; y: 1020
        text: "OK selects  ·  Back cancels"
        font.family: win.face; font.pixelSize: 26; color: "#80ffffff"
    }

    Item {
        anchors.fill: parent
        focus: true
        Keys.onPressed: function(event) {
            var n = win.buttons().length
            var step = 72
            if (event.key === Qt.Key_Left) { if (win.sel > 0) win.sel--; event.accepted = true }
            else if (event.key === Qt.Key_Right) { if (win.sel < n - 1) win.sel++; event.accepted = true }
            else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                if (n > 0) win.activate(win.sel); event.accepted = true
            } else if (event.key === Qt.Key_Escape || event.key === Qt.Key_Back) {
                backend.cancel(); event.accepted = true
            } else if (win.page === "licence" && (event.key === Qt.Key_Down || event.key === Qt.Key_PageDown
                                                 || event.key === Qt.Key_Up || event.key === Qt.Key_PageUp)) {
                var d = (event.key === Qt.Key_PageDown || event.key === Qt.Key_PageUp) ? flick.height - 40 : step
                if (event.key === Qt.Key_Up || event.key === Qt.Key_PageUp) d = -d
                flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, flick.contentY + d))
                event.accepted = true
            }
        }
    }
}
'''


def run_gui():
    from PyQt5.QtCore import QObject, Qt, QTimer, pyqtProperty, pyqtSignal, pyqtSlot
    from PyQt5.QtGui import QCursor, QFontDatabase, QGuiApplication
    from PyQt5.QtQml import QQmlApplicationEngine

    class Backend(QObject):
        changed = pyqtSignal()
        licenceReady = pyqtSignal()
        failed = pyqtSignal()
        finished = pyqtSignal()
        _licence = pyqtSignal(str)
        _error = pyqtSignal(str, bool)
        _done = pyqtSignal()

        def __init__(self, app):
            super().__init__()
            self.app = app
            self.result = 1
            self._status = ""
            self._progress = -1.0
            self._ptext = ""
            self._lic = ""
            self._err = ""
            self._retry = True
            self.cancel_ev = threading.Event()
            self.work = None
            self.out = None
            self.url = None
            self.thread = None
            self._licence.connect(self._on_licence)
            self._error.connect(self._on_error)
            self._done.connect(self._on_done)

        # properties for the QML side
        @pyqtProperty(str, constant=True)
        def offer(self):
            return OFFER

        @pyqtProperty(str, notify=changed)
        def status(self):
            return self._status

        @pyqtProperty(float, notify=changed)
        def progress(self):
            return self._progress

        @pyqtProperty(str, notify=changed)
        def progressText(self):
            return self._ptext

        @pyqtProperty(str, notify=changed)
        def licence(self):
            return self._lic

        @pyqtProperty(str, notify=changed)
        def error(self):
            return self._err

        @pyqtProperty(bool, notify=changed)
        def canRetry(self):
            return self._retry

        def set(self, **kw):
            for k, v in kw.items():
                setattr(self, "_" + k, v)
            self.emit(self.changed)

        def emit(self, signal, *args):
            # from the worker thread; after a cancel the window may already be closed
            try:
                signal.emit(*args)
            except RuntimeError:
                pass

        # actions
        @pyqtSlot()
        def start(self):
            self.cleanup()
            self.result = 1
            self.cancel_ev = threading.Event()
            self.work = workdir()
            self.set(status="Connecting ...", progress=0.0, ptext="")
            self.thread = threading.Thread(target=self._fetch, daemon=True)
            self.thread.start()

        def _fetch(self):
            try:
                zpath, self.url = fetch(self.work, lambda s: self.set(status=s), self._prog, self.cancel_ev)
                self.set(status="Unpacking ...", progress=-1.0)
                self.out = unpack(self.work, zpath)
                if not self.cancel_ev.is_set():
                    self.emit(self._licence, licence_text(self.out))
            except Cancelled:
                pass
            except SetupError as e:
                if not self.cancel_ev.is_set():
                    self.emit(self._error, str(e), True)
            except Exception as e:      # anything unexpected still ends on the error page
                if not self.cancel_ev.is_set():
                    self.emit(self._error, "Unexpected error: %s" % e, True)

        def _prog(self, done, total):
            self.set(progress=done / total, ptext="%.1f of %.1f MB" % (done / 1e6, total / 1e6))

        def _on_licence(self, text):
            self.set(lic=text)
            self.licenceReady.emit()

        def _on_error(self, text, retry):
            self.cleanup()
            self.result = 2
            self.set(err=text, retry=retry)
            self.failed.emit()

        @pyqtSlot()
        def accept(self):
            self.set(status="Installing ...", progress=-1.0)
            try:
                install(self.out, self.url)
            except OSError as e:
                self._on_error("Installing failed: %s" % e, False)
                return
            self.cleanup()
            self.result = 0
            self.finished.emit()
            QTimer.singleShot(1500, self.app.quit)

        @pyqtSlot()
        def cancel(self):
            # Cancel/Back: 1; Close on the error page keeps 2 (failed). A running download
            # stops at its next block; wait for it before the folder goes
            self.cancel_ev.set()
            if self.thread is not None and self.thread.is_alive():
                self.thread.join(3)
            self.cleanup()
            self.app.quit()

        def _on_done(self):
            pass

        def cleanup(self):
            if self.work:
                shutil.rmtree(self.work, ignore_errors=True)
                self.work = None

    app = QGuiApplication(sys.argv[:1])
    app.setOverrideCursor(QCursor(Qt.BlankCursor))       # a TV screen, driven by the remote
    for f in ("Quicksand-Regular.ttf", "Quicksand-Bold.ttf"):
        QFontDatabase.addApplicationFont("/usr/share/fonts/truetype/quicksand/" + f)
    backend = Backend(app)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.loadData(QML.encode())
    if not engine.rootObjects():
        return 2
    app.exec_()
    backend.cancel_ev.set()
    backend.cleanup()
    result = backend.result
    del engine
    del backend
    return result


def main():
    args = sys.argv[1:]
    if "--check" in args:
        return 0 if installed() else 1
    if installed():
        return 0
    if os.geteuid() != 0:
        print("quake-shareware-setup: installing the Quake data needs root (sudo quake)", file=sys.stderr)
        return 2
    gui = "--gui" in args or ("--tty" not in args and bool(os.environ.get("DISPLAY")))
    return run_gui() if gui else run_tty()


if __name__ == "__main__":
    sys.exit(main())
