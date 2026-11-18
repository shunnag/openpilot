#!/bin/bash
# Stable cron entry point for the local nightly runner (README: "Where the nightly runs").
#
# Copy this file outside any repository into a folder of its own (mode 700),
# next to a private local_nightly.conf, and let cron run the copy by its absolute
# path. It never runs files from a working checkout: each run fetches wpa3-ci
# into a private mirror, exports that exact commit with git archive and runs
# scripts/local_nightly.sh from the read-only export. The token goes from a
# private file into the environment only. Works with bash 3.2.
#
# local_nightly.conf holds KEY=value lines (no quotes) and # comments:
#   GH_REPO=<owner>/openpilot           required
#   WORK_ROOT=<this folder>/work        required; inside this folder
#   TOKEN_FILE=/absolute/token/file     required; mode 600 in a mode 700 folder
#   PATH=...                            optional; default below
#   KEEP_DAYS=14                        exports and logs older than this go
#   TIME_LIMIT_MINUTES=90 LOCK_WAIT_MINUTES=30 FETCH_LIMIT_SECONDS=300 DRY_RUN=0
#   (whole numbers without leading zeros, at most 4 digits)
# crontab (host local time), a main run and a catch-up run, e.g. in JST:
#   7 20 * * * /absolute/path/local_nightly_launcher.sh
#   43 21 * * * /absolute/path/local_nightly_launcher.sh
set -u -o pipefail
umask 077
PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
LC_ALL=C
export PATH LC_ALL
for name in $(compgen -e); do
  case "$name" in
    GIT_*|GH_*|GITHUB_*|RUNNER_*|PYTHON*|DRY_*|WPA3_*|LOCAL_NIGHTLY_*|BASH_ENV|ENV|CDPATH) unset "$name" 2>/dev/null || true ;;
  esac
done
# Cron mails what reaches the original stderr; keep it for one short line.
exec 3>&2
LOG_NAME=
CHILD=

say() {
  printf '%s launcher: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

# Before the log exists: one line for cron mail, with no token and no path.
die() {
  printf 'local nightly launcher: %s\n' "$*" >&3
  exit 2
}

# Owned by this user, with no group or other permission bits and no ACL.
private() {
  entry=$(ls -ldn "$1" 2>/dev/null) || return 1
  read -r mode _ uid _ <<EOF
$entry
EOF
  [ "$uid" = "$(id -u)" ] || return 1
  case "$mode" in *+) return 1 ;; esac
  [ "${mode:4:6}" = '------' ] || return 1
  # macOS ls shows "@", not "+", when an entry has extended attributes and an
  # ACL; ls -le prints every ACL entry on a line of its own.
  if [ "$(uname -s)" = Darwin ]; then
    # shellcheck disable=SC2012 # one known path; an odd name only adds lines and fails closed
    [ "$(ls -lden "$1" 2>/dev/null | wc -l | tr -d ' ')" = 1 ] || return 1
  fi
}

