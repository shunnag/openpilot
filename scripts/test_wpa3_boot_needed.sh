#!/usr/bin/env bash
# Source only the WPA3 functions, never the launcher's device entrypoint.
set -euo pipefail
sed -n '/^function wpa3_.* {$/,/^}$/p' "$1" > "$2/wpa3-function.sh"
source "$2/wpa3-function.sh"
declare -F wpa3_boot_needed >/dev/null
export WPA3_CMDLINE_PATH="$2/cmdline"
export WPA3_ATTEMPTS_PATH="$2/attempts"
export WPA3_BOOT_TAG='wpa3.sae=1'
export WPA3_BOOT_HASH='hash-a'

fail() { echo "FAIL: $*" >&2; exit 1; }
not_needed() { if wpa3_boot_needed; then fail "unexpected boot trigger"; fi; }

printf 'hash-a 2\n' > "$WPA3_ATTEMPTS_PATH"
for cmdline in 'wpa3.sae=1' 'wpa3.sae=1 quiet' 'quiet wpa3.sae=1' $'quiet\twpa3.sae=1\tro'; do
  printf '%s\n' "$cmdline" > "$WPA3_CMDLINE_PATH"
  not_needed
  [ ! -e "$WPA3_ATTEMPTS_PATH" ] || fail "tag must clear attempts"
done

# Substrings are not whole command-line tokens.
printf 'quiet not-wpa3.sae=1 wpa3.sae=10\n' > "$WPA3_CMDLINE_PATH"
for count in 1 2 3; do
  wpa3_boot_needed || fail "attempt $count did not trigger"
  [ "$(cat "$WPA3_ATTEMPTS_PATH")" = "hash-a $count" ] || fail "wrong count $count"
done
not_needed
[ "$(cat "$WPA3_ATTEMPTS_PATH")" = 'hash-a 3' ] || fail "limit modified attempts"
printf 'hash-a 99999999999999999999999999\n' > "$WPA3_ATTEMPTS_PATH"
not_needed

export WPA3_BOOT_HASH='hash-b'
wpa3_boot_needed || fail "new hash did not reset attempts"
[ "$(cat "$WPA3_ATTEMPTS_PATH")" = 'hash-b 1' ] || fail "new hash did not start at 1"
printf 'hash-b invalid\n' > "$WPA3_ATTEMPTS_PATH"
not_needed

export WPA3_BOOT_TAG=''
not_needed
[ "$(cat "$WPA3_ATTEMPTS_PATH")" = 'hash-b invalid' ] || fail "empty tag changed attempts"
export WPA3_BOOT_TAG='wpa3.sae=1'
export WPA3_BOOT_HASH=''
not_needed

# A tag is literal, even if it contains shell glob characters.
export WPA3_BOOT_TAG='wpa3.test=*'
export WPA3_BOOT_HASH='hash-c'
printf 'wpa3.test=1\n' > "$WPA3_CMDLINE_PATH"
wpa3_boot_needed || fail "glob characters matched a different token"
printf 'wpa3.test=*\n' > "$WPA3_CMDLINE_PATH"
not_needed
[ ! -e "$WPA3_ATTEMPTS_PATH" ] || fail "literal tag did not clear attempts"
echo 'PASS: wpa3_boot_needed (tokens, counts 1/2/3, brake, hash reset, empty tag/hash)'

# A version bump uses the same counter before verifying/swapping the boot slot.
export WPA3_VERSION_PATH="$2/version"
export AGNOS_VERSION='19.9'
export WPA3_BOOT_TAG='wpa3.sae=1'
export WPA3_BOOT_HASH='hash-a'
DIR="$2/device"
STOCK="$DIR/openpilot/common/hardware/comma/agnos.stock.json"
WPA3="$DIR/openpilot/system/hardware/comma/agnos.json"
mkdir -p "$(dirname "$STOCK")"
printf '[]\n' > "$STOCK"
printf '19.8\n' > "$WPA3_VERSION_PATH"
printf 'quiet wpa3.sae=1\n' > "$WPA3_CMDLINE_PATH"
printf 'hash-a 2\n' > "$WPA3_ATTEMPTS_PATH"
wpa3_update_manifest
[ "$MANIFEST" = "$WPA3" ] || fail "proven kernel did not use WPA3 manifest"
[ "$(cat "$WPA3_ATTEMPTS_PATH")" = 'hash-a 2' ] || fail "proven kernel changed count"

printf 'quiet wpa3.sae=10\n' > "$WPA3_CMDLINE_PATH"
rm -f "$WPA3_ATTEMPTS_PATH"
for count in 1 2 3; do
  wpa3_update_manifest
  [ "$MANIFEST" = "$WPA3" ] || fail "attempt $count used stock prematurely"
  [ "$(cat "$WPA3_ATTEMPTS_PATH")" = "hash-a $count" ] || fail "mismatch wrong count $count"
done
for repeat in 1 2; do
  wpa3_update_manifest
  [ "$MANIFEST" = "$STOCK" ] || fail "exhausted counter did not fall back to stock ($repeat)"
  [ "$(cat "$WPA3_ATTEMPTS_PATH")" = 'hash-a 3' ] || fail "stock fallback changed count"
done
for invalid in 'hash-a invalid' 'hash-a' 'hash-a 2 junk' $'hash-a 2\njunk' 'hash-a 999999999999999999999999'; do
  printf '%s\n' "$invalid" > "$WPA3_ATTEMPTS_PATH"
  wpa3_update_manifest
  [ "$MANIFEST" = "$STOCK" ] || fail "malformed count did not use stock"
  [ "$(cat "$WPA3_ATTEMPTS_PATH")" = "$invalid" ] || fail "malformed count modified"
done
rm -f "$STOCK"
wpa3_update_manifest
[ "$MANIFEST" = "$WPA3" ] || fail "missing stock manifest did not retain WPA3 manifest"
[ "$(cat "$WPA3_ATTEMPTS_PATH")" = "$invalid" ] || fail "missing stock modified exhausted count"

# Equal-version flow counts only in wpa3_boot_needed, never twice.
printf '19.9\n' > "$WPA3_VERSION_PATH"
rm -f "$WPA3_ATTEMPTS_PATH"
wpa3_boot_needed || fail "equal-version retry did not trigger"
wpa3_update_manifest
[ "$MANIFEST" = "$WPA3" ] || fail "equal-version retry chose stock"
[ "$(cat "$WPA3_ATTEMPTS_PATH")" = 'hash-a 1' ] || fail "equal-version retry counted twice"
echo 'PASS: wpa3_update_manifest (version mismatch, proven tag, attempts 1/2/3, stock fallback, malformed, missing stock)'

# Native SAE/H2E uses the launcher patch with both boot placeholders disabled.
export WPA3_BOOT_TAG='' WPA3_BOOT_HASH=''
printf '19.8\n' > "$WPA3_VERSION_PATH"
printf 'hash-a 3\n' > "$WPA3_ATTEMPTS_PATH"
not_needed
wpa3_update_manifest
[ "$MANIFEST" = "$WPA3" ] || fail "native mode must update with the upstream manifest"
[ "$(cat "$WPA3_ATTEMPTS_PATH")" = 'hash-a 3' ] || fail "native version update changed retry count"
echo 'PASS: native boot placeholders (no boot trigger or version retry counting)'
