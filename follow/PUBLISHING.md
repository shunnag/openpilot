# Follow publication and administration

The owner controls the repository variables `WPA3_FOLLOW_MODE` and
`WPA3_FOLLOW_BRANCHES`. Workflows never set them. Modes are `off`, `dryrun`,
`state`, and `on`; there is no canary or soak. All four policy branches,
including `release-tizi-staging`, are eligible. A nonempty `replay` input,
including `latest`, always forces dryrun. The optional `wpa_reference` run
also remains an artifact-only qualification run.

`state` can commit system probes, tag reservations and attempts and upload
drafts. Only `on` can publish a kernel release or commit its pin. The
`policy.wpa.auto_publish` switch remains false: WPA candidates/test requests
stay in drafts, no rebuilt supplicant is installed or publicly released.
The independent T3 gate accepts only a matching result and log read without
credentials from `shunnag/wpa3-test-results`. A private draft is not visible
to an anonymous poller; this part does not bypass the publication gate to
bootstrap that channel.

`follow_publish.py` verifies artifacts as data; it never executes a build,
an artifact, or an upstream launcher. `follow_git.py` performs the shared
fast-forward transaction: fetch, detached worktree, fresh brakes, pure
`follow_state.apply`, validation, commit, fresh brakes again, committed-diff
allowlist, normal push. A concurrent update is reapplied on a new head, with
three total attempts. Bot identity and run/key/mode trailers identify each
commit. No-op/status-only commits dispatch no nightly run.

The short follow publish job and the admin job share job-level `wpa3-state`
concurrency with `queue: max` and `cancel-in-progress: false`. Builds and probes
are outside that group. Correctness also uses fast-forward pushes and fresh
state, rather than relying on the group alone.

Release publication reserves both tag numbers in a state commit first.
Uploads target drafts exclusively, with `prerelease: true` and
`make_latest: false`. Every asset is downloaded through the API and compared
with `SHA256SUMS` before publication. The runtime immutable-releases endpoint
must report enabled; the published release must report immutable. The image
and revert are then checked through their public URLs before committing the
pin. Both release publication and every state push re-read the current head,
gate version, pause/withdrawal mirrors and follow workflow state; kernel
transitions also enforce K12. Administrative brake operations can still run
while automatic following is paused or disabled.

Published immutable releases are the recovery source. Mutable releases are
never trusted. A previous draft is abandoned, never deleted; retained Actions
build artifacts are downloaded and reverified before reserving fresh numbers.
If those artifacts have expired, the draft is abandoned and the next detection
rebuilds. Held attempts wait seven days unless forced or the gates change;
only K1 holds retry on relevant ref changes. A force request never bypasses
a brake or rate deferral. Consecutive infrastructure errors escalate on the
third attempt for the same stock/gate/ref identity.

The immutable `provenance.json` contains the complete pin template. Two fields
are null in that asset: its own SHA-256 and GitHub's future `published_at`.
`pin_from_provenance` fills exactly those fields from the asset bytes and the
immutable release response. This avoids a self-referential hash and records
the actual server publication time. Recovery produces exactly the same pin.
The release also retains stock bytes and the public signing key so K9/K11
checks do not depend on a still-live commadist stock URL.

Owner-only `follow-admin` actions:

- `mark-tested`: automatic release tag, device (`mici` or `tizi`), note. Source
  identity comes from immutable provenance; tested devices live in the status
  sidecar. This does not republish composed branches.
- `approve`: stock boot hash, `device_tested=yes|no`, note, and device if tested.
  Only an existing risk-hold draft qualifies; integrity holds and missing
  qualification references cannot be waived. It reruns K9/K13 and never builds.
- `revoke`: automatic release tag and reason. It installs the pause issue,
  commits withdrawal and pause, prefixes the release title with `WITHDRAWN`,
  and dispatches nightly with `upstream=published`. If nightly was disabled,
  it is temporarily enabled, the exact returned dispatch run is monitored,
  and the disabled state is restored in `finally` and an `always()` cleanup.
  Dispatch/run/restore failures produce a `revoke-blocked` issue.
