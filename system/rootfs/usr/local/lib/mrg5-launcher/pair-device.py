#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Roman Lut
"""Search for Bluetooth devices and pair one (checks/41, "Pair Bluetooth Device"; checks/34).

    pair-device.py scan [seconds]       (default 10)
    pair-device.py pair <mac>

The launcher's settings run this. Output is one JSON object per line:

    scan: {"ev": "device", "mac", "name", "kind", "paired"} for every device seen (again when
          its name arrives), then {"ev": "end"}
    pair: {"ev": "state", "state": "searching" | "pairing" | "connecting"}, then
          {"ev": "done", "mac", "name", "connected"} or {"ev": "failed", "reason"}

"done" means connected; for an input device (game pad, keyboard, remote) it means its kernel
input device exists. A device that pairs but does not connect is "failed" ("paired, but ..."):
a PG-9055 whose service search timed out right after pairing stayed in pairing mode while
the dialog said "paired". Connect is tried CONNECT_TRIES times.

scan lists devices with a name or a device class (a Classic device such as the Ipega PG-9055
reports no name in discovery, only its class); nameless LE advertisers are left out.

pair pairs first, then trusts, then connects. Device1.Connect() on an unpaired Classic
device authenticates with "No Bonding", so the kernel keeps no link key and a DualShock 4
cannot reconnect after power-on (checks/34, "Pairing from Blueman"). A device that is
already paired here is removed first and paired afresh: a pad or remote in pairing mode has
dropped its side of the old bond. The device must be in range: pair searches for it again
(BlueZ drops unpaired devices 30 s after it last saw them). A "busy" refusal (the controller
disallowing the page) is retried once.

The discovery filter must not contain "Discoverable" and must contain "DuplicateData":
BlueZ 5.66 (Debian 12) corrupts its heap otherwise (pair-remote.py, top comment).
Agent: NoInputNoOutput, accepts everything; legacy PIN devices get "0000" (pair-remote.py).
"""
import glob
import json
import signal
import sys

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

BLUEZ = "org.bluez"
ADAPTER = "org.bluez.Adapter1"
DEVICE = "org.bluez.Device1"
PROPS = "org.freedesktop.DBus.Properties"
AGENT_PATH = "/mrg5/pair_device/agent"
FIND_WAIT = 30                # s: pair searches this long for the device
PAIR_TIMEOUT = 60             # s
CONNECT_TIMEOUT = 30          # s
CONNECT_TRIES = 3             # Connect attempts after pairing
INPUT_WAIT = 10               # s an input device has to bring up its kernel input device

KINDS = {                     # BlueZ's Icon property -> what the list shows
    "input-gaming": "Game pad", "input-keyboard": "Keyboard", "input-mouse": "Mouse",
    "input-tablet": "Tablet", "audio-headset": "Headset", "audio-headphones": "Headphones",
    "audio-card": "Speaker", "phone": "Phone", "computer": "Computer",
    "video-display": "Display", "multimedia-player": "Player",
}


def emit(**kv):
    print(json.dumps(kv), flush=True)


def err(*a):
    print(*a, file=sys.stderr, flush=True)


