#!/usr/bin/env python3
"""Write rtl_bt/rtl8761a_tv_config.bin for the onboard RTL8761ATV (checks/34):
linux-firmware has none for the 8761A, and btrtl needs one on UART for the
link speed.

Two parts:

- The UART entry (offset 0x000c) is the free RTL8761B config from
  linux-firmware (rtl8761b_config.bin, Debian firmware-realtek), unchanged. As
  btrtl reads it, it matches how the controller ran on the stock system -
  speed word 0x04928002 = 1500000 baud (which UART1 makes exactly from its
  48 MHz baud-mux input, clk-mrg5-uart) and hardware flow control on
  (data[12] = 0x5f, bit 2). The stock entry differs only in data[10] (0xf1
  there, 0xfd here), a field neither btrtl nor our notes name.
- The eleven further entries are the settings of the stock system's
  /lib/firmware/rtlbt/rtl8761a_config (sha256 f73cf2db...), written here as
  values (owner decision 2026-09-28: settings learned from vendor configs may
  be used, vendor binaries not). The stock system sent all of them with the
  firmware we now use too (Realtek's TV rtl8761au_fw, fetch-rtl8761a-tv.sh),
  and so do we. Their meaning is not documented; they look like RF/power
  tuning.

usage: make-rtl8761a-config.py <rtl8761b_config.bin> <out rtl8761a_tv_config.bin>
       make-rtl8761a-config.py --uart-only <rtl8761b_config.bin> <out>
           (the earlier free-only config, for comparison)
"""
import struct
import sys

MAGIC = 0x8723ab55

# offset -> data, in the stock file's order (the UART entry, 0x000c, is second there)
STOCK_SETTINGS = [
    (0x00f4, "0000000005500000"),
    (0x0027, "63"),
    (0x00fe, "01"),
    (0x015b, "0b0b0b0a"),
    (0x017a, "0019"),
    (0x00df, "03"),
    (0x0177, "3d"),
    (0x01b6, "1000b000"),
    (0x00dc, "08"),
    (0x1000, "00ff055d00030001ffffffffff"),
    (0x1040, "2808303000ffffffffffff"),
]

args = sys.argv[1:]
uart_only = args[:1] == ["--uart-only"]
if uart_only:
    args = args[1:]
src = open(args[0], "rb").read()
sig, length = struct.unpack_from("<IH", src, 0)
assert sig == MAGIC, "not a Realtek config"
off, entries = 6, []
while off + 3 <= len(src):
    o, n = struct.unpack_from("<HB", src, off)
    entries.append((o, src[off + 3:off + 3 + n]))
    off += 3 + n
assert [o for o, _ in entries] == [0x000c], "expected only the UART entry: %r" % entries
uart = entries[0][1]
assert len(uart) >= 13 and struct.unpack_from("<I", uart, 0)[0] == 0x04928002

res = [(0x000c, uart)]
if not uart_only:
    res += [(o, bytes.fromhex(v)) for o, v in STOCK_SETTINGS]
body = b"".join(struct.pack("<HB", o, len(v)) + v for o, v in res)
out = struct.pack("<IH", MAGIC, len(body)) + body
open(args[1], "wb").write(out)
print("%s: %d bytes, UART entry %s (1500000 baud, flow control %s), %d more entries"
      % (args[1], len(out), uart.hex(), "on" if uart[12] & 4 else "off", len(res) - 1))
