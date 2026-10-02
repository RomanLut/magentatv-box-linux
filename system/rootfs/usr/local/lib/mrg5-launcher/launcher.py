#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Roman Lut
"""MRG5 TV launcher (checks/41, "TV launcher"): a full-screen row of tiles for the remote.

The tiles come from an XML file (default /etc/mrg5-launcher/tiles.xml, or the first
argument). Main.qml draws them; this file reads the XML, starts the programs and tells
the QML side when a program's window is up (hide the launcher) and when the program
has ended (show the launcher again). Game pads (Pads) drive the tiles like the remote.

The remote pairing screen (RemoteSetup, pair-remote.py) comes up at the first start, until
REMOTE_FLAG exists, and when the rear button is held for 3 s (ResetButton). Any other
Bluetooth device (game pads) is paired from the settings, "Pair Bluetooth Device" (BtPair,
pair-device.py). The settings also show a QR code for the phone remote (phone_remote_qr).

Energy: the scene graph draws only when something changes. Nothing here animates
by itself; while a program runs the launcher window is unmapped, so it draws nothing.
"""
import errno
import hashlib
import json
import os
import shlex
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from PyQt5.QtCore import (QEvent, QFileSystemWatcher, QObject, QProcess, QProcessEnvironment,
                          QSocketNotifier, Qt, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot)
from PyQt5.QtGui import QFontDatabase, QGuiApplication, QKeyEvent
from PyQt5.QtQml import QQmlApplicationEngine

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, "icons")
CONFIG = sys.argv[1] if len(sys.argv) > 1 else "/etc/mrg5-launcher/tiles.xml"
SWITCH = os.path.join(HERE, "switch")
PAIR_REMOTE = os.path.join(HERE, "pair-remote.py")
PAIR_DEVICE = os.path.join(HERE, "pair-device.py")   # settings: "Pair Bluetooth Device"
MICROP = "/usr/local/bin/microp"          # front LEDs (work/led/microp.py)
WINDOW_WAIT = 90          # s: stop waiting for a program's window, hide anyway
# Written once the pairing screen has been passed (remote paired, or skipped with Esc);
# while it is missing the launcher starts with that screen. make-usb-stick.sh deletes it.
REMOTE_FLAG = "/var/lib/mrg5-launcher/remote-setup-done"
# Soft standby settings, shared with mrg5-standby (work/standby/): "cpu=low" (default: 331 MHz,
# cores 1-3 offline) or "cpu=normal" (the CPU is left as it is).
STANDBY_CONF = "/etc/mrg5-standby.conf"
STORAGE = "/usr/local/bin/mrg5-storage"     # /DATA on USB or HDD (work/storage/)
# Phone remote (work/phone-remote/, mrg5-phone-remote.service): remote-touchpad on this port,
# with a secret made once per boot; the settings show http://<address>:<port>/#<secret> as a QR
# code, drawn with python3-qrcode into QR_DIR (RAM)
PHONE_REMOTE_SECRET = "/run/mrg5-phone-remote/secret"
PHONE_REMOTE_PORT = 8090
QR_DIR = "/run/mrg5-launcher"


def phone_remote_qr(ip):
    """A file URL of the phone remote's QR code for the settings, or "" when there is no address,
    no secret (the service is not installed or not started) or no python3-qrcode."""
    try:
        with open(PHONE_REMOTE_SECRET) as f:
            secret = f.read().strip()
        import qrcode
    except (OSError, ImportError):
        return ""
    if not ip or not secret:
        return ""
    url = "http://%s:%d/#%s" % (ip, PHONE_REMOTE_PORT, secret)
    # a new file name for every address/secret: QML caches images by URL
    path = os.path.join(QR_DIR, "phone-remote-%s.png" % hashlib.sha1(url.encode()).hexdigest()[:12])
    if not os.path.exists(path):
        try:
            os.makedirs(QR_DIR, exist_ok=True)
            for f in os.listdir(QR_DIR):
                if f.startswith("phone-remote-"):
                    os.remove(os.path.join(QR_DIR, f))
            # 7 px per module and a 2-module white border: drawn 1:1, sharp for the phone's camera
            qrcode.make(url, box_size=7, border=2).save(path)
        except (OSError, ValueError) as e:
            log("phone remote QR:", e)
            return ""
    return QUrl.fromLocalFile(path).toString()


