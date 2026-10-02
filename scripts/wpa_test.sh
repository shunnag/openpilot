#!/bin/bash
# T0-T2, on a disposable native arm64 Linux runner. T3 is delegated to Mac mini.
set -euo pipefail
[[ $# == 3 ]] || { echo 'usage: wpa_test.sh CANDIDATE STOCK SYSTEM_RAW' >&2; exit 2; }
candidate=$(realpath "$1")
stock=$(realpath "$2")
raw=$(realpath "$3")
recipe=$(cd "$(dirname "$0")" && pwd)
python3 "$recipe/wpa_abi.py" "$candidate" "$stock"
work=$(mktemp -d)
root=$work/root
runtime=$work/run
pid=
mounted=()
interface_created=false
cleanup() {
  local rc=$? failed=0 i
  trap - EXIT
  set +e
  if [[ -n $pid ]]; then sudo kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
  if $interface_created; then sudo ip link delete wpa3test || failed=1; fi
  for ((i=${#mounted[@]}-1; i>=0; i--)); do
    sudo umount "${mounted[i]}" || failed=1
  done
  if ((rc != 0 || failed != 0)); then
    echo 'T2: wpa_supplicant log (all starts):' >&2
    if [[ -f $runtime/wpa.log ]]; then cat "$runtime/wpa.log" >&2; fi
  fi
  if ((failed == 0)); then
    sudo rm -rf "$work" || rc=1
  else
    echo "T2: cleanup failed; retaining $work" >&2
    rc=1
  fi
  exit "$rc"
}
trap cleanup EXIT
mount_at() {
  local target=$1
  shift
  sudo mount "$@" "$target"
  mounted+=("$target")
}
mkdir "$root" "$runtime"
mount_at "$root" -o loop,ro,noload "$raw"
mount_at "$root/usr/sbin/wpa_supplicant" --bind "$candidate"
sudo mount -o remount,bind,ro "$root/usr/sbin/wpa_supplicant"
sudo chroot "$root" /usr/sbin/wpa_supplicant -v | grep -E '^wpa_supplicant v2\.10([ -]|$)'
echo 'T1: PASS'
mount_at "$root/run" --bind "$runtime"
# The image stays read-only; both control endpoints share this writable /tmp.
mount_at "$root/tmp" -t tmpfs -o mode=1777,nosuid,nodev tmpfs
mount_at "$root/dev" --bind /dev
sudo mount -o remount,bind,ro "$root/dev"
if ! sudo test -x "$root/usr/sbin/wpa_cli"; then
  echo 'T2: FAIL: image is missing executable /usr/sbin/wpa_cli from its wpasupplicant package; cannot run the chroot control-interface test.' >&2
  exit 1
fi
# Ubuntu's -Dnone still opens an l2_packet socket, so the interface must exist.
sudo ip link add wpa3test type dummy
interface_created=true
sudo ip link set wpa3test up
printf 'ctrl_interface=/run/ctrl\nupdate_config=1\n' > "$runtime/wpa.conf"
cli() { sudo chroot "$root" /usr/sbin/wpa_cli -p /run/ctrl -i wpa3test "$@"; }
start() {
  # The log is deliberately owned by the invoking user, outside the chroot.
  echo 'Starting wpa_supplicant' >> "$runtime/wpa.log"
  # shellcheck disable=SC2024
  sudo chroot "$root" /usr/sbin/wpa_supplicant -Dnone -i wpa3test -c /run/wpa.conf >> "$runtime/wpa.log" 2>&1 &
  pid=$!
  for ((i=0; i<50; i++)); do
    if ! sudo kill -0 "$pid" 2>/dev/null; then
      echo 'T2: wpa_supplicant exited before control interface readiness' >&2
      return 1
    fi
    if [[ $(cli ping 2>/dev/null) == PONG ]]; then return; fi
    sleep 0.2
  done
  echo 'T2: control interface readiness timed out' >&2
  return 1
}
expect() {
  local expected=$1 actual
  shift
  actual=$(cli "$@")
  if [[ $actual != "$expected" ]]; then
    printf 'T2: %s: expected %q, got %q\n' "$*" "$expected" "$actual" >&2
    return 1
  fi
}
start
expect 2 get sae_pwe
expect OK set sae_pwe 0
expect OK save_config
expect OK terminate
wait "$pid"
pid=
start
expect 0 get sae_pwe
expect OK terminate
wait "$pid"
pid=
echo 'T2: PASS: default 2; saved override 0 survives restart'
echo 'T3: PENDING (dryrun): Mac mini result required for future publication'
