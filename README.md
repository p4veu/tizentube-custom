# TTCC

Custom TizenBrew module built from the clean TizenTube 1.15.0 source
(upstream commit 893b663d35efa558d8bdf9f54f0c4f9a31ab6a07).

Changes:
- direct "Turn off screen / Wyłącz ekran" player button;
- safe wake-up: the first non-media remote-key sequence only restores the picture;
- Play/Pause keeps controlling playback while the Screen Off overlay stays black;
- no global display:block restore, preventing Theme Configuration from appearing on wake;
- DIAL/casting launches gh/p4veu/ttcc rather than the upstream npm module.

Upstream: https://github.com/reisxd/TizenTube
License: GPL-3.0-only
