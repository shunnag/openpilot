# Part 2 verification — 2026-10-02

## Scope and outcome

Implemented Part 2 on `wpa3-ci`, starting and ending at HEAD
`27f670af57d4141ddecdd86420e498f5ed8b27c0`. No commits, pushes or workflow runs.
No changes to nightly.yml, rollback.yml, pins.py, compose.py or gates.py.

Added the read-only workflow, discovery/pre-build/build/assembly scripts,
Q5 comparison, offline harness, 22 tests, replay inputs, stock reference facts
and documentation. The only modified pre-existing tracked file is policy.json:
Ubuntu 20.04 is pinned to the digest from the successful local GCC 8.2 build.
New files are deliberately untracked; nothing was staged.

## Unit suites

All commands exited 0. Tests use standard-library Python and local fixtures.

| Command | Result |
|---|---|
| `python3 -m unittest discover -s scripts -p 'test_*.py' -v` | Ran 198 tests in 51.142s; OK (skipped=3) |
| `python3.12 -m unittest discover -s scripts -p 'test_*.py'` | Ran 198 tests in 50.886s; OK (skipped=3) |
| Requested non-verbose python3 run | Ran 198 tests in 51.783s; OK (skipped=3) |
| Requested python3.12 repeat | Ran 198 tests in 49.964s; OK (skipped=3) |

Full captured output:

- [python3 verbose](/tmp/part2-final-python3-verbose.log)
- [python3.12](/tmp/part2-final-python312.log)
- [requested python3](/tmp/part2-requested-python3.log)
- [requested python3.12](/tmp/part2-requested-python312.log)

The exact `2>&1 | tail -3` output is the same for each requested invocation
because existing shell-test output is flushed after unittest's summary:

```text
WPA3: reverted to stock wpa_supplicant after service failure
WPA3: reverted to stock wpa_supplicant after service failure
PASS: wpa3_supplicant_override (guards, MainPID executable, failure reasons/threshold, busy bind, verified rollback, retained crash hook, unit quoting)
```

## Lint and unchanged files

Each command exited 0 with no output:

```bash
actionlint .github/workflows/*.yml
actionlint -ignore 'unexpected key "queue"' .github/workflows/*.yml
shellcheck scripts/kernel_build.sh
bash -n scripts/kernel_build.sh
python3 -m py_compile scripts/kernel_*.py scripts/test_kernel_follow.py
git diff --check
git diff --exit-code -- .github/workflows/nightly.yml .github/workflows/rollback.yml scripts/pins.py scripts/compose.py scripts/gates.py
```

## Offline discovery and gates

Command (exit 0):

```bash
python3 scripts/kernel_dryrun.py --out /tmp/kernel-follow-final
```

Output:

```text
K1: OK: 8b0e4d289b246a5cc1b0484b25a3f9f8d4772544 from refs/heads/agnos18.1.1@2862c8f8ea69e65a8796967b62889c5060712dc7; refs/heads/xhci-soft-retry-upstream
K0: OK: shape, agnos.py, hash, signature and byte-identical repack
K2: OK: normalized function, recipe blobs and GCC pointer equal policy
K3: OK: 55 changed lines; ancestor=True; commits=3
K4(a): OK: no risk paths (both sides of renames included)
K4(b): OK: stock ikconfig unchanged
K4(c): OK: DTB multiset unchanged (strict interim rule)
K4(d): OK: not paused; untested chain=0
K4(e): SKIP: TODO Q1: reviewed Wi-Fi dependency reference missing; dryrun only
K4(f): OK: stock and builder cmdline unchanged
DRYRUN: OK: cached 19.9 replay; no network, build, remote write or state change
```

[Candidate JSON](/tmp/kernel-follow-final/candidates.json) and
[pre-build report](/tmp/kernel-follow-final/prebuild.json).

The short DESIGN gate command also exits 0 using the documented known-stock
cache defaults:

```bash
python3 scripts/kernel_gates.py --stock /Volumes/agnos/ref199/boot-b9c9b926.img --candidate 8b0e4d289b246a5cc1b0484b25a3f9f8d4772544 --baseline eccd1465 --policy follow/policy.json
```

```text
K0: OK: shape, agnos.py, hash, signature and byte-identical repack
K2: OK: normalized function, recipe blobs and GCC pointer equal policy
K3: OK: 55 changed lines; ancestor=True; commits=3
K4(a): OK: no risk paths (both sides of renames included)
K4(b): OK: stock ikconfig unchanged
K4(c): OK: DTB multiset unchanged (strict interim rule)
K4(d): OK: not paused; untested chain=0
K4(e): SKIP: TODO Q1: reviewed Wi-Fi dependency reference missing; dryrun only
K4(f): OK: stock and builder cmdline unchanged
```

The original network discovery command exits 1, before accessing the network,
as required by the task's network-only-inside-workflow constraint:

```bash
python3 scripts/kernel_discover.py --version 19.9 --stock /Volumes/agnos/ref199/boot-b9c9b926.img --builder-url https://github.com/commaai/agnos-builder --out /tmp/cand.json
```

```text
K1: FAIL: network is allowed only inside the workflow; use --offline with cached repositories
```

The offline harness above runs the same discovery/gate functions against cached
data. The cached PR list is empty, since the deleted PR #631 head was not
available locally; the builder branch yields the required source. Synthetic
repository tests cover same-repository PR heads and rejection of fork/PR-only
kernel sources.

## Source preparation and assembly

Host-only preparation ran against the real cached candidate/baseline in a
fresh temporary clone. It applied both pinned patches and checked/exported the
seven changed files. No make or Docker build was run:

