# Part 3 verification — 2026-10-02

Worktree: `/Users/nagash/Github/OP_wpa3/wpa3-ci`, branch `wpa3-ci`.
HEAD remains `2b22eb529399da1aa8cdbf1dc3d32b13f169602f`.
No commit, push, workflow execution, or SSH connection to the Mac mini was made.

## Changes

Diff summary: 5 existing tracked files changed (+276 / -13 lines), plus 41 new
task files, including fixtures and complete verification outputs. The public
archive keyring was also saved in the pre-existing untracked research directory.

- `scripts/system_probe.py`: streaming xz/sparse hashing, all four chunk types,
  CRC/length bounds, temporary-output disposal on mismatch, read-only debugfs,
  stock/dpkg/changelog extraction, and the 4.9 module-directory check.
- `scripts/wpa_classify.py`: gpgv → InRelease → Packages/Sources → deb/dsc
  verification, W1/W2/W3, Launchpad/snapshot fallback, pinned reference Debian
  tarball, and file-content/mode checks on Debian deltas.
- `userspace/wpa-build/`: parameterized native recipe and seven unchanged patches
  from builder commit `2c74c82`; fixed `/tmp/wpa`, pinned base image and apt
  snapshot `20260925T120000Z`, build logs, debdiff, `.buildinfo`, image/package
  provenance, and copyright files. `wpa_patch.py` implements P1/P2;
  `wpa_abi.py` and `wpa_test.sh` implement T0–T2. R1 builds twice; R0 is reported
  without modifying automatic state.
- `userspace/wpa-build/hwsim/suite.py`: 16 synthetic candidate/stock association
  cases for SAE H&P, H2E defaults/overrides, WPA2, transition PSK, and PMF.
- `follow/macmini/`: poller, strict Python runner, VM adapter, keychain askpass,
  30-minute launchd template and Japanese user setup guide. Only reviewed local
  suite code runs; request bundles are never executed. No host mounts or agent
  forwarding; only the separate public results repository receives writes.
- `scripts/wpa_request.py`: strict request/result schemas, every asset hash and
  size, suite pin, deadline, complete test list and redacted-log digest checks.
- `follow.yml`: read-only `probe`, `wpa-classify`, arm64 `wpa-build` and
  `wpa-test`; artifact-only requests; optional anonymous result verification.
  A prior public request is accepted only for identical rebuilt assets and the
  same suite commit. Missing results print `T3: PENDING (dryrun)`.
- Policy adds the apt snapshot and reference Debian tarball digest.
  `wpa.auto_publish` and seeded `ci_reproduced_reference` remain false.
  Existing G8/R0 enforcement is retained. The existing workflow-structure test
  now expects the four additional jobs; composition regression tests are unchanged.
- 37 new offline tests, including inert request fixtures, hash tampering,
  forbidden shipped commands, real reverse-patch detection, signed-index
  failures, sparse corruption, function identity, VM cleanup, and prior results.

`nightly.yml`, `rollback.yml`, `pins.py`, `compose.py`, `gates.py`, existing
supplicant binaries/copyrights, and `agnos/auto/*` have no diff. The seven patch
files compare byte-for-byte equal with the supplied builder checkout.

## Required verification commands and complete outputs

All commands below were run from the worktree root. The linked text files retain
the full stdout/stderr, including existing launcher integration-test output.

| Command | Result | Full output |
| --- | --- | --- |
| `python3 -m unittest discover -s scripts -p 'test_*.py' -v` | Python 3.14.8; 237 tests, OK (skipped=3) | [python3.txt](verification-part3/python3.txt) |
| `python3.12 -m unittest discover -s scripts -p 'test_*.py'` | Python 3.12.15; 237 tests, OK (skipped=3) | [python3.12.txt](verification-part3/python3.12.txt) |
| `actionlint -ignore 'unexpected key "queue"' .github/workflows/*.yml` | exit 0, no diagnostics | [actionlint.txt](verification-part3/actionlint.txt) |
| `shellcheck scripts/wpa_test.sh userspace/wpa-build/compile-wpasupplicant.sh` | exit 0, no diagnostics | [shellcheck-wpa.txt](verification-part3/shellcheck-wpa.txt) |
| `shellcheck follow/macmini/*.sh` | exit 0, no diagnostics | [shellcheck-macmini.txt](verification-part3/shellcheck-macmini.txt) |

The exact design probe command passed (debugfs 1.47.4 was found at the supplied
Homebrew path):

```bash
python3 scripts/system_probe.py --sparse /Volumes/agnos/sys199/system.img --expect-hash 9aebca09b9d142718e71efbfe44b723010eec6e70067c043c63186067291739d --expect-hash-raw 80d9373348ddff2a5d1f534fab3420383939c96f3eba60baab6b15339fc602c7 --out /tmp/probe199.json && cat /tmp/probe199.json
```

[Full probe output](verification-part3/probe199.txt):

