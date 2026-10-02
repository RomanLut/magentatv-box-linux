BIOS files for the emulators on this box
========================================

Put BIOS / system files in THIS directory. RetroArch is configured with
    system_directory = /DATA/Games/bios
so every core looks here, and the file names must match exactly (this is a
case-sensitive Linux filesystem).

Run

    bios-check

on the box to see what each core expects, what is present, and whether the file
you put here is the dump the core asks for - it compares the MD5 with the hash the
core documents. `bios-check psx`, `bios-check megacd` and `bios-check --all` give
more detail.

Nothing here is required: every installed core has a built-in fallback, so an
empty directory is a valid state. The files are not needed for Nintendo 64 at all.

What the cores actually need (system -> file)

  psx        scph5500.bin / scph5501.bin / scph5502.bin   PS1 (optional, but the
                                                          built-in HLE BIOS is worse)
  megacd     bios_CD_U.bin / bios_CD_E.bin / bios_CD_J.bin  Sega CD (required for
                                                          CD games: no free BIOS exists)
  pce        syscard3.pce                                   PC Engine CD (same)
  nes        disksys.rom                                    Famicom Disk System games
  gb / gbc   gb_bios.bin / gbc_bios.bin                     boot logo (optional)
  gba        gba_bios.bin                                   boot logo (optional)
  megadrive  bios_MD.bin, sk.bin, sk2chip.bin               optional extras
  snes       dsp1*.rom, st010*.rom, ...                     optional, core HLEs them

BIOS files are copyrighted by Sony, Sega, NEC, Nintendo and others. They are not
shipped with RetroArch or with this box and cannot be downloaded from here: dump
them from your own hardware, or use the core's built-in fallback.

64DD (Nintendo 64 disk drive) is the one N64 case that would need a file - the IPL
as Mupen64plus/IPL.n64 in a subdirectory - and no 64DD support is installed.
