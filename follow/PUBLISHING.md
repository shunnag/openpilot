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

## AGNOS 20 APN patch registry and modem pin

Selection uses the upstream `launch_env.sh` AGNOS_VERSION. Below 20, the existing
APN patches, composed bytes and input identities are preserved. The legacy
`compose.py` input digest is frozen at
`01da873d5ba539bbbeec1ecaccc6208f5c80ae41cc0f7f290bf6b92bcca7a156`;
AGNOS 20 and later hash the current composer. With `--apn auto`, AGNOS >= 20 uses
`apn-auth-nightly-agnos20.patch` or `apn-auth-release-agnos20.patch`. These retain
the v0113 APN store, UI, diagnostics and translations, without the deleted
openpilot modem path. `publish_branch.sh` explicitly passes `--apn-family nightly` for `nightly` and
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
AGNOS 20 (`51d33446…`) was withdrawn upstream because it had no display.
In follow mode `off`, same-boot AGNOS 20.x after 20.1 publishes as derived from the 20.1 pin; an unprobed system only warns at G8.
A stock boot kernel change holds publication until a new WPA3 kernel is built and pinned.

Its optional `modem` object sits alongside `wpa_supplicant`:

```json
"modem": {
  "path": "userspace/modem/agnos-20/modem.py",
  "sha256": "<SHA-256 of the shipped override file>",
  "stock_sha256": "c4ceaa996ede974fee9ce4c23dfdf8f5f37345d357c8c0ca0144b9539beea2bf",
  "service_sha256": "371ce23460b7d13a365fb78e27202fbf43c95762a6d9d6b1003f0edd26924dc4"
}
```

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
