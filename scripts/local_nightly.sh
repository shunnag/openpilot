#!/usr/bin/env bash
# Run the nightly publish of all four branches off GitHub Actions.
#
# local_nightly_launcher.sh runs this file from a read-only git archive export
# of wpa3-ci and sets WPA3_CI_HEAD to that commit. It does what nightly.yml's
# publish and request-follow jobs do; each branch still runs publish_branch.sh.
# Works with macOS bash 3.2 and bash 5, without GNU-only tools.
#
# Inputs: GH_REPO and WPA3_WORK_ROOT (required), WPA3_CI_HEAD (required),
# GH_TOKEN (required unless DRY_RUN=1), UPSTREAM_SOURCE (latest|published),
# FORCE (true|false), DRY_RUN (0|1), LOCAL_NIGHTLY_TIME_LIMIT and
# LOCAL_NIGHTLY_LOCK_WAIT and LOCAL_NIGHTLY_CALL_LIMIT (each GitHub call outside the
# worker) in seconds. WPA3_FOLLOW_MODE_OVERRIDE is honoured only with DRY_RUN=1
# or the test marker LOCAL_NIGHTLY_TEST=1.
# A dry run from a checkout reads the real repositories and prints the writes:
#   DRY_RUN=1 GH_REPO=<owner>/openpilot WPA3_CI_HEAD=$(git rev-parse origin/wpa3-ci) \
#     WPA3_WORK_ROOT=$(mktemp -d) bash scripts/local_nightly.sh
set -u -o pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd -P) || exit 2
cd "$ROOT" || exit 2

