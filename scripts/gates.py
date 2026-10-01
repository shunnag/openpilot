#!/usr/bin/env python3
"""Fail closed when the upstream tree or the pinned boot image has drifted."""
import argparse
import json
import os
from pathlib import Path
import sys

from boot_download import fetch_boot
from compose import AGNOS_PY, MANIFEST, apply_ui, blob, error_text, git, launch_values, load_pin, resolve_commit, select_launcher_patch, supplicant_files, temporary_index
from follow_state import load, mode_value, resolve_supplicant


def check_download(boot):
  fetch_boot(boot["url"], boot["hash_raw"], boot["size"])


def check_supplicant(pin):
  data = supplicant_files(pin)["wpa3/wpa_supplicant"][1]
  if (len(data) < 64 or data[:7] != b"\x7fELF\x02\x01\x01" or data[18:20] != b"\xb7\x00"
      or int.from_bytes(data[16:18], "little") not in (2, 3)):
    raise ValueError("wpa_supplicant must be an ELF64 little-endian aarch64 executable")


def check_g8(resolved, system_hash, state, mode="off", revoke=False):
  mode_value(mode)
  pin = resolved if resolved['mode'] == 'native' else resolved['pin']
  advisory = mode in ('off', 'dryrun') or revoke or pin.get('withdrawn') is not None
  try:
    checked = resolve_supplicant(resolved, system_hash, state, mode)
    if checked != resolved:
      raise ValueError('resolved supplicant does not match G8 probe data')
  except ValueError as error:
    if not advisory:
      raise
    print(f"G8: WARN: {error_text(error)}", flush=True)
  else:
    level = 'WARN' if advisory else 'OK'
    print(f"G8: {level}: probed stock wpa_supplicant and override agree", flush=True)


def run_gates(repo, upstream, pin_file, skip_download=False, published=None, follow_mode=None, revoke=False):
  gate = "G1"
  try:
    upstream = resolve_commit(repo, upstream)
    resolved = load_pin(repo, upstream, pin_file)
    version = resolved["version"]
    native = resolved["mode"] == "native"
    pin = resolved if native else resolved["pin"]
    if native:
      print(f"G1: OK: AGNOS {version}: native SAE/H2E in stock boot", flush=True)
      print("G2: SKIP: native stock manifest is retained", flush=True)
      print("G4: SKIP: native stock boot was download-verified by the pin resolver", flush=True)
    else:
      print(f"G1: OK: AGNOS {version} has pin {pin['release_tag']}", flush=True)

      gate = "G2"
      manifest = json.loads(blob(repo, upstream, MANIFEST))
      for name in ("boot", "system"):
        entries = [entry for entry in manifest if entry["name"] == name]
        expected = pin["derived_from"][f"{name}_hash_raw"]
        if len(entries) != 1 or entries[0]["hash_raw"] != expected:
          raise ValueError(f"upstream {name}.hash_raw differs from derived_from ({expected})")
      print("G2: OK: stock boot/system hashes match derived_from", flush=True)

      gate = "G3"
      oid = git(repo, "rev-parse", f"{upstream}:{AGNOS_PY}").decode().strip()
      if oid != pin["derived_from"]["agnos_py_blob"]:
        raise ValueError(f"upstream agnos.py blob changed: {oid}")

    gate = "G3"
    launcher_patch = select_launcher_patch(repo, upstream)
    with temporary_index(repo, upstream) as (env, _):
      if native:
        print(f"G3: SKIP: pinned agnos.py check in native mode; launcher patch {launcher_patch.name} applies", flush=True)
      else:
        print(f"G3: OK: agnos.py blob matches and launcher patch {launcher_patch.name} applies", flush=True)

        gate = "G4"
        if skip_download:
          print("G4: SKIP: --skip-download (offline test only)", flush=True)
        else:
          check_download(pin["boot"])
          print("G4: OK: downloaded xz boot image matches raw hash and size", flush=True)

      gate = "G5"
      print(f"G5: OK: UI patch {apply_ui(repo, env, check=True)}", flush=True)

    gate = "G6"
    if native:
      print("G6: SKIP: native mode has no WPA3 boot tag/hash", flush=True)
    elif not published:
      print("G6: SKIP: no published commit", flush=True)
    else:
      published = resolve_commit(repo, published)
      _, old_tag, old_hash, _ = launch_values(blob(repo, published, "launch_env.sh"))
      if not old_tag:
        print("G6: SKIP: published build has no WPA3 boot tag", flush=True)
      else:
        tag, digest = pin["tag"], pin["boot"]["hash_raw"]
        if (old_tag == tag) != (old_hash == digest):
          raise ValueError(f"published {published} tag/hash {old_tag!r}/{old_hash} conflicts with AGNOS {version} {tag!r}/{digest}")
        print("G6: OK: published and resolved WPA3 tag/hash identities are consistent", flush=True)

    gate = "G7"
    if "wpa_supplicant" not in pin:
      print("G7: SKIP: pin has no wpa_supplicant", flush=True)
    else:
      check_supplicant(pin)
      print("G7: OK: pinned wpa_supplicant SHA-256, aarch64 ELF and copyright verified", flush=True)

    gate = "G8"
    state = load()
    mode = os.environ.get('WPA3_FOLLOW_MODE', 'off') if follow_mode is None else follow_mode
    manifest = json.loads(blob(repo, upstream, MANIFEST))
    systems = [entry for entry in manifest if entry['name'] == 'system']
    if len(systems) != 1:
      raise ValueError('upstream manifest must have exactly one system entry')
    check_g8(resolved, systems[0]['hash_raw'], state, mode, revoke)
  except Exception as error:
    print(f"{gate}: FAIL: {error_text(error)}", file=sys.stderr, flush=True)
    return 1
  return 0


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--repo", required=True, type=Path)
  parser.add_argument("--upstream", required=True)
  parser.add_argument("--pin-file", required=True, type=Path, help="resolved JSON from pins.py")
  parser.add_argument("--published", help="currently published fork commit, if the branch exists")
  parser.add_argument("--skip-download", action="store_true", help="skip G4 for offline tests; never use when publishing")
  parser.add_argument("--follow-mode", default=os.environ.get("WPA3_FOLLOW_MODE", "off"))
  parser.add_argument("--revoke", action="store_true", help="G8 is advisory for a withdrawal publish")
  args = parser.parse_args()
  return run_gates(args.repo.resolve(), args.upstream, args.pin_file, args.skip_download, args.published, args.follow_mode, args.revoke)


if __name__ == "__main__":
  sys.exit(main())