- `unpause`: clears git pause and closes pause mirrors; withdrawals remain.
- `retry`: clears the target attempt and dispatches follow. It does not change
  either owner variable or bypass K12, withdrawal or pause.

Part 4b still supplies nightly's `upstream=published` consumer and broader
nightly integration/notices. Until then a real revoke dispatch will fail
loudly after persisting withdrawal/pause, and restore a previously disabled
nightly. The reviewed K4(e)/K7b reference files are also required before an
automatic kernel can be published. Live queueing, GitHub write semantics,
workflow dispatch and draft-to-immutable behavior still require the sandbox
qualification; local tests mock gh/git and make no network requests.

## UI patch forms

`compose.py` registers two forms of the WPA3 UI change in `UI_PATCHES`:
`ui-wpa3.patch`, and `ui-wpa3-worker.patch` for trees with openpilot #39339
(`057e21249f`), where WifiManager runs its requests on one shared worker thread.
Both make the same `wifi_manager.py` and `networkmanager.py` changes (identical
+/- lines). The worker form only puts `import os` and `import socket` around the
new `import queue`, and its connection test runs the queued request instead of
patching `threading.Thread`. Exactly one form must apply or already be applied;
none or several hold at G5, and `--inputs-only` selects the form as well, also
with tethering and APN off. WPA3-Inputs hashes the selected form's name and bytes.
Trees that take `ui-wpa3.patch` keep their frozen composer digest (snd launcher
with a raylib_nb APN form: 5d8835bd7's `007dd695…`), so their commits and
WPA3-Inputs are unchanged. The #39339 forms (this one and
`tethering-nat-worker.patch`) are frozen at fe9cfa498's `e65e8bed…`; only
`apn-auth-release-agnos20-nb-expmode.patch` hashes the current `compose.py`.
The worker form was run on one comma four on 2026-11-15: the Wi-Fi settings listed networks
and connected.

## Tethering patch forms

With `--tether apply`, `compose.py` picks the tethering form the same way:
`tethering-nat.patch`, or `tethering-nat-worker.patch` for trees with #39339.
Exactly one form must apply on top of the UI patch. If none applies, G5 holds
with a `git apply` error that lists both forms. If both apply, it holds too. A
form that is already upstream holds for review, even when the other form would
apply. WPA3-Inputs keeps `tether` and `tether_patch` (the SHA-256 of the chosen
form). `tethering-nat.patch` trees keep exactly these two keys and their frozen
composer digest, so their commits and WPA3-Inputs are unchanged. The worker form
adds `tether_patch_name` and keeps fe9cfa498's composer digest (`e65e8bed…`). The commit trailer
stays `WPA3-Tethering-Patch: applied`, and G5 prints the chosen form's name.

#39339 runs `set_tethering_active` on WifiManager's one request thread. It also
replaced the `time.sleep(5)` before `sysctl net.ipv4.ip_forward=0` with
`threading.Timer(5, disable_forward)`, so the shared thread is not blocked for
5 s. NetworkManager's shared mode turns forwarding on while the hotspot comes
up. The 5 s wait lets that finish before comma turns forwarding off again when
`set_ipv4_forward(False)` (the network settings pass `False` with full prime).
The worker form adds the same `wifi_manager.py` lines as
`tethering-nat.patch` (identical +/- lines, nothing removed), in the same places:

1. `TETHERING_SUBNET` and `TETHERING_NAT_RULE` after `TETHERING_IP_ADDRESS`.
2. The `_sudo` helper before `normalize_ssid`.
3. In the queued request, the `iptables-legacy -C`/`-A` of the MASQUERADE rule
   right after `activate_connection(block=True)` and before upstream's
   `if not self._ipv4_forward:` timer block, and the `-D` right after
   `_deactivate_connection`. Upstream's timer block is unchanged context.

