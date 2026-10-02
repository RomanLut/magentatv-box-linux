#!/usr/bin/env python3
"""Front LEDs as status lights (checks/25, "Front-panel microcontroller"; mrg5-leds.service).

    left LED    red    no IPv4 address on eth0
                green  eth0 has one (DHCP lease)
    middle LED  green, blinking   the system is booting
                green, steady     the TV launcher has started (launcher.py sets it)

Brightness: only the middle LED can be dimmed ('-D' 0; nothing dims the left one, tested
2026-09-29), so it is set to 100 % to match the left LED.

Started early in the boot (before sysinit.target): sets the brightness, the booting blink
and the left LED, then follows eth0's addresses through
`ip -4 monitor address` (netlink events, no polling) and switches the left LED when the
state changes. If it starts while the launcher already runs (a restart of this service),
the middle LED is set to steady green instead of the blink.

Before this service starts, BLS1 sets the LEDs (middle green blinking, then left and middle
red), and the initramfs (work/linux-full-root/leds-early.sh) sets this service's booting
state about 1 s after the kernel starts. When it stops (shutdown) the LEDs are switched
off (ExecStopPost), since the controller keeps them through a reboot.
All LED writes go through `microp`, which serialises access to the controller.
"""
import os
import subprocess
import sys

MICROP = "/usr/local/bin/microp"
IFACE = sys.argv[1] if len(sys.argv) > 1 else "eth0"
BRIGHTNESS = "100"                          # middle LED ('-D' 0), to match the left


def microp(*args):
    subprocess.run([MICROP, *args], stdout=subprocess.DEVNULL, check=False)


def has_address():
    out = subprocess.run(["ip", "-4", "-o", "addr", "show", "dev", IFACE, "scope", "global"],
                         capture_output=True, text=True).stdout
    return " inet " in out


def launcher_running():
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                with open("/proc/%s/cmdline" % pid, "rb") as f:
                    if b"mrg5-launcher/launcher.py" in f.read():
                        return True
            except OSError:
                pass
    return False


def left(ip):
    if ip:
        microp("set", "left", "red", "off", "left", "yellow", "off", "left", "green", "on")
    else:
        microp("set", "left", "green", "off", "left", "yellow", "off", "left", "red", "on")
    print("eth0", "has an address: left green" if ip else "has no address: left red", flush=True)


def main():
    microp("lum", BRIGHTNESS, "0")
    if launcher_running():
        microp("set", "middle", "red", "off", "middle", "yellow", "off", "middle", "green", "on")
    else:
        microp("set", "middle", "red", "off", "middle", "yellow", "off", "middle", "green", "flash")
    state = has_address()
    left(state)
    mon = subprocess.Popen(["ip", "-4", "monitor", "address"], stdout=subprocess.PIPE, text=True)
    for _line in mon.stdout:                    # any address event: look at eth0 again
        now = has_address()
        if now != state:
            state = now
            left(state)
    sys.exit(mon.wait() or 1)


if __name__ == "__main__":
    main()
