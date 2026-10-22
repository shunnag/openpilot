#!/usr/bin/env bash
# Invoke with bash -eu -o pipefail; the job initialises BARE_REPO once.
set -eu -o pipefail

: "${BRANCH:?}" "${RUNNER_TEMP:?}" "${GH_REPO:?}" "${WPA3_FOLLOW_MODE:?}"
[[ "$BRANCH" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]
BARE_REPO="${BARE_REPO:-$RUNNER_TEMP/wpa3.git}"
BRANCH_TEMP="$RUNNER_TEMP/$BRANCH"
mkdir -p "$BRANCH_TEMP"
export GITHUB_OUTPUT="${GITHUB_OUTPUT:-$BRANCH_TEMP/github_output}"
NIGHTLY_LOG="$BRANCH_TEMP/nightly.log"
export PIN_FILE="$BRANCH_TEMP/pin.json"
: > "$NIGHTLY_LOG"
UPSTREAM_SOURCE="${UPSTREAM_SOURCE:-latest}"
FORCE="${FORCE:-false}"
REASON='fetch or inputs failed'
UPSTREAM=unknown
BOOKKEEPING=false

# All remote writes go through this function. Reads and local composition still
# run in DRY_RUN, including the pins, download gates and installer smoke test.
write() {
  if [ "${DRY_RUN:-0}" = 1 ]; then
    printf 'DRY_RUN:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

report_failure() {
  rc=$?
  trap - EXIT
  if [ "$rc" != 0 ]; then
    if [ "$BOOKKEEPING" = true ]; then
      echo 'failed (issue bookkeeping)' > "$BRANCH_TEMP/result"
    else
      KIND=hold
      if [ "$UPSTREAM_SOURCE" = published ]; then KIND=revoke-blocked; fi
      write python3 scripts/issues.py "$KIND" --branch "$BRANCH" --upstream "${UPSTREAM:-unknown}" --reason "$REASON" --log "$NIGHTLY_LOG" || true
      echo "held/failed ($rc): $REASON" > "$BRANCH_TEMP/result"
    fi
  fi
  exit "$rc"
}
trap report_failure EXIT

close_resolved() {
  write python3 scripts/issues.py hold --branch "$BRANCH" --close --upstream "$UPSTREAM"
  write python3 scripts/issues.py pending --branch "$BRANCH" --close --upstream "$UPSTREAM"
  write python3 scripts/issues.py revoke-blocked --branch "$BRANCH" --close --upstream "$UPSTREAM"
}

require_active_nightly() {
  REASON='nightly workflow state could not be read'
  if [ "${DRY_RUN:-0}" = 1 ] && [ "${DRY_WORKFLOW_STATE+x}" = x ]; then
    WORKFLOW_STATE="$DRY_WORKFLOW_STATE"
  else
    WORKFLOW_STATE=$(gh api "repos/$GH_REPO/actions/workflows/nightly.yml" --jq .state)
  fi
  if [ "$WORKFLOW_STATE" != active ]; then
    echo '::notice::Nightly workflow is disabled; skipping branch.' | tee -a "$NIGHTLY_LOG"
    echo 'skipped (nightly disabled)' > "$BRANCH_TEMP/result"
    exit 0
  fi
}

record_evaluated() {
  if [ "$UPSTREAM_SOURCE" = latest ]; then
    REASON='evaluation marker failed'
    EVALUATED=$(python3 scripts/nightly_skip.py create --repo "$BARE_REPO" --branch "$BRANCH" --head "$WPA3_CI_HEAD" --mode "$MODE" --upstream "$UPSTREAM" --fork "$1" 2>> "$NIGHTLY_LOG")
    [[ "$EVALUATED" =~ ^[0-9a-f]{40}$ ]]
    write git -C "$BARE_REPO" push --force origin "$EVALUATED:refs/wpa3-evaluated/$BRANCH" 2>&1 | tee -a "$NIGHTLY_LOG"
  fi
}

if [ "${DRY_RUN:-0}" = 1 ] && [ "${DRY_HEAD+x}" = x ]; then
  export WPA3_CI_HEAD="$DRY_HEAD"
else
  export WPA3_CI_HEAD="${WPA3_CI_HEAD:-$(git rev-parse HEAD)}"
fi
[[ "$WPA3_CI_HEAD" =~ ^[0-9a-f]{40}$ ]]

case "$BRANCH" in
  nightly) TETHER=apply; APN=auto; APN_FAMILY=nightly ;;
  nightly-chestnut) TETHER=apply; APN=auto; APN_FAMILY=nightly ;;
  release-mici-staging) TETHER=apply; APN=auto; APN_FAMILY=release ;;
  release-tizi-staging) TETHER=apply; APN=auto; APN_FAMILY=release ;;
  *) TETHER=off; APN=off; APN_FAMILY=nightly ;;
