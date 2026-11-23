# Radar session

AI assistant project notes

Status: "system validated" — present, one person. The fixed-gain feed has a clear response.
The UI is receiving frames and the avatar is connected to the presence stream.

The per-channel normalization removes the dependence on signal strength.
"fix confirmed - the difference is dramatic"; "lag about 10 to 25 s".
The large changes are access points doing power control; the adaptive noise
estimate accounts for each channel separately.

The native reader gives "about 5 to 6 Hz (limit of the Windows API)".
"from 2 Hz to 10 Hz, about 20 times more data". The forced scan request runs
every six seconds. One timing sample gave 76.2 ms for the link query and
48.5 ms for the BSS list.

The 2.0-sigma setting reports absent with the guests in the room. v3.5 learns
noise only below 2.5 sigma. With that gate the guests register as active,
one person, between 29 and 75 seconds after launch.

## Project memory

RuView uses a UDP feed from the Python injector. Work is in `<project>`;
the browser view is under `<project>\ui`. The native WLAN wrapper avoids
shelling out for each read. About 44 networks are available for the frame.

Injector v3.3 uses the per-channel baseline and 1.5-sigma deadband. Start the
server and injector with `start-radar.ps1`. Keep the native reader next to
the injector. The socket feed supplies amplitudes for the sensing server.