# All remote writes go through this function, as in publish_branch.sh.
write() {
  if [ "${DRY_RUN:-0}" = 1 ]; then
    printf 'DRY_RUN:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

say() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

# Same as nightly.yml's publish job: the shared bare repository, then every
# branch in order. A failed branch never stops the next one.
worker() {
  # nightly.yml also runs "gh auth setup-git" here. The local runner never does:
  # git gets the token only from the per-process credential helper.
  BARE_REPO="$RUNNER_TEMP/wpa3.git"
  export BARE_REPO
  if ! { git init --bare "$BARE_REPO" && git -C "$BARE_REPO" remote add origin "https://github.com/$GH_REPO.git"; }; then
    echo 'shared bare repository setup failed' >> "$LOCAL_RUN_DIR/local-failure"
    return 3
  fi
  : > "$GITHUB_OUTPUT"
  failed=0
  local_failed=0
  for BRANCH in $BRANCHES; do
    echo "=== $BRANCH"
    if (export BRANCH; bash -eu -o pipefail scripts/publish_branch.sh); then
      rc=0
    else
      rc=$?
      failed=1
    fi
    if [ -f "$RUNNER_TEMP/$BRANCH/result" ]; then
      result=$(cat "$RUNNER_TEMP/$BRANCH/result")
    else
      result="failed ($rc)"
      local_failed=1
      echo "publish_branch.sh ended without a result for $BRANCH ($rc)" >> "$LOCAL_RUN_DIR/local-failure"
    fi
    echo "$BRANCH: $result"
    echo "- $BRANCH: $result" >> "$LOCAL_RUN_DIR/summary"
  done
  # Same as nightly.yml's request-follow job: one dispatch for all pending branches.
  if grep -Eq '^pending_[a-z0-9_]+=true$' "$GITHUB_OUTPUT"; then
    echo 'Requesting follow once for all pending branches'
    if ! write gh workflow run follow.yml --ref wpa3-ci --repo "$GH_REPO" -f reason=nightly-pending; then
      local_failed=1
      echo 'follow.yml dispatch for pending branches failed; the token needs Actions write for it' >> "$LOCAL_RUN_DIR/local-failure"
    fi
  fi
  # 4 tells the runner to report even if local-failure could not be written.
  if [ "$local_failed" = 1 ]; then return 4; fi
  return "$failed"
}

if [ "${1:-}" = --worker ]; then
  worker
  exit "$?"
fi

# Runs the worker in its own process group and stops the whole group at the time
# limit, so no git push or gh call outlives the run (macOS has no timeout(1)).
LIMITER='
import os, signal, subprocess, sys, time
limit = int(sys.argv[1])
pidfile = os.environ.pop("LIMITER_PIDFILE", "")
child = subprocess.Popen(sys.argv[2:], start_new_session=True)
if pidfile:
  with open(pidfile, "w") as stream:
    stream.write(str(os.getpid()))
def stop(code):
  for number in (signal.SIGTERM, signal.SIGKILL):
    try:
      os.killpg(child.pid, number)
    except (ProcessLookupError, PermissionError):
      pass
    deadline = time.monotonic() + 30
    while number == signal.SIGTERM and child.poll() is None and time.monotonic() < deadline:
      time.sleep(0.2)
  child.wait()
  sys.exit(code)
for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
  signal.signal(number, lambda received, frame: stop(128 + received))
try:
  code = child.wait(timeout=limit)
except subprocess.TimeoutExpired:
  print(f"LOCAL: FAIL: time limit of {limit} seconds reached; stopping {sys.argv[2:4]}", file=sys.stderr, flush=True)
  stop(124)
sys.exit(code if code >= 0 else 128 - code)
'

# Every GitHub call outside the worker gets its own short bound, so a stalled
# connection cannot hold the lock under a live process forever.
bounded() {
  python3 -c "$LIMITER" "$CALL_LIMIT" "$@"
}

write_bounded() {
  if [ "$DRY_RUN" = 1 ]; then
    write "$@"
  else
    bounded "$@"
  fi
}

# Remove variables a caller (or an Actions-like shell) may have left behind; the
# runner sets every value publish_branch.sh reads explicitly below.
clean_environment() {
  for name in $(compgen -e); do
    case "$name" in
      GH_TOKEN|GH_REPO|DRY_RUN) ;;
      WPA3_FOLLOW_MODE_OVERRIDE)
        if [ "$DRY_RUN" != 1 ] && [ "${LOCAL_NIGHTLY_TEST:-}" != 1 ]; then unset "$name"; fi ;;
      GITHUB_*|RUNNER_*|GIT_*|GH_*|PYTHON*|DRY_*|DYLD_*|LD_PRELOAD|LD_LIBRARY_PATH|BASH_ENV|ENV|CDPATH|SSH_ASKPASS|\
      BARE_REPO|BRANCH|BRANCHES|OWNER|PIN_FILE|MODE|WPA3_FOLLOW_MODE|KERNEL_FOLLOW_NETWORK|LIMITER_PIDFILE)
        unset "$name" 2>/dev/null || true ;;
    esac
  done
}

report_failure() {
  say "LOCAL: FAIL: $1"
  if [ "$DRY_RUN" != 1 ] && [ -z "${GH_TOKEN:-}" ]; then
    say 'LOCAL: no token; the local-runner issue cannot be opened'
    return 0
  fi
  if [ -n "${2:-}" ] && [ -f "$2" ]; then
    write_bounded python3 scripts/issues.py local-runner --reason "$1" --log "$2" || say 'LOCAL: WARN: the local-runner issue could not be opened or updated'
  else
    write_bounded python3 scripts/issues.py local-runner --reason "$1" || say 'LOCAL: WARN: the local-runner issue could not be opened or updated'
  fi
}

process_start() {
  ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' | sed 's/^ //; s/ $//'
}

# A lock is stale when its process is gone or the pid now belongs to a process
# started at another time; a lock without an owner is stale after one minute.
# A live limiter recorded in the lock still holds it: a runner killed without
# its cleanup can leave the worker running.
lock_is_stale() {
  pid=${1%% *}
  case "$pid" in
    ''|*[!0-9]*) [ -n "$(find "$LOCK" -maxdepth 0 -mmin +1 2>/dev/null)" ] || return 1 ;;
    *) [ "$(process_start "$pid")" != "${1#* }" ] || return 1 ;;
  esac
  limiter=$(cat "$LOCK/limiter" 2>/dev/null || true)
  case "${limiter%% *}" in ''|*[!0-9]*) return 0 ;; esac
  [ "$(process_start "${limiter%% *}")" != "${limiter#* }" ]
}

