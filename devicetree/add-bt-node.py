#!/usr/bin/env python3
"""Describe the onboard RTL8761ATV as a serdev device on UART1 (checks/34), so
the kernel's hci_h5 + btrtl bring it up with free firmware (linux-firmware
rtl_bt/rtl8761a_fw.bin) and no vendor attach tool.

Adds to serial@f040d000 (ttyS1) the child

    bluetooth { compatible = "realtek,rtl8761a-bt"; };

the binding hci_h5 uses for its other Realtek UART parts (rtl8723bs/cs/ds,
rtl8822cs), with the compatible that rtl8761a-uart.py adds to it. The board
has no Bluetooth enable/wake GPIOs in its DT; the h5 Realtek setup treats them
as optional. With the child present, the port is no longer /dev/ttyS1.

usage: add-bt-node.py <in.dtb> <out.dtb>          (in: dtb-kms-pool.bin)
"""
import subprocess
import sys

SRC, DST = sys.argv[1], sys.argv[2]
dts = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", SRC],
                     capture_output=True, text=True, check=True).stdout
assert "rtl8761a-bt" not in dts, "the node is already there"
head = "\t\tserial@f040d000 {\n"
assert dts.count(head) == 1, "serial@f040d000 not found exactly once"
node = ("\n\t\t\tbluetooth {\n"
        "\t\t\t\tcompatible = \"realtek,rtl8761a-bt\";\n"
        "\t\t\t};\n")
# a child node goes after the node's properties: just before its closing brace
start = dts.index(head)
end = dts.index("\n\t\t};", start)
dts = dts[:end] + node + dts[end:]
p = subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", DST],
                   input=dts, capture_output=True, text=True)
if p.returncode:
    sys.exit("dtc failed:\n" + p.stderr)
back = subprocess.run(["dtc", "-I", "dtb", "-O", "dts", DST],
                      capture_output=True, text=True, check=True).stdout
i = back.index("serial@f040d000 {")
print(back[i:i + 400].rstrip())
