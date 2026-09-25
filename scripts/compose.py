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
STOCK_MANIFEST = "openpilot/common/hardware/comma/agnos.stock.json"
AGNOS_PY = "openpilot/common/hardware/comma/agnos.py"
LAUNCHER_PATCH = ROOT / "patches/launcher-wpa3.patch"
UI_PATCH = ROOT / "patches/ui-wpa3.patch"
UI_ALLOWED = {
  "openpilot/system/ui/lib/networkmanager.py",
  "openpilot/system/ui/lib/wifi_manager.py",
  "openpilot/system/ui/lib/tests/test_security_type.py",
}
SUPPLICANT_FILES = {
  "wpa3/wpa_supplicant": ("path", "100755"),
  "wpa3/wpa_supplicant.copyright": ("copyright", "100644"),
}
ALLOWED = UI_ALLOWED | {
  "launch_chffrplus.sh", "launch_env.sh", MANIFEST, STOCK_MANIFEST,
  "openpilot/system/updated/updated.py",
} | SUPPLICANT_FILES.keys()
NATIVE_ALLOWED = ALLOWED - {MANIFEST, STOCK_MANIFEST}
LFS_ENV = {"GIT_LFS_SKIP_SMUDGE": "1", "GIT_LFS_SKIP_PUSH": "1"}
BOOT_KEYS = ("name", "url", "hash", "hash_raw", "size", "sparse", "full_check", "has_ab", "ondevice_hash")


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
  command = ('unset AGNOS_VERSION WPA3_BOOT_TAG WPA3_BOOT_HASH WPA3_SUPPLICANT_STOCK_SHA256; source "$1"; '
             'printf "%s\\0" "$AGNOS_VERSION" "$WPA3_BOOT_TAG" "$WPA3_BOOT_HASH" "$WPA3_SUPPLICANT_STOCK_SHA256"')
  # macOS bash 3.2 can read an empty /dev/stdin when sourcing a pipe under load.
  with tempfile.NamedTemporaryFile(prefix="wpa3-launch-", suffix=".sh") as source:
    source.write(script)
    source.flush()
    result = subprocess.run(["bash", "-e", "-c", command, "launch-values", source.name], check=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env={**os.environ, "BASH_ENV": "/dev/null"})
  values = result.stdout.decode().split("\0")
  if len(values) != 5 or values[-1] != "":
    raise ValueError("launch_env.sh must source quietly and export the expected values")
  return tuple(values[:4])


def pin_description(resolved):
  base = f" from {resolved['base']}" if resolved["mode"] == "derived" else ""
  return f"{resolved['mode']} {resolved['version']}{base}"


def validate_pin(version, pin):
  def require(value, keys, prefix=""):
    if not isinstance(value, dict):
      raise ValueError(f"pin {version}: {prefix or 'entry'} must be an object")
    for key in keys:
      if key not in value:
        raise ValueError(f"pin {version}: missing {prefix}{key}")

  require(pin, ("tag", "release_tag", "derived_from", "boot"))
  require(pin["derived_from"], ("boot_url", "boot_hash_raw", "system_hash_raw", "agnos_py_blob"), "derived_from.")
  require(pin["boot"], BOOT_KEYS, "boot.")
  try:
    validate_pin_values(pin)
  except (ValueError, TypeError) as error:
    raise ValueError(f"pin {version}: {error}") from error


def validate_pin_values(pin):
  if not re.fullmatch(r"[A-Za-z0-9_.=-]+", pin["tag"]):
    raise ValueError("pin tag must be one shell-safe kernel command-line token")
  boot = pin["boot"]
  if boot["name"] != "boot" or not re.fullmatch(r"[0-9a-f]{64}", boot["hash_raw"]):
    raise ValueError("pin must describe a boot image with a SHA-256 hash_raw")
  if boot["hash"] != boot["hash_raw"] or boot["sparse"] or not boot["full_check"] or not boot["has_ab"]:
    raise ValueError("pin must describe a raw, fully checked A/B boot image")
  if set(boot) != set(BOOT_KEYS):
    raise ValueError(f"unexpected boot keys: {sorted(set(boot) - set(BOOT_KEYS))}")
  origin = pin["derived_from"]
  for key in ("boot_hash_raw", "system_hash_raw"):
    if not re.fullmatch(r"[0-9a-f]{64}", origin[key]):
      raise ValueError(f"derived_from.{key} must be a SHA-256 hash")
  if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", origin["agnos_py_blob"]):
    raise ValueError("derived_from.agnos_py_blob must be a Git blob id")
  if not isinstance(origin["boot_url"], str) or not origin["boot_url"]:
    raise ValueError("derived_from.boot_url must be a nonempty URL")
  if "wpa_supplicant" in pin:
    validate_supplicant(pin["wpa_supplicant"])


