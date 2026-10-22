#!/usr/bin/env bash
# Run the shipped launcher function with systemd/mount stubs, never as root.
set -euo pipefail
if [ "$#" = 0 ]; then
  scratch=$(mktemp -d)
  trap 'rm -rf "$scratch"' EXIT
  sed -n '/^+function wpa3_modem_override {$/,/^+}$/p' "$(dirname "$0")/../patches/launcher-modem-agnos20.patch" | sed 's/^+//' > "$scratch/launcher.sh"
  set -- "$scratch/launcher.sh" "$scratch"
fi
work="$2/modem tests"
mkdir -p "$work/stubs"
sed -n '/^function wpa3_modem_override {$/,/^}$/p' "$1" > "$work/function.sh"
# shellcheck source=/dev/null
source "$work/function.sh"
declare -F wpa3_modem_override >/dev/null
export PATH="$work/stubs:$PATH"
export STUB_CALLS="$work/calls" STUB_BACKUP="$work/stock-backup" STUB_POLLS="$work/polls"
export WPA3_MODEM_SYS="$work/stock modem.py" WPA3_MODEM_BIN="$work/patched modem.py"
export WPA3_MODEM_SERVICE="$work/modem.service" WPA3_MODEM_FAILED="$work/failed hashes"
export WPA3_MODEM_DROPIN_DIR="$work/run/drop-in" WPA3_MODEM_STATE="$work/run/state"
export WPA3_MODEM_STATUS="$work/status" WPA3_MODEM_PROC_ROOT="$work/proc"
export DIR="$work/openpilot"
export WPA3_MODEM_AUTH_DIR="$work/auth"
export STUB_MOUNTED="$work/mounted" STUB_TIME="$work/time" STUB_RESTARTS="$work/restarts"
mkdir -p "$WPA3_MODEM_AUTH_DIR"
mkdir -p "$WPA3_MODEM_PROC_ROOT/4242"
cat > "$work/stubs/sudo" <<'STUB'
#!/usr/bin/env bash
exec "$@"
STUB
cat > "$work/stubs/mount" <<'STUB'
#!/usr/bin/env bash
set -eu
printf 'mount|%s|%s|%s\n' "$@" >> "$STUB_CALLS"
[ "$1" = --bind ]
[ -f "$WPA3_MODEM_DROPIN_DIR/wpa3.conf" ]
[ "${STUB_MOUNT_RC:-0}" = 0 ] || exit "$STUB_MOUNT_RC"
cp "$3" "$STUB_BACKUP"
cp "$2" "$3"
: > "$STUB_MOUNTED"
STUB
cat > "$work/stubs/umount" <<'STUB'
#!/usr/bin/env bash
set -eu
printf 'umount|%s|%s\n' "$@" >> "$STUB_CALLS"
[ "$1" = -l ]
[ "${STUB_UMOUNT_RC:-0}" = 0 ] || exit "$STUB_UMOUNT_RC"
cp "$STUB_BACKUP" "$2"
rm -f "$STUB_MOUNTED"
STUB
cat > "$work/stubs/mountpoint" <<'STUB'
#!/usr/bin/env bash
[ "$1" = -q ] && [ -f "$STUB_MOUNTED" ]
STUB
cat > "$work/stubs/systemctl" <<'STUB'
#!/usr/bin/env bash
set -eu
printf 'systemctl' >> "$STUB_CALLS"
printf '|%s' "$@" >> "$STUB_CALLS"
printf '\n' >> "$STUB_CALLS"
case "$*" in
  'show -p TimeoutStopUSec --value modem.service') printf '%s\n' "${STUB_STOP_TIMEOUT:-45s}" ;;
  'show -p InvocationID --value modem.service')
    if [ "$(< "$STUB_RESTARTS")" -gt 0 ] && [ "$(< "$STUB_TIME")" -ge "${STUB_NEW_AFTER:-0}" ] && [ "${STUB_NO_NEW:-0}" = 0 ]; then
      printf '%032d\n' 2
    else
      printf '%032d\n' 1
    fi ;;
  'show -p MainPID --value modem.service') printf '%s\n' "${STUB_PID:-4242}" ;;
  'is-active --quiet modem.service')
    polls=$(< "$STUB_POLLS")
    polls=$((polls + 1))
    printf '%s\n' "$polls" > "$STUB_POLLS"
    if [ "${STUB_CRASH_POLL:-0}" = "$polls" ]; then
      cp "$STUB_BACKUP" "$WPA3_MODEM_SYS"
      rm -f "$STUB_MOUNTED" "$WPA3_MODEM_DROPIN_DIR/wpa3.conf" "$WPA3_MODEM_AUTH_DIR"/modem_pppd_auth_*
      printf '%s signal\n' "$WPA3_MODEM_SHA256" >> "$WPA3_MODEM_FAILED"
      exit 3
    fi
    [ "$(< "$STUB_TIME")" -ge "${STUB_ACTIVE_AT:-0}" ] || exit 3
    [ "$polls" -ge "${STUB_ACTIVE_AFTER:-1}" ] && exit "${STUB_ACTIVE_RC:-0}"
    exit 3 ;;
  '--no-block restart modem.service')
    printf '%s\n' "$(( $(< "$STUB_RESTARTS") + 1 ))" > "$STUB_RESTARTS"
    exit "${STUB_RESTART_RC:-0}" ;;
  'daemon-reload') exit "${STUB_RELOAD_RC:-0}" ;;
  'reset-failed modem.service') exit 0 ;;
  *) echo "unexpected systemctl arguments: $*" >&2; exit 99 ;;
