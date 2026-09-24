#!/usr/bin/env bash
# Source only the function from a patched launcher, never its device entrypoint.
set -euo pipefail
sed -n '/^function wpa3_boot_needed {$/,/^}$/p' "$1" > "$2/wpa3-function.sh"
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