def standby_cpu_low():
    try:
        with open(STANDBY_CONF) as f:
            for line in f:
                if line.strip().replace(" ", "") == "cpu=normal":
                    return False
    except OSError:
        pass
    return True


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def icon_url(name, base):
    """Icon attribute -> file URL: absolute path, or a file in the icon folder(s)."""
    if not name:
        name = "application.svg"
    cands = [name] if os.path.isabs(name) else [os.path.join(base, name), os.path.join(ICONS, name)]
    for c in cands:
        if os.path.isfile(c):
            return QUrl.fromLocalFile(c).toString()
    log("icon not found:", name)
    return QUrl.fromLocalFile(os.path.join(ICONS, "application.svg")).toString()


def read_config(path):
    root = ET.parse(path).getroot()
    base = os.path.dirname(os.path.abspath(path))
    icons = root.get("icons", ICONS)
    if not os.path.isabs(icons):
        icons = os.path.join(base, icons)
    tiles = []
    for t in root.findall("tile"):
        tiles.append({
            "title": t.get("title", "?"),
            "icon": icon_url(t.get("icon", ""), icons),
            "exec": t.get("exec", ""),
            "action": t.get("action", ""),
            "color": t.get("color", "#2c3e35"),
            "iconScale": float(t.get("iconScale", "1")),
        })
    bg = root.get("background", "")
    return {
        "title": root.get("title", "Main Menu"),
        "background": QUrl.fromLocalFile(bg).toString() if bg and os.path.isfile(bg) else "",
        "storage": root.get("storage", "/"),
        "tiles": tiles,
    }


