#!/usr/bin/env bash
# Execute only the function extracted from the composed launcher, under strict bash.
set -euo pipefail
work="$2/supplicant tests"
mkdir -p "$work/stubs"
sed -n '/^function wpa3_supplicant_override {$/,/^}$/p' "$1" > "$work/function.sh"
source "$work/function.sh"
declare -F wpa3_supplicant_override >/dev/null
export PATH="$work/stubs:$PATH"
export STUB_CALLS="$work/calls"
export STUB_VERSION_CALLS="$work/version-calls"
export STUB_STOCK_BACKUP="$work/stock-backup"
export STUB_POLLS="$work/polls"
export WPA3_SUPPLICANT_SYS="$work/stock supplicant"
export WPA3_SUPPLICANT_BIN="$work/patched supplicant"
export WPA3_SUPPLICANT_FAILED="$work/failed hashes"
export WPA3_SUPPLICANT_DROPIN_DIR="$work/run/drop-in"
export DIR="$work/openpilot"

cat > "$work/stubs/sudo" <<'SH'
#!/usr/bin/env bash
printf 'sudo' >> "$STUB_CALLS"
printf '|%s' "$@" >> "$STUB_CALLS"
printf '\n' >> "$STUB_CALLS"
if [ "$1" = sha256sum ] && [ "${2:-}" = /proc/4242/exe ]; then
  exec sha256sum < "$STUB_MAINPID_EXE"
fi
exec "$@"
SH
cat > "$work/stubs/mount" <<'SH'
#!/usr/bin/env bash
set -eu
printf 'mount|%s|%s|%s\n' "$@" >> "$STUB_CALLS"
[ "$1" = --bind ]
[ -f "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" ]
[ "${STUB_MOUNT_RC:-0}" = 0 ] || exit "$STUB_MOUNT_RC"
cp "$3" "$STUB_STOCK_BACKUP"
cp "$2" "$3"
SH
cat > "$work/stubs/umount" <<'SH'
#!/usr/bin/env bash
set -eu
printf 'umount' >> "$STUB_CALLS"
printf '|%s' "$@" >> "$STUB_CALLS"
printf '\n' >> "$STUB_CALLS"
if [ "$1" = -l ]; then
  shift
elif [ "${STUB_PROCESS_ALIVE:-0}" = 1 ]; then
  exit 32  # A running executable pins the bind; ordinary umount returns EBUSY.
fi
[ "${STUB_UMOUNT_RC:-0}" = 0 ] || exit "$STUB_UMOUNT_RC"
[ "${STUB_UMOUNT_KEEP:-0}" = 0 ] || exit 0
cp "$STUB_STOCK_BACKUP" "$1"
SH
cat > "$work/stubs/systemctl" <<'SH'
#!/usr/bin/env bash
set -eu
printf 'systemctl' >> "$STUB_CALLS"
printf '|%s' "$@" >> "$STUB_CALLS"
printf '\n' >> "$STUB_CALLS"
case "$*" in
  'show -p MainPID --value wpa_supplicant') printf '4242\n' ;;
  'is-active --quiet wpa_supplicant')
    polls=$(cat "$STUB_POLLS")
    polls=$((polls + 1))
    printf '%s\n' "$polls" > "$STUB_POLLS"
    [ "$polls" -ge "${STUB_ACTIVE_AFTER:-1}" ] && exit "${STUB_ACTIVE_RC:-0}"
    exit 3 ;;
  '--no-block restart wpa_supplicant') exit "${STUB_RESTART_RC:-0}" ;;
  'daemon-reload') exit "${STUB_RELOAD_RC:-0}" ;;
  'reset-failed wpa_supplicant') exit 0 ;;
  *) echo "unexpected systemctl arguments: $*" >&2; exit 99 ;;
