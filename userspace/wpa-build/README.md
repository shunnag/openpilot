# WPA dryrun recipe

The seven patch files are byte-for-byte copies of agnos-builder commit `2c74c82`
(`wpa-supplicant-sae-fixes`). The compile script is parameterized from that commit.
Patch headers and the Ubuntu copyright file are retained; every candidate artifact
includes its extracted `candidate.copyright`, and stock carries `stock.copyright`.

`scripts/wpa_classify.py` authenticates noble indices with the Ubuntu archive
keyring and gpgv, hashes Packages/Sources, matches the stock ELF from the signed
arm64 deb, and pins the reference Debian tarball and upstream orig tarball.
Online lookup tries updates/security and then Launchpad publication snapshots.
Only the noble 2:2.10-21ubuntu0.N family is accepted. Native +agnos holds in v1.

`scripts/wpa_follow.py build` rechecks classification across artifact boundaries,
pulls the policy-pinned Ubuntu digest, exports a recipe without `.git`, and builds
twice in separate containers at `/tmp/wpa`. Apt uses one pinned Ubuntu snapshot
for all packages and build dependencies; apt signatures remain mandatory. HTTPS
bootstraps from the hosted runner's CA bundle (its digest is recorded) before the
snapshot's ca-certificates package is installed.
The changelog date comes from the authenticated source version. Ccache is disabled.

P1 applies the unchanged seven patches through quilt with fuzz 0, checks reverse
application separately, records offsets, and holds non-C offsets over 100 lines.
P2 compares the exact C functions changed by these patches against 0.4 after
Ubuntu's own patches. Unknown/ambiguous C syntax holds. A `git diff -W` report with
line numbers normalized is also retained. R1 requires identical ELF hashes.
R0 is reported only when this output equals `139be31d…`; no state flag is changed.

T0 checks aarch64 ELF, NEEDED/version subsets and BIND_NOW. T1 mounts the verified
AGNOS ext4 image `loop,ro,noload` and overlays only the candidate executable for a
chroot `-v`. T2 uses a scratch `/run` bind for `-Dnone`, checks default `sae_pwe=2`,
then saves 0 and restarts. There is no writable system-image mount.

T3 is the standard-library `hwsim/suite.py`, adapted from our 2026-09-25
`cli_tests.sh` association experiments. The original generic netlink `hwsim.py`
depends on an external module; the runner instead provisions exactly two hwsim
radios with iw in an isolated network namespace. No original Intel generic-netlink
implementation or NetworkManager experiments are included. All names and passwords
in the suite are synthetic, public test values. H2E opt-in is a positive control
for the expected stock-default failure; PMF is checked at hostapd.

See [Mac mini setup](../../follow/macmini/README_ja.md). Requests are artifacts
only until Part 4a. `policy.wpa.auto_publish` stays false. The dryrun publish job
validates optional results, but never creates releases, state commits, or dispatches.