```text
PROBE: OK: 80d9373348ddff2a5d1f534fab3420383939c96f3eba60baab6b15339fc602c7
hash = 9aebca09b9d142718e71efbfe44b723010eec6e70067c043c63186067291739d
hash_raw = 80d9373348ddff2a5d1f534fab3420383939c96f3eba60baab6b15339fc602c7
stock_wpa_sha256 = b0f1c8ee9bb32153faed468c68390db4691b252ffd6a90e6d3d7b49f4d106bdd
dpkg_version = 2:2.10-21ubuntu0.4
changelog_head = wpa (2:2.10-21ubuntu0.4) noble; urgency=medium
kernel_modules_present = false
```

The exact offline classification command was attempted and **held**, exit 1:

```bash
python3 scripts/wpa_classify.py --stock-sha b0f1c8ee9bb32153faed468c68390db4691b252ffd6a90e6d3d7b49f4d106bdd --dpkg-version 2:2.10-21ubuntu0.4 --offline .autofollow_1001/wpa
```

[Full classifier output](verification-part3/classify.txt):

```text
WPA: HOLD: W1: gpgv: can't open '/Users/nagash/Github/OP_wpa3/wpa3-ci/.autofollow_1001/wpa/InRelease': No such file or directory
gpgv: verify signatures failed: No such file or directory
```

The archive keyring was extracted from the hash-verified 19.9 image to
`.autofollow_1001/wpa/ubuntu-archive-keyring.gpg`. The missing InRelease could not
be downloaded: `curl` returned exit 6, `Could not resolve host:
snapshot.ubuntu.com`. The sandbox has restricted network access and does not
permit escalation. No unsigned evidence was substituted for W1.

Supplemental local checks (not a replacement for signed W1) produced:

```text
W2: PASS
W3 baseline self-comparison: []
stock extracted binary SHA256: b0f1c8ee9bb32153faed468c68390db4691b252ffd6a90e6d3d7b49f4d106bdd
```

`git diff --check` passed. The launchd template parsed with `plistlib` and has
`StartInterval=1800`; the poller's [help output](verification-part3/macmini-help.txt)
also passed. A broader optional `shellcheck scripts/*.sh ...` check reported
pre-existing SC1091 warnings in the two launcher test scripts and SC2155/SC2016
in `test_wpa3_supplicant_override.sh`. Those existing scripts were left unchanged;
all requested Part 3 shellcheck targets are clean.

## Checks not satisfied in this environment

1. **Acceptance criterion 3 remains blocked:** the real offline W1–W3 command
   needs a signed InRelease matching its saved Sources/Packages files. The full
   classifier is covered with offline fixtures, but that does not authenticate
   the supplied research cache. Fetch matching signed evidence on a networked
   host and rerun the command; do not disable gpgv.
2. **Native R0/R1, quilt/P2 against the full Ubuntu source, and T0–T3 runtime
   execution remain unverified.** The local Docker API denied access at
   `unix:///Users/nagash/.colima/default/docker.sock`. No build was attempted
   through another mechanism. The user reserved Mac mini installation/testing
   for the orchestrator and prohibited SSH to it from this task.
3. No public request, release, workflow run, result-repository push, keychain
   token installation or launchd installation occurred. Requests are artifacts
   only in Part 3. R0 qualification, the initial Linux `-Dnone` test, and the
   Mac mini self-test must succeed before claiming runtime qualification.

To prepare fresh signed evidence on a networked machine with gpgv and zstd,
using the extracted public keyring (or Ubuntu's installed archive keyring):

```bash
python3 scripts/wpa_classify.py \
  --stock-sha b0f1c8ee9bb32153faed468c68390db4691b252ffd6a90e6d3d7b49f4d106bdd \
  --dpkg-version 2:2.10-21ubuntu0.4 \
  --keyring .autofollow_1001/wpa/ubuntu-archive-keyring.gpg \
  --work /tmp/wpa-signed-evidence --out /tmp/wpa-classified.json
```

## Exact Mac mini self-test commands

After the orchestrator has placed the **reviewed Part 3 commit** in
`~/wpa3-hwsim-code` on the Mac mini and installed the tools described in
[README_ja.md](macmini/README_ja.md), run there:

```bash
cd "$HOME/wpa3-hwsim-code"
WPA3_SUITE_COMMIT=$(git rev-parse HEAD)
git cat-file -e "$WPA3_SUITE_COMMIT:userspace/wpa-build/hwsim/suite.py"
git cat-file -e "$WPA3_SUITE_COMMIT:follow/macmini/vm_run.sh"
bash follow/macmini/wpa3_hwsim_poll.sh \
  --self-test --dry-run --suite-repo "$PWD" --suite-commit "$WPA3_SUITE_COMMIT"
```

This uses the published `139be31d…` candidate and hash-pinned Ubuntu stock.
It requires no request or token, never pushes, starts/stops `wpa3hwsim`, and
writes local self-test JSON/log files. Expected success is 16 PASS cases and
exit 0. Current HEAD `2b22eb529` predates these files and cannot serve as the
suite pin; no nonexistent commit hash has been invented here.