esac

# Resolve metadata before fetching any upstream or fork objects.
REMOTE_REFS=$(git ls-remote "https://github.com/$GH_REPO.git" "refs/heads/$BRANCH" "refs/wpa3-evaluated/$BRANCH")
FORK=$(printf '%s\n' "$REMOTE_REFS" | awk -v ref="refs/heads/$BRANCH" '$2 == ref {print $1}')
MARKER=$(printf '%s\n' "$REMOTE_REFS" | awk -v ref="refs/wpa3-evaluated/$BRANCH" '$2 == ref {print $1}')
[[ -z "$FORK" || "$FORK" =~ ^[0-9a-f]{40}$ ]]
[[ -z "$MARKER" || "$MARKER" =~ ^[0-9a-f]{40}$ ]]
echo "Current fork: ${FORK:-absent}" | tee -a "$NIGHTLY_LOG"
if [ "$UPSTREAM_SOURCE" = published ]; then
  if [ -z "$FORK" ]; then
    echo skipped > "$BRANCH_TEMP/result"
    exit 0
  fi
  # A revoke needs the parent; never shallow-fetch the published fork.
  git -C "$BARE_REPO" fetch --no-tags --no-recurse-submodules origin "$FORK" 2>&1 | tee -a "$NIGHTLY_LOG"
  U=$(python3 scripts/nightly.py published-upstream --repo "$BARE_REPO" --published "$FORK")
  if [ -z "$U" ]; then
    echo skipped > "$BRANCH_TEMP/result"
    exit 0
  fi
