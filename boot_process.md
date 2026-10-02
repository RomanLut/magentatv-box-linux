# The secure boot process

## Boot chain

The box uses Broadcom's secure boot. Each stage checks the next before it runs it:

```
BootROM (in the SoC)
  → BFW   Broadcom firmware, NOR 0x000000
  → BLS1  first boot loader, based on Broadcom BOLT v1.42, NOR 0x080000
  → BLS2  second boot loader, NOR 0x200000 and 0x400000 (two copies, A/B), encrypted
  → stock Linux 4.9 from the eMMC, stored encrypted
```

- **BootROM → BFW.** The ROM inside the SoC loads BFW from the NOR flash. Keys in the SoC's
  one-time-programmable memory (OTP) decide what it accepts.
- **BFW → BLS1.** BFW trains the memory and loads BLS1. It checks BLS1's signature before starting
  it, so a modified BLS1 does not run. There is only one copy of BLS1.
- **BLS1 → BLS2.** BLS1 is Broadcom's BOLT boot loader with Telekom's additions. It picks one of
  the two BLS2 copies, checks its signature and decrypts it.
- **BLS2 → Linux.** BLS2 decrypts the stock Linux kernel and its root file system from the eMMC
  and starts them. The eMMC holds no plain-text kernel or file system.

### Recovery

The box counts failed boots in its NOR flash. After three failed attempts to load BLS2, BLS1
marks the current copy as bad and switches to the other one. If both copies are bad, the box goes
into network recovery: it contacts Telekom's disaster-recovery servers and downloads a recovery
image (`JARVIS_T_DE_DRA.img`, encrypted).

Separately, BLS1 contains a service path meant for factory testing: on every boot, if a USB
disk is connected, it runs the script `Testapp6/BOOT/boot.ini` from that disk. This path is what
the project uses.

## How booting Linux is possible

The SoC itself is not cracked. The secure boot chain stays intact, and you cannot change it by
rewriting the flash or the eMMC: a changed boot loader would fail its signature check. No
encryption keys were extracted.

This project works only because BLS1 has the USB service path described above. That is the
"recovery hole" left in the box.

### `boot.ini`

`boot.ini` is a plain-text list of BOLT shell commands. BLS1 runs it from a FAT-formatted USB
stick, from the folder `Testapp6/BOOT/`. The script is not signed. BOLT's own `boot` command can
start an unsigned 32-bit Linux kernel directly. With it, BLS1 skips BLS2 and the whole encrypted
chain, and starts our kernel instead.

A simplified example:

```
load -raw -nz -fatfs -addr=0x08000000 -max=0x20000 usbdisk0:Testapp6/BOOT/dtb.bin;
setenv DT_ADDRESS 8000000;
boot -32 -nopsci -zimg -nz -fatfs usbdisk0:Testapp6/BOOT/zImage;
```

1. `load` reads the device tree, which describes the hardware to Linux, into memory. It is the
   tree the stock system uses, captured from a running box and adjusted.
2. `setenv DT_ADDRESS` tells `boot` to pass that tree to the kernel. `dt` commands can edit it
   before the boot.
3. `boot -32 -zimg` loads the kernel from the stick and jumps to it in 32-bit mode.

Things to know:

- Every command must end with `;`.
- BLS1 reads at most 2048 bytes of the script. Anything after that is cut off.
- BLS1 cannot start 64-bit kernels, which is why the system is 32-bit.
- BLS1 prints nothing on the serial console by default. One `e` command at the start of the
  script patches BLS1 in memory to turn its output on. The patch lives in RAM only and is gone
  after a reboot.

### Booting from the eMMC without a stick

The stock system on the eMMC is encrypted and useless without Telekom's service, so the eMMC can
be reused. One of its partitions, `splash` (64 MB), is formatted as FAT32 and holds the kernel,
the device tree and a `boot.ini`, laid out the same way as on the stick. BOLT reads FAT from eMMC
partitions (`emmcflash0.splash:`) just as it does from USB.

The remaining step is to make BLS1 look there. BOLT runs the command in its environment variable
`STARTUP` early in every boot. We set it once, with BOLT's own command:

```
setenv -p STARTUP "batch -fatfs emmcflash0.splash:Testapp6/BOOT/startup.ini";
```

That stores one line in BOLT's environment block in the NOR flash, which is empty on a stock
box. No boot loader code is changed. Everything else lives in `startup.ini` on the eMMC and can
be changed later without touching the NOR again:

```
waitusb -t=2 -d=usbdisk && batch -fatfs usbdisk0:Testapp6/BOOT/boot.ini;
batch -fatfs emmcflash0.splash:Testapp6/BOOT/boot.ini;
```

- If a USB stick with `Testapp6/BOOT/boot.ini` is connected, the box boots from the stick. A stick
  therefore always works as a rescue.
- Otherwise the box boots Linux from the eMMC.

To undo it, run `unsetenv STARTUP` from a stick's `boot.ini`.