esac
SH
chmod +x "$work"/stubs/*

fail() { echo "FAIL: $*" >&2; exit 1; }
hash() { sha256sum < "$1" | cut -d ' ' -f 1; }
called() { grep -Fxq -- "$*" "$STUB_CALLS" || fail "missing call: $*"; }
not_called() { if grep -Fq -- "$*" "$STUB_CALLS"; then fail "unexpected call: $*"; fi; }
log_has() { grep -Fq -- "$*" "$work/output" || fail "missing log: $*"; }
# Advance the bash monotonic seconds counter without waiting 15 real seconds.
sleep() {
  [ "$1" = 1 ] || fail "unexpected sleep: $*"
  SECONDS=$((SECONDS + 1))
}
reset_case() {
  rm -rf "$WPA3_SUPPLICANT_DROPIN_DIR"
  rm -f "$WPA3_SUPPLICANT_FAILED"
  : > "$STUB_CALLS"
  : > "$STUB_VERSION_CALLS"
  printf '0\n' > "$STUB_POLLS"
  cat > "$WPA3_SUPPLICANT_SYS" <<'SH'
#!/bin/sh
[ "$1" = -v ] && echo stock && exit 0
exit 2
SH
  cat > "$WPA3_SUPPLICANT_BIN" <<'SH'
#!/bin/sh
printf '%s\n' "$*" >> "$STUB_VERSION_CALLS"
[ "$1" = -v ] && exit "${STUB_VERSION_RC:-0}"
exit 2
SH
  chmod +x "$WPA3_SUPPLICANT_SYS" "$WPA3_SUPPLICANT_BIN"
  export WPA3_SUPPLICANT_STOCK_SHA256="$(hash "$WPA3_SUPPLICANT_SYS")"
  export STUB_ACTIVE_RC=0 STUB_ACTIVE_AFTER=1 STUB_MOUNT_RC=0 STUB_VERSION_RC=0 STUB_RESTART_RC=0 STUB_RELOAD_RC=0
  export STUB_PROCESS_ALIVE=0 STUB_UMOUNT_RC=0 STUB_UMOUNT_KEEP=0
  export STUB_MAINPID_EXE="$WPA3_SUPPLICANT_BIN"
  bin_hash=$(hash "$WPA3_SUPPLICANT_BIN")
  SECONDS=0
}
run_override() {
  # Do not put the call in an if/||: errexit must remain enabled inside it.
  wpa3_supplicant_override > "$work/output" 2>&1
}
no_change() {
  [ ! -s "$STUB_CALLS" ] || fail "guard changed the system"
  [ "$(hash "$WPA3_SUPPLICANT_SYS")" = "$WPA3_SUPPLICANT_STOCK_SHA256" ] || fail "stock changed"
}

reset_case
unset WPA3_SUPPLICANT_STOCK_SHA256
run_override
[ ! -s "$STUB_CALLS" ] && [ ! -s "$STUB_VERSION_CALLS" ] || fail "unset stock hash"
export WPA3_SUPPLICANT_STOCK_SHA256=''
run_override
[ ! -s "$STUB_CALLS" ] && [ ! -s "$STUB_VERSION_CALLS" ] || fail "empty stock hash"

reset_case
chmod -x "$WPA3_SUPPLICANT_BIN"
run_override
no_change
rm "$WPA3_SUPPLICANT_BIN"
run_override
no_change
[ ! -s "$STUB_VERSION_CALLS" ] || fail "missing/nonexecutable binary was run"

reset_case
printf '# other system\n' >> "$WPA3_SUPPLICANT_SYS"
run_override
[ ! -s "$STUB_CALLS" ] && [ ! -s "$STUB_VERSION_CALLS" ] || fail "stock mismatch changed system"
log_has 'stock wpa_supplicant differs; not overriding'

reset_case
export STUB_VERSION_RC=127
run_override
no_change
log_has '-v failed'

reset_case
printf 'older-hash signal\n%s start\nanother-hash start\n' "$bin_hash" > "$WPA3_SUPPLICANT_FAILED"
run_override
no_change
log_has 'failed to start or failed three times'

# One or two external failures are retried; three failures for this hash stop it.
reasons=(oom-kill timeout signal core-dump)
for count in 1 2 3 4; do
  reset_case
  for ((i=0; i<count; i++)); do
    printf '%s %s\n' "$bin_hash" "${reasons[$i]}" >> "$WPA3_SUPPLICANT_FAILED"
  done
  run_override
  if [ "$count" -ge 3 ]; then
    no_change
    log_has 'failed to start or failed three times'
  else
    called "mount|--bind|$WPA3_SUPPLICANT_BIN|$WPA3_SUPPLICANT_SYS"
    [ "$(hash "$WPA3_SUPPLICANT_SYS")" = "$bin_hash" ] || fail "one-off failure disabled the override"
  fi
done

reset_case
# Only complete records for the exact hash count (old hash-only markers expire).
printf 'prefix-%s start\n%s-suffix start\n%s\n%s start junk\nother-hash start\n' \
  "$bin_hash" "$bin_hash" "$bin_hash" "$bin_hash" > "$WPA3_SUPPLICANT_FAILED"
run_override
[ "$(hash "$WPA3_SUPPLICANT_SYS")" = "$bin_hash" ] || fail "bind did not activate binary"
called "systemctl|daemon-reload"
called "mount|--bind|$WPA3_SUPPLICANT_BIN|$WPA3_SUPPLICANT_SYS"
called "systemctl|--no-block|restart|wpa_supplicant"
called "systemctl|is-active|--quiet|wpa_supplicant"
called "systemctl|show|-p|MainPID|--value|wpa_supplicant"
called "sudo|sha256sum|/proc/4242/exe"
not_called 'umount|'
log_has 'patched wpa_supplicant active'
grep -Fqx '[Service]' "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" || fail "missing service section"
grep -Fq 'ExecStopPost=/bin/sh -c' "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" || fail "missing crash hook"
grep -Fq '$$SERVICE_RESULT' "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" || fail "service result expanded too soon"
[ "$(cat "$STUB_VERSION_CALLS")" = '-v' ] || fail "binary viability not checked"
filtered=$(grep -E '^(mount|systemctl)\|' "$STUB_CALLS")
expected=$(printf '%s\n' "systemctl|daemon-reload" "mount|--bind|$WPA3_SUPPLICANT_BIN|$WPA3_SUPPLICANT_SYS" \
  "systemctl|--no-block|restart|wpa_supplicant" "systemctl|is-active|--quiet|wpa_supplicant" \
  "systemctl|show|-p|MainPID|--value|wpa_supplicant")
[ "$filtered" = "$expected" ] || fail "incorrect activation order"

# A second launch leaves the bind and drop-in intact, without another -v/restart.
: > "$STUB_CALLS"
: > "$STUB_VERSION_CALLS"
run_override
[ ! -s "$STUB_CALLS" ] && [ ! -s "$STUB_VERSION_CALLS" ] || fail "already active changed system"
log_has 'already active'

run_stop_post() {
  SERVICE_RESULT="$1" python3 - "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" <<'PY'
import os
from pathlib import Path
import shlex
import subprocess
import sys

line, = [line.removeprefix("ExecStopPost=") for line in Path(sys.argv[1]).read_text().splitlines()
         if line.startswith("ExecStopPost=")]
# For the generated unit's quote/backslash escapes, systemd unquotes both quote
# styles, then expands %%/$$. No shell evaluation of the unit text is involved.
lexer = shlex.shlex(line, posix=True)
lexer.whitespace_split = True
lexer.escapedquotes = "\"'"
args = [arg.replace("%%", "%").replace("$$", "$") for arg in lexer]
assert args[:2] == ["/bin/sh", "-c"], args
assert args[4:] == [os.environ["WPA3_SUPPLICANT_SYS"], os.environ["WPA3_SUPPLICANT_BIN_HASH"],
                   os.environ["WPA3_SUPPLICANT_FAILED"], os.environ["WPA3_SUPPLICANT_STOCK_SHA256"],
                   str(Path(os.environ["WPA3_SUPPLICANT_DROPIN_DIR"]) / "wpa3.conf")], args
subprocess.run(args, check=True)
PY
}
export WPA3_SUPPLICANT_BIN_HASH="$bin_hash"
rm "$WPA3_SUPPLICANT_FAILED"
run_stop_post success
[ ! -s "$STUB_CALLS" ] && [ ! -e "$WPA3_SUPPLICANT_FAILED" ] || fail "clean exit reverted"
[ "$(hash "$WPA3_SUPPLICANT_SYS")" = "$bin_hash" ] || fail "clean exit unmounted"
run_stop_post exit-code
called "umount|-l|$WPA3_SUPPLICANT_SYS"
[ "$(hash "$WPA3_SUPPLICANT_SYS")" = "$WPA3_SUPPLICANT_STOCK_SHA256" ] || fail "crash did not restore stock"
[ "$(cat "$WPA3_SUPPLICANT_FAILED")" = "$bin_hash exit-code" ] || fail "crash marker lost the reason"
[ ! -e "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" ] || fail "restored stock retained crash hook"
called "systemctl|daemon-reload"

reset_case
export STUB_ACTIVE_AFTER=3
run_override
[ "$(cat "$STUB_POLLS")" = 3 ] || fail "did not wait for activation"
not_called 'umount|'

# An active stock MainPID (e.g. D-Bus reactivation after a startup crash) must
# not satisfy the patched-binary check, even while the bind still points at it.
reset_case
export STUB_MAINPID_EXE="$STUB_STOCK_BACKUP"
run_override
called "systemctl|show|-p|MainPID|--value|wpa_supplicant"
called "sudo|sha256sum|/proc/4242/exe"
called "umount|-l|$WPA3_SUPPLICANT_SYS"
called "systemctl|reset-failed|wpa_supplicant"
[ "$(grep -Fxc 'systemctl|--no-block|restart|wpa_supplicant' "$STUB_CALLS")" = 2 ] || fail "stock not restarted"
[ "$(hash "$WPA3_SUPPLICANT_SYS")" = "$WPA3_SUPPLICANT_STOCK_SHA256" ] || fail "active stock was not restored"
[ "$(cat "$WPA3_SUPPLICANT_FAILED")" = "$bin_hash start" ] || fail "active stock bypassed the start failure brake"
[ ! -e "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" ] || fail "active stock retained crash hook"
[ "$SECONDS" -ge 15 ] && [ "$SECONDS" -le 16 ] || fail "active stock ended the poll early"
if grep -Fq 'WPA3: patched wpa_supplicant active' "$work/output"; then fail "stock reported as patched"; fi
: > "$STUB_CALLS"
run_override
no_change
log_has 'failed to start or failed three times'

for alive in 0 1; do
  reset_case
  export STUB_ACTIVE_RC=3 STUB_PROCESS_ALIVE="$alive"
  if [ "$alive" = 1 ]; then
    cp "$WPA3_SUPPLICANT_SYS" "$STUB_STOCK_BACKUP"
    cp "$WPA3_SUPPLICANT_BIN" "$WPA3_SUPPLICANT_SYS"
    if umount "$WPA3_SUPPLICANT_SYS"; then
      fail "ordinary unmount should fail while the executable is alive"
    else
      [ "$?" = 32 ] || fail "expected EBUSY exit 32"
    fi
    [ "$(hash "$WPA3_SUPPLICANT_SYS")" = "$bin_hash" ] || fail "busy bind disappeared"
    cp "$STUB_STOCK_BACKUP" "$WPA3_SUPPLICANT_SYS"
    : > "$STUB_CALLS"
  fi
  run_override
  called "umount|-l|$WPA3_SUPPLICANT_SYS"
  called "systemctl|reset-failed|wpa_supplicant"
  [ "$(grep -Fxc 'systemctl|--no-block|restart|wpa_supplicant' "$STUB_CALLS")" = 2 ] || fail "stock not restarted"
  [ "$(hash "$WPA3_SUPPLICANT_SYS")" = "$WPA3_SUPPLICANT_STOCK_SHA256" ] || fail "timeout did not restore stock"
  [ "$(cat "$WPA3_SUPPLICANT_FAILED")" = "$bin_hash start" ] || fail "missing start failure marker"
  [ ! -e "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" ] || fail "stock retained crash hook"
  [ "$SECONDS" -ge 15 ] && [ "$SECONDS" -le 16 ] || fail "wrong activation deadline"
  log_has 'reverted to stock wpa_supplicant'
  : > "$STUB_CALLS"
  run_override
  no_change
  log_has 'failed to start or failed three times'
done

# Even a successful umount exit status is insufficient: verify the stock digest.
for failure in error unchanged; do
  reset_case
  export STUB_ACTIVE_RC=3
  if [ "$failure" = error ]; then export STUB_UMOUNT_RC=32; else export STUB_UMOUNT_KEEP=1; fi
  run_override
  [ -f "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" ] || fail "unrestored stock lost the crash hook"
  [ "$(hash "$WPA3_SUPPLICANT_SYS")" = "$bin_hash" ] || fail "unexpected detach"
  [ "$(grep -Fxc 'systemctl|daemon-reload' "$STUB_CALLS")" = 1 ] || fail "unrestored stock reloaded the unit"
  log_has 'ERROR: stock wpa_supplicant not restored; crash hook remains armed'
  if grep -Fq 'reverted to stock' "$work/output"; then fail "false rollback success"; fi
  # The retained hook must also keep itself armed if its own detach fails.
  : > "$STUB_CALLS"
  run_stop_post signal > "$work/hook-output"
  called "umount|-l|$WPA3_SUPPLICANT_SYS"
  not_called 'systemctl|daemon-reload'
  [ -f "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" ] || fail "crash hook disarmed after failed detach"
  grep -Fq 'ERROR: stock wpa_supplicant not restored' "$work/hook-output" || fail "silent hook failure"
  if grep -Fq 'reverted to stock' "$work/hook-output"; then fail "false hook rollback success"; fi
  grep -Fxq "$bin_hash signal" "$WPA3_SUPPLICANT_FAILED" || fail "hook did not append SERVICE_RESULT"
  # Lazy detach can restore stock while the old executable is still alive.
  export STUB_UMOUNT_RC=0 STUB_UMOUNT_KEEP=0 STUB_PROCESS_ALIVE=1
  run_stop_post timeout
  [ "$(hash "$WPA3_SUPPLICANT_SYS")" = "$WPA3_SUPPLICANT_STOCK_SHA256" ] || fail "hook failed to detach busy executable"
  [ ! -e "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" ] || fail "restored hook not removed"
  grep -Fxq "$bin_hash timeout" "$WPA3_SUPPLICANT_FAILED" || fail "hook did not append timeout"
done

for failure in mount reload; do
  reset_case
  if [ "$failure" = mount ]; then export STUB_MOUNT_RC=1; else export STUB_RELOAD_RC=1; fi
  run_override
  [ ! -e "$WPA3_SUPPLICANT_DROPIN_DIR/wpa3.conf" ] || fail "$failure failure retained drop-in"
  [ "$(hash "$WPA3_SUPPLICANT_SYS")" = "$WPA3_SUPPLICANT_STOCK_SHA256" ] || fail "$failure failure changed stock"
  [ "$(grep -Fxc 'systemctl|daemon-reload' "$STUB_CALLS")" = 2 ] || fail "$failure cleanup not reloaded"
  not_called 'systemctl|--no-block|restart'
  not_called 'umount|'
  [ ! -e "$WPA3_SUPPLICANT_FAILED" ] || fail "$failure failure blacklisted binary"
done

# Exercise unit argument escaping as well as spaces, without interpolating paths
# into shell code. The hook must receive these exact literal path strings.
special="$work/quote'\"\\\$%"
mkdir -p "$special"
export WPA3_SUPPLICANT_SYS="$special/sys"
export WPA3_SUPPLICANT_FAILED="$special/failed"
reset_case
run_override
: > "$STUB_CALLS"
run_stop_post success
[ ! -s "$STUB_CALLS" ] || fail "quoted clean exit reverted"
run_stop_post exit-code
called "umount|-l|$WPA3_SUPPLICANT_SYS"
[ "$(cat "$WPA3_SUPPLICANT_FAILED")" = "$bin_hash exit-code" ] || fail "quoted crash marker lost"
echo 'PASS: wpa3_supplicant_override (guards, MainPID executable, failure reasons/threshold, busy bind, verified rollback, retained crash hook, unit quoting)'
