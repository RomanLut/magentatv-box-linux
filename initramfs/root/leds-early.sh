#!/bin/sh
# Front LEDs as early as possible after BLS1 (checks/25, "Front-panel microcontroller").
# Run as its own process by /init-script (never sourced: a failed `exec 3>` would end
# PID 1) about 1 s after the kernel starts; the Debian service mrg5-leds (work/led/)
# takes over later with the same states:
#   middle LED  green blinking   = booting
#   left LED    red              = no network address yet
# BLS1 leaves both red; without this they stayed red until mrg5-leds started (~19 s).
#
# The controller is on /dev/ttyS2, 38400 8N1. The frames are those of work/led/microp.py
# (BLS1's own LED commands): '-E' <id> <mode> (mode 1 on, 2 off, 3 flash; ids 0-2 middle
# green/red/yellow, 3-5 left) and '-D' 0 <level> (the middle LED's brightness; the left
# LED cannot be dimmed). One byte at a time, 4 ms apart, as BLS1 sends them; the
# controller's '#' replies are not read.

mrg5_led() {
    for b in "$@"; do
        printf "$b" >&3
        usleep 4000
    done
    usleep 20000
}

if [ -c /dev/ttyS2 ] &&
    stty -F /dev/ttyS2 38400 raw -echo -hupcl clocal cs8 -cstopb -parenb -crtscts 2>/dev/null &&
    exec 3>/dev/ttyS2; then
    mrg5_led '\055' '\104' '\000' '\377'    # -D 0 255   middle LED full brightness
    mrg5_led '\055' '\105' '\001' '\002'    # -E 1 off   middle red
    mrg5_led '\055' '\105' '\002' '\002'    # -E 2 off   middle yellow
    mrg5_led '\055' '\105' '\000' '\003'    # -E 0 flash middle green
    mrg5_led '\055' '\105' '\003' '\002'    # -E 3 off   left green
    mrg5_led '\055' '\105' '\005' '\002'    # -E 5 off   left yellow
    mrg5_led '\055' '\105' '\004' '\001'    # -E 4 on    left red
    exec 3>&-
    echo "front LEDs: booting (middle green blinking, left red)"
fi