def client_windows():
    """Top-level windows the window manager manages (_NET_CLIENT_LIST)."""
    try:
        out = subprocess.run(["xprop", "-root", "_NET_CLIENT_LIST"], capture_output=True,
                             text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(w.strip() for w in out.partition("#")[2].split(",") if w.strip())


class Backend(QObject):
    appWindowShown = pyqtSignal()                 # hide the launcher
    appFinished = pyqtSignal(str, int)            # show it again (title, exit code)
    appFailed = pyqtSignal(str, str)              # could not start (title, reason)
    statusChanged = pyqtSignal()
    settingsChanged = pyqtSignal()                # free RAM, standby CPU, storage (settings)

    def __init__(self, cfg):
        super().__init__()
        self._cfg = cfg
        self._proc = None
        self._title = ""
        self._before = set()
        self._since = 0.0
        self._ip = ""
        self._free = ""
        self._ram = ""
        self._cpu_low = standby_cpu_low()
        self._storage = ""
        self._qr = ""
        self._poll = QTimer(self)
        self._poll.setInterval(400)
        self._poll.timeout.connect(self._check_window)
        self.refreshStatus()

    @pyqtProperty(str, constant=True)
    def title(self):
        return self._cfg["title"]

    @pyqtProperty(str, constant=True)
    def background(self):
        return self._cfg["background"]

    @pyqtProperty("QVariantList", constant=True)
    def tiles(self):
        return self._cfg["tiles"]

    @pyqtProperty(str, notify=statusChanged)
    def ip(self):
        return self._ip

    @pyqtProperty(str, notify=statusChanged)
    def freeSpace(self):
        return self._free

    @pyqtProperty(str, notify=settingsChanged)
    def freeRam(self):
        return self._ram

    @pyqtProperty(bool, notify=settingsChanged)
    def standbyCpuLow(self):
        return self._cpu_low

    @pyqtProperty(str, notify=settingsChanged)
    def phoneRemoteQr(self):
        """File URL of the phone remote's QR code, "" when there is none."""
        return self._qr

    @pyqtSlot()
    def refreshSettings(self):
        """For the settings panel only, so the idle launcher never redraws for them."""
        ram = ""
        try:
            with open("/proc/meminfo") as f:
                kb = next(int(l.split()[1]) for l in f if l.startswith("MemAvailable:"))
            ram = "%.1f GB" % (kb / 1e6)
        except (OSError, StopIteration, ValueError):
            pass
        self._ram = ram
        self._cpu_low = standby_cpu_low()
        self._storage_status()
        self._qr = phone_remote_qr(self._ip)
        self.settingsChanged.emit()

    # ---- data storage: only shown (mrg5-storage status) ----
    # There is no switch between USB and the internal HDD any more (owner, 2026-10-01): a USB
    # Boot box whose stick is removed boots its stock firmware, whose recovery formats the
    # internal HDD (checks/42 §2a), so data kept there could be lost. /DATA stays where the
    # release puts it.

    def _storage_status(self):
        try:
            st = json.loads(subprocess.run([STORAGE, "status"], capture_output=True, text=True,
                                           timeout=15).stdout)
        except (OSError, ValueError, subprocess.SubprocessError):
            self._storage = ""
            return
        where = st.get("storage", "")
        self._storage = {"usb": "USB", "hdd": "HDD", "emmc": "eMMC"}.get(where, where.upper())

    @pyqtProperty(str, notify=settingsChanged)
    def storageName(self):
        """HDD, USB or eMMC: where /DATA is."""
        return self._storage

    @pyqtSlot()
    def toggleStandbyCpu(self):
        low = not standby_cpu_low()
        try:
            with open(STANDBY_CONF, "w") as f:
                f.write("# soft standby (mrg5-standby): cpu=low (331 MHz, one core) or cpu=normal\n"
                        "cpu=%s\n" % ("low" if low else "normal"))
                f.flush()
                os.fsync(f.fileno())
            log("standby CPU:", "low" if low else "normal")
        except OSError as e:
            log("cannot write", STANDBY_CONF, e)
        self.refreshSettings()

    @pyqtProperty(bool, notify=statusChanged)
    def running(self):
        return self._proc is not None

    @pyqtProperty(str, notify=statusChanged)
    def startedTitle(self):
        """Title of the program started last (the one running while `running`)."""
        return self._title

    @pyqtSlot()
    def refreshStatus(self):
        ip = ""
        try:
            out = subprocess.run(["ip", "-4", "-o", "route", "get", "1.1.1.1"], capture_output=True,
                                 text=True, timeout=3).stdout.split()
            ip = out[out.index("src") + 1] if "src" in out else ""
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        try:
            st = os.statvfs(self._cfg["storage"])
            gb = st.f_bavail * st.f_frsize / 1e9
            free = "%.0f GB" % gb if gb >= 10 else "%.1f GB" % gb
        except OSError:
            free = ""
        if (ip, free) != (self._ip, self._free):
            self._ip, self._free = ip, free
            self.statusChanged.emit()

    @pyqtSlot(int)
    def launch(self, index):
        if self._proc is not None:
            return
        t = self._cfg["tiles"][index]
        if t["action"] in ("desktop", "console", "reboot"):
            log("action", t["action"])
            # systemd-run: the switch must outlive this unit, which it stops
            subprocess.Popen(["systemd-run", "--no-block", "--collect", "--quiet",
                              SWITCH, t["action"]])
            return
        if not t["exec"]:
            return
        self._title = t["title"]
        self._before = client_windows()
        self._since = time.monotonic()
        p = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        for k in ("QT_QPA_PLATFORM", "QT_SCALE_FACTOR", "QT_ENABLE_HIGHDPI_SCALING",
                  "QT_AUTO_SCREEN_SCALE_FACTOR", "QSG_RENDER_LOOP"):
            env.remove(k)
        p.setProcessEnvironment(env)
        p.setProcessChannelMode(QProcess.ForwardedChannels)
        p.finished.connect(self._finished)
        p.errorOccurred.connect(self._error)
        log("start", t["title"], ":", t["exec"])
        self._proc = p
        self.statusChanged.emit()
        p.start("/bin/sh", ["-c", "exec " + t["exec"]])
        self._poll.start()

    def _check_window(self):
        new = client_windows() - self._before
        if new or time.monotonic() - self._since > WINDOW_WAIT:
            self._poll.stop()
            log("window up" if new else "no window after %d s" % WINDOW_WAIT, self._title)
            self.appWindowShown.emit()

    def _finished(self, code, _status):
        self._poll.stop()
        log("ended", self._title, "code", code)
        self._proc = None
        self.refreshStatus()
        self.statusChanged.emit()
        self.appFinished.emit(self._title, code)

    def _error(self, err):
        if err == QProcess.FailedToStart:
            self._poll.stop()
            log("failed to start", self._title)
            self._proc = None
            self.statusChanged.emit()
            self.appFailed.emit(self._title, "could not be started")

    @pyqtSlot()
    def reboot(self):
        log("reboot")
        subprocess.Popen(["systemd-run", "--no-block", "--collect", "--quiet", SWITCH, "reboot"])


class RemoteSetup(QObject):
    """The pairing screen's side: runs pair-remote.py and reports its progress.

    state: "" (not running), searching, found, removed, pairing, paired, ready (done),
    failed (the last attempt; searching goes on), error (the helper stopped).
    """
    changed = pyqtSignal()
    ready = pyqtSignal()                          # a remote is paired

    def __init__(self):
        super().__init__()
        self._proc = None
        self._state = ""
        self._detail = ""
        self._buf = b""
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.setInterval(5000)
        self._retry.timeout.connect(self.start)

    @pyqtProperty(bool, constant=True)
    def firstStart(self):
        return not os.path.exists(REMOTE_FLAG)

    @pyqtProperty(str, notify=changed)
    def state(self):
        return self._state

    @pyqtProperty(str, notify=changed)
    def detail(self):
        return self._detail

    def _set(self, state, detail=""):
        self._state, self._detail = state, detail
        self.changed.emit()

    @pyqtSlot()
    def start(self):
        if self._proc is not None:
            return
        log("remote pairing: start")
        self._buf = b""
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.SeparateChannels)
        p.readyReadStandardOutput.connect(self._read)
        p.readyReadStandardError.connect(lambda: log("pair-remote:", bytes(p.readAllStandardError()).decode(errors="replace").strip()))
        p.finished.connect(self._finished)
        self._proc = p
        self._set("searching")
        p.start("python3", ["-u", PAIR_REMOTE])

    @pyqtSlot()
    def stop(self):
        self._retry.stop()
        p, self._proc = self._proc, None
        if p is not None:
            log("remote pairing: stop")
            p.finished.disconnect(self._finished)
            p.terminate()                             # the helper cleans up on SIGTERM
            if not p.waitForFinished(3000):
                p.kill()
                p.waitForFinished(1000)
        self._set("")

    @pyqtSlot()
    def markDone(self):
        try:
            os.makedirs(os.path.dirname(REMOTE_FLAG), exist_ok=True)
            with open(REMOTE_FLAG, "w") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S\n"))
            log("remote setup flag written")
        except OSError as e:
            log("cannot write", REMOTE_FLAG, e)

    def _read(self):
        self._buf += bytes(self._proc.readAllStandardOutput())
        *lines, self._buf = self._buf.split(b"\n")
        for line in lines:
            words = line.decode(errors="replace").split()
            if not words:
                continue
            log("pair-remote:", *words)
            what = words[0]
            if what == "found":
                self._set("found", " ".join(words[2:]))
            elif what == "failed":
                self._set("failed", " ".join(words[2:]))
            elif what in ("searching", "removed", "pairing", "paired"):
                self._set(what, self._detail)
            elif what == "ready":
                self._set("ready", self._detail)
                self.ready.emit()

    def _finished(self, code, _status):
        self._proc = None
        if self._state != "ready":
            log("pair-remote ended, code", code)
            self._set("error")
            self._retry.start()


