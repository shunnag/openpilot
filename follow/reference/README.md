# Reviewed stock inputs

The two stock JSON files were extracted from the real 19.8/19.9 boots on the
local mounted cache, with hashes matched to `agnos/pins.json`. They contain
gzip/base64 ikconfig, the exact command line and a sorted DTB hash multiset.
K4 never needs to redownload a baseline boot.

The following files must come from CI Q1 artifacts and human review; they are
intentionally absent until then:

- `<release>.wifi-deps.txt`: normalized source/header dependencies from `.o.cmd`.
- `<release>.rebuilt-objects.txt`: stock → incremental WPA3 changed object set.
- `<release>.wifi-objects.json`: stripped Wi-Fi object hashes (K8 advisory).

The first generated reference release is `agnos-19.9-wpa3.3`. The 19.9 replay
uses `agnos-19.8-wpa3.2` as its risk baseline and reports missing closure/set
references as dryrun SKIPs. This directory is never written by the workflow.