The timer callback stays upstream's and only turns forwarding off; no
iptables call runs in it. All requests run in order on one thread, so on, off
and on again add and remove the rule in that order and leave at most one rule.
With `tethering-nat.patch`, each toggle had its own thread, and the iptables
calls of quick toggles could run in either order. A timer from an earlier
activation that fires after tethering was turned on again only repeats
`ip_forward=0`. The new activation's timer does the same when forwarding is not
allowed. As before #39339, the timer does not recheck `set_ipv4_forward`, so a
prime change during those 5 s behaves as in comma's code. If an iptables call
fails, the error is logged and the timer still starts. The worker form's test
uses upstream's `OpenpilotTestCase`, runs the queued requests and mocks
`threading.Timer`. `scripts/test_tether_worker.py` runs both composed
`wifi_manager.py` forms against a fake nat table. For toggles that each finish
before the next one, it checks that both forms give the same NetworkManager,
iptables, wait and sysctl sequence. The worker form was device-tested on one
comma four on 2026-11-15 (`agnos20_follow/device_test_206_log_ja.md`): a phone
with mobile data off joined the hotspot while the device used LTE, a quick
off/on (on again 2–3 s after off) left one `openpilot-tethering` rule, and
turning the hotspot off removed it. `ip_forward` stayed 1 after off, as in
upstream's code.

## AGNOS 20 APN patch registry and modem pin