def validate_supplicant(supplicant):
  if not isinstance(supplicant, dict):
    raise ValueError("wpa_supplicant must be an object")
  keys = ("path", "sha256", "copyright", "stock_sha256")
  for key in keys:
    if key not in supplicant:
      raise ValueError(f"missing wpa_supplicant.{key}")
  if set(supplicant) != set(keys):
    raise ValueError("unexpected wpa_supplicant keys")
  for key in ("sha256", "stock_sha256"):
    if not isinstance(supplicant[key], str) or not re.fullmatch(r"[0-9a-f]{64}", supplicant[key]):
      raise ValueError(f"wpa_supplicant.{key} must be a SHA-256 hash")
  for key in ("path", "copyright"):
    repo_path(supplicant[key])


def repo_path(value):
  if (not isinstance(value, str) or not value or "\0" in value or Path(value).is_absolute()
      or ".." in Path(value).parts or Path(value) == Path(".")):
    raise ValueError("wpa_supplicant paths must be relative files inside the repo")
  path = (ROOT / value).resolve()
  if not path.is_relative_to(ROOT.resolve()) or path == ROOT.resolve():
    raise ValueError("wpa_supplicant paths must stay inside the repo")
  return path


def supplicant_files(pin):
  if "wpa_supplicant" not in pin:
    return {}
  supplicant = pin["wpa_supplicant"]
  binary = repo_path(supplicant["path"]).read_bytes()
  if hashlib.sha256(binary).hexdigest() != supplicant["sha256"]:
    raise ValueError("wpa_supplicant SHA-256 differs from pin")
  return {
    path: (mode, binary if key == "path" else repo_path(supplicant[key]).read_bytes())
    for path, (key, mode) in SUPPLICANT_FILES.items()
  }


def load_pin(repo, upstream, pin_file):
  version = launch_values(blob(repo, upstream, "launch_env.sh"))[0]
  resolved = json.loads(Path(pin_file).read_text())
  if resolved["mode"] not in ("pinned", "derived", "native"):
    raise ValueError("unknown resolved pin mode")
  if resolved["version"] != version:
    raise ValueError(f"resolved pin version {resolved['version']!r} does not match upstream AGNOS {version!r}")
  if resolved["mode"] == "native":
    if "wpa_supplicant" in resolved:
      if not resolved.get("base"):
        raise ValueError("native supplicant has no base version")
      validate_supplicant(resolved["wpa_supplicant"])
    return resolved
  if resolved["mode"] == "derived" and not resolved.get("base"):
    raise ValueError("derived pin has no base version")
  validate_pin(version, resolved["pin"])
  # Match upstream's field order even if resolved JSON has been reordered.
  resolved["pin"]["boot"] = {key: resolved["pin"]["boot"][key] for key in BOOT_KEYS}
  return resolved


def inputs_hash(upstream, resolved):
  # Hash the entire resolved pin as canonical JSON, independent of file formatting.
  inputs = {
    "upstream": upstream,
    "patches": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (LAUNCHER_PATCH, UI_PATCH)},
    "pin": resolved,
    "compose.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
  }
  pin = resolved if resolved["mode"] == "native" else resolved["pin"]
  if "wpa_supplicant" in pin:
    # The binary digest is in the pin; the accompanying license also affects the tree.
    copyright_file = repo_path(pin["wpa_supplicant"]["copyright"])
    inputs["wpa_supplicant.copyright"] = hashlib.sha256(copyright_file.read_bytes()).hexdigest()
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


def put_blob(repo, env, path, data, mode=None):
  if mode is None:
    mode = git(repo, "ls-files", "--stage", "--", path, env=env).split()[0].decode()
  if mode not in ("100644", "100755"):
    raise ValueError(f"refusing to replace non-regular file {path} (mode {mode})")
  oid = git(repo, "hash-object", "-w", "--stdin", data=data).decode().strip()
  git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}", env=env)


def manifest_bytes(entries):
  return (json.dumps(entries, indent=2) + "\n").encode()


