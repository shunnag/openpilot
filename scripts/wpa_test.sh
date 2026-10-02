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
cleanup() {
  if [[ -n $pid ]]; then sudo kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
  sudo umount "$root/run" 2>/dev/null || true
  sudo umount "$root/usr/sbin/wpa_supplicant" 2>/dev/null || true
  sudo umount "$root" 2>/dev/null || true
  sudo rm -rf "$work"
}
trap cleanup EXIT
mkdir "$root" "$runtime"
sudo mount -o loop,ro,noload "$raw" "$root"
sudo mount --bind "$candidate" "$root/usr/sbin/wpa_supplicant"
sudo mount -o remount,bind,ro "$root/usr/sbin/wpa_supplicant"
sudo chroot "$root" /usr/sbin/wpa_supplicant -v | grep -E '^wpa_supplicant v2\.10([ -]|$)'
echo 'T1: PASS'
sudo mount --bind "$runtime" "$root/run"
printf 'ctrl_interface=/run/ctrl\nupdate_config=1\n' > "$runtime/wpa.conf"
start() {
  # The log is deliberately owned by the invoking user, outside the chroot.
  # shellcheck disable=SC2024
  sudo chroot "$root" /usr/sbin/wpa_supplicant -Dnone -i wpa3test -c /run/wpa.conf > "$runtime/wpa.log" 2>&1 &
  pid=$!
  for ((i=0; i<50; i++)); do
    if [[ -S $runtime/ctrl/wpa3test ]]; then return; fi
    sleep 0.2
  done
  cat "$runtime/wpa.log"; return 1
}
cli() { sudo wpa_cli -p "$runtime/ctrl" -i wpa3test "$@"; }
start
[[ $(cli get sae_pwe) == 2 ]]
[[ $(cli set sae_pwe 0) == OK ]]
[[ $(cli save_config) == OK ]]
cli terminate
wait "$pid"
pid=
start
[[ $(cli get sae_pwe) == 0 ]]
cli terminate
wait "$pid"
pid=
echo 'T2: PASS: default 2; saved override 0 survives restart'
echo 'T3: PENDING (dryrun): Mac mini result required for future publication'