class BtPair(QObject):
    """Settings -> "Pair Bluetooth Device": runs pair-device.py, a SEARCH_S search, then a
    list to pick from; picking one pairs, trusts and connects it.

    state: "" (closed), searching, list, pairing (detail: what it does now), paired, failed
    (detail: reason). devices: [{mac, name, kind, paired}], named ones first.
    """
    changed = pyqtSignal()
    SEARCH_S = 10

    def __init__(self):
        super().__init__()
        self._proc = None
        self._buf = b""
        self._state = ""
        self._detail = ""
        self._devices = {}
        self._left = 0
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._count)

    @pyqtProperty(str, notify=changed)
    def state(self):
        return self._state

    @pyqtProperty(str, notify=changed)
    def detail(self):
        return self._detail

    @pyqtProperty(int, notify=changed)
    def secondsLeft(self):
        return self._left

    @pyqtProperty("QVariantList", notify=changed)
    def devices(self):
        return sorted(self._devices.values(),
                      key=lambda d: (d["name"] == d["mac"].replace(":", "-"), d["name"].lower()))

    def _set(self, state, detail=""):
        self._state, self._detail = state, detail
        self.changed.emit()

    def _run(self, args):
        self._kill()
        self._buf = b""
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.SeparateChannels)
        p.readyReadStandardOutput.connect(self._read)
        p.readyReadStandardError.connect(lambda: log("pair-device:", bytes(p.readAllStandardError()).decode(errors="replace").strip()))
        p.finished.connect(self._finished)
        self._proc = p
        log("pair-device", *args)
        p.start("python3", ["-u", PAIR_DEVICE] + args)

    def _kill(self):
        p, self._proc = self._proc, None
        if p is not None:
            p.finished.disconnect(self._finished)
            p.terminate()                             # the helper cleans up on SIGTERM
            if not p.waitForFinished(3000):
                p.kill()
                p.waitForFinished(1000)

    @pyqtSlot()
    def search(self):
        self._devices = {}
        self._left = self.SEARCH_S
        self._tick.start()
        self._set("searching")
        self._run(["scan", str(self.SEARCH_S)])

    @pyqtSlot(str)
    def pair(self, mac):
        if self._state in ("searching", "pairing"):
            return
        name = self._devices.get(mac, {}).get("name", mac)
        self._set("pairing", "Pairing with " + name + " …")
        self._run(["pair", mac])

    @pyqtSlot()
    def stop(self):
        self._tick.stop()
        self._kill()
        self._set("")

    def _count(self):
        self._left = max(0, self._left - 1)
        self.changed.emit()

    def _read(self):
        self._buf += bytes(self._proc.readAllStandardOutput())
        *lines, self._buf = self._buf.split(b"\n")
        for line in lines:
            try:
                ev = json.loads(line.decode(errors="replace"))
            except ValueError:
                continue
            log("pair-device:", ev)
            what = ev.get("ev")
            if what == "device":
                self._devices[ev["mac"]] = {k: ev.get(k, "") for k in ("mac", "name", "kind", "paired")}
                self.changed.emit()
            elif what == "end":
                self._tick.stop()
                self._set("list")
            elif what == "state":
                self._set("pairing", {"searching": "Looking for the device …",
                                      "pairing": "Pairing with %s …",
                                      "connecting": "Paired, connecting %s …"}
                          .get(ev["state"], "…").replace("%s", ev.get("name", "")))
            elif what == "done":
                d = self._devices.get(ev["mac"])
                if d is not None:
                    d["paired"] = True
                self._set("paired", ev.get("name", "") + (" is paired and connected" if ev.get("connected")
                                                          else " is paired"))
            elif what == "failed":
                self._tick.stop()
                reason = ev.get("reason", "?")
                self._set("failed", reason[:1].upper() + reason[1:] if reason.startswith("paired")
                          else "Pairing failed: " + reason)

    def _finished(self, code, _status):
        self._proc = None
        self._tick.stop()
        if self._state == "searching":
            self._set("list")
        elif self._state == "pairing":
            self._set("failed", "Pairing failed (code %d)" % code)