else
  U=$(git ls-remote https://github.com/commaai/openpilot "refs/heads/$BRANCH" | awk '{print $1}')
  [[ "$U" =~ ^[0-9a-f]{40}$ ]]
  UPSTREAM="$U"
  if [ "$FORCE" != true ] && [ -n "$FORK" ] && [ "${GITHUB_REF:-}" = refs/heads/wpa3-ci ]; then
    SKIP=$(python3 scripts/nightly_skip.py check --upstream "$U" --published "$FORK" --marker "$MARKER")
    if [ "$SKIP" = true ]; then
      echo 'early-skip: unchanged' | tee -a "$NIGHTLY_LOG"
      require_active_nightly
      BOOKKEEPING=true
      close_resolved
      echo unchanged > "$BRANCH_TEMP/result"
      exit 0
    fi
  fi
  if ! [ "$(gh api "repos/commaai/openpilot/commits/$U" --jq '.parents | length')" = 0 ]; then
    echo "::error::Upstream $BRANCH is no longer an orphan commit; this fork's publish design assumes one." | tee -a "$NIGHTLY_LOG"
    exit 1
  fi
fi
UPSTREAM="$U"
echo "Upstream: $U" | tee -a "$NIGHTLY_LOG"

# Withdrawal must fetch the published parent first. Resolve its pin in that
# full repo as before, without relying on an old orphan still existing upstream.
MODE="$WPA3_FOLLOW_MODE"
PIN_REPO="$BARE_REPO"
if [ "$UPSTREAM_SOURCE" = published ]; then
  MODE=off
else
  PIN_REPO="$BRANCH_TEMP/check.git"
  {
    git init --bare "$PIN_REPO"
    git -C "$PIN_REPO" remote add upstream https://github.com/commaai/openpilot
    git -C "$PIN_REPO" fetch --no-tags --filter=blob:none upstream "$U"
  } 2>&1 | tee -a "$NIGHTLY_LOG"
fi

REASON='AGNOS pin could not be resolved'
if python3 scripts/pins.py --repo "$PIN_REPO" --upstream "$UPSTREAM" --out "$PIN_FILE" --follow-mode "$MODE" --branch "$BRANCH" 2>&1 | tee -a "$NIGHTLY_LOG"; then rc=0; else rc=${PIPESTATUS[0]}; fi
if [ "$rc" = 3 ]; then
  write python3 scripts/issues.py pending --branch "$BRANCH" --upstream "$UPSTREAM" --log "$NIGHTLY_LOG" 2>&1 | tee -a "$NIGHTLY_LOG"
  echo "pending_${BRANCH//-/_}=true" >> "$GITHUB_OUTPUT"
  echo pending > "$BRANCH_TEMP/result"
  exit 0
fi
if [ "$rc" != 0 ]; then exit "$rc"; fi

if [ "$UPSTREAM_SOURCE" != published ]; then
  REASON='fetch or inputs failed'
  {
    # --depth=1 marks even a root shallow; receive-pack rejects "shallow update not allowed".
    git -C "$BARE_REPO" fetch --no-tags --no-recurse-submodules https://github.com/commaai/openpilot "$U"
    if [ -n "$FORK" ]; then
      git -C "$BARE_REPO" fetch --depth=1 --no-tags --no-recurse-submodules origin "$FORK"
    fi
  } 2>&1 | tee -a "$NIGHTLY_LOG"
fi
if [ -f "$BARE_REPO/shallow" ] && grep -Fxq "$U" "$BARE_REPO/shallow"; then
  echo '::error::Upstream commit is recorded as shallow; publishing would be rejected.' | tee -a "$NIGHTLY_LOG"
  exit 1
fi
# Keep roots reachable so later fetches can negotiate their shared objects.
git -C "$BARE_REPO" update-ref "refs/wpa3-upstream/$BRANCH" "$U"
if [ "$UPSTREAM_SOURCE" != published ]; then
  mv "$PIN_FILE" "$BRANCH_TEMP/pin.blobless.json"
  REASON='AGNOS pin could not be resolved'
  python3 scripts/pins.py --repo "$BARE_REPO" --upstream "$UPSTREAM" --out "$PIN_FILE" --follow-mode "$MODE" --branch "$BRANCH" 2>&1 | tee -a "$NIGHTLY_LOG"
  REASON='pin mismatch between blobless and full fetch'
  if ! cmp -s "$BRANCH_TEMP/pin.blobless.json" "$PIN_FILE"; then
    echo "PIN: FAIL: $REASON" | tee -a "$NIGHTLY_LOG"
    exit 1
  fi
fi
python3 - <<'PY'
import json
import os
from pathlib import Path
pin = json.loads(Path(os.environ['PIN_FILE']).read_text())
if pin['mode'] != 'pinned':
  base = f" from {pin['base']}" if pin['mode'] == 'derived' else ''
  print(f"::notice::AGNOS pin: {pin['mode']} {pin['version']}{base}")
PY

# Keep the full-repository, exact inputs check as the second skip decision.
REASON='fetch or inputs failed'
if INPUTS=$(python3 scripts/compose.py --repo "$BARE_REPO" --upstream "$UPSTREAM" --pin-file "$PIN_FILE" --tether "$TETHER" --apn "$APN" --apn-family "$APN_FAMILY" --inputs-only 2>> "$NIGHTLY_LOG"); then
  if [ -n "$FORK" ]; then
    PREVIOUS=$(git -C "$BARE_REPO" show -s --format='%(trailers:key=WPA3-Inputs,valueonly)' "$FORK")
    if [ "$PREVIOUS" = "$INPUTS" ] && [ "$FORCE" != true ]; then
      echo unchanged
      require_active_nightly
      BOOKKEEPING=true
      close_resolved
      record_evaluated "$FORK"
      echo unchanged > "$BRANCH_TEMP/result"
      exit 0
    fi
  fi
fi

REASON='gate checks failed'
PUBLISHED_ARGS=()
if [ -n "$FORK" ]; then
  PUBLISHED_ARGS=(--published "$FORK")
fi
if [ "$UPSTREAM_SOURCE" = published ]; then PUBLISHED_ARGS+=(--revoke); fi
python3 scripts/gates.py --repo "$BARE_REPO" --upstream "$UPSTREAM" --pin-file "$PIN_FILE" --tether "$TETHER" --apn "$APN" --apn-family "$APN_FAMILY" "${PUBLISHED_ARGS[@]}" 2>&1 | tee -a "$NIGHTLY_LOG"

REASON='compose failed'
{
  python3 scripts/compose.py --repo "$BARE_REPO" --upstream "$UPSTREAM" --pin-file "$PIN_FILE" --tether "$TETHER" --apn "$APN" --apn-family "$APN_FAMILY" | tee "$BRANCH_TEMP/composed.txt"
} 2>&1 | tee -a "$NIGHTLY_LOG"
# read works with macOS bash 3.2 as well as the runner's bash 5.
IFS= read -r NEW < "$BRANCH_TEMP/composed.txt"
[[ "$NEW" =~ ^[0-9a-f]{40}$ ]]

require_active_nightly
REASON='publish failed'
PUBLISHED=false
if [ "$NEW" = "$FORK" ]; then
  echo 'unchanged (deterministic commit already published)'
else
  {
    if [ -n "$FORK" ]; then
      KEEP_LASTGOOD=$(python3 scripts/nightly.py keep-lastgood --repo "$BARE_REPO" --published "$FORK")
      if [ "$KEEP_LASTGOOD" != true ]; then
        write git -C "$BARE_REPO" push --force origin "$FORK:refs/heads/$BRANCH-lastgood"
      fi
    fi
    write git -C "$BARE_REPO" push --force-with-lease="refs/heads/$BRANCH:$FORK" origin "$NEW:refs/heads/$BRANCH"
  } 2>&1 | tee -a "$NIGHTLY_LOG"
  PUBLISHED=true
fi
BOOKKEEPING=true
REASON='close resolved issues failed'
close_resolved
record_evaluated "$NEW"
echo success > "$BRANCH_TEMP/result"

if [ "$PUBLISHED" = true ]; then
  # A separate bash process keeps errexit active inside the conditional below.
  # Testing a shell function directly with "if" would disable its errexit.
  if bash -eu -o pipefail <<'SMOKE' 2>&1 | tee "$BRANCH_TEMP/smoke.log"
DEVICE_TYPE=mici
if [ "$BRANCH" = release-tizi-staging ]; then DEVICE_TYPE=tizi; fi
STATUS=$(curl -sS --connect-timeout 20 --max-time 120 -A 'AGNOSSetup-19.8' -H "X-openpilot-device-type: $DEVICE_TYPE" \
  -o "$RUNNER_TEMP/$BRANCH/installer.elf" -w '%{http_code}' "https://installer.comma.ai/$OWNER/$BRANCH")
echo "Installer HTTP $STATUS"
[ "$STATUS" = 200 ]
python3 - <<'PYSMOKE'
import os
from pathlib import Path
data = (Path(os.environ['RUNNER_TEMP']) / os.environ['BRANCH'] / 'installer.elf').read_bytes()
assert data.startswith(b'\x7fELF'), 'installer response is not ELF'
expected = f"github.com/{os.environ['OWNER']}/openpilot.git".encode()
assert expected in data, f'installer ELF does not contain {expected!r}'
print('Installer ELF and fork URL verified')
PYSMOKE
SMOKE
  then
    write python3 scripts/issues.py smoke --branch "$BRANCH" --close --upstream "$UPSTREAM" || true
  else
    echo '::warning::Installer smoke test failed. Published nightly is retained.'
    write python3 scripts/issues.py smoke --branch "$BRANCH" --upstream "$UPSTREAM" --reason 'installer smoke test failed' --log "$BRANCH_TEMP/smoke.log" || true
  fi
fi