# The absolute directory with no symlink, . or .. component, or empty.
physical_dir() {
  case "$1" in /*) ;; *) return 1 ;; esac
  case "$1/" in *//*|*/./*|*/../*) return 1 ;; esac
  [ "$(cd "$1" 2>/dev/null && pwd -P)" = "$1" ]
}

# Every folder above, up to /, must be root's or yours and closed to writes by
# others; a root-owned folder may be writable by others only with the sticky bit.
safe_ancestors() {
  local dir=$1 entry mode uid
  while [ "$dir" != / ]; do
    dir=$(dirname "$dir")
    entry=$(ls -ldn "$dir" 2>/dev/null) || return 1
    read -r mode _ uid _ <<EOF
$entry
EOF
    case "$uid" in 0|"$(id -u)") ;; *) return 1 ;; esac
    if [ "${mode:5:1}" = w ] || [ "${mode:8:1}" = w ]; then
      [ "$uid" = 0 ] || return 1
      case "${mode:9:1}" in t|T) ;; *) return 1 ;; esac
    fi
  done
}

# macOS can mount a volume with ownership ignored; then no mode check means anything.
noowners() {
  local point table
  [ "$(uname -s)" = Darwin ] || return 1
  point=$(df -P "$1" 2>/dev/null | awk 'NR == 2 {for (i = 6; i <= NF; i++) printf "%s%s", (i > 6 ? " " : ""), $i}')
  [ -n "$point" ] || return 0
  # Unknown counts as ignored ownership: refuse rather than guess.
  table=$("$(command -v mount || echo /sbin/mount)" 2>/dev/null) || return 0
  printf '%s\n' "$table" | awk -v point="$point" '{ i = index($0, " on " point " ("); if (i && index(substr($0, i), "noowners")) found = 1 }
    END { exit !found }'
}

# A whole number without leading zeros, at most 4 digits (no octal surprises).
number() {
  case "$1" in [0-9]|[1-9][0-9]|[1-9][0-9][0-9]|[1-9][0-9][0-9][0-9]) ;; *) return 1 ;; esac
}

# git for the mirror only, without the host's configuration or credential
# helpers (wpa3-ci is public); a stalled transfer is aborted.
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 GIT_CONFIG_COUNT=3
export GIT_CONFIG_KEY_0=credential.helper GIT_CONFIG_VALUE_0=''
export GIT_CONFIG_KEY_1=http.lowSpeedLimit GIT_CONFIG_VALUE_1=1000 GIT_CONFIG_KEY_2=http.lowSpeedTime GIT_CONFIG_VALUE_2=60
# Hard bound on the fetch: kill its whole process group after the limit.
LIMITER='
import os, signal, subprocess, sys
child = subprocess.Popen(sys.argv[2:], start_new_session=True)
try:
  sys.exit(child.wait(timeout=int(sys.argv[1])))
except subprocess.TimeoutExpired:
  os.killpg(child.pid, signal.SIGKILL)
  child.wait()
  sys.exit(124)
'

case "$0" in /*) ;; *) die 'run the launcher by its absolute path' ;; esac
[ ! -L "$0" ] || die 'the launcher must not be a symlink'
BASE=$(dirname "$0")
physical_dir "$BASE" || die 'the launcher folder path must not contain a symlink'
SELF="$BASE/$(basename "$0")"
CONFIG="$BASE/local_nightly.conf"
private "$BASE" || die 'the launcher folder must be yours, mode 700 and without an ACL'
{ [ -f "$CONFIG" ] && [ ! -L "$CONFIG" ] && private "$CONFIG"; } ||
  die 'local_nightly.conf must be a regular file of yours next to the launcher, mode 600, without an ACL'

GH_REPO='' WORK_ROOT='' TOKEN_FILE='' KEEP_DAYS=14 TIME_LIMIT_MINUTES=90 LOCK_WAIT_MINUTES=30 FETCH_LIMIT_SECONDS=300 DRY_RUN=0
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    ''|'#'*) continue ;;
    *=*) ;;
    *) die 'local_nightly.conf has a line that is not KEY=value' ;;
  esac
  key=${line%%=*}
  value=${line#*=}
  case "$key" in
    GH_REPO) GH_REPO=$value ;;
    WORK_ROOT) WORK_ROOT=$value ;;
    TOKEN_FILE) TOKEN_FILE=$value ;;
    PATH) PATH=$value ;;
    KEEP_DAYS) KEEP_DAYS=$value ;;
    TIME_LIMIT_MINUTES) TIME_LIMIT_MINUTES=$value ;;
    LOCK_WAIT_MINUTES) LOCK_WAIT_MINUTES=$value ;;
    FETCH_LIMIT_SECONDS) FETCH_LIMIT_SECONDS=$value ;;
    DRY_RUN) DRY_RUN=$value ;;
    *) die 'local_nightly.conf has an unknown key' ;;
  esac
done < "$CONFIG"

[[ "$GH_REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || die 'GH_REPO must be owner/repository'
case "$WORK_ROOT" in "$BASE"/?*) ;; *) die 'WORK_ROOT must be a folder inside the launcher folder' ;; esac
case "$WORK_ROOT/" in *//*|*/./*|*/../*) die 'WORK_ROOT must be a plain path inside the launcher folder' ;; esac
case "$TOKEN_FILE" in /*) ;; *) die 'TOKEN_FILE must be an absolute path' ;; esac
for value in "$KEEP_DAYS" "$TIME_LIMIT_MINUTES" "$LOCK_WAIT_MINUTES" "$FETCH_LIMIT_SECONDS"; do
  number "$value" || die 'the time and day settings must be whole numbers without leading zeros, at most 4 digits'
done
for value in "$KEEP_DAYS" "$TIME_LIMIT_MINUTES" "$FETCH_LIMIT_SECONDS"; do
  [ "$value" != 0 ] || die 'KEEP_DAYS, TIME_LIMIT_MINUTES and FETCH_LIMIT_SECONDS must be at least 1'
done
case "$DRY_RUN" in 0|1) ;; *) die 'DRY_RUN must be 0 or 1' ;; esac
[ -n "$PATH" ] || die 'PATH must not be empty'
export PATH
TOKEN_DIR=$(dirname "$TOKEN_FILE")
{ physical_dir "$TOKEN_DIR" && private "$TOKEN_DIR"; } ||
  die 'the token folder must be yours, mode 700, without an ACL or a symlink in its path'
for folder in "$BASE" "$TOKEN_DIR"; do
  safe_ancestors "$folder" || die 'a folder above the launcher or token folder is not owned by root or you, or others can write to it'
  if noowners "$folder"; then die 'the launcher or token folder is on a volume that ignores ownership'; fi
done
{ [ -f "$TOKEN_FILE" ] && [ ! -L "$TOKEN_FILE" ] && private "$TOKEN_FILE"; } ||
  die 'the token file must be a regular file of yours, mode 600, without an ACL'
mkdir -p "$WORK_ROOT" || die 'WORK_ROOT cannot be created'
{ physical_dir "$WORK_ROOT" && private "$WORK_ROOT"; } ||
  die 'WORK_ROOT must be yours, mode 700, without an ACL or a symlink in its path'
mkdir -p "$WORK_ROOT/logs" "$WORK_ROOT/exports" || die 'WORK_ROOT cannot be written'

LOG="$WORK_ROOT/logs/nightly-$(date -u +%Y%m%d).log"
{ : >> "$LOG"; } 2>/dev/null || die 'the log cannot be written'
exec >> "$LOG" 2>&1 || die 'the log cannot be written'
LOG_NAME=$(basename "$LOG")
VERSION=$({ shasum -a 256 "$SELF" 2>/dev/null || sha256sum "$SELF"; } | cut -d' ' -f1)
say "start; launcher sha256 $VERSION; repository $GH_REPO; dry run $DRY_RUN"

EXPORT=
EXPORT_NAME=none
# shellcheck disable=SC2329 # the EXIT trap
finish() {
  status=$?
  # Paths go to chmod and rm as arguments, never through a line-by-line read.
  find "$WORK_ROOT/exports" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" ! -name "$EXPORT_NAME" \
    -exec chmod -R u+w {} \; -exec rm -rf {} \; 2>/dev/null
  find "$WORK_ROOT/logs" -mindepth 1 -maxdepth 1 -type f -name 'nightly-*.log' -mtime +"$KEEP_DAYS" -exec rm -f {} + 2>/dev/null
  say "end ($status)"
  if [ "$status" != 0 ]; then
    printf 'local nightly launcher: failed (exit %s); see %s\n' "$status" "$LOG_NAME" >&3
  fi
  exit "$status"
}
trap finish EXIT
# shellcheck disable=SC2329 # the TERM, HUP and INT trap
on_signal() {
  say "signal received; stopping"
  if [ -n "$CHILD" ]; then kill -TERM "$CHILD" 2>/dev/null; else exit 143; fi
}
trap on_signal TERM HUP INT

# The mirror is a cache. Every command names it with --git-dir, so a broken
# mirror can never send git to an enclosing repository. The ref is deleted
# before each fetch, so a failed fetch never runs an earlier commit; a broken
# mirror is rebuilt once.
MIRROR="$WORK_ROOT/mirror.git"
fetch_wpa3_ci() {
  if [ ! -f "$MIRROR/HEAD" ]; then
    rm -rf "$MIRROR"
    git init --bare --quiet "$MIRROR" || return 1
  fi
  git --git-dir="$MIRROR" update-ref -d refs/heads/wpa3-ci &&
    python3 -c "$LIMITER" "$FETCH_LIMIT_SECONDS" git --git-dir="$MIRROR" fetch --quiet --no-tags --no-recurse-submodules \
      "https://github.com/$GH_REPO.git" '+refs/heads/wpa3-ci:refs/heads/wpa3-ci'
}
if ! fetch_wpa3_ci; then
  say 'fetch of wpa3-ci failed; rebuilding the mirror and trying once more'
  rm -rf "$MIRROR"
  if ! fetch_wpa3_ci; then
    say 'fetch of wpa3-ci failed again; nothing was run'
    exit 2
  fi
fi
SHA=$(git --git-dir="$MIRROR" rev-parse --verify --quiet 'refs/heads/wpa3-ci^{commit}')
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { say 'wpa3-ci did not resolve to a commit'; exit 2; }
EXPORT_NAME="$(date -u +%Y%m%dT%H%M%SZ)-$(printf '%.12s' "$SHA")-$$"
EXPORT="$WORK_ROOT/exports/$EXPORT_NAME"
if ! { mkdir "$EXPORT" && git --git-dir="$MIRROR" archive --format=tar "$SHA" | tar -xf - -C "$EXPORT"; }; then
  say "export of $SHA failed; nothing was run"
  exit 2
fi
chmod -R a-w "$EXPORT"
if [ ! -f "$EXPORT/scripts/local_nightly.sh" ]; then
  say "wpa3-ci $SHA has no scripts/local_nightly.sh; nothing was run"
  exit 2
fi
say "running scripts/local_nightly.sh from wpa3-ci $SHA"

GH_TOKEN=
IFS= read -r GH_TOKEN < "$TOKEN_FILE" || [ -n "$GH_TOKEN" ] || { say 'the token file is empty'; exit 2; }
case "$GH_TOKEN" in
  ''|*[!A-Za-z0-9_]*) say 'the token file must hold the token alone on its first line'; exit 2 ;;
esac
export GH_TOKEN
(
  cd "$EXPORT" || exit 2
  exec 3>&-
  export WPA3_CI_HEAD="$SHA" GH_REPO DRY_RUN WPA3_WORK_ROOT="$WORK_ROOT/runner"
  export LOCAL_NIGHTLY_TIME_LIMIT=$((TIME_LIMIT_MINUTES * 60)) LOCAL_NIGHTLY_LOCK_WAIT=$((LOCK_WAIT_MINUTES * 60))
  exec "$BASH" scripts/local_nightly.sh
) &
CHILD=$!
# A signal interrupts wait; pass it on and keep waiting for the runner's own exit.
while :; do
  wait "$CHILD"
  RC=$?
  kill -0 "$CHILD" 2>/dev/null || break
done
exit "$RC"