def post_checks(repo, upstream, tree, resolved, scratch):
  native = resolved["mode"] == "native"
  pin = resolved if native else resolved["pin"]
  allowed = NATIVE_ALLOWED if native else ALLOWED
  if "wpa_supplicant" not in pin:
    allowed = allowed - SUPPLICANT_FILES.keys()
  changed = git(repo, "diff-tree", "--no-commit-id", "-r", "--name-only", "-z", upstream, tree).decode().split("\0")
  for path in filter(None, changed):
    if path not in allowed and not path.startswith(".github/workflows/"):
      raise ValueError(f"unexpected composed change: {path}")
    if path.endswith(".py") and path in allowed:
      source = scratch / Path(path).name
      source.write_bytes(blob(repo, tree, path))
      py_compile.compile(str(source), cfile=str(source) + "c", doraise=True)
  if git(repo, "ls-tree", "-r", tree, "--", ".github/workflows"):
    raise ValueError("composed tree still contains upstream workflows")
  version = resolved["version"]
  for path in ("launch_chffrplus.sh", "launch_env.sh"):
    subprocess.run(["bash", "-n"], input=blob(repo, tree, path), check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  launch_env = blob(repo, tree, "launch_env.sh")
  if b"__WPA3_" in launch_env:
    raise ValueError("unfilled launch_env.sh placeholders")
  stock_sha256 = pin.get("wpa_supplicant", {}).get("stock_sha256", "")
  tag, boot_hash = ("", "") if native else (pin["tag"], pin["boot"]["hash_raw"])
  if launch_values(launch_env) != (version, tag, boot_hash, stock_sha256):
    raise ValueError("composed launch_env.sh values do not match the pin")
  for path, (mode, data) in supplicant_files(pin).items():
    oid = git(repo, "hash-object", "--stdin", data=data).decode().strip()
    if git(repo, "ls-tree", tree, "--", path).decode().strip() != f"{mode} blob {oid}\t{path}":
      raise ValueError(f"composed {path} must match the pinned file with mode {mode}")

  original = blob(repo, upstream, MANIFEST)
  if native:
    if blob(repo, tree, MANIFEST) != original or git(repo, "ls-tree", tree, "--", STOCK_MANIFEST):
      raise ValueError("native mode must retain the upstream manifest without agnos.stock.json")
    return
  if blob(repo, tree, STOCK_MANIFEST) != original:
    raise ValueError("stock manifest differs from upstream manifest bytes")
  if not git(repo, "ls-tree", tree, "--", STOCK_MANIFEST).startswith(b"100644 blob "):
    raise ValueError("stock manifest must have mode 100644")
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


def compose(repo, upstream, resolved):
  native = resolved["mode"] == "native"
  pin = resolved if native else resolved["pin"]
  files = supplicant_files(pin)
  inputs = inputs_hash(upstream, resolved)
  with temporary_index(repo, upstream) as (env, scratch):
    git(repo, "apply", "--cached", "--whitespace=error", str(LAUNCHER_PATCH), env=env)
    launch_env = git(repo, "show", ":launch_env.sh", env=env)
    for name, value in (("BOOT_TAG", "" if native else pin["tag"]), ("BOOT_HASH", "" if native else pin["boot"]["hash_raw"]),
                        ("SUPPLICANT_STOCK_SHA256", pin.get("wpa_supplicant", {}).get("stock_sha256", ""))):
      placeholder = f"__WPA3_{name}__".encode()
      if launch_env.count(placeholder) != 1:
        raise ValueError(f"expected exactly one {placeholder.decode()} placeholder")
      launch_env = launch_env.replace(placeholder, value.encode())
    put_blob(repo, env, "launch_env.sh", launch_env)
    for path, (mode, data) in files.items():
      put_blob(repo, env, path, data, mode=mode)

    if not native:
      original = blob(repo, upstream, MANIFEST)
      entries = json.loads(original)
      assert manifest_bytes(entries) == original, "upstream manifest no longer round-trips byte-for-byte"
      if len([p for p in entries if p["name"] == "boot"]) != 1:
        raise ValueError("upstream manifest must have exactly one boot entry")
      put_blob(repo, env, MANIFEST, manifest_bytes([pin["boot"] if p["name"] == "boot" else p for p in entries]))
      put_blob(repo, env, STOCK_MANIFEST, original, mode="100644")

    workflows = git(repo, "ls-files", "-z", "--", ".github/workflows", env=env)
    if workflows:
      removals = b"".join(b"0 " + b"0" * len(upstream) + b"\t" + path + b"\0" for path in workflows.split(b"\0") if path)
      git(repo, "update-index", "-z", "--index-info", data=removals, env=env)
    apply_ui(repo, env)
    tree = git(repo, "write-tree", env=env).decode().strip()
    post_checks(repo, upstream, tree, resolved, scratch)

  date = git(repo, "show", "-s", "--format=%cI", upstream).decode().strip()
  subject = git(repo, "show", "-s", "--format=%s", upstream).decode().strip()
  identity = {f"GIT_{role}_{key}": value for role in ("AUTHOR", "COMMITTER")
              for key, value in (("NAME", "openpilot-wpa3-bot"), ("EMAIL", "shunnag@users.noreply.github.com"), ("DATE", date))}
  message = (f"{subject} + WPA3\n\nUpstream-Commit: {upstream}\n"
             f"WPA3-Inputs: {inputs}\nWPA3-AGNOS: {'none' if native else resolved['pin']['release_tag']}\n"
             f"WPA3-Pin: {pin_description(resolved)}\n")
  commit = git(repo, "-c", "commit.gpgsign=false", "commit-tree", tree, "-p", upstream,
               data=message.encode(), env=identity).decode().strip()
  return commit, inputs


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--repo", required=True, type=Path, help="local bare repository")
  parser.add_argument("--upstream", required=True, help="already fetched upstream commit")
  parser.add_argument("--pin-file", required=True, type=Path, help="resolved JSON from pins.py")
  parser.add_argument("--inputs-only", action="store_true", help="print only WPA3-Inputs, without composing")
  args = parser.parse_args()
  try:
    repo = args.repo.resolve()
    upstream = resolve_commit(repo, args.upstream)
    resolved = load_pin(repo, upstream, args.pin_file)
    if args.inputs_only:
      print(inputs_hash(upstream, resolved))
    else:
      commit, inputs = compose(repo, upstream, resolved)
      print(f"{commit}\n{inputs}")
  except (OSError, ValueError, AssertionError, KeyError, subprocess.CalledProcessError, py_compile.PyCompileError) as error:
    print(f"compose: FAIL: {error_text(error)}", file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