class ResetButton(QObject):
    """The rear "Reset" button: a plain GPIO input (checks/25), GPIO 47 = gpiochip1 line 15,
    low while pressed. Held for HOLD_MS -> held(). Waits for edge interrupts; polls nothing."""
    held = pyqtSignal()
    CHIP, LINE, HOLD_MS = "gpiochip1", 15, 3000

    def __init__(self):
        super().__init__()
        self._line = None
        try:
            import gpiod                              # python3-libgpiod
            self._gpiod = gpiod
            self._chip = gpiod.Chip(self.CHIP)
            line = self._chip.get_line(self.LINE)
            line.request(consumer="mrg5-launcher", type=gpiod.LINE_REQ_EV_BOTH_EDGES)
        except Exception as e:                        # no gpiod, no such line, line busy
            log("reset button not available:", e)
            return
        self._line = line
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.HOLD_MS)
        self._timer.timeout.connect(self._check)
        self._sn = QSocketNotifier(line.event_get_fd(), QSocketNotifier.Read, self)
        self._sn.activated.connect(self._event)
        log("reset button: %s line %d" % (self.CHIP, self.LINE))

    def _event(self):
        for ev in self._line.event_read_multiple():
            if ev.type == self._gpiod.LineEvent.FALLING_EDGE:
                self._timer.start()                   # pressed: time the hold
            else:
                self._timer.stop()                    # released early

    def _check(self):
        if self._line.get_value() == 0:               # still held (bounces end up here too)
            log("reset button held")
            self.held.emit()


