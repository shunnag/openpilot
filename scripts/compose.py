#!/usr/bin/env python3
"""Compose a deterministic WPA3 commit in a bare repository, without checkout."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import py_compile
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "openpilot/common/hardware/comma/agnos.json"
AGNOS_PY = "openpilot/common/hardware/comma/agnos.py"
LAUNCHER_PATCH = ROOT / "patches/launcher-wpa3.patch"
UI_PATCH = ROOT / "patches/ui-wpa3.patch"
ALLOWED = {
  "launch_chffrplus.sh", "launch_env.sh", MANIFEST,
  "openpilot/system/updated/updated.py",
  "openpilot/system/ui/lib/networkmanager.py",
  "openpilot/system/ui/lib/wifi_manager.py",
  "openpilot/system/ui/lib/tests/test_security_type.py",
}
LFS_ENV = {"GIT_LFS_SKIP_SMUDGE": "1", "GIT_LFS_SKIP_PUSH": "1"}


def git(repo, *args, data=None, env=None):
  return subprocess.run(
    ["git", "--git-dir", str(repo), "-c", "core.hooksPath=/dev/null", *args],
    input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    env={**os.environ, **LFS_ENV, **(env or {})},
  ).stdout


def error_text(error):
  if isinstance(error, subprocess.CalledProcessError):
    detail = (error.stderr or error.stdout or str(error).encode()).decode(errors="replace").strip()
    return f"{' '.join(map(str, error.cmd))}: {detail}"
  return str(error)


def resolve_commit(repo, upstream):
  if git(repo, "rev-parse", "--is-bare-repository").strip() != b"true":
    raise ValueError("a bare repository is required")
  return git(repo, "rev-parse", "--verify", f"{upstream}^{{commit}}").decode().strip()


def blob(repo, tree, path):
  return git(repo, "show", f"{tree}:{path}")


def launch_values(script):
  command = ('unset AGNOS_VERSION WPA3_BOOT_TAG WPA3_BOOT_HASH; source /dev/stdin; '
             'printf "%s\\0" "$AGNOS_VERSION" "$WPA3_BOOT_TAG" "$WPA3_BOOT_HASH"')
  result = subprocess.run(["bash", "-e", "-c", command], input=script, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env={**os.environ, "BASH_ENV": "/dev/null"})
  values = result.stdout.decode().split("\0")
  if len(values) != 4 or values[-1] != "":
    raise ValueError("launch_env.sh must source quietly and export the expected values")
  return tuple(values[:3])


def load_pin(repo, upstream):
  version = launch_values(blob(repo, upstream, "launch_env.sh"))[0]
  pins = json.loads((ROOT / "agnos/pins.json").read_text())
  if version not in pins:
    raise ValueError(f"AGNOS {version!r} has no pin in agnos/pins.json")
  pin = pins[version]
  if not re.fullmatch(r"[A-Za-z0-9_.=-]+", pin["tag"]):
    raise ValueError("pin tag must be one shell-safe kernel command-line token")
  boot = pin["boot"]
  if boot["name"] != "boot" or not re.fullmatch(r"[0-9a-f]{64}", boot["hash_raw"]):
    raise ValueError("pin must describe a boot image with a SHA-256 hash_raw")
  if boot["hash"] != boot["hash_raw"] or boot["sparse"] or not boot["full_check"] or not boot["has_ab"]:
    raise ValueError("pin must describe a raw, fully checked A/B boot image")
  # Match upstream's field order even if pins.json has been reordered.
  keys = ("name", "url", "hash", "hash_raw", "size", "sparse", "full_check", "has_ab", "ondevice_hash")
  if set(boot) != set(keys):
    raise ValueError("pin boot entry has missing or unexpected fields")
  pin["boot"] = {key: boot[key] for key in keys}
  return version, pin


def inputs_hash(upstream, pin):
  # Hash canonical JSON so key ordering/whitespace in pins.json does not matter.
  inputs = {
    "upstream": upstream,
    "patches": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (LAUNCHER_PATCH, UI_PATCH)},
    "pin": pin,
    "compose.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
  }
  return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@contextmanager
def temporary_index(repo, upstream):
  # Scratch blobs for syntax checks are not an upstream working tree.
  with tempfile.TemporaryDirectory(prefix="wpa3-", dir=repo) as directory:
    scratch = Path(directory)
    env = {"GIT_INDEX_FILE": str(scratch / "index")}
    git(repo, "read-tree", upstream, env=env)
    yield env, scratch


def apply_ui(repo, env, check=False):
  try:
    git(repo, "apply", "--cached", "--reverse", "--check", str(UI_PATCH), env=env)
    return "already applied"
  except subprocess.CalledProcessError:
    args = ["apply", "--cached", "--whitespace=error"]
    if check:
      args.append("--check")
    git(repo, *args, str(UI_PATCH), env=env)
    return "applies cleanly" if check else "applied"


def put_blob(repo, env, path, data):
  mode = git(repo, "ls-files", "--stage", "--", path, env=env).split()[0].decode()
  if mode not in ("100644", "100755"):
    raise ValueError(f"refusing to replace non-regular file {path} (mode {mode})")
  oid = git(repo, "hash-object", "-w", "--stdin", data=data).decode().strip()
  git(repo, "update-index", "--cacheinfo", f"{mode},{oid},{path}", env=env)


def manifest_bytes(entries):
  return (json.dumps(entries, indent=2) + "\n").encode()


def post_checks(repo, upstream, tree, version, pin, scratch):
  changed = git(repo, "diff-tree", "--no-commit-id", "-r", "--name-only", "-z", upstream, tree).decode().split("\0")
  for path in filter(None, changed):
    if path not in ALLOWED and not path.startswith(".github/workflows/"):
      raise ValueError(f"unexpected composed change: {path}")
    if path.endswith(".py") and path in ALLOWED:
      source = scratch / Path(path).name
      source.write_bytes(blob(repo, tree, path))
      py_compile.compile(str(source), cfile=str(source) + "c", doraise=True)
  if git(repo, "ls-tree", "-r", tree, "--", ".github/workflows"):
    raise ValueError("composed tree still contains upstream workflows")

  for path in ("launch_chffrplus.sh", "launch_env.sh"):
    subprocess.run(["bash", "-n"], input=blob(repo, tree, path), check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  launch_env = blob(repo, tree, "launch_env.sh")
  if b"__WPA3_BOOT_" in launch_env:
    raise ValueError("unfilled launch_env.sh placeholders")
  if launch_values(launch_env) != (version, pin["tag"], pin["boot"]["hash_raw"]):
    raise ValueError("composed launch_env.sh values do not match the pin")

  original = blob(repo, upstream, MANIFEST)
  old_entries = json.loads(original)
  new_data = blob(repo, tree, MANIFEST)
  new_entries = json.loads(new_data)
  if new_data != manifest_bytes(new_entries):
    raise ValueError("composed manifest is not canonical upstream formatting")
  if [p for p in new_entries if p["name"] == "boot"] != [pin["boot"]]:
    raise ValueError("composed boot entry does not match the pin")
  old_boot = next(p for p in old_entries if p["name"] == "boot")
  restored = [old_boot if p["name"] == "boot" else p for p in new_entries]
  if manifest_bytes(restored) != original:
    raise ValueError("non-boot manifest bytes changed")


def compose(repo, upstream, version, pin):
  inputs = inputs_hash(upstream, pin)
  with temporary_index(repo, upstream) as (env, scratch):
    git(repo, "apply", "--cached", "--whitespace=error", str(LAUNCHER_PATCH), env=env)
    apply_ui(repo, env)
    launch_env = git(repo, "show", ":launch_env.sh", env=env)
    for name, value in (("TAG", pin["tag"]), ("HASH", pin["boot"]["hash_raw"])):
      placeholder = f"__WPA3_BOOT_{name}__".encode()
      if launch_env.count(placeholder) != 1:
        raise ValueError(f"expected exactly one {placeholder.decode()} placeholder")
      launch_env = launch_env.replace(placeholder, value.encode())
    put_blob(repo, env, "launch_env.sh", launch_env)

    original = blob(repo, upstream, MANIFEST)
    entries = json.loads(original)
    assert manifest_bytes(entries) == original, "upstream manifest no longer round-trips byte-for-byte"
    if len([p for p in entries if p["name"] == "boot"]) != 1:
      raise ValueError("upstream manifest must have exactly one boot entry")
    put_blob(repo, env, MANIFEST, manifest_bytes([pin["boot"] if p["name"] == "boot" else p for p in entries]))

    workflows = git(repo, "ls-files", "-z", "--", ".github/workflows", env=env)
    if workflows:
      removals = b"".join(b"0 " + b"0" * len(upstream) + b"\t" + path + b"\0" for path in workflows.split(b"\0") if path)
      git(repo, "update-index", "-z", "--index-info", data=removals, env=env)
    tree = git(repo, "write-tree", env=env).decode().strip()
    post_checks(repo, upstream, tree, version, pin, scratch)

  date = git(repo, "show", "-s", "--format=%cI", upstream).decode().strip()
  subject = git(repo, "show", "-s", "--format=%s", upstream).decode().strip()
  identity = {f"GIT_{role}_{key}": value for role in ("AUTHOR", "COMMITTER")
              for key, value in (("NAME", "openpilot-wpa3-bot"), ("EMAIL", "shunnag@users.noreply.github.com"), ("DATE", date))}
  message = (f"{subject} + WPA3\n\nUpstream-Commit: {upstream}\n"
             f"WPA3-Inputs: {inputs}\nWPA3-AGNOS: {pin['release_tag']}\n")
  commit = git(repo, "-c", "commit.gpgsign=false", "commit-tree", tree, "-p", upstream,
               data=message.encode(), env=identity).decode().strip()
  return commit, inputs


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--repo", required=True, type=Path, help="local bare repository")
  parser.add_argument("--upstream", required=True, help="already fetched upstream commit")
  parser.add_argument("--inputs-only", action="store_true", help="print only WPA3-Inputs, without composing")
  args = parser.parse_args()
  try:
    repo = args.repo.resolve()
    upstream = resolve_commit(repo, args.upstream)
    version, pin = load_pin(repo, upstream)
    if args.inputs_only:
      print(inputs_hash(upstream, pin))
    else:
      commit, inputs = compose(repo, upstream, version, pin)
      print(f"{commit}\n{inputs}")
  except (OSError, ValueError, AssertionError, KeyError, subprocess.CalledProcessError, py_compile.PyCompileError) as error:
    print(f"compose: FAIL: {error_text(error)}", file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