Selection uses the upstream `launch_env.sh` AGNOS_VERSION. Below 20, the existing
APN patches, composed bytes and input identities are preserved. The legacy
`compose.py` input digest is frozen at
`01da873d5ba539bbbeec1ecaccc6208f5c80ae41cc0f7f290bf6b92bcca7a156`;
AGNOS 20 selections are frozen at the composer that introduced them, and only
the newest form hashes the current composer (see [UI patch forms](#ui-patch-forms)). With `--apn auto`, AGNOS >= 20 uses
`apn-auth-nightly-agnos20.patch` or `apn-auth-release-agnos20.patch`. These retain
the v0113 APN store, UI, diagnostics and translations, without the deleted
openpilot modem path. comma's 0.11.3 release (2026-11-20, `52b2b6265`) ends
`app_ja.po` with four Experimental mode entries (toggles.py); its trees take
`apn-auth-release-agnos20-nb-expmode.patch`, which is
`apn-auth-release-agnos20-nb.patch` with only the `app_ja.po` blob index, hunk
header and three context lines changed (the 51 added lines are the same). The
fork's entries then follow upstream's last entry after one blank line, not two.
`publish_branch.sh` explicitly passes `--apn-family nightly` for `nightly` and
`nightly-chestnut`, and `--apn-family release` for `release-*-staging`, to gates,
inputs-only and compose. Local master tests default to nightly. Exactly one
patch in the chosen family must apply; zero or multiple matches hold at G5.
Both families carry `prebuilt`, so it is not used for selection. A release-staging
tree on the 0.11.2 UI holds at G5 until a matching release form exists; this is
an accepted hold. The old release v0113 candidate is superseded for AGNOS >= 20.

After the selected launcher patch, compose applies the separate
`launcher-modem-agnos20.patch` and copies the stdlib-only modem override to
`wpa3/modem.py` (mode 100644, with the upstream MIT license in its header).
G9 and compose's post-check require the UI, complete launcher addition, pinned
launch values and exact override bytes together. Only this exact new path is
added to the output allowlist; AGNOS 20 cannot change the old openpilot modem.
`--apn off` adds neither the modem launcher patch nor the override and rejects
an already-present unbundled APN UI.

The real `20.1` entry in `agnos/pins.json` uses `agnos-20.1-wpa3.4` / `wpa3.sae=4`,
boot `cc3ce53477e58056309a0cab1ddcbd052ba69f9d8eb38e131a375db2c8cb9744`
and the draft's stock provenance. Tag 4 is seeded in allocated_tags and the
`7300706856…` system has the supplied supplicant probe. The release asset is not
yet available: offline checks use `--skip-download`; production URL/download
checks are unchanged and must pass before publication.
The real `20.2` entry uses `agnos-20.2-wpa3.5` / `wpa3.sae=5`,
boot `8781946a19efae45a007c7de683f59a9964f57d603cf75a0fa4339a80090359e`
and stock system `8faed425…`, with its supplied supplicant probe and tag 5 seeded in allocated_tags.
AGNOS 20.2's kernel only drops 3 latency tracers (comma #148).
The 20.2 release asset is not yet uploaded; the same offline and production checks apply.
The `20.5` entry uses `agnos-20.5-wpa3.6` / `wpa3.sae=6`,
boot `1e06f202cb8fb12c20017660476978ed1b75aa8b74b5bcb384e645093c24bfc3` (built on comma's kernel `d3b4243e2`),
stock boot `b457040d…` and stock system `193e949c…`, with its supplicant probe and tag 6 in allocated_tags.
It is NOT device-tested yet, so `device_tested` has no `agnos-20.5-wpa3.6` entry; add one after the device test.
Its release asset is not uploaded, so a tree that sets AGNOS 20.5 holds at G4; the same offline and production checks apply.
The `20.6` entry (openpilot #39314) uses `agnos-20.6-wpa3.7` / `wpa3.sae=7`,
boot `4fc5071b0c9050bed960f2e20438d3ada827f8f0ba907171b7dbeabfeda9978b`
(built on comma's kernel `e88ac80cc` = `d3b4243e2` + the glink SSR race fix, comma #156),
stock boot `2388598c…` and stock system `ec939431…` (agnos-builder `5b865b6c`), with its supplicant probe and tag 7 in allocated_tags.
The pinned image was device-tested on one comma four on 2026-11-15 (`agnos20_follow/device_test_206_log_ja.md`),
on a tree composed from comma's `nightly-chestnut` `acbcc9ea` (AGNOS 20.6, with #39339) with `ui-wpa3-worker.patch`,
`tethering-nat-worker.patch`, `apn-auth-nightly-agnos20-nb.patch` and `launcher-wpa3-snd.patch`.
From the fork's 20.3, the launcher's AGNOS update wrote the other slot after "Download & install" was tapped,
with boot and system from a computer over USB.
On each of 3 boots: SAE with PMF and H2E from boot, the modem override with LTE, and no subsystem restarts or glink errors.
Also checked: the patched wpa_supplicant, the Wi-Fi settings, and the hotspot (quick off/on, rule removed after off).
A power cycle, WPA2-PSK on a mixed WPA2/WPA3 AP and the memory and task limits were checked only on 2026-11-14,
with an earlier build of this image (same kernel source and config, different build identity) on a test tree
built on the device from comma's master.
Not tested: `updated.py` or a Wi-Fi download, APN authentication (CHAP/PAP),
the eSIM screen and the AT-lock wait, driving, and the comma 3X.
`device_tested` has the `agnos-20.6-wpa3.7` entry (2026-11-15, `mici`).
A 20.6 tree holds at G4 until the `agnos-20.6-wpa3.7` release has the boot asset.
Trees that still set AGNOS 20.5 keep resolving to the unchanged `20.5` pin; only AGNOS 20.6 trees resolve to `20.6`.
AGNOS 20 (`51d33446…`) was withdrawn upstream because it had no display.
In follow mode `off`, a same-boot AGNOS 20.x publishes as derived from the newest pin with an equivalent stock boot
(20.6 for comma's 20.6 kernel, 20.5 for the 20.5 kernel, 20.2 for the 20.2/20.3 kernel); an unprobed system only warns at G8.
A stock boot kernel change holds publication until a new WPA3 kernel is built and pinned.

Its optional `modem` object sits alongside `wpa_supplicant`:

```json
"modem": {
  "path": "userspace/modem/agnos-20.6/modem.py",
  "sha256": "<SHA-256 of the shipped override file>",
  "stock_sha256": "71b602d872b978781add8d50894f4904fbca757058f9cfeb505f7a9000add5b4",
  "service_sha256": "371ce23460b7d13a365fb78e27202fbf43c95762a6d9d6b1003f0edd26924dc4"
}
```

Each override matches one stock `modem.py`. Pins 20.1 and 20.2 use
`userspace/modem/agnos-20/modem.py` for stock `c4ceaa996ede974fee9ce4c23dfdf8f5f37345d357c8c0ca0144b9539beea2bf`
(AGNOS 20.1–20.3). Pin 20.5 uses `userspace/modem/agnos-20.5/modem.py` for stock `9e35f0d5…`
(AGNOS 20.4/20.5, agnos-builder #711: udev is gone and modem.py links `/dev/modem_at0|1` itself in `_sync_ports`).
The 20.5 file is the 20.1 override merged onto the new stock with `git merge-file`, with no other edit;
`scripts/test_modem_agnos20.py` checks this against the reviewed stock copies in `follow/reference/agnos20/`
and `follow/reference/agnos20.5/`.
Pin 20.6 uses `userspace/modem/agnos-20.6/modem.py` (`9a1f52fc…`) for stock `71b602d8…`
(AGNOS 20.6, agnos-builder #761: `_at` waits for the AT lock while `_initializing` is set, and `_do_initializing`
became a wrapper that sets the flag, calls the new `_initialize` and resets the flag in `finally`).
The 20.6 file is the 20.5 override plus exactly this stock change. `git merge-file` leaves two conflicts here,
because #761 edits lines next to two fork hunks, so the tests check content identities instead of replaying a merge:
the fork's +/- lines against stock 20.6 equal those against stock 20.5, the override's 20.5 → 20.6 +/- lines equal
stock's, every fork hunk of the old `_do_initializing` is unchanged in `_initialize`, and the wrapper and
`_sync_ports` (non-blocking lock) are byte-identical to stock. The stock copy is in `follow/reference/agnos20.6/`.
Never edit an override file in place: pins hash it.
No gate compares `stock_sha256` with the system image. If a same-boot AGNOS changes the stock
`modem.py`, the derived pin keeps its base's `modem` block, and the launcher leaves the override
inactive (`inactive stock-hash`) until a matching override is pinned.

All three digests must be 64 lowercase hex characters and the path must resolve
to a file inside this repository. The override digest also covers its inline
license. Compose fills `WPA3_MODEM_SHA256`, `WPA3_MODEM_STOCK_SHA256` and
`WPA3_MODEM_SERVICE_SHA256` from this object. The modem launcher patch digest
is included in AGNOS >= 20 APN auto inputs, and the explicit APN family is
included in all AGNOS >= 20 inputs. AGNOS < 20 ignores the family for selection
and hashing. Native resolved pins can carry the same object at the top level.

At launch, both stock files and the shipped override must match their pins.
The launcher installs a runtime service drop-in, binds the override onto
`/usr/comma/modem.py`, and restarts `modem.service`. Before the restart it reads
InvocationID and TimeoutStopUSec. It first waits for a new running invocation,
bounded by the unit's stop timeout plus ten seconds (120 seconds for an
infinite/unreadable duration). Only then does the 20-second success window
start, requiring an active service, a MainPID running that path, and a valid
`/dev/shm/modem` JSON marker `fork_apn_auth` (`none`, `pap` or `chap`). A new
invocation that fails this health check restores stock and records
`<override sha> start`; no new invocation produces `inactive restart-timeout`
without a start record. A reload/bind failure removes the drop-in and reports
`inactive bind`, without recording a start or restarting stock. A re-run with
the override bound waits up to ten seconds through RestartSec for it to become
active. If the crash hook already restored stock and recorded a failure, the
launcher neither counts it twice nor restarts again. Subsequent launches skip
after one start failure or three service failures for that digest. The root
ExecStopPost hook detaches the bind and records the service result on crashes.
It removes `/dev/shm/modem_pppd_auth_*` on every stop, including success; the
launcher also removes those files before restarting stock on rollback.
`/run/wpa3_modem_state` reports every result. The APN settings on mici and tizi
show “APN auth off: stock modem service” only for an `inactive` state, with a
Japanese translation. Missing state or `active` shows no note.

The UI creates `/data/apn_auth` as comma (0700) and writes settings.json atomically
with mode 0600; the stock modem unit also uses `User=comma`, so the override's
read-only equivalent of `apn_auth_store.read()` can read it. Credentials go only
to AT commands and a private 0600 temporary PPP options file; they are absent
from argv, logs, status JSON and `/run`. Stock SIGTERM handling and startup
`sudo killall -9 pppd` are retained. Local stub tests do not establish device
behaviour.