class Pads(QObject):
    """Game pads as the launcher's keys: D-pad = arrows (held: repeats), O = OK (Enter).

    Watches /dev/input for pads coming and going (a DS4 on Bluetooth disconnects when idle),
    so nothing polls. A pad is an event device with BTN_SOUTH (0x130) among its keys, which
    leaves out a DS4's touchpad and motion devices. Reads without grabbing, so a program
    started from the launcher gets the pad as usual; while one runs, or the window is hidden,
    the events are read and dropped. The keys are sent to the window as key events, so they
    take the same path as the remote's.
    """
    EV = struct.Struct("llHHi")                       # struct input_event on 32-bit ARM
    EV_KEY, EV_ABS = 1, 3
    BTN_SOUTH, BTN_EAST = 0x130, 0x131                # cross, circle (O)
    ABS_HAT0X, ABS_HAT0Y = 0x10, 0x11                 # the D-pad on hid-playstation / xpad
    DPAD_KEYS = {0x220: Qt.Key_Up, 0x221: Qt.Key_Down, 0x222: Qt.Key_Left, 0x223: Qt.Key_Right}
    BUTTONS = {BTN_EAST: Qt.Key_Return}
    LONG_BITS = struct.calcsize("l") * 8

    def __init__(self, backend, window):
        super().__init__()
        self._backend = backend
        self._window = window
        self._devs = {}                               # /dev/input/eventN -> (fd, notifier)
        self._hat = {self.ABS_HAT0X: 0, self.ABS_HAT0Y: 0}
        self._held = None
        self._repeat = QTimer(self)
        self._repeat.timeout.connect(self._again)
        self._watch = QFileSystemWatcher(["/dev/input"], self)
        # udev sets the node up just after it appears
        self._watch.directoryChanged.connect(lambda _p: QTimer.singleShot(700, self.scan))
        self.scan()

    @classmethod
    def _is_pad(cls, name):
        try:
            words = open("/sys/class/input/%s/device/capabilities/key" % name).read().split()
        except OSError:
            return False
        words.reverse()                               # sysfs lists the highest word first
        i, bit = divmod(cls.BTN_SOUTH, cls.LONG_BITS)
        return i < len(words) and (int(words[i], 16) >> bit) & 1 == 1

    def scan(self):
        for path in [p for p in self._devs if not os.path.exists(p)]:
            self._close(path)
        try:
            names = [n for n in os.listdir("/sys/class/input") if n.startswith("event")]
        except OSError:
            return
        for n in names:
            path = "/dev/input/" + n
            if path in self._devs or not self._is_pad(n):
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            sn = QSocketNotifier(fd, QSocketNotifier.Read, self)
            sn.activated.connect(lambda _fd, p=path: self._read(p))
            self._devs[path] = (fd, sn)
            try:
                title = open("/sys/class/input/%s/device/name" % n).read().strip()
            except OSError:
                title = "?"
            log("game pad:", title, path)

    def _close(self, path):
        fd, sn = self._devs.pop(path)
        sn.setEnabled(False)
        sn.deleteLater()
        os.close(fd)
        self._stop()
        log("game pad gone:", path)

    def _read(self, path):
        fd = self._devs[path][0]
        try:
            data = os.read(fd, self.EV.size * 64)
        except OSError as e:
            if e.errno != errno.EAGAIN:
                self._close(path)
            return
        for off in range(0, len(data) - self.EV.size + 1, self.EV.size):
            _s, _us, typ, code, value = self.EV.unpack_from(data, off)
            if typ == self.EV_ABS and code in self._hat:
                self._on_hat(code, value)
            elif typ == self.EV_KEY and code in self.DPAD_KEYS:
                self._on_dir(self.DPAD_KEYS[code] if value else None)
            elif typ == self.EV_KEY and code in self.BUTTONS and value == 1:
                self._send(self.BUTTONS[code])

    def _on_hat(self, code, value):
        self._hat[code] = value
        x, y = self._hat[self.ABS_HAT0X], self._hat[self.ABS_HAT0Y]
        key = (Qt.Key_Left if x < 0 else Qt.Key_Right if x > 0 else
               Qt.Key_Up if y < 0 else Qt.Key_Down if y > 0 else None)
        if key != self._held:
            self._on_dir(key)

    def _on_dir(self, key):
        self._stop()
        if key is None:
            return
        self._held = key
        self._send(key)
        self._repeat.start(400)                        # first repeat after 0.4 s

    def _again(self):
        self._repeat.setInterval(110)                  # then about 9 a second
        if self._held is not None:
            self._send(self._held)

    def _stop(self):
        self._repeat.stop()
        self._held = None

    def _send(self, key):
        # only for the launcher itself: a program in front keeps the pad to itself
        if self._backend.running or not self._window.isVisible():
            self._stop()
            return
        for t in (QEvent.KeyPress, QEvent.KeyRelease):
            QGuiApplication.sendEvent(self._window, QKeyEvent(t, key, Qt.NoModifier))