acquire_lock() {
  waited=0
  takeovers=0
  if [ ! -d "$(dirname "$LOCK")" ]; then
    say 'the lock folder is missing'
    return 2
  fi
  while ! mkdir "$LOCK" 2>/dev/null; do
    if [ ! -d "$LOCK" ]; then
      say 'the lock cannot be created'
      return 2
    fi
    holder=$(cat "$LOCK/owner" 2>/dev/null || true)
    if [ "$takeovers" -lt 5 ] && lock_is_stale "$holder"; then
      takeovers=$((takeovers + 1))
      aside="$LOCK.stale.$$.$takeovers"
      # Rename first, then make sure the lock moved aside is the stale one. A lock
      # that another run took in between is put back.
      if mv "$LOCK" "$aside" 2>/dev/null; then
        if [ "$(cat "$aside/owner" 2>/dev/null || true)" = "$holder" ]; then
          say "removed stale lock (${holder:-no owner})"
          rm -rf "$aside"
        elif [ ! -e "$LOCK" ] && mv "$aside" "$LOCK" 2>/dev/null; then
          say 'the lock changed hands meanwhile; it was put back'
        else
          say 'LOCAL: WARN: a lock taken meanwhile could not be put back'
        fi
      fi
      continue
    fi
    if [ "$waited" -ge "$LOCK_WAIT" ]; then
      say "lock held by ${holder:-an unknown process}"
      return 1
    fi
    sleep 10
    waited=$((waited + 10))
  done
  if ! printf '%s %s\n' "$$" "$(process_start "$$")" > "$LOCK/owner"; then
    # An ownerless lock would look stale to the next run within a minute.
    rm -rf "$LOCK"
    say 'the lock owner could not be written'
    return 2
  fi
  LOCKED=1
}

# Keep the logs of the last failed run; drop its repositories.
# shellcheck disable=SC2329 # called from finish, the EXIT trap
keep_failed_logs() {
  keep="$WORK_ROOT/last-failed"
  rm -rf "$keep"
  mkdir -p "$keep" || return 0
  for name in runner.log summary local-failure; do
    if [ -f "$RUN_DIR/$name" ]; then cp "$RUN_DIR/$name" "$keep/"; fi
  done
  for branch in $BRANCHES; do
    if [ -d "$RUNNER_TEMP/$branch" ]; then
      mkdir -p "$keep/$branch"
      for name in nightly.log result smoke.log; do
        if [ -f "$RUNNER_TEMP/$branch/$name" ]; then cp "$RUNNER_TEMP/$branch/$name" "$keep/$branch/"; fi
      done
    fi
  done
}

# shellcheck disable=SC2329 # the EXIT trap
finish() {
  status=$?
  if [ -n "$RUN_DIR" ] && [ -d "$RUN_DIR" ]; then
    if [ "$status" != 0 ]; then keep_failed_logs; fi
    rm -rf "$RUN_DIR"
  fi
  if [ "$LOCKED" = 1 ] && [ "$(cut -d' ' -f1 "$LOCK/owner" 2>/dev/null)" = "$$" ]; then
    rm -rf "$LOCK"
  fi
  say "local nightly finished ($status)"
  exit "$status"
}

signal_code() {
  case "$SIGNAL" in HUP) echo 129 ;; INT) echo 130 ;; *) echo 143 ;; esac
}

# Stop the worker's whole process group through its limiter, then let the EXIT
# trap keep the logs and release the lock. Before the worker starts, just exit.
# shellcheck disable=SC2329 # the TERM, HUP and INT traps
on_signal() {
  SIGNAL=$1
  say "LOCAL: received SIG$1; stopping the run"
  case "$WORKER_STARTED" in
    0) exit "$(signal_code)" ;;
    2) return 0 ;;  # the worker is done; the run ends with the signal's code
  esac
  tries=0
  while [ ! -s "$RUN_DIR/limiter.pid" ] && [ "$tries" -lt 25 ]; do
    sleep 0.2
    tries=$((tries + 1))
  done
  if [ -s "$RUN_DIR/limiter.pid" ]; then kill -TERM "$(cat "$RUN_DIR/limiter.pid")" 2>/dev/null || true; fi
}