```text
K6: OK: prepared two git archive exports; 7 pinned patched files
K6: patch bytes, normalized diff and seven baseline/candidate blobs agree
source contains .git: False
host git removed: True
```

The dependency parser also processed the existing Mac WPA3 `.o.cmd` files:
1,311 normalized source/header paths; `include/linux/skbuff.h` is included,
`drivers/usb/host/xhci.h` is absent. This measurement was not promoted to a
reviewed CI reference.

Assembly command (exit 0; the manual directory contains hash-checked copies of
the existing tag2 and tag3 images):

```bash
python3 scripts/kernel_assemble.py --stock /Volumes/agnos/ref199/boot-b9c9b926.img --rebuilt-stock /Volumes/agnos/ref199/our-stock-199.Image-dtb --wpa3-boot /Volumes/agnos/boot199/boot-wpa3-sae-h2e-19.9-tag3.img --key /Volumes/agnos/agnos-builder-199/vble-qti.key --manual-dir /tmp/kernel-follow-manual --out /tmp/kernel-follow-assembled
```

```text
K5: OK: rebuild equivalence re-derived from stock and rebuilt Image-dtb bytes
K6: SKIP: local Mac artifact check; no build-job patch proof supplied
K7: OK: only WLAN_FEATURE_SAE changed; MODULE_SIG_FORCE unset
K7b: SKIP: TODO Q1: Mac replay has no CI rebuilt-object manifest
K8: SKIP: TODO Q5: compare two CI builds before qualifying object determinism
K9-selfcheck: OK: ondevice_hash self-check passed for both manual pins
K9: OK: verified signature, header, layout, SAE/RSNXE, stock DTB order; e77c83eb7afd36f762a04d61db7db1b8efbf06bab6d8d244f0e5f027dcabcef2
K11: OK: unchanged stock kernel; verified tagged header/signature
K12: SKIP: local byte check has no publication state
Q1-WPA3: OK: assembled WPA3 image rebuild-equivalent to device-tested manual image
```

The output was independently decompressed and compared with tag3:

```text
tag3 rebuild_equivalent: (True, ['0 differing runs, all build identity', 'appended DTB order differs; contents identical as a multiset'])
assembled hash_raw: e77c83eb7afd36f762a04d61db7db1b8efbf06bab6d8d244f0e5f027dcabcef2
assembled ondevice_hash: e4bf9ed862d1d5667c778679fecb42dcca1bd01f5dbe209eaa44951b651dbb32
revert hash_raw: f58be24e11820ba1a8b1ffe5ee79f243aabb6beb93d28307f2658cce3e9aa89d
```

[Local artifact provenance](/tmp/kernel-follow-assembled/provenance.json).
The raw hash differs from tag3 because assembly deliberately uses comma's
original DTB order. The requested rebuild equivalence holds.

## Remaining GitHub checks and explicit spec adjustments

No clean CI build or workflow execution was performed, per instruction. The
workflow summary has TODOs and artifacts for:

- Q1: actual hosted 19.9/19.8 rebuilds and the negative parent replay; review the
  generated K4(e), K7b and K8 references before committing them.
- Q5: compare two independent same-source builds with
  `kernel_build_data.py compare-wifi`; K8 remains advisory.
- Q7: sampled free-disk minimum, wall time, trusted-head history fetch time,
  and fallback ancestry timing when the fallback is exercised.
- Q8/Q10: hosted checkout and job/concurrency semantics.

The no-write override takes precedence over the design's `follow-dryrun` issue:
there is no issue write step or issues:write token. `queue: max` is deferred
because local actionlint rejects it and the requested plain lint command must
pass; the read-only publish job retains the `wpa3-state` concurrency group.
The writing stage will need the queue setting and its GitHub verification.

Actual stock 19.8/19.9 ikconfig lacks the SAE symbol, since patch 0001 introduces
it. K7 therefore accepts only absent-or-disabled to enabled for that one symbol,
rejects every other delta, and requires MODULE_SIG_FORCE unset. Recipe parsing
handles the real escaped quotes in `dyndbg=\"\"` without relaxing other text.

No reference qualification, resource estimate or K8 determinism result is
claimed. Missing reviewed references are explicit dryrun SKIPs. Optional
certificate pre-generation is not enabled; a length-mismatch retry requires a
centrally reserved spare full-build slot.

## Git outputs

The pre-existing `.autofollow_1001/` and `.relstaging_1001/` directories remain untouched.

```text
 M follow/policy.json
?? .autofollow_1001/
?? .github/workflows/follow.yml
?? .relstaging_1001/
?? follow/PART2-VERIFICATION.md
?? follow/README.md
?? follow/reference/
?? follow/replay/
?? scripts/kernel_assemble.py
?? scripts/kernel_build.sh
?? scripts/kernel_build_data.py
?? scripts/kernel_common.py
?? scripts/kernel_discover.py
?? scripts/kernel_dryrun.py
?? scripts/kernel_follow.py
?? scripts/kernel_gates.py
?? scripts/test_kernel_follow.py
 follow/policy.json | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
```

`git diff --stat` excludes new untracked files. The additions comprise the new
workflow, nine script/test files, replay/reference data, README documentation
and this verification report. No staging was done.

## Orchestrator replay command

After the reviewed changes are made available on the remote branch:

```bash
gh workflow run follow.yml --repo shunnag/openpilot --ref wpa3-ci -f replay=19.9 -f mode=dryrun
```

This command was not executed.