def main():
    # one logical pixel = one screen pixel: the QML is laid out for 1920x1080
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
    app = QGuiApplication(sys.argv[:1])
    for f in ("Quicksand-Bold.ttf", "Quicksand-Medium.ttf"):
        QFontDatabase.addApplicationFont("/usr/share/fonts/truetype/quicksand/" + f)
    cfg = read_config(CONFIG)
    log("config", CONFIG, len(cfg["tiles"]), "tiles")
    backend = Backend(cfg)
    remote = RemoteSetup()
    button = ResetButton()
    btpair = BtPair()
    app.aboutToQuit.connect(remote.stop)
    app.aboutToQuit.connect(btpair.stop)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("remote", remote)
    engine.rootContext().setContextProperty("resetButton", button)
    engine.rootContext().setContextProperty("btpair", btpair)
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "Main.qml")))
    if not engine.rootObjects():
        sys.exit(1)
    # front LED: the launcher is up (mrg5-leds.py blinks the middle LED green while booting)
    if os.path.exists(MICROP):
        subprocess.Popen([MICROP, "set", "middle", "red", "off", "middle", "yellow", "off",
                          "middle", "green", "on"], stdout=subprocess.DEVNULL)
    pads = Pads(backend, engine.rootObjects()[0])  # noqa: F841 (kept alive by this frame)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