class Agent(dbus.service.Object):
    """NoInputNoOutput agent that accepts every request, as simple-agent answering "yes"."""

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        return "0000"

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        return dbus.UInt32(0)

    @dbus.service.method("org.bluez.Agent1", in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        pass


class Bt:
    def __init__(self, bus, loop):
        self.bus = bus
        self.loop = loop
        self.ok = False
        self.agent = False
        self.was_pairable = None
        self.on_device = None          # callback(path, props) for every device seen
        om = dbus.Interface(bus.get_object(BLUEZ, "/"), "org.freedesktop.DBus.ObjectManager")
        self.path = next(p for p, i in om.GetManagedObjects().items() if ADAPTER in i)
        obj = bus.get_object(BLUEZ, self.path)
        self.adapter = dbus.Interface(obj, ADAPTER)
        self.aprops = dbus.Interface(obj, PROPS)
        self.aprops.Set(ADAPTER, "Powered", True)
        bus.add_signal_receiver(self._added, dbus_interface="org.freedesktop.DBus.ObjectManager",
                                signal_name="InterfacesAdded")
        bus.add_signal_receiver(self._changed, dbus_interface=PROPS, signal_name="PropertiesChanged",
                                arg0=DEVICE, path_keyword="path")

    def props(self, path):
        return dbus.Interface(self.bus.get_object(BLUEZ, path), PROPS).GetAll(DEVICE)

    def dev(self, path):
        return dbus.Interface(self.bus.get_object(BLUEZ, path), DEVICE)

    def path_of(self, mac):
        return "%s/dev_%s" % (self.path, mac.upper().replace(":", "_"))

    def _added(self, path, ifaces):
        if DEVICE in ifaces and "RSSI" in ifaces[DEVICE] and self.on_device:
            self.on_device(str(path), ifaces[DEVICE])

    def _changed(self, _iface, changed, _invalidated, path=None):
        if self.on_device and str(path).startswith(self.path + "/") and \
                ("RSSI" in changed or "Name" in changed):
            try:
                self.on_device(str(path), self.props(path))
            except dbus.DBusException:
                pass

    def discover(self, on):
        try:
            if on:
                # no "Discoverable" key: it corrupts bluetoothd 5.66's heap (top comment)
                self.adapter.SetDiscoveryFilter({"Transport": "auto", "DuplicateData": True})
                self.adapter.StartDiscovery()
            else:
                self.adapter.StopDiscovery()
        except dbus.DBusException as e:
            err("discovery %s: %s" % ("start" if on else "stop", e.get_dbus_name()))

    def register_agent(self):
        Agent(self.bus, AGENT_PATH)
        manager = dbus.Interface(self.bus.get_object(BLUEZ, "/org/bluez"), "org.bluez.AgentManager1")
        try:
            manager.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
        except dbus.DBusException as e:
            if not e.get_dbus_name().endswith("AlreadyExists"):
                raise
        # default too: a pad opens its HID channels right after pairing, before it is trusted
        manager.RequestDefaultAgent(AGENT_PATH)
        self.agent = True
        self.was_pairable = bool(self.aprops.Get(ADAPTER, "Pairable"))
        self.aprops.Set(ADAPTER, "Pairable", True)

    def cleanup(self):
        self.discover(False)
        try:
            if self.was_pairable is not None:
                self.aprops.Set(ADAPTER, "Pairable", self.was_pairable)
            if self.agent:
                dbus.Interface(self.bus.get_object(BLUEZ, "/org/bluez"),
                               "org.bluez.AgentManager1").UnregisterAgent(AGENT_PATH)
        except dbus.DBusException:
            pass


def kind_of(p):
    return KINDS.get(str(p.get("Icon", "")), "")


def is_input(p):
    """Game pad, keyboard, mouse, remote: Icon input-*, or the Peripheral major class."""
    return str(p.get("Icon", "")).startswith("input-") or (int(p.get("Class", 0)) >> 8) & 0x1f == 5


def has_input(mac):
    """The device's kernel input device exists (uniq = its address; as pair-remote.py)."""
    for f in glob.glob("/sys/class/input/input*/uniq"):
        try:
            with open(f) as u:
                if u.read().strip().lower() == mac.lower():
                    return True
        except OSError:
            pass
    return False


def scan(bt, seconds):
    seen = {}

    def found(path, p):
        name = str(p.get("Name", ""))
        if not name and "Class" not in p:
            return
        mac = str(p.get("Address", ""))
        entry = (name, bool(p.get("Paired", False)))
        if not mac or seen.get(mac) == entry:
            return
        seen[mac] = entry
        emit(ev="device", mac=mac, name=name or str(p.get("Alias", mac)), kind=kind_of(p),
             paired=entry[1])

    def end():
        bt.ok = True
        bt.loop.quit()
        return False

    bt.on_device = found
    bt.discover(True)
    GLib.timeout_add(seconds * 1000, end)


def pair(bt, mac):
    path = bt.path_of(mac)
    state = {"name": mac, "busy_retry": True, "searching": False}

    def fail(reason):
        emit(ev="failed", reason=reason)
        bt.loop.quit()

    def exists():
        try:
            return bt.props(path)
        except dbus.DBusException:
            return None

    def search():
        emit(ev="state", state="searching")
        state["searching"] = True

        def found(p_path, _p):
            if p_path == path and state["searching"]:
                state["searching"] = False
                bt.on_device = None
                bt.discover(False)
                GLib.timeout_add(500, start_pair)

        def give_up():
            if state["searching"]:
                state["searching"] = False
                fail("not found - is it in pairing mode?")
            return False

        bt.on_device = found
        bt.discover(True)
        GLib.timeout_add(FIND_WAIT * 1000, give_up)

    def start_pair():
        p = exists()
        if p is None:
            fail("not found")
            return False
        state["name"] = str(p.get("Name", "") or p.get("Alias", mac))
        emit(ev="state", state="pairing", name=state["name"])
        bt.dev(path).Pair(reply_handler=paired, error_handler=pair_error, timeout=PAIR_TIMEOUT)
        return False

    def pair_error(e):
        name = e.get_dbus_name()
        if name.endswith("AlreadyExists"):
            paired()
        elif "busy" in str(e).lower() and state["busy_retry"]:
            state["busy_retry"] = False
            err("pair busy, retrying:", e)
            GLib.timeout_add(1500, start_pair)
        else:
            fail(name.rsplit(".", 1)[-1] + (": " + e.get_dbus_message() if e.get_dbus_message() else ""))

    def paired():
        try:
            dbus.Interface(bt.bus.get_object(BLUEZ, path), PROPS).Set(DEVICE, "Trusted", True)
        except dbus.DBusException as e:
            err("trust:", e)
        p = exists() or {}
        state["name"] = str(p.get("Name", "") or state["name"])
        state["input"] = is_input(p)
        state["tries"] = 0
        connect()

    def connect():
        # Connect resolves the services first when they are not known yet; that search can
        # time out right after pairing (the PG-9055, 2026-10-03), so it is tried again
        state["tries"] += 1
        emit(ev="state", state="connecting", name=state["name"])
        bt.dev(path).Connect(reply_handler=connected, error_handler=connect_error,
                             timeout=CONNECT_TIMEOUT)

    def connect_error(e):
        err("connect %d: %s" % (state["tries"], e))
        if e.get_dbus_name().endswith("AlreadyConnected"):
            connected()
        elif state["tries"] < CONNECT_TRIES:
            GLib.timeout_add(2000, lambda: connect() and False)
        else:
            fail("paired, but it did not connect (%s)" % (e.get_dbus_message() or e.get_dbus_name()))

    def connected():
        if not state["input"]:
            done(True)
            return
        # an input device is working once the kernel has its input device (HIDP and HoG
        # both set uniq to the device's address); a connection alone proves nothing
        waited = [0]

        def check():
            if has_input(mac):
                done(True)
                return False
            waited[0] += 1
            if waited[0] < INPUT_WAIT * 2:
                return True
            if state["tries"] < CONNECT_TRIES:
                connect()
            else:
                fail("paired, but no input from it - try again")
            return False
        GLib.timeout_add(500, check)

    def done(connected):
        # paired and trusted: a device that did not connect now connects by itself later
        emit(ev="done", mac=mac, name=state["name"], connected=connected)
        bt.ok = True
        bt.loop.quit()

    bt.register_agent()
    bt.discover(False)
    p = exists()
    if p is not None and p.get("Paired"):
        # in pairing mode it has dropped its side of the bond: pair afresh
        try:
            bt.adapter.RemoveDevice(path)
        except dbus.DBusException as e:
            err("remove:", e)
        p = None
    if p is None:
        search()
    else:
        start_pair()


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("scan", "pair") or \
            (sys.argv[1] == "pair" and len(sys.argv) < 3):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        sys.exit(2)
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    loop = GLib.MainLoop()
    for s in (signal.SIGTERM, signal.SIGINT):
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, s, loop.quit)
    try:
        bt = Bt(bus, loop)
    except (dbus.DBusException, StopIteration) as e:
        emit(ev="failed", reason="Bluetooth is not ready")
        err(e)
        sys.exit(1)
    try:
        if sys.argv[1] == "scan":
            scan(bt, int(sys.argv[2]) if len(sys.argv) > 2 else 10)
        else:
            pair(bt, sys.argv[2])
        loop.run()
    except dbus.DBusException as e:
        emit(ev="failed", reason=e.get_dbus_name().rsplit(".", 1)[-1])
    finally:
        bt.cleanup()
        if sys.argv[1] == "scan":
            emit(ev="end")
    sys.exit(0 if bt.ok else 1)


if __name__ == "__main__":
    main()
