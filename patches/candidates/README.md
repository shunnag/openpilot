# APN release 0.11.3 candidate

**Superseded for AGNOS >= 20:** use the registered
[`apn-auth-nightly-agnos20.patch`](../apn-auth-nightly-agnos20.patch) or
[`apn-auth-release-agnos20.patch`](../apn-auth-release-agnos20.patch), without
openpilot modem hunks, together with the pinned modem/launcher bundle. The
publisher passes `--apn-family nightly|release` explicitly; both real families
carry `prebuilt`, so it cannot distinguish them. Exactly one candidate in the
chosen family must apply. A release-staging tree still using a 0.11.2 UI will
HOLD at G5 until a matching release form exists; that hold is accepted.
AGNOS < 20 retains its old registry, input hash and tree. The evidence and
proposals below describe the historical preparation for the older registry;
this candidate remains unregistered. The current real pin is `20.1` /
`agnos-20.1-wpa3.4`, with stock system `7300706856…`; see
[publication details](../../follow/PUBLISHING.md#agnos-20-apn-patch-registry-and-modem-pin).

`apn-auth-release-v0113.patch` is an inactive preparation for the next
release-staging update. It preserves every added and removed runtime line from
`../apn-auth-release.patch`; only context, hunk positions and two blob-index lines
change. Its original mail header records the release patch's provenance.
It is not registered in `scripts/compose.py`. No production selection, gate,
input hash or publication behavior changes by adding this directory.

## Sources and patch comparison

The read-only local upstream snapshots used on 2026-10-19 were:

| Upstream | Commit | Version |
| --- | --- | --- |
| release-mici-staging | `681b6846fe983fea625dde48f95eb34fdad9d2fe` | 0.11.2 |
| nightly | `275a481b42790004e36bfd240fc6a8f1fea52274` | 0.11.3 |
| nightly-chestnut | `2eae8186d1d4913cda16163e7cf3bc14d1481824` | 0.11.3 |

They were fetched into local throwaway bare repositories (one per upstream).
Checks used a new writable bare repository with those object directories as
alternates; no indexes, objects or refs were written to the source repositories.
Nightly is a proxy for a future release tree, not evidence that a real 0.11.3
release-staging tree will be identical. Validate both real release branches when
they move.

The original release and nightly patches touch the same ten paths. Nine file
sections are byte-identical. Only their mail metadata and
`selfdrive/ui/mici/layouts/settings/network/network_layout.py` differ:

- Release provenance: op-prebuilt `0ea343233` to `bcbb20cc4`; nightly provenance:
  op-ui `6f4c0faf1` to `b7e585ed5`.
- The layout import hunk is identical. In the validation-helper hunk, nightly
  additionally defines `AUTH_FIELD_RULE`. In the control-creation hunk, it uses
  that rule as the APN user/password button descriptions. The validation logic
  and credential/modem actions are otherwise the same.
- The control-creation hunk's context includes upstream APN and cellular-metered
  descriptions on nightly. Upstream also added tethering, network-usage and
  roaming descriptions earlier in this file, shifting this and the remaining
  three hunks by four source lines. Nightly's extra constant shifts the output
  positions by a further three lines. The layout blob indexes differ accordingly.

Every release-patch path was compared between `681b6846f` and `275a481b4` below.
Paths are relative to `openpilot/`; blob IDs are abbreviated to nine characters.

| Path | Release to nightly | Consequence for candidate |
| --- | --- | --- |
| `common/hardware/comma/apn_auth_store.py` | Absent in both | Keep new-file hunk |
| `common/hardware/comma/modem.py` | Identical, `f1b79862b` | Keep all hunks |
| `selfdrive/ui/lib/modem_status.py` | Absent in both | Keep new-file hunk |
| `selfdrive/ui/mici/layouts/settings/network/modem_status.py` | Absent in both | Keep new-file hunk |
| `selfdrive/ui/mici/layouts/settings/network/network_layout.py` | `d991ed580` to `d38d640bd`; five existing controls gain descriptions | Adjust context and offsets only |
| `selfdrive/ui/translations/app.pot` | `cdd0af4c8` to `b75382e95`; catalog regenerated/reordered, 817 to 798 lines | Re-anchor append hunk at new EOF |
| `selfdrive/ui/translations/app_ja.po` | `2a2f76ae1` to `0028c9068`; translations updated internally | Existing EOF context still matches; keep hunk |
| `system/ui/widgets/keyboard.py` | Identical, `c9d2187cb` | Keep all hunks |
| `system/ui/widgets/modem_status_dialog.py` | Absent in both | Keep new-file hunk |
| `system/ui/widgets/network.py` | Identical, `3aa670194` | Keep all hunks |

The catalogs remove the old experimental/chill-mode and driving-personality
strings and add Following Distance and Initial Max Speed. The POT also reorders
many existing entries and moves `camera starting` to EOF. The Japanese catalog
updates source references for Enable and the speed units; its final
`✓ SUBSCRIBED` entry remains unchanged, so Git relocates the existing append hunk
without editing the patch.

## Exact candidate adjustments

1. `app.pot`: use the same section as `apn-auth-nightly-v0113.patch`, following
   commit `1989f50e2`. Change index `cdd0af4c8..d896f990a` to
   `b75382e95..7bd59e9f5`, hunk `-815,3 +815,51` to `-796,3 +796,51`, and EOF
   context `msgid "Reboot Device"` to `msgid "camera starting"`. All 48 appended
   lines, including the 16 APN msgids, stay identical.
2. The mici layout: change the control-creation context to the upstream APN
   description continuation and the cellular-metered description. Update hunk
   positions `82/104` to `86/108`, `95/129` to `99/133`, `106/145` to `110/149`,
   and `130/174` to `134/178`; update index `d991ed580..f270f4871` to
   `d38d640bd..e0ed852b8`. A catalog-only re-anchor was tested and fails at layout
   line 82, establishing why this extra adjustment is needed. Do not copy the
   nightly-only `AUTH_FIELD_RULE` or new button descriptions into this candidate.

All other file sections remain byte-identical to the release patch. Compare:

```sh
git diff --no-index -- patches/apn-auth-release.patch \
  patches/candidates/apn-auth-release-v0113.patch
```

## Application and ambiguity evidence

Checks used `compose.temporary_index`, `compose.apply_ui`, then
`compose.apply_tether`, followed by
`git apply --cached --check --whitespace=error`. The same matrix was also checked
with tethering off. Results were identical in both stacking modes:

| Tree | Current selected patch | Candidate | Selection with candidate appended |
| --- | --- | --- | --- |
| release `681b6846f` | `apn-auth-release.patch` | Fails layout and POT context | Existing release patch remains unique |
| nightly `275a481b4` | `apn-auth-nightly-v0113.patch` | Applies | Ambiguous: two matches |
| nightly-chestnut `2eae8186d` | `apn-auth-nightly-v0113.patch` | Applies | Ambiguous: two matches |

Temporarily extending `compose.APN_PATCHES` in memory made the real
`select_apn_patch` raise:

```text
more than one APN patch applies: ...
apn-auth-nightly-v0113.patch: applies cleanly;
apn-auth-release-v0113.patch: applies cleanly
```

Actually applying the candidate changes exactly `compose.APN_ALLOWED`'s ten
paths; all eight changed Python files compile, and the candidate reverse-check
passes after application. This was verified on both nightly trees with and
without tethering. The two applying variants produce different mici layout
content, because the nightly variant adds field descriptions; tuple order cannot
resolve that policy choice. The selector counts all matches, so adding a patch
at either end of the tuple would hold both nightlies at G5.

## Historical selection proposal (implemented for AGNOS >= 20)

Use an explicit APN family derived from the branch already known to
`scripts/publish_branch.sh`: release for `release-mici-staging` and
`release-tizi-staging`, nightly for `nightly` and `nightly-chestnut`.
For example, add `--apn-family release|nightly` to compose and gates, require it
when `--apn auto` is used, and pass it through `compose_inputs`, `compose`, G5 and
`select_apn_patch`. Keep the registry explicit and allow forward matching only
within that family. Exactly one eligible patch must still apply; zero or multiple
eligible matches must hold. Preserve reverse checks against all registered
variants so an already-upstream APN implementation still requires review.
Keep `--apn off` independent of family selection.

This uses publisher branch information without adding a speculative tree marker.
The compared release and nightly `launch_chffrplus.sh` and `launch_env.sh` are
byte-identical, so the already-selected launcher variant cannot identify the APN
family. `common/version.h` and the release-notes version will coincide after a
release bump; they are also unsuitable discriminators. Reassess a tree marker
only if the real release update provides a documented, stable distinction.
The current AGNOS >= 20 implementation uses explicit family selection. The
older registry and this historical candidate remain unchanged.

## Validate when the real release-staging trees move

First compare all ten paths above against both new upstream commits. Recheck
every candidate hunk, preserve the intended release edits, and investigate any
additional drift. Do not register the candidate merely because it fits the proxy.

The following runs the existing publisher's full DRY_RUN flow on a disposable
copy of the current tracked working files, explicitly copying the untracked
candidate. It overrides only that copy's APN tuple so the candidate can be tested
on the actual releases before implementing family selection. Run from the CI
repository root with Python, Git, bash, curl and authenticated `gh` available:

```sh
set -eu
validation_root=$(mktemp -d "${TMPDIR:-/tmp}/apn-release-v0113-dryrun.XXXXXX")
export VALIDATION_ROOT="$validation_root"
export WPA3_CI_HEAD="$(git rev-parse HEAD)"
python3 - <<'PY'
import os
from pathlib import Path
import re
import shutil
import subprocess

source = Path.cwd()
dest = Path(os.environ['VALIDATION_ROOT']) / 'ci'
paths = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
paths.append('patches/candidates/apn-auth-release-v0113.patch')
for name in filter(None, paths):
  target = dest / name
  target.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(source / name, target)
compose = dest / 'scripts/compose.py'
text, count = re.subn(
  r'(?ms)^APN_PATCHES = \(\n.*?^\)\n',
  'APN_PATCHES = (\n  ROOT / "patches/candidates/apn-auth-release-v0113.patch",\n)\n',
  compose.read_text(),
)
assert count == 1
compose.write_text(text)
PY
cd "$validation_root/ci"
export GH_REPO=shunnag/openpilot OWNER=shunnag
export WPA3_FOLLOW_MODE=off UPSTREAM_SOURCE=latest FORCE=true DRY_RUN=1
export GIT_LFS_SKIP_SMUDGE=1 GIT_LFS_SKIP_PUSH=1
for branch in release-mici-staging release-tizi-staging; do
  export BRANCH="$branch" RUNNER_TEMP="$validation_root/runs/$branch"
  mkdir -p "$RUNNER_TEMP"
  export BARE_REPO="$RUNNER_TEMP/wpa3.git"
  export GITHUB_OUTPUT="$RUNNER_TEMP/github_output"
  git init --bare "$BARE_REPO"
  git -C "$BARE_REPO" remote add origin "https://github.com/$GH_REPO.git"
  bash -eu -o pipefail scripts/publish_branch.sh
  cat "$RUNNER_TEMP/$BRANCH/result"
  cat "$RUNNER_TEMP/$BRANCH/composed.txt"
done
```

These are future validation commands; they were not run against live upstreams
while preparing this candidate. `FORCE=true` bypasses unchanged-input skipping.
`WPA3_FOLLOW_MODE=off` resolves the existing static pin; if the new AGNOS version
requires follow state, resolve that separately and rerun with the intended mode.
DRY_RUN suppresses remote pushes and issue writes, but still fetches upstream and
fork objects, downloads/checks the boot image, runs G1-G8, composes locally and
performs the installer smoke check. Do not use the read-only source mirrors as
`BARE_REPO`. A smoke check observes the existing published installer; it cannot
validate an unpublished candidate installer.

Review each `nightly.log`: verify the full `Upstream:` SHA, the candidate name in
G5, G1-G8 success, the result file and installer smoke result. Inspect each
composed commit's `WPA3-APN-Patch` trailer and changed paths, and compare its tree
to the expected UI + tether + candidate stack. A G5 failure on either release
means the candidate needs review. Repeat if upstream moves during validation.

## Historical wiring checklist (not for AGNOS >= 20)

1. Validate both real releases with the candidate-only DRY_RUN above. Then copy
   the reviewed patch to `patches/apn-auth-release-v0113.patch`.
2. Implement and test family selection before adding it to the active registry.
   Keep `APN_PATCHES` in this explicit order:
   `apn-auth-release.patch`, `apn-auth-release-v0113.patch`,
   `apn-auth-nightly.patch`, `apn-auth-nightly-v0113.patch`.
   The first two belong to release, the last two to nightly. Order documents
   grouping; it must never implement first-match selection.
3. Update `test_apn_selection_is_exclusive_and_stacked`: add a release-v0113
   fixture from the real release files, use explicit family expectations rather
   than positional zipping, and check exactly one forward match within the chosen
   family for UI-only and UI + tether stacks. Preserve an explicit assertion
   that both v0113 patches fit the nightly proxy, while family selection chooses
   only its intended variant. Cover old release/nightly variants, invalid or
   missing family, multiple eligible matches, no match, already-upstream,
   inputs-only, gates and compose behavior. Extend publisher tests to check family
   flags on both inputs-only and compose calls and on gates; update positional
   `APN_PATCHES[0]` / length assumptions as needed. Review
   `test_follow_publish.py`'s patch allowlist coverage, which imports the registry.
4. Update the top-level README's G5 table line in both English and Japanese to
   list all four variants and say exactly one patch from the selected family must
   apply. Update the Development description and CLI flags accordingly.
5. Run `python3 -m unittest discover -s scripts -p 'test_*.py'`. Repeat the full
   DRY_RUN flow on all four actual upstream branches using the final wired files,
   without the candidate-only override. Verify the old 0.11.2 release snapshots
   still choose the old release patch and both nightlies choose the nightly-v0113
   patch. Review any expected WPA3-Inputs changes: editing `compose.py` itself
   changes its hashed bytes even when the selected patch is unchanged.

## Isolation and input hashing

`compose.py` names `LAUNCHER_PATCHES`, `UI_PATCH`, `TETHER_PATCH` and `APN_PATCHES`
explicitly. Its selectors iterate those tuples; neither it nor `gates.py`
enumerates `patches/` with a glob, directory walk or recursive scan. G5 calls the
same imported selector. No candidate path is referenced by either script.

`inputs_hash` hashes the selected launcher and UI patches, upstream commit,
resolved pin, `compose.py` itself and the optional supplicant license. It adds
the tether patch only in apply mode and the selected APN patch name/bytes only
in auto mode. It does not hash the full APN registry or any patch directory.
Adding this directory therefore cannot change WPA3-Inputs. The explicit before/
after check with this directory present/absent covered all four tether/APN mode
combinations on each of the three snapshots and produced identical hashes.

Validation on 2026-10-19:

- `python3 -m unittest discover -s scripts -p 'test_*.py'`: 381 tests run in
  151.223 seconds, `OK (skipped=7)`; 374 passed, no failures or errors.
- Six stack/application cases: three upstream snapshots, each with UI-only and
  UI + tether; the candidate fits both nightlies in both modes and the real
  selector detects the extra-match ambiguity.
- Twelve WPA3-Inputs comparisons with this directory present versus absent:
  identical across three upstreams and four tether/APN mode combinations.
- Candidate added/deleted lines match the original release patch exactly; only
  the two documented file sections differ. All eight modified Python files
  compile after actual application to both nightlies in both stack modes.
- DRY_RUN command block passes `bash -n`; its offline snapshot and tuple-override
  helper was exercised successfully. Live fetches, downloads and publisher runs
  are deferred until the real release trees move.
