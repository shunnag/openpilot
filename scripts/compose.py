#!/usr/bin/env python3
"""Compose a deterministic WPA3 commit in a bare repository, without checkout."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import py_compile
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "openpilot/common/hardware/comma/agnos.json"
STOCK_MANIFEST = "openpilot/common/hardware/comma/agnos.stock.json"
AGNOS_PY = "openpilot/common/hardware/comma/agnos.py"
LAUNCHER_PATCHES = (ROOT / "patches/launcher-wpa3.patch", ROOT / "patches/launcher-wpa3-release.patch")
UI_PATCH = ROOT / "patches/ui-wpa3.patch"
MODEM_PATCH = ROOT / "patches/modem-apn.patch"
MODEM_PY = "openpilot/common/hardware/comma/modem.py"
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
  # Never execute upstream code in a job holding a write token. Only these
  # literal exports and the exact default-version block have meaning here.
  text = script.decode("utf-8")
  names = ("AGNOS_VERSION", "WPA3_BOOT_TAG", "WPA3_BOOT_HASH", "WPA3_SUPPLICANT_STOCK_SHA256")
  block = re.compile(r'^if \[ -z "\$AGNOS_VERSION" \]; then\n'
                     r'  export AGNOS_VERSION="([0-9]+(?:\.[0-9]+)*)"\nfi$', re.M)
  matches = list(block.finditer(text))
  if len(matches) != 1:
    raise ValueError("launch_env.sh requires exactly one AGNOS_VERSION default block")
  values = [matches[0][1]]
  remainder = block.sub("", text)
  for name, pattern in zip(names[1:], (r'(?:wpa3\.sae=[1-9][0-9]*)?', r'(?:[0-9a-f]{64})?', r'(?:[0-9a-f]{64})?')):
    assignment = re.compile(r'^export ' + name + r'="(' + pattern + r')"$', re.M)
    exports = list(assignment.finditer(remainder))
    if len(exports) > 1:
      raise ValueError(f"launch_env.sh has a second assignment of {name}")
    values.append(exports[0][1] if exports else "")
    remainder = assignment.sub("", remainder)
  if any(name in remainder for name in names):
    raise ValueError("launch_env.sh has an unexpected reference or assignment to a protected name")
  # Also reject command separators, substitutions and continuations that could
  # disguise one of the prohibited commands. Comments need no interpretation.
  for line in text.splitlines():
    if line.lstrip().startswith("#"):
      continue
    if (re.search(r'(?:^|[;&|()]|\bthen\s|\bdo\s)\s*(?:source\b|eval\b|\.\s)', line)
        or "$(" in line or "`" in line or line.endswith("\\") or "\0" in line or "\r" in line):
      raise ValueError("launch_env.sh contains a prohibited command or substitution")
  return tuple(values)


def pin_description(resolved):
  base = f" from {resolved['base']}" if resolved["mode"] == "derived" else ""
  return f"{resolved['mode']} {resolved['version']}{base}"


def validate_pin(version, pin, repository=None):
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
    if "auto" in pin:
      if repository is None:
        repository = json.loads((ROOT / "follow/policy.json").read_text())["repository"]
      validate_auto_pin(pin, repository)
    elif "revert" in pin or "withdrawn" in pin:
      raise ValueError("revert and withdrawn require auto metadata")
  except (ValueError, TypeError, KeyError) as error:
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
  if (type(boot["size"]) is not int or boot["size"] <= 0
      or any(type(boot[key]) is not bool for key in ("sparse", "full_check", "has_ab"))
      or not isinstance(boot["ondevice_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", boot["ondevice_hash"])):
    raise ValueError("boot size, flags or ondevice_hash invalid")
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


def utc_time(value):
  if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value):
    raise ValueError("expected a UTC timestamp YYYY-MM-DDTHH:MM:SSZ")
  return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def validate_auto_pin(pin, repository):
  meta = pin["auto"]
  keys = {"kernel_commit", "builder_commit", "recipe_sha256", "patchset_sha256", "baseline_release",
          "baseline_kernel_commit", "gate_version", "provenance_sha256", "run_url", "published_at"}
  if not isinstance(meta, dict) or set(meta) != keys:
    raise ValueError("invalid auto metadata keys")
  for key in ("kernel_commit", "builder_commit", "baseline_kernel_commit"):
    if not isinstance(meta[key], str) or not re.fullmatch(r"[0-9a-f]{40}", meta[key]):
      raise ValueError(f"auto.{key} must be a Git commit id")
  for key in ("recipe_sha256", "patchset_sha256", "gate_version", "provenance_sha256"):
    if not isinstance(meta[key], str) or not re.fullmatch(r"[0-9a-f]{64}", meta[key]):
      raise ValueError(f"auto.{key} must be a SHA-256 hash")
  release_pattern = r"agnos-[0-9]+(?:\.[0-9]+)*-wpa3\.[1-9][0-9]*"
  for value in (pin["release_tag"], meta["baseline_release"]):
    if not isinstance(value, str) or not re.fullmatch(release_pattern, value):
      raise ValueError("invalid auto release tag")
  if not isinstance(meta["run_url"], str) or not re.fullmatch(r"https://github\.com/" + re.escape(repository) + r"/actions/runs/[0-9]+", meta["run_url"]):
    raise ValueError("invalid auto.run_url")
  utc_time(meta["published_at"])
  if "withdrawn" not in pin:
    raise ValueError("missing withdrawn")
  if pin["withdrawn"] is not None:
    withdrawal = pin["withdrawn"]
    if (not isinstance(withdrawal, dict) or set(withdrawal) != {"at", "by", "reason"}
        or any(not isinstance(withdrawal[k], str) or not withdrawal[k].strip() for k in withdrawal)):
      raise ValueError("withdrawn must be null or {at, by, reason}")
    utc_time(withdrawal["at"])
  revert = pin.get("revert")
  if not isinstance(revert, dict) or set(revert) != {"tag", "boot"}:
    raise ValueError("revert must contain tag and boot")
  if not isinstance(revert["boot"], dict) or set(revert["boot"]) != set(BOOT_KEYS):
    raise ValueError("unexpected boot keys in revert")
  validate_pin_values({**pin, **revert})
  number = int(pin["release_tag"].rsplit(".", 1)[1])
  if revert["tag"] != f"wpa3.sae={number + 1}":
    raise ValueError("revert tag must follow the release tag number")
  if pin["tag"] != f"wpa3.sae={number}" and not (pin["withdrawn"] and pin["tag"] == revert["tag"] and pin["boot"] == revert["boot"]):
    raise ValueError("auto tag must match release number (or its withdrawn revert)")
  for boot in (pin["boot"], revert["boot"]):
    expected = f'https://github.com/{repository}/releases/download/{pin["release_tag"]}/boot-{boot["hash_raw"]}.img.xz'
    if boot["url"] != expected:
      raise ValueError("auto boot URL must match repository, release tag and hash_raw")
  origin = pin["derived_from"]
  url = urlsplit(origin["boot_url"])
  if (url.scheme != "https" or url.netloc != "commadist.azureedge.net" or url.query or url.fragment
      or url.path != f'/agnosupdate/boot-{origin["boot_hash_raw"]}.img.xz'):
    raise ValueError("auto derived_from.boot_url must name its stock hash on commadist")


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
      validate_supplicant(resolved["wpa_supplicant"])
    return resolved
  if resolved["mode"] == "derived" and not resolved.get("base"):
    raise ValueError("derived pin has no base version")
  validate_pin(version, resolved["pin"])
  # Match upstream's field order even if resolved JSON has been reordered.
  resolved["pin"]["boot"] = {key: resolved["pin"]["boot"][key] for key in BOOT_KEYS}
  return resolved


def inputs_hash(upstream, resolved, launcher_patch, modem="skip"):
  # Hash the entire resolved pin as canonical JSON, independent of file formatting.
  inputs = {
    "upstream": upstream,
    "patches": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (launcher_patch, UI_PATCH)},
    "pin": resolved,
    "compose.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
  }
  if modem == "apply":
    inputs["modem"] = modem
    inputs["patches"][MODEM_PATCH.name] = hashlib.sha256(MODEM_PATCH.read_bytes()).hexdigest()
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


def select_launcher_patch(repo, upstream):
  matches, diagnostics = [], []
  with temporary_index(repo, upstream) as (env, _):
    for patch in LAUNCHER_PATCHES:
      try:
        git(repo, "apply", "--cached", "--check", str(patch), env=env)
      except subprocess.CalledProcessError as error:
        diagnostics.append(f"{patch.name}: {error_text(error)}")
      else:
        matches.append(patch)
        diagnostics.append(f"{patch.name}: applies cleanly")
  if len(matches) != 1:
    reason = "no launcher patch applies" if not matches else "more than one launcher patch applies"
    raise ValueError(f"{reason}: {'; '.join(diagnostics)}")
  return matches[0]


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


def apply_modem(repo, env, check=False):
  try:
    git(repo, "apply", "--cached", "--reverse", "--check", str(MODEM_PATCH), env=env)
    return "already upstream"
  except subprocess.CalledProcessError:
    args = ["apply", "--cached", "--whitespace=error"]
    if check:
      args.append("--check")
    try:
      git(repo, *args, str(MODEM_PATCH), env=env)
    except subprocess.CalledProcessError as error:
      print(f"modem patch: skipped (does not apply): {error_text(error)}", file=sys.stderr)
      return "skipped (does not apply)"
    return "applies cleanly" if check else "applied"


def put_blob(repo, env, path, data, mode=None):
  if mode is None:
    mode = git(repo, "ls-files", "--stage", "--", path, env=env).split()[0].decode()
  if mode not in ("100644", "100755"):
    raise ValueError(f"refusing to replace non-regular file {path} (mode {mode})")
  oid = git(repo, "hash-object", "-w", "--stdin", data=data).decode().strip()
  git(repo, "update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}", env=env)


def manifest_bytes(entries, *, trailing_newline=True):
  return (json.dumps(entries, indent=2) + ("\n" if trailing_newline else "")).encode()


def release_notice(resolved):
  pin = resolved.get("pin", {})
  if "auto" not in pin:
    return b""
  if pin["withdrawn"] is not None:
    text = (f"WPA3 kernel {pin['release_tag']} was withdrawn; this update installs "
            f"comma's kernel for AGNOS {resolved['version']}.")
  else:
    text = (f"WPA3 kernel {pin['release_tag']} was built automatically and has NOT been tested on any device, "
            "and never on a comma 3X. Details and how to undo: github.com/shunnag/openpilot")
  return (text + "\n").encode()


def post_checks(repo, upstream, tree, resolved, scratch, modem_result="off"):
  native = resolved["mode"] == "native"
  pin = resolved if native else resolved["pin"]
  allowed = NATIVE_ALLOWED if native else ALLOWED
  if modem_result == "applied":
    allowed = allowed | {MODEM_PY}
  notice = release_notice(resolved)
  if notice:
    allowed = allowed | {"RELEASES.md"}
    if blob(repo, tree, "RELEASES.md") != notice + blob(repo, upstream, "RELEASES.md"):
      raise ValueError("RELEASES.md must contain exactly the one prepended notice line")
    if git(repo, "ls-tree", tree, "--", "RELEASES.md").split()[:1] != git(repo, "ls-tree", upstream, "--", "RELEASES.md").split()[:1]:
      raise ValueError("RELEASES.md mode changed")
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
  trailing_newline = original.endswith(b"\n")
  new_data = blob(repo, tree, MANIFEST)
  new_entries = json.loads(new_data)
  if new_data != manifest_bytes(new_entries, trailing_newline=trailing_newline):
    raise ValueError("composed manifest is not canonical upstream formatting")
  if [p for p in new_entries if p["name"] == "boot"] != [pin["boot"]]:
    raise ValueError("composed boot entry does not match the pin")
  old_boot = next(p for p in old_entries if p["name"] == "boot")
  restored = [old_boot if p["name"] == "boot" else p for p in new_entries]
  if manifest_bytes(restored, trailing_newline=trailing_newline) != original:
    raise ValueError("non-boot manifest bytes changed")


def compose(repo, upstream, resolved, modem="skip"):
  native = resolved["mode"] == "native"
  pin = resolved if native else resolved["pin"]
  files = supplicant_files(pin)
  launcher_patch = select_launcher_patch(repo, upstream)
  inputs = inputs_hash(upstream, resolved, launcher_patch, modem)
  with temporary_index(repo, upstream) as (env, scratch):
    notice = release_notice(resolved)
    if notice:
      releases = blob(repo, upstream, "RELEASES.md")
      if not re.match(rb"(?:#+ )?Version [^\n]+\n", releases):
        raise ValueError("RELEASES.md must start with the upstream Version heading")
      put_blob(repo, env, "RELEASES.md", notice + releases)
    git(repo, "apply", "--cached", "--whitespace=error", str(launcher_patch), env=env)
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
      trailing_newline = original.endswith(b"\n")
      assert manifest_bytes(entries, trailing_newline=trailing_newline) == original, "upstream manifest no longer round-trips byte-for-byte"
      if len([p for p in entries if p["name"] == "boot"]) != 1:
        raise ValueError("upstream manifest must have exactly one boot entry")
      put_blob(repo, env, MANIFEST, manifest_bytes([pin["boot"] if p["name"] == "boot" else p for p in entries],
                                                trailing_newline=trailing_newline))
      put_blob(repo, env, STOCK_MANIFEST, original, mode="100644")

    workflows = git(repo, "ls-files", "-z", "--", ".github/workflows", env=env)
    if workflows:
      removals = b"".join(b"0 " + b"0" * len(upstream) + b"\t" + path + b"\0" for path in workflows.split(b"\0") if path)
      git(repo, "update-index", "-z", "--index-info", data=removals, env=env)
    apply_ui(repo, env)
    modem_result = apply_modem(repo, env) if modem == "apply" else "off"
    tree = git(repo, "write-tree", env=env).decode().strip()
    post_checks(repo, upstream, tree, resolved, scratch, modem_result)

  date = git(repo, "show", "-s", "--format=%cI", upstream).decode().strip()
  subject = git(repo, "show", "-s", "--format=%s", upstream).decode().strip()
  identity = {f"GIT_{role}_{key}": value for role in ("AUTHOR", "COMMITTER")
              for key, value in (("NAME", "openpilot-wpa3-bot"), ("EMAIL", "shunnag@users.noreply.github.com"), ("DATE", date))}
  message = (f"{subject} + WPA3\n\nUpstream-Commit: {upstream}\n"
             f"WPA3-Inputs: {inputs}\nWPA3-AGNOS: {'none' if native else resolved['pin']['release_tag']}\n"
             f"WPA3-Pin: {pin_description(resolved)}\nWPA3-Launcher-Patch: {launcher_patch.name}\n"
             f"WPA3-Modem-Patch: {modem_result}\n"
             f"WPA3-Boot-Build: {'auto' if 'auto' in pin else 'manual'}\n")
  commit = git(repo, "-c", "commit.gpgsign=false", "commit-tree", tree, "-p", upstream,
               data=message.encode(), env=identity).decode().strip()
  return commit, inputs


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--repo", required=True, type=Path, help="local bare repository")
  parser.add_argument("--upstream", required=True, help="already fetched upstream commit")
  parser.add_argument("--pin-file", required=True, type=Path, help="resolved JSON from pins.py")
  parser.add_argument("--inputs-only", action="store_true", help="print only WPA3-Inputs, without composing")
  parser.add_argument("--modem", choices=("apply", "skip"), default="skip", help="optional modem APN patch")
  args = parser.parse_args()
  try:
    repo = args.repo.resolve()
    upstream = resolve_commit(repo, args.upstream)
    resolved = load_pin(repo, upstream, args.pin_file)
    if args.inputs_only:
      print(inputs_hash(upstream, resolved, select_launcher_patch(repo, upstream), args.modem))
    else:
      commit, inputs = compose(repo, upstream, resolved, args.modem)
      print(f"{commit}\n{inputs}")
  except (OSError, ValueError, AssertionError, KeyError, subprocess.CalledProcessError, py_compile.PyCompileError) as error:
    print(f"compose: FAIL: {error_text(error)}", file=sys.stderr)
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
