#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Roman Lut
"""Pair the MagentaTV remote with BlueZ (checks/41, "Remote pairing screen"; checks/34).

    pair-remote.py [name-prefix]        (default DTG5-RCU, the remote's name)

Searches for a remote in pairing mode (hold the button with the red icon until its LED
blinks green), pairs with it, trusts and connects it. It keeps searching after a failed
attempt and ends once a remote is paired (exit 0), or when stopped (SIGTERM/SIGINT, exit 1).
Progress goes to stdout, one line per step, for the launcher:

    searching | found <mac> <name> | removed <mac> | pairing <mac> | paired <mac>
    | failed <mac> <reason> | ready <mac>

A remote with no bond here is paired as soon as it advertises. A remote still bonded here
(it forgets its side of the bond when it enters pairing mode) counts once it advertises
without reconnecting for BONDED_WAIT seconds: a bonded remote woken by a key press
reconnects within about a second, one in pairing mode never does. Its old bond is then
removed and it pairs afresh. So a working remote is left alone. A bonded remote that
connects while this runs (in pairing mode it reconnects with the stored bond when the box
still has it; the LED stops blinking) is paired already: that ends it too ("ready").

"ready" always means the remote's kernel input device exists (BlueZ's HoG creates it
through uhid, `uniq` = the remote's address, once the link is encrypted and the report map
read). A connection alone proves nothing: after the remote paired with another system on the
same Bluetooth adapter (the USB system stick is a copy of this one), it holds new keys and
the box the old ones. It then connects, every encrypted read fails ("Request attribute has
encountered an unlikely error"), and no input device appears. A bonded remote that connects
without one within INPUT_WAIT seconds therefore has a stale bond: it is removed and the
remote pairs afresh.

The discovery filter must not contain "Discoverable": BlueZ 5.66 (Debian 12) reads that
D-Bus boolean (4 bytes) straight into a 1-byte bool at the end of a 20-byte heap block
(src/adapter.c parse_discoverable; upstream reads into a dbus_bool_t since) and
bluetoothd later aborts with heap corruption ("realloc(): invalid next size", valgrind:
"Invalid write of size 4 ... 17 bytes inside a block of size 20"). "DuplicateData" is
parsed the same way but lands inside the struct, and it must be given: 5.66 leaves both
bools uninitialised otherwise. It also makes every advertisement count (no dedup).

Modelled on BlueZ's test/simple-agent and test/test-discovery (org.bluez.Agent1 with
NoInputNoOutput, Adapter1.SetDiscoveryFilter/StartDiscovery, Device1.Pair). On exit
the agent is unregistered, discovery stopped and Pairable set back to what it was.
"""
import glob
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
AGENT_PATH = "/mrg5/pair_remote/agent"
PREFIX = sys.argv[1] if len(sys.argv) > 1 else "DTG5-RCU"
CONNECT_WAIT = 20             # s to wait for the connection after pairing
BONDED_WAIT = 4               # s a bonded remote may advertise before it counts as pairing
INPUT_WAIT = 10               # s a connected, bonded remote has to bring up its input device


def say(*a):
    print(*a, flush=True)


def has_input(mac):
    """The remote's input device exists: HoG sets its uniq to the remote's address."""
    for f in glob.glob("/sys/class/input/input*/uniq"):
        try:
            with open(f) as u:
                if u.read().strip().lower() == mac.lower():
                    return True
        except OSError:
            pass
    return False


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


def err(*a):
    print(*a, file=sys.stderr, flush=True)


