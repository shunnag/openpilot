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
