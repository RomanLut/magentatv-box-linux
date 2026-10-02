# Wi-Fi pairing

The box's Wi-Fi is handled by its separate Wi-Fi board, which runs its own original Telekom
firmware (see [hardware.md](hardware.md#wifi-board)). This project does not change it, so Wi-Fi
is set up exactly as on the original device: with the buttons on the front of the box. Linux
needs no Wi-Fi settings. Once the Wi-Fi board is connected, Linux gets its network access through
it.

The steps below follow Telekom's
[MagentaTV Box operating manual](https://gzhls.at/blob/ldb/4/f/9/f/43f9dfc84250b9777c1bcdaaea6e98fef420.pdf)
(German).

## Buttons and lights

| Where | Button / light | What it does |
|---|---|---|
| Front | **Wi-Fi button** | Switches the box's Wi-Fi or mesh network on or off. It lights up to show the Wi-Fi state: blinking yellow = not connected yet, green = connected. |
| Front | **"+" button** | Starts WPS pairing. It blinks while pairing is active, for up to 2 minutes. Held for 5 seconds, it shows the network role on the right LED (see below). |
| Front | **Right LED** | Shows the network role for 10 seconds after "+" is held for 5 seconds. It is driven by the Wi-Fi board, not by Linux. |
| Back | **Reset (WLAN)** | Resets the Wi-Fi board's network settings to factory defaults. |

## Pairing with your router (WPS)

Your router must support WPS (on Telekom Speedport routers it is the "Anmelden/WPS" or "+"
button).

1. Power on the box and wait until the **Wi-Fi button blinks yellow**. The Wi-Fi board starts on
   its own, independently of Linux.
2. Press the **"+" button** on the box.
3. Right after that, press the **WPS button** on your router (on a Speedport: "Anmelden/WPS" or
   "+"; on a Speed Home WiFi: "+").
4. When the connection is made, the **Wi-Fi button lights green**. This can take up to 5 minutes.

The Wi-Fi board remembers the connection. Linux then gets its address from your router over
Wi-Fi, with no network cable.

## Network roles

Depending on the router and whether a network cable is connected, the Wi-Fi board takes one of
these roles:

| Router | Network cable | Role |
|---|---|---|
| Speedport with mesh, or Speed Home WiFi | not connected | mesh repeater |
| Speedport with mesh | connected | mesh repeater |
| Speedport without mesh, or another router | not connected | Wi-Fi repeater |
| Speedport without mesh, or another router | connected | mesh base |

In every role the box also extends your Wi-Fi network, so other devices can connect through it.
A mesh network can have up to 6 mesh devices.

To check the role, hold the **"+" button** for 5 seconds. For 10 seconds the right LED shows it:
**blinking** = mesh repeater, **steady** = mesh base or Wi-Fi repeater. The manual tells the two
steady states apart by colour, which it shows only in its pictures.

## Sharing the connection over the network socket

When the box is connected over Wi-Fi, its network socket can connect another device, for example
a smart TV, to the internet. The socket is on the Wi-Fi board's network switch.

## Resetting the network settings

1. Let the box run for at least 2 minutes.
2. Press the **Reset (WLAN)** button on the back with a pointed object until the Wi-Fi button,
   the "+" button and the right LED blink. The rear cover may have to come off first.
3. The reset is done when the **Wi-Fi button blinks yellow**. Pair again as described above.

If the box is a mesh base, the reset breaks up the mesh network, and all connected mesh repeaters
that are switched on are reset too. If it is a mesh repeater, only the box itself is reset.

If automatic pairing does not work, the manual describes a manual mesh setup: reset the network
settings, connect the box to the router with a network cable, and finish the setup in the
router's web interface. The box then becomes the mesh base.