read_follow_mode() {
  if [ -n "${WPA3_FOLLOW_MODE_OVERRIDE:-}" ]; then
    mode=$WPA3_FOLLOW_MODE_OVERRIDE
    say "WPA3_FOLLOW_MODE from WPA3_FOLLOW_MODE_OVERRIDE: $mode"
  elif mode=$(bounded gh variable get WPA3_FOLLOW_MODE --repo "$GH_REPO"); then
    # nightly.yml uses vars.WPA3_FOLLOW_MODE || 'off'.
    if [ -z "$mode" ]; then mode=off; fi
  elif names=$(bounded gh variable list --repo "$GH_REPO" --json name --jq '.[].name'); then
    # Only a successful listing proves that the variable does not exist.
    if printf '%s\n' "$names" | grep -Fxq WPA3_FOLLOW_MODE; then
      return 1
    fi
    mode=off
    say 'WPA3_FOLLOW_MODE is not set; using off'
  else
    return 1
  fi
  case "$mode" in
    off|dryrun|state|on) ;;
    *) say "invalid WPA3_FOLLOW_MODE"; return 1 ;;
  esac
  WPA3_FOLLOW_MODE=$mode
  export WPA3_FOLLOW_MODE
}

RUN_DIR=
LOCKED=0
SIGNAL=
WORKER_STARTED=0
DRY_RUN=${DRY_RUN:-0}
UPSTREAM_SOURCE=${UPSTREAM_SOURCE:-latest}
FORCE=${FORCE:-false}
WORK_ROOT=${WPA3_WORK_ROOT:-}
LIMIT=${LOCAL_NIGHTLY_TIME_LIMIT:-5400}
LOCK_WAIT=${LOCAL_NIGHTLY_LOCK_WAIT:-1800}
CALL_LIMIT=${LOCAL_NIGHTLY_CALL_LIMIT:-300}
clean_environment

say "local nightly start: commit ${WPA3_CI_HEAD:-unset}, dry run $DRY_RUN"
case "$DRY_RUN" in 0|1) ;; *) say 'LOCAL: FAIL: DRY_RUN must be 0 or 1'; exit 2 ;; esac
if [[ ! "${GH_REPO:-}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  say 'LOCAL: FAIL: GH_REPO must be owner/repository'
  exit 2
fi
if [ "$DRY_RUN" != 1 ] && [ -z "${GH_TOKEN:-}" ]; then
  say 'LOCAL: FAIL: GH_TOKEN is required unless DRY_RUN=1'
  exit 2
fi
# Whole seconds, at most 6 digits and no leading zeros (no octal surprises).
for value in "$LIMIT" "$LOCK_WAIT" "$CALL_LIMIT"; do
  case "$value" in ''|*[!0-9]*|0?*|???????*) say 'LOCAL: FAIL: time limits must be whole seconds without leading zeros'; exit 2 ;; esac
done
if [ "$LIMIT" = 0 ] || [ "$CALL_LIMIT" = 0 ]; then
  say 'LOCAL: FAIL: time limits must be at least 1 second'
  exit 2
fi

export GH_REPO DRY_RUN UPSTREAM_SOURCE FORCE
export OWNER="${GH_REPO%%/*}"
# publish_branch.sh and nightly_skip.py allow the marker early-skip only on wpa3-ci.
export GITHUB_REF=refs/heads/wpa3-ci
export GIT_LFS_SKIP_SMUDGE=1 GIT_LFS_SKIP_PUSH=1 GIT_TERMINAL_PROMPT=0
# Ignore the host's own git configuration, like a fresh Actions runner: a global
# commit.gpgSign, i18n.commitEncoding or whitespace setting could change composed
# commits or patch checks, and the system osxkeychain helper could store the token.
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
# Per-process credentials: reset every helper, then answer from GH_TOKEN for the
# fork's own URL only (git matches the path too), never for commaai/openpilot or
# any other github.com path. The helper's own shell expands $GH_TOKEN, so the
# token is never in argv, a remote URL, a file or the log. It answers only "get".
export GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=credential.helper GIT_CONFIG_VALUE_0=''
export GIT_CONFIG_KEY_1="credential.https://github.com/$GH_REPO.git.helper"
# shellcheck disable=SC2016
export GIT_CONFIG_VALUE_1='!f() { test "$1" = get || return 0; echo username=x-access-token; echo "password=$GH_TOKEN"; }; f'
export GH_PROMPT_DISABLED=1 GH_NO_UPDATE_NOTIFIER=1
export PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 LC_ALL=C
export WPA3_LOCAL_RUN=1
WPA3_LOCAL_RUN_ID=$(date -u +%Y-%m-%dT%H:%M:%SZ)
export WPA3_LOCAL_RUN_ID WPA3_EXPORT_DIR="$ROOT"

case "$UPSTREAM_SOURCE" in latest|published) ;; *) report_failure 'invalid UPSTREAM_SOURCE'; exit 2 ;; esac
case "$FORCE" in true|false) ;; *) report_failure 'invalid FORCE'; exit 2 ;; esac
if [[ ! "${WPA3_CI_HEAD:-}" =~ ^[0-9a-f]{40}$ ]]; then
  # An export has no .git; never fall back to git rev-parse of an enclosing repository.
  report_failure 'WPA3_CI_HEAD is not a commit SHA'
  exit 2