class Pairer:
    def __init__(self, bus, loop):
        self.bus = bus
        self.loop = loop
        self.busy = None              # the device being paired
        self.done = False
        self.bonded_seen = set()      # bonded remotes seen advertising, being timed
        self.verifying = set()        # bonded remotes connected, waiting for their input device
        self.was_pairable = None
        Agent(bus, AGENT_PATH)
        bus.add_signal_receiver(self.added, dbus_interface="org.freedesktop.DBus.ObjectManager",
                                signal_name="InterfacesAdded")
        bus.add_signal_receiver(self.changed, dbus_interface=PROPS, signal_name="PropertiesChanged",
                                arg0=DEVICE, path_keyword="path")
        # bluetoothd restarted (it has aborted on bond removal and pairing, checks/34):
        # the agent, Pairable and the discovery filter went with the old daemon
        bus.add_signal_receiver(self.owner, dbus_interface="org.freedesktop.DBus",
                                signal_name="NameOwnerChanged", arg0=BLUEZ)

    def setup(self):
        """Agent, adapter and discovery on the current bluetoothd; True if it must be retried."""
        try:
            manager = dbus.Interface(self.bus.get_object(BLUEZ, "/org/bluez"), "org.bluez.AgentManager1")
            try:
                manager.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
            except dbus.DBusException as e:
                if not e.get_dbus_name().endswith("AlreadyExists"):
                    raise
            manager.RequestDefaultAgent(AGENT_PATH)
            om = dbus.Interface(self.bus.get_object(BLUEZ, "/"), "org.freedesktop.DBus.ObjectManager")
            self.path = next(p for p, i in om.GetManagedObjects().items() if ADAPTER in i)
            obj = self.bus.get_object(BLUEZ, self.path)
            self.adapter = dbus.Interface(obj, ADAPTER)
            self.aprops = dbus.Interface(obj, PROPS)
            if self.was_pairable is None:
                self.was_pairable = bool(self.aprops.Get(ADAPTER, "Pairable"))
            self.aprops.Set(ADAPTER, "Powered", True)
            self.aprops.Set(ADAPTER, "Pairable", True)
            # no "Discoverable" key: it corrupts bluetoothd 5.66's heap (see the top)
            self.adapter.SetDiscoveryFilter({"Transport": "le", "DuplicateData": True})
        except (dbus.DBusException, StopIteration) as e:
            err("setup:", e)
            return True
        self.busy = None
        self.discover(True)
        return False

    def start(self):
        if self.setup():
            GLib.timeout_add(1000, self.setup)
        GLib.timeout_add(2000, self.watch)
        say("searching")

    def owner(self, _name, _old, new):
        if new and not self.done:
            err("bluetoothd restarted")
            GLib.timeout_add(1000, self.setup)

    def stop(self):
        self.discover(False)
        try:
            if self.was_pairable is not None:
                self.aprops.Set(ADAPTER, "Pairable", self.was_pairable)
            dbus.Interface(self.bus.get_object(BLUEZ, "/org/bluez"),
                           "org.bluez.AgentManager1").UnregisterAgent(AGENT_PATH)
        except (dbus.DBusException, AttributeError):
            pass

    def discover(self, on):
        try:
            if on:
                self.adapter.StartDiscovery()
            else:
                self.adapter.StopDiscovery()
        except dbus.DBusException as e:
            # e.g. InProgress right after a stop: watch() tries again
            print("discovery %s: %s" % ("start" if on else "stop", e.get_dbus_name()),
                  file=sys.stderr, flush=True)

    def watch(self):
        """Every 2 s: discovery must run whenever no device is being handled."""
        try:
            if not self.done and not self.busy and not bool(self.aprops.Get(ADAPTER, "Discovering")):
                self.discover(True)
        except (dbus.DBusException, AttributeError) as e:
            err("watch:", e)          # no bluetoothd right now; owner() sets up again
        return not self.done

    def dev(self, path, iface=DEVICE):
        return dbus.Interface(self.bus.get_object(BLUEZ, path), iface)

    def added(self, path, ifaces):
        if DEVICE in ifaces and "RSSI" in ifaces[DEVICE]:
            self.consider(path)

    def changed(self, _iface, changed, _invalidated, path=None):
        # Paired: the remote may also start the pairing itself once it is connected
        if (changed.get("Connected") or changed.get("Paired")) and not self.busy and not self.done:
            self.reconnected(path)
        if "RSSI" in changed or "Name" in changed:
            self.consider(path)

    def reconnected(self, path):
        """A remote bonded here connected: in pairing mode (or woken by a key) it uses the
        stored bond. It is ready once its input device appears; without one the bond is stale
        (the remote has other keys now) and is removed, so the remote pairs afresh."""
        if path in self.verifying:
            return
        try:
            p = self.dev(path, PROPS).GetAll(DEVICE)
        except dbus.DBusException:
            return
        if not (str(p.get("Name", "")).startswith(PREFIX) and p.get("Paired")):
            return
        mac = str(p["Address"])
        self.verifying.add(path)
        say("found", mac, str(p["Name"]))
        waited = [0]

        def check():
            if self.done or self.busy:
                self.verifying.discard(path)
                return False
            if has_input(mac):
                self.verifying.discard(path)
                try:
                    self.dev(path, PROPS).Set(DEVICE, "Trusted", True)
                except dbus.DBusException:
                    pass
                say("ready", mac)
                self.done = True
                self.loop.quit()
                return False
            waited[0] += 1
            if waited[0] < INPUT_WAIT * 2:
                return True
            self.verifying.discard(path)
            try:
                self.adapter.RemoveDevice(path)
            except dbus.DBusException:
                pass
            say("removed", mac)       # stale bond; it is paired when it advertises again
            return False
        GLib.timeout_add(500, check)

    def consider(self, path):
        if self.busy or self.done or not str(path).startswith(self.path + "/"):
            return
        try:
            p = self.dev(path, PROPS).GetAll(DEVICE)
        except dbus.DBusException:
            return
        name = str(p.get("Name", ""))
        if not name.startswith(PREFIX) or p.get("Connected"):
            return
        mac = str(p["Address"])
        if p.get("Paired"):
            # advertising while bonded: a reconnect, or pairing mode if it stays unconnected
            if path not in self.bonded_seen:
                self.bonded_seen.add(path)
                GLib.timeout_add(BONDED_WAIT * 1000, lambda: self.bonded_check(path))
            return
        self.busy = path
        self.discover(False)
        say("found", mac, name)
        say("pairing", mac)
        self.dev(path).Pair(reply_handler=lambda: self.paired(path, mac),
                            error_handler=lambda e: self.failed(path, mac, e), timeout=60)

    def bonded_check(self, path):
        self.bonded_seen.discard(path)
        if self.busy or self.done:
            return False
        try:
            p = self.dev(path, PROPS).GetAll(DEVICE)
        except dbus.DBusException:
            return False
        if p.get("Connected") or not p.get("Paired"):
            return False              # it reconnected: a working remote, left alone
        mac = str(p["Address"])
        say("found", mac, str(p.get("Name", "")))
        # the remote in pairing mode has dropped its side of the old bond
        try:
            self.adapter.RemoveDevice(path)
        except dbus.DBusException:
            pass
        say("removed", mac)           # it is paired when it advertises again
        return False

    def paired(self, path, mac):
        say("paired", mac)
        try:
            self.dev(path, PROPS).Set(DEVICE, "Trusted", True)
        except dbus.DBusException as e:
            say("failed", mac, "trust:" + e.get_dbus_name())
        self.dev(path).Connect(reply_handler=lambda: None, error_handler=lambda e: None, timeout=30)
        self.waited = 0

        def check():
            self.waited += 1
            try:
                connected = bool(self.dev(path, PROPS).Get(DEVICE, "Connected"))
            except dbus.DBusException:
                connected = False
            if connected or self.waited >= CONNECT_WAIT * 2:
                # bonded and trusted: it also connects by itself on its next key press
                say("ready", mac)
                self.done = True
                self.loop.quit()
                return False
            return True
        GLib.timeout_add(500, check)

    def failed(self, path, mac, e):
        say("failed", mac, e.get_dbus_name().rsplit(".", 1)[-1])
        try:
            self.adapter.RemoveDevice(path)
        except dbus.DBusException:
            pass
        self.busy = None
        GLib.timeout_add(1000, self.again)

    def again(self):
        if not self.done:
            self.discover(True)
        return False


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    loop = GLib.MainLoop()
    pairer = Pairer(bus, loop)
    for s in (signal.SIGTERM, signal.SIGINT):
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, s, loop.quit)
    try:
        pairer.start()
        loop.run()
    finally:
        pairer.stop()
    sys.exit(0 if pairer.done else 1)


if __name__ == "__main__":
    main()
