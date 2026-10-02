#!/usr/bin/env python3
"""Resolve a pinned, equivalent-kernel derived, or native-SAE AGNOS nightly."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from boot_download import fetch_boot
from compose import AGNOS_PY, MANIFEST, ROOT, blob, error_text, launch_values, pin_description, resolve_commit, validate_pin
from follow_state import FollowNeeded, follow_exit, load, merged_pins, mode_value, resolve_supplicant, validate
from kernel_equiv import equivalent, has_rsnxe, native_sae


def version_key(version):
  if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", version):
    raise ValueError(f"invalid numeric AGNOS base version {version!r}")
  return tuple(map(int, version.split(".")))


def partition(manifest, name):
  entries = [entry for entry in manifest if entry["name"] == name]
  if len(entries) != 1:
    raise ValueError(f"upstream manifest must have exactly one {name} entry")
  return entries[0]


def download(fetch, label, url, hash_raw, size):
  try:
    return fetch(url, hash_raw, size)
  except Exception as error:
    raise ValueError(f"{label} boot download failed: {error_text(error)}") from error


def git_blob_id(data):
  return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def resolve(reader, pins, fetch, *, state=None, mode="off", branch=None, now=None, warn=None):
  """Resolve using only reader(path) -> bytes and the injected boot fetcher."""
  mode_value(mode)
  state = deepcopy(load() if state is None else state)
  state['manual'] = deepcopy(pins)
  validate(state)  # Validate even ignored automatic state, before any download.
  pins = merged_pins(pins, state['pins'], mode, branch, state['policy']['allowed_branches'], now,
                     repository=state['policy']['repository'])

  def finish(resolved, system_hash):
    pin = resolved if resolved['mode'] == 'native' else resolved['pin']
    advisory = mode in ('off', 'dryrun') or pin.get('withdrawn') is not None
    try:
      checked = resolve_supplicant(resolved, system_hash, state, mode)
    except ValueError as error:
      if not advisory:
        raise
      if warn:
        warn(f"G8: WARN: {error_text(error)}")
    else:
      if not advisory:
        return checked
      if warn:
        warn("G8: WARN: advisory only; probed supplicant matches")
    return resolved

  version = launch_values(reader("launch_env.sh"))[0]
  if version in pins:
    return finish({"mode": "pinned", "version": version, "pin": pins[version]},
                  pins[version]["derived_from"]["system_hash_raw"])

  manifest = json.loads(reader(MANIFEST))
  boot = partition(manifest, "boot")
  stock = download(fetch, f"upstream AGNOS {version}", boot["url"], boot["hash_raw"], boot["size"])
  # A revoke must not wait on an unrelated newer base's expired stock URL.
  # Within each group keep the existing numeric descending preference.
  bases = sorted(pins, key=lambda version: (pins[version].get('withdrawn') is not None, version_key(version)), reverse=True)
  sae, counts = native_sae(stock)
  if sae == "all":
    if not has_rsnxe(stock):
      raise ValueError("stock kernel has SAE but no RSNXE (H2E); add a pin")
    resolved = {"mode": "native", "version": version}
    if bases:
      resolved["base"] = bases[0]
      if mode in ("off", "dryrun") and "wpa_supplicant" in pins[bases[0]]:
        resolved["wpa_supplicant"] = deepcopy(pins[bases[0]]["wpa_supplicant"])
    return finish(resolved, partition(manifest, "system")["hash_raw"])
  if sae == "partial":
    raise ValueError(f"partial SAE markers in AGNOS {version}: {counts}")

  reasons = []
  for base in bases:
    pin = pins[base]
    origin = pin["derived_from"]
    base_stock = download(fetch, f"base AGNOS {base}", origin["boot_url"], origin["boot_hash_raw"], None)
    same, why = equivalent(base_stock, stock)
    if not same:
      reasons.append(f"{base}: {'; '.join(why)}")
      continue
    agnos_py = git_blob_id(reader(AGNOS_PY))
    if agnos_py != origin["agnos_py_blob"]:
      raise ValueError(f"agnos.py changed since {base}: {agnos_py}")
    derived = deepcopy(pin)
    derived["derived_from"] = {
      "boot_hash_raw": boot["hash_raw"],
      "boot_url": boot["url"],
      "system_hash_raw": partition(manifest, "system")["hash_raw"],
      "agnos_py_blob": agnos_py,
    }
    if mode in ("state", "on") and derived.get('withdrawn') is None:
      # An inherited override is not an explicit manual pin for this new system.
      derived.pop("wpa_supplicant", None)
    return finish({"mode": "derived", "version": version, "base": base, "pin": derived},
                  derived["derived_from"]["system_hash_raw"])
  raise FollowNeeded("kernel", boot["hash_raw"], f"kernel changed since {', '.join(bases) or '(no base pins)'}: "
                   f"{'; '.join(reasons) or 'no stock boot available for comparison'}")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--repo", type=Path, help="local bare repository")
  parser.add_argument("--upstream")
  parser.add_argument("--out", type=Path)
  parser.add_argument("--validate-state", action="store_true")
  parser.add_argument("--state-root", type=Path, help="data root, only with --validate-state")
  parser.add_argument("--follow-mode", default=os.environ.get("WPA3_FOLLOW_MODE", "off"))
  parser.add_argument("--branch")
  parser.add_argument("--now", help="UTC timestamp for deterministic tests")
  args = parser.parse_args()
  follow_needed = None
  try:
    mode_value(args.follow_mode)
    if args.state_root is not None and not args.validate_state:
      raise ValueError("--state-root is only for --validate-state")
    state = load(args.state_root or ROOT)
    if args.validate_state:
      print("PIN: OK: state valid")
      return 0
    if args.repo is None or args.upstream is None or args.out is None:
      raise ValueError("--repo, --upstream and --out are required for resolution")
    upstream = resolve_commit(args.repo, args.upstream)
    try:
      resolved = resolve(lambda path: blob(args.repo, upstream, path), state['manual'], fetch_boot,
                         state=state, mode=args.follow_mode, branch=args.branch, now=args.now,
                         warn=lambda line: print(line, file=sys.stderr))
    except FollowNeeded as needed:
      follow_needed = needed
      rc = follow_exit(needed, args.follow_mode, state['policy'], state['status'])
      if rc == 3:
        print(f"PIN: FOLLOW: {needed.kind} {needed.key} {needed.detail}", file=sys.stderr)
        return 3
      raise ValueError(needed.detail) from needed
    args.out.write_text(json.dumps(resolved, sort_keys=True, indent=2) + "\n")
    print(f"PIN: OK: {pin_description(resolved)}")
  except Exception as error:
    print(f"PIN: FAIL: {error_text(error)}", file=sys.stderr)
    if follow_needed is not None and args.follow_mode in ('state', 'on'):
      print(f"PIN: KEY: {follow_needed.kind} {follow_needed.key} {follow_needed.detail}", file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
