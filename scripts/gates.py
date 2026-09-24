#!/usr/bin/env python3
"""Fail closed when the upstream tree or the pinned boot image has drifted."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import sys
import urllib.request

from compose import AGNOS_PY, LAUNCHER_PATCH, MANIFEST, apply_ui, blob, error_text, git, load_pin, resolve_commit, temporary_index


def check_download(boot):
  request = urllib.request.Request(boot["url"], headers={"User-Agent": "openpilot-wpa3-ci", "Accept-Encoding": "identity"})
  digest = hashlib.sha256()
  size = 0
  # urlopen follows redirects; LZMAFile streams the decompressed bytes in bounded chunks.
  with urllib.request.urlopen(request, timeout=60) as response, lzma.LZMAFile(response) as image:
    while chunk := image.read(1024 * 1024):
      size += len(chunk)
      if size > boot["size"]:
        raise ValueError(f"boot download exceeds expected raw size {boot['size']}")
      digest.update(chunk)
  if size != boot["size"] or digest.hexdigest() != boot["hash_raw"]:
    raise ValueError(f"boot download mismatch: raw size={size}, sha256={digest.hexdigest()}")


def run_gates(repo, upstream, skip_download=False):
  gate = "G1"
  try:
    upstream = resolve_commit(repo, upstream)
    version, pin = load_pin(repo, upstream)
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
    with temporary_index(repo, upstream) as (env, _):
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
  except Exception as error:
    print(f"{gate}: FAIL: {error_text(error)}", file=sys.stderr, flush=True)
    return 1
  return 0


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--repo", required=True, type=Path)
  parser.add_argument("--upstream", required=True)
  parser.add_argument("--skip-download", action="store_true", help="skip G4 for offline tests; never use when publishing")
  args = parser.parse_args()
  return run_gates(args.repo.resolve(), args.upstream, args.skip_download)


if __name__ == "__main__":
  sys.exit(main())