esac
STUB
chmod +x "$work"/stubs/*
# Keep polling stubs cheap; subprocess crash hooks still use the same executables.
sudo() { "$@"; }
systemctl() ( source "$work/stubs/systemctl" )
mountpoint() { [ "$1" = -q ] && [ -f "$STUB_MOUNTED" ]; }
fail() { echo "FAIL: $*" >&2; exit 1; }
hash() { sha256sum < "$1" | cut -d ' ' -f 1; }
called() { grep -Fxq -- "$*" "$STUB_CALLS" || fail "missing call: $*"; }
not_called() { if grep -Fq -- "$*" "$STUB_CALLS"; then fail "unexpected call: $*"; fi; }
state_is() { [ "$(cat "$WPA3_MODEM_STATE")" = "$*" ] || fail "state: expected $*, got $(cat "$WPA3_MODEM_STATE")"; }
fake_clock() { printf '%s\n' "$fake_seconds"; }
fake_sleep() { [ "$1" = 1 ] || fail "unexpected sleep"; fake_seconds=$((fake_seconds + 1)); printf '%s\n' "$fake_seconds" > "$STUB_TIME"; }
export WPA3_MODEM_CLOCK=fake_clock WPA3_MODEM_SLEEP=fake_sleep
reset_case() {
  rm -rf "$WPA3_MODEM_DROPIN_DIR"
  rm -f "$WPA3_MODEM_FAILED" "$WPA3_MODEM_STATE" "$STUB_MOUNTED" "$WPA3_MODEM_AUTH_DIR"/modem_pppd_auth_*
  mkdir -p "$(dirname "$WPA3_MODEM_STATE")"
  : > "$STUB_CALLS"
  printf '0\n' > "$STUB_POLLS"
  printf '0\n' > "$STUB_TIME"
  printf '0\n' > "$STUB_RESTARTS"
  printf '# stock modem\n' > "$WPA3_MODEM_SYS"
  printf '# override modem\n' > "$WPA3_MODEM_BIN"
  printf '[Service]\nUser=comma\n' > "$WPA3_MODEM_SERVICE"
  export WPA3_MODEM_STOCK_SHA256="$(hash "$WPA3_MODEM_SYS")"
  export WPA3_MODEM_SERVICE_SHA256="$(hash "$WPA3_MODEM_SERVICE")"
  export WPA3_MODEM_SHA256="$(hash "$WPA3_MODEM_BIN")"
  printf '/usr/bin/python3\0-u\0%s\0' "$WPA3_MODEM_SYS" > "$WPA3_MODEM_PROC_ROOT/4242/cmdline"
  printf '{"fork_apn_auth":"none"}\n' > "$WPA3_MODEM_STATUS"
  export STUB_ACTIVE_RC=0 STUB_ACTIVE_AFTER=1 STUB_MOUNT_RC=0 STUB_RESTART_RC=0 STUB_RELOAD_RC=0 STUB_UMOUNT_RC=0 STUB_PID=4242
  export STUB_NEW_AFTER=0 STUB_NO_NEW=0 STUB_ACTIVE_AT=0 STUB_CRASH_POLL=0 STUB_STOP_TIMEOUT=45s
  fake_seconds=0
}
run_override() { wpa3_modem_override > "$work/output" 2>&1; }
no_bind() { not_called 'mount|'; not_called 'systemctl|--no-block|restart'; }

reset_case
run_override
state_is active "$WPA3_MODEM_SHA256"
called "mount|--bind|$WPA3_MODEM_BIN|$WPA3_MODEM_SYS"
called 'systemctl|--no-block|restart|modem.service'
not_called 'umount|'
grep -Fxq '[Service]' "$WPA3_MODEM_DROPIN_DIR/wpa3.conf" || fail 'missing section'
grep -Fq 'ExecStopPost=+/bin/sh -c' "$WPA3_MODEM_DROPIN_DIR/wpa3.conf" || fail 'cleanup must run as root in User=comma unit'
# shellcheck disable=SC2016
grep -Fq '$$SERVICE_RESULT' "$WPA3_MODEM_DROPIN_DIR/wpa3.conf" || fail 'early SERVICE_RESULT expansion'

# Re-entering the launcher recognizes the active bind without another restart.
: > "$STUB_CALLS"
run_override
state_is active "$WPA3_MODEM_SHA256"
no_bind
not_called 'umount|'

run_stop_post() {
  SERVICE_RESULT="$1" python3.12 - "$WPA3_MODEM_DROPIN_DIR/wpa3.conf" <<'PY'
import os
from pathlib import Path
import shlex
import subprocess
import sys
line, = [line.removeprefix("ExecStopPost=") for line in Path(sys.argv[1]).read_text().splitlines() if line.startswith("ExecStopPost=")]
lexer = shlex.shlex(line, posix=True)
lexer.whitespace_split = True
lexer.escapedquotes = "\"'"
args = [arg.replace("%%", "%").replace("$$", "$") for arg in lexer]
assert args[:2] == ["+/bin/sh", "-c"], args
args[0] = "/bin/sh"
assert args[4:] == [os.environ["WPA3_MODEM_SYS"], os.environ["WPA3_MODEM_SHA256"], os.environ["WPA3_MODEM_FAILED"],
                   os.environ["WPA3_MODEM_STOCK_SHA256"], str(Path(os.environ["WPA3_MODEM_DROPIN_DIR"]) / "wpa3.conf"),
                   os.environ["WPA3_MODEM_STATE"], os.environ["WPA3_MODEM_AUTH_DIR"]], args
subprocess.run(args, check=True)
PY
}
: > "$STUB_CALLS"
printf 'test credential\n' > "$WPA3_MODEM_AUTH_DIR/modem_pppd_auth_success"
run_stop_post success
[ ! -e "$WPA3_MODEM_AUTH_DIR/modem_pppd_auth_success" ] || fail 'normal stop retained auth file'
[ ! -s "$STUB_CALLS" ] || fail 'success reverted'
state_is active "$WPA3_MODEM_SHA256"
printf 'test credential\n' > "$WPA3_MODEM_AUTH_DIR/modem_pppd_auth_failure"
run_stop_post exit-code
[ ! -e "$WPA3_MODEM_AUTH_DIR/modem_pppd_auth_failure" ] || fail 'failure retained auth file'
called "umount|-l|$WPA3_MODEM_SYS"
[ "$(hash "$WPA3_MODEM_SYS")" = "$WPA3_MODEM_STOCK_SHA256" ] || fail 'crash did not restore stock'
[ "$(cat "$WPA3_MODEM_FAILED")" = "$WPA3_MODEM_SHA256 exit-code" ] || fail 'crash marker'
[ ! -e "$WPA3_MODEM_DROPIN_DIR/wpa3.conf" ] || fail 'crash hook retained'
state_is inactive service-failure

for guard in unpinned missing-file stock-hash service-hash override-hash; do
  reset_case
  case "$guard" in
    unpinned) unset WPA3_MODEM_STOCK_SHA256 ;;
    missing-file) rm "$WPA3_MODEM_BIN" ;;
    stock-hash) printf 'drift\n' >> "$WPA3_MODEM_SYS" ;;
    service-hash) printf 'drift\n' >> "$WPA3_MODEM_SERVICE" ;;
    override-hash) printf 'drift\n' >> "$WPA3_MODEM_BIN" ;;
  esac
  run_override
  state_is inactive "$guard"
  no_bind
done

for count in 1 2 3 4; do
  reset_case
  for ((i=0; i<count; i++)); do printf '%s signal\n' "$WPA3_MODEM_SHA256" >> "$WPA3_MODEM_FAILED"; done
  run_override
  if [ "$count" -ge 3 ]; then state_is inactive retry-limit; no_bind; else state_is active "$WPA3_MODEM_SHA256"; fi
done
reset_case
printf 'old start\n%s start\n' "$WPA3_MODEM_SHA256" > "$WPA3_MODEM_FAILED"
run_override
state_is inactive retry-limit
no_bind

reset_case
export STUB_ACTIVE_AFTER=3
run_override
state_is active "$WPA3_MODEM_SHA256"
[ "$(cat "$STUB_POLLS")" = 3 ] || fail 'did not wait'

# Active service alone cannot prove that this override is running.
for failure in inactive wrong-command stale-status invalid-json; do
  reset_case
  activation_deadline=20
  case "$failure" in
    inactive) export STUB_ACTIVE_RC=3 STUB_NEW_AFTER=38; activation_deadline=58 ;;
    wrong-pid) export STUB_PID=0 ;;
    wrong-command) printf '/usr/bin/python3\0/other/modem.py\0' > "$WPA3_MODEM_PROC_ROOT/4242/cmdline" ;;
    stale-status) printf '{"state":"SEARCHING"}\n' > "$WPA3_MODEM_STATUS" ;;
    invalid-json) printf 'not-json\n' > "$WPA3_MODEM_STATUS" ;;
    restart) export STUB_RESTART_RC=1 STUB_ACTIVE_RC=3 ;;
    mount) export STUB_MOUNT_RC=1 ;;
    reload) export STUB_RELOAD_RC=1 ;;
  esac
  printf 'test credential\n' > "$WPA3_MODEM_AUTH_DIR/modem_pppd_auth_revert"
  run_override
  [ ! -e "$WPA3_MODEM_AUTH_DIR/modem_pppd_auth_revert" ] || fail 'revert retained auth file'
  state_is inactive start
  [ "$(hash "$WPA3_MODEM_SYS")" = "$WPA3_MODEM_STOCK_SHA256" ] || fail 'stock not restored'
  [ "$(cat "$WPA3_MODEM_FAILED")" = "$WPA3_MODEM_SHA256 start" ] || fail 'start not recorded'
  [ ! -e "$WPA3_MODEM_DROPIN_DIR/wpa3.conf" ] || fail 'failed hook retained'
  called 'systemctl|reset-failed|modem.service'
  called 'systemctl|--no-block|restart|modem.service'
  if [ "$failure" != mount ] && [ "$failure" != reload ]; then
    [ "$fake_seconds" = "$activation_deadline" ] || fail 'wrong activation deadline'
    called "umount|-l|$WPA3_MODEM_SYS"
  fi
  : > "$STUB_CALLS"
  run_override
  state_is inactive retry-limit
  no_bind
done

# A slow stock SIGTERM must finish before the override's twenty-second window.
reset_case
export STUB_NEW_AFTER=38 STUB_ACTIVE_AT=40
run_override
state_is active "$WPA3_MODEM_SHA256"
[ "$fake_seconds" = 40 ] || fail 'old invocation accepted or health check delayed'
[ ! -e "$WPA3_MODEM_FAILED" ] || fail 'slow stop blacklisted override'
printf 'PASS: slow stock stop -> new invocation -> active\n'

for active_at in 19 20; do
  reset_case
  export STUB_ACTIVE_AT="$active_at"
  run_override
  if [ "$active_at" = 19 ]; then
    state_is active "$WPA3_MODEM_SHA256"
    [ "$fake_seconds" = 19 ] || fail 'success before deadline was not accepted'
  else
    state_is inactive start
    [ "$fake_seconds" = 20 ] || fail 'success deadline was extended'
  fi
done
printf 'PASS: success before 20 seconds accepted, at deadline rejected\n'

for reason in no-new wrong-pid restart; do
  reset_case
  restart_deadline=55
  case "$reason" in
    no-new) export STUB_NO_NEW=1 ;;
    wrong-pid) export STUB_PID=0 STUB_STOP_TIMEOUT='1min 30s'; restart_deadline=100 ;;
    restart) export STUB_RESTART_RC=1 STUB_NO_NEW=1 STUB_STOP_TIMEOUT=infinity; restart_deadline=120 ;;
  esac
  printf 'test credential\n' > "$WPA3_MODEM_AUTH_DIR/modem_pppd_auth_timeout"
  run_override
  state_is inactive restart-timeout
  [ "$fake_seconds" = "$restart_deadline" ] || fail 'stop timeout plus margin not observed'
  [ ! -e "$WPA3_MODEM_FAILED" ] || fail 'no invocation appended start line'
  [ ! -e "$WPA3_MODEM_AUTH_DIR/modem_pppd_auth_timeout" ] || fail 'timeout retained auth file'
  [ "$(hash "$WPA3_MODEM_SYS")" = "$WPA3_MODEM_STOCK_SHA256" ] || fail 'restart timeout did not restore stock'
done
printf 'PASS: no new invocation -> inactive restart-timeout, no start record\n'

for reason in mount reload; do
  reset_case
  if [ "$reason" = mount ]; then export STUB_MOUNT_RC=1; else export STUB_RELOAD_RC=1; fi
  run_override
  state_is inactive bind
  [ ! -e "$WPA3_MODEM_FAILED" ] || fail 'bind failure appended start line'
  [ ! -e "$WPA3_MODEM_DROPIN_DIR/wpa3.conf" ] || fail 'bind failure retained hook'
  not_called 'systemctl|--no-block|restart'
done
printf 'PASS: bind/reload failure -> inactive bind, no restart\n'

reset_case
run_override
: > "$STUB_CALLS"
export STUB_ACTIVE_AT=$((fake_seconds + 5))
run_override
state_is active "$WPA3_MODEM_SHA256"
no_bind
[ "$fake_seconds" = 5 ] || fail 're-run did not wait for RestartSec'
printf 'PASS: bound override restarting -> active\n'

reset_case
export STUB_ACTIVE_RC=3 STUB_CRASH_POLL=2
run_override
state_is inactive service-failure
[ "$(cat "$WPA3_MODEM_FAILED")" = "$WPA3_MODEM_SHA256 signal" ] || fail 'crash hook failure counted twice'
[ "$(cat "$STUB_RESTARTS")" = 1 ] || fail 'already reverted hook triggered another restart'
printf 'PASS: crash-hook rollback -> one record, no extra restart\n'

reset_case
export STUB_ACTIVE_RC=3 STUB_UMOUNT_RC=32
run_override
state_is inactive restore-failed
[ -e "$WPA3_MODEM_DROPIN_DIR/wpa3.conf" ] || fail 'failed restore disarmed hook'
export STUB_UMOUNT_RC=0
run_stop_post signal
state_is inactive service-failure
[ ! -e "$WPA3_MODEM_DROPIN_DIR/wpa3.conf" ] || fail 'restored hook not removed'

# Unit escaping must preserve spaces, quotes, backslashes, dollars and percent.
special="$work/quote'\"\\\$%"
mkdir -p "$special"
export WPA3_MODEM_SYS="$special/sys" WPA3_MODEM_FAILED="$special/failed" WPA3_MODEM_STATE="$special/state"
reset_case
run_override
run_stop_post signal
[ "$(cat "$WPA3_MODEM_FAILED")" = "$WPA3_MODEM_SHA256 signal" ] || fail 'quoted hook arguments'
state_is inactive service-failure
printf 'PASS: auth files removed on success, failure and launcher rollback\n'
printf 'PASS: wpa3_modem_override\n'
