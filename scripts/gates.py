#!/usr/bin/env python3
"""Fail closed when the upstream tree or the pinned boot image has drifted."""
import argparse
import json
from pathlib import Path
import sys

from boot_download import fetch_boot
from compose import AGNOS_PY, LAUNCHER_PATCH, MANIFEST, apply_ui, blob, error_text, git, launch_values, load_pin, resolve_commit, temporary_index


def check_download(boot):
  fetch_boot(boot["url"], boot["hash_raw"], boot["size"])


def run_gates(repo, upstream, pin_file, skip_download=False, published=None):
  gate = "G1"
  try:
    upstream = resolve_commit(repo, upstream)
    resolved = load_pin(repo, upstream, pin_file)
    version = resolved["version"]
    native = resolved["mode"] == "native"
    if native:
      print(f"G1: OK: AGNOS {version}: native SAE in stock boot", flush=True)
      print("G2: SKIP: native stock manifest is retained", flush=True)
      print("G3: SKIP: native SAE needs no launcher patch or pinned agnos.py", flush=True)
      print("G4: SKIP: native stock boot was download-verified by the pin resolver", flush=True)
    else:
      pin = resolved["pin"]
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

    gate = "G5" if native else "G3"
    with temporary_index(repo, upstream) as (env, _):
      if not native:
        git(repo, "apply", "--cached", "--check", str(LAUNCHER_PATCH), env=env)
        print("G3: OK: agnos.py blob matches and launcher patch applies", flush=True)

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
      _, old_tag, old_hash = launch_values(blob(repo, published, "launch_env.sh"))
      if not old_tag:
        print("G6: SKIP: published build has no WPA3 boot tag", flush=True)
      else:
        tag, digest = pin["tag"], pin["boot"]["hash_raw"]
        if (old_tag == tag) != (old_hash == digest):
          raise ValueError(f"published {published} tag/hash {old_tag!r}/{old_hash} conflicts with AGNOS {version} {tag!r}/{digest}")
        print("G6: OK: published and resolved WPA3 tag/hash identities are consistent", flush=True)
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
  args = parser.parse_args()
  return run_gates(args.repo.resolve(), args.upstream, args.pin_file, args.skip_download, args.published)


if __name__ == "__main__":
  sys.exit(main())
