#!/usr/bin/env python3
"""Resolve a pinned, equivalent-kernel derived, or native-SAE AGNOS nightly."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import sys

from boot_download import fetch_boot
from compose import AGNOS_PY, MANIFEST, ROOT, blob, error_text, git, launch_values, pin_description, resolve_commit, validate_pin
from kernel_equiv import equivalent, native_sae


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


def resolve(repo, upstream, pins, fetch):
  tags, hashes = {}, {}
  for pin_version, pin in pins.items():
    validate_pin(pin_version, pin)
    tag, digest = pin["tag"], pin["boot"]["hash_raw"]
    if tag in tags and tags[tag][0] != digest:
      raise ValueError(f"pins {tags[tag][1]} and {pin_version}: tag {tag!r} identifies different boot hashes")
    if digest in hashes and hashes[digest][0] != tag:
      raise ValueError(f"pins {hashes[digest][1]} and {pin_version}: boot hash {digest} has different tags")
    tags[tag], hashes[digest] = (digest, pin_version), (tag, pin_version)
  version = launch_values(blob(repo, upstream, "launch_env.sh"))[0]
  if version in pins:
    return {"mode": "pinned", "version": version, "pin": pins[version]}

  manifest = json.loads(blob(repo, upstream, MANIFEST))
  boot = partition(manifest, "boot")
  stock = download(fetch, f"upstream AGNOS {version}", boot["url"], boot["hash_raw"], boot["size"])
  sae, counts = native_sae(stock)
  if sae == "all":
    return {"mode": "native", "version": version}
  if sae == "partial":
    raise ValueError(f"partial SAE markers in AGNOS {version}: {counts}")

  bases = sorted(pins, key=version_key, reverse=True)
  reasons = []
  for base in bases:
    pin = pins[base]
    origin = pin["derived_from"]
    base_stock = download(fetch, f"base AGNOS {base}", origin["boot_url"], origin["boot_hash_raw"], None)
    same, why = equivalent(base_stock, stock)
    if not same:
      reasons.append(f"{base}: {'; '.join(why)}")
      continue
    agnos_py = git(repo, "rev-parse", f"{upstream}:{AGNOS_PY}").decode().strip()
    if agnos_py != origin["agnos_py_blob"]:
      raise ValueError(f"agnos.py changed since {base}: {agnos_py}")
    derived = deepcopy(pin)
    derived["derived_from"] = {
      "boot_hash_raw": boot["hash_raw"],
      "boot_url": boot["url"],
      "system_hash_raw": partition(manifest, "system")["hash_raw"],
      "agnos_py_blob": agnos_py,
    }
    return {"mode": "derived", "version": version, "base": base, "pin": derived}
  raise ValueError(f"kernel changed since {', '.join(bases) or '(no base pins)'}: "
                   f"{'; '.join(reasons) or 'no stock boot available for comparison'}")


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--repo", required=True, type=Path, help="local bare repository")
  parser.add_argument("--upstream", required=True)
  parser.add_argument("--out", required=True, type=Path)
  args = parser.parse_args()
  try:
    upstream = resolve_commit(args.repo, args.upstream)
    pins = json.loads((ROOT / "agnos/pins.json").read_text())
    resolved = resolve(args.repo, upstream, pins, fetch_boot)
    args.out.write_text(json.dumps(resolved, sort_keys=True, indent=2) + "\n")
    print(f"PIN: OK: {pin_description(resolved)}")
  except Exception as error:
    print(f"PIN: FAIL: {error_text(error)}", file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