fi
export WPA3_CI_HEAD
case "$WORK_ROOT" in
  /*) ;;
  *) report_failure 'WPA3_WORK_ROOT must be an absolute path'; exit 2 ;;
esac
# The branch list is nightly.yml's, so a manual dispatch and the local run agree.
BRANCHES=$(sed -n "s/^      BRANCHES: '\([A-Za-z0-9 ._-]*\)'\$/\1/p" .github/workflows/nightly.yml)
for branch in $BRANCHES; do
  if [[ ! "$branch" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; then BRANCHES=; fi
done
if [ -z "$BRANCHES" ]; then
  report_failure 'branch list could not be read from nightly.yml'
  exit 2
fi
export BRANCHES
umask 077
if ! mkdir -p "$WORK_ROOT/runs"; then
  report_failure 'work root could not be created'
  exit 2
fi
WPA3_WORK_ROOT=$WORK_ROOT
export WPA3_WORK_ROOT
# No git command may find an enclosing repository and use its config (for
# example a url.*.insteadOf rule): stop discovery above the export and the work root.
GIT_CEILING_DIRECTORIES="$(dirname "$ROOT"):$WORK_ROOT"
export GIT_CEILING_DIRECTORIES
LOCK="$WORK_ROOT/lock"

trap finish EXIT
trap 'on_signal TERM' TERM
trap 'on_signal HUP' HUP
trap 'on_signal INT' INT
acquire_lock
case "$?" in
  0) ;;
  1) report_failure 'another local nightly run still holds the lock'; exit 75 ;;
  *) report_failure 'the lock cannot be created'; exit 2 ;;
esac
# Repositories of a run that was killed before its cleanup.
find "$WORK_ROOT/runs" -mindepth 1 -maxdepth 1 -type d -name 'run.*' -mmin +$((LIMIT / 60 + 30)) -exec rm -rf {} + 2>/dev/null
if ! RUN_DIR=$(mktemp -d "$WORK_ROOT/runs/run.XXXXXX"); then
  RUN_DIR=
  report_failure 'run directory could not be created'
  exit 2
fi
export LOCAL_RUN_DIR="$RUN_DIR" RUNNER_TEMP="$RUN_DIR/temp" TMPDIR="$RUN_DIR/tmp"
export GITHUB_OUTPUT="$RUNNER_TEMP/github_output"
mkdir -p "$RUNNER_TEMP" "$TMPDIR"
: > "$RUN_DIR/summary"

if [ -n "${GH_TOKEN:-}" ]; then
  write_bounded python3 scripts/issues.py local-runner --token-check || say 'LOCAL: WARN: token expiry check failed'
else
  say 'token expiry check skipped: no GH_TOKEN'
fi

if ! read_follow_mode; then
  report_failure 'WPA3_FOLLOW_MODE could not be read'
  exit 3
fi
say "WPA3_FOLLOW_MODE=$WPA3_FOLLOW_MODE UPSTREAM_SOURCE=$UPSTREAM_SOURCE FORCE=$FORCE"

# A disabled nightly.yml pauses publishing (rollback.yml, or gh workflow disable).
# On Actions a disabled workflow does not start at all, so nothing runs here
# either; publish_branch.sh reads the state again once per branch, before that
# branch publishes or records anything.
if ! STATE=$(bounded gh api "repos/$GH_REPO/actions/workflows/nightly.yml" --jq .state); then
  report_failure 'nightly workflow state could not be read'
  exit 3
fi
if [ "$STATE" != active ]; then
  say "nightly.yml is not active ($STATE); publishing is paused"
  for branch in $BRANCHES; do
    echo "- $branch: skipped (nightly disabled)" >> "$RUN_DIR/summary"
  done
  say 'Summary:'
  cat "$RUN_DIR/summary"
  exit 0
fi

# In the background, so that a signal reaches on_signal while the worker runs.
WORKER_STARTED=1
{ LIMITER_PIDFILE="$RUN_DIR/limiter.pid" python3 -c "$LIMITER" "$LIMIT" "$BASH" "$ROOT/scripts/local_nightly.sh" --worker 2>&1
  echo "$?" > "$RUN_DIR/worker.rc"; } | tee -a "$RUN_DIR/runner.log" &
PIPELINE=$!
# Record the limiter in the lock, so that a later run sees the worker as live
# even if this shell is killed without its cleanup.
tries=0
while [ ! -s "$RUN_DIR/limiter.pid" ] && [ "$tries" -lt 50 ]; do
  sleep 0.1
  tries=$((tries + 1))
done
if [ -s "$RUN_DIR/limiter.pid" ]; then
  limiter_pid=$(cat "$RUN_DIR/limiter.pid")
  printf '%s %s\n' "$limiter_pid" "$(process_start "$limiter_pid")" > "$LOCK/limiter" || say 'LOCAL: WARN: the limiter could not be recorded in the lock'
fi
while :; do
  wait "$PIPELINE"
  kill -0 "$PIPELINE" 2>/dev/null || break
done
# The limiter is gone; never signal its pid again (it may be reused).
WORKER_STARTED=2
rm -f "$RUN_DIR/limiter.pid"
WORKER_RC=$(cat "$RUN_DIR/worker.rc" 2>/dev/null || true)
case "$WORKER_RC" in ''|*[!0-9]*) WORKER_RC=125 ;; esac
say 'Summary:'
cat "$RUN_DIR/summary"
# 0 and 1 are branch results; anything else is the runner's own failure, also
# when local-failure could not be written. A signal is reported as such.
FILE_REASON=$(head -n 1 "$RUN_DIR/local-failure" 2>/dev/null || true)
if [ -n "$SIGNAL" ]; then
  REASON="stopped by SIG$SIGNAL"
  WORKER_RC=$(signal_code)
else
  case "$WORKER_RC" in
    0|1) REASON=$FILE_REASON ;;
    124) REASON="time limit reached after $LIMIT seconds" ;;
    *) REASON=${FILE_REASON:-"runner stopped ($WORKER_RC)"} ;;
  esac
fi
if [ -n "$REASON" ]; then
  report_failure "$REASON" "$RUN_DIR/runner.log"
  if [ "$WORKER_RC" = 0 ]; then WORKER_RC=1; fi
  exit "$WORKER_RC"
fi
if [ "$WORKER_RC" = 0 ]; then
  write_bounded python3 scripts/issues.py local-runner --close || say 'LOCAL: WARN: the local-runner issue could not be closed'
fi
if [ -n "$SIGNAL" ]; then exit "$(signal_code)"; fi
exit "$WORKER_RC"
