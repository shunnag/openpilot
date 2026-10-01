#!/usr/bin/env python3
import ast
from copy import deepcopy
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, call, patch
import urllib.error

import compose
import gates
import boot_download
from boot_fixture import boot_image, identity_pair
import pins

ROOT = compose.ROOT
REF = ROOT / "ref/nightly-chestnut"
RELEASE_REF = ROOT / "ref/release-staging"
UPDATED = "openpilot/system/updated/updated.py"
MANIFEST_LINK = "openpilot/system/hardware/comma/agnos.json"


class TestCompose(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    (ROOT / ".tmp").mkdir(exist_ok=True)
    cls.temp = tempfile.TemporaryDirectory(prefix="test-compose-", dir=ROOT / ".tmp")
    cls.addClassCleanup(cls.temp.cleanup)
    cls.work = Path(cls.temp.name)
    cls.repo = cls.work / "upstream.git"
    subprocess.run(["git", "init", "--bare", str(cls.repo)], check=True, capture_output=True, env={**os.environ, **compose.LFS_ENV})
    env = {"GIT_INDEX_FILE": str(cls.work / "index")}
    compose.git(cls.repo, "read-tree", "--empty", env=env)
    files = {str(p.relative_to(REF)): ("100755" if os.access(p, os.X_OK) else "100644", p.read_bytes())
             for p in REF.rglob("*") if p.is_file()}
    files[MANIFEST_LINK] = ("120000", b"../../../common/hardware/comma/agnos.json")
    files[".github/workflows/upstream.yml"] = ("100644", b"name: upstream workflow\n")
    files[".github/keep.txt"] = ("100644", b"keep this\n")
    files["openpilot/selfdrive/modeld/models/big_test_tinygrad.pkl"] = (
      "100644", b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 773000000\n")
    for path, (mode, data) in files.items():
      oid = compose.git(cls.repo, "hash-object", "-w", "--stdin", data=data).decode().strip()
      compose.git(cls.repo, "update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}", env=env)
    tree = compose.git(cls.repo, "write-tree", env=env).decode().strip()
    cls.identity = {f"GIT_{role}_{key}": value for role in ("AUTHOR", "COMMITTER")
                    for key, value in (("NAME", "fixture"), ("EMAIL", "fixture@example.com"), ("DATE", "2026-09-24T09:15:00+00:00"))}
    cls.upstream = compose.git(cls.repo, "commit-tree", tree, data=b"Synthetic upstream\n", env=cls.identity).decode().strip()
    cls.pin_file = cls.work / "pin.json"
    result = cls.cli("pins.py", cls.upstream, "--out", str(cls.pin_file))
    if result.stdout != "PIN: OK: pinned 19.8\n":
      raise AssertionError(result.stdout)
    cls.resolved = compose.load_pin(cls.repo, cls.upstream, cls.pin_file)
    cls.version, cls.pin = cls.resolved["version"], cls.resolved["pin"]
    result = cls.cli("compose.py", cls.upstream)
    cls.commit, cls.inputs = result.stdout.strip().splitlines()

  @classmethod
  def cli(cls, script, upstream, *args, check=True, pin_file=None):
    resolved_args = ["--pin-file", str(pin_file or cls.pin_file)] if script in ("compose.py", "gates.py") else []
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--repo", str(cls.repo), "--upstream", upstream,
                             *resolved_args, *args],
                            text=True, capture_output=True, env={**os.environ, **compose.LFS_ENV})
    if check and result.returncode:
      raise AssertionError(f"{script} failed:\n{result.stdout}{result.stderr}")
    return result

  def variant(self, path, data):
    return self.variant_many({path: data})

  def variant_many(self, changes, upstream=None):
    with compose.temporary_index(self.repo, upstream or self.upstream) as (env, _):
      for path, data in changes.items():
        compose.put_blob(self.repo, env, path, data)
      tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
      return compose.git(self.repo, "commit-tree", tree, data=b"Upstream drift\n", env=self.identity).decode().strip()

  def test_offline_gates(self):
    result = self.cli("gates.py", self.upstream, "--skip-download")
    for gate in ("G1", "G2", "G3", "G5", "G7"):
      self.assertIn(f"{gate}: OK:", result.stdout)
    self.assertIn("G4: SKIP:", result.stdout)
    self.assertIn("G6: SKIP: no published commit", result.stdout)
    self.assertIn("G3: OK: agnos.py blob matches and launcher patch launcher-wpa3.patch applies", result.stdout)

  def test_release_launcher_selection_and_compose(self):
    upstream = self.variant("launch_chffrplus.sh", (RELEASE_REF / "launch_chffrplus.sh").read_bytes())
    self.assertEqual(compose.select_launcher_patch(self.repo, upstream), compose.LAUNCHER_PATCHES[1])
    result = self.cli("gates.py", upstream, "--skip-download")
    self.assertIn("G3: OK: agnos.py blob matches and launcher patch launcher-wpa3-release.patch applies", result.stdout)
    commit, inputs = self.cli("compose.py", upstream).stdout.splitlines()
    self.assertEqual(self.cli("compose.py", upstream, "--inputs-only").stdout.strip(), inputs)
    self.assertNotEqual(inputs, self.inputs)
    message = compose.git(self.repo, "show", "-s", "--format=%B", commit).decode().strip()
    self.assertTrue(message.endswith("WPA3-Pin: pinned 19.8\nWPA3-Launcher-Patch: launcher-wpa3-release.patch\nWPA3-Boot-Build: manual"))
    launcher = compose.blob(self.repo, commit, "launch_chffrplus.sh")
    nightly_launcher = compose.blob(self.repo, self.commit, "launch_chffrplus.sh")

    def functions(script, pattern):
      return subprocess.run(["sed", "-n", pattern], input=script, capture_output=True, check=True).stdout

    pattern = '/^function wpa3_.* {$/,/^}$/p'
    self.assertEqual(functions(launcher, pattern), functions(nightly_launcher, pattern))
    agnos_init = functions(launcher, '/^function agnos_init {$/,/^}$/p')
    for expected in (b"|| wpa3_boot_needed", b"wpa3_update_manifest", b"wpa3_supplicant_override"):
      self.assertIn(expected, agnos_init)
    self.assertEqual(agnos_init.count(b"    $DIR/openpilot/common/hardware/comma/updater $AGNOS_PY $MANIFEST\n"), 1)
    self.assertNotIn(b"while true", agnos_init)
    launcher_file = self.work / "release-launcher.sh"
    launcher_file.write_bytes(launcher)
    work = self.work / "release-runtime"
    work.mkdir()
    for name, messages in (
      ("test_wpa3_boot_needed.sh", ("PASS: wpa3_boot_needed", "PASS: wpa3_update_manifest")),
      ("test_wpa3_supplicant_override.sh", ("PASS: wpa3_supplicant_override",)),
    ):
      with self.subTest(script=name):
        result = subprocess.run(["bash", str(ROOT / "scripts" / name), str(launcher_file), str(work)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for expected in messages:
          self.assertIn(expected, result.stdout)

  def test_launcher_patches_are_exclusive(self):
    release = self.variant("launch_chffrplus.sh", (RELEASE_REF / "launch_chffrplus.sh").read_bytes())
    nightly_patch, release_patch = compose.LAUNCHER_PATCHES
    for upstream, matching, other in ((self.upstream, nightly_patch, release_patch), (release, release_patch, nightly_patch)):
      with self.subTest(patch=matching.name), compose.temporary_index(self.repo, upstream) as (env, _):
        before = compose.git(self.repo, "write-tree", env=env)
        self.assertEqual(compose.select_launcher_patch(self.repo, upstream), matching)
        compose.git(self.repo, "apply", "--cached", "--check", str(matching), env=env)
        with self.assertRaises(subprocess.CalledProcessError):
          compose.git(self.repo, "apply", "--cached", "--check", str(other), env=env)
        self.assertEqual(compose.git(self.repo, "write-tree", env=env), before)
    self.assertFalse((self.repo / "index").exists())

  def test_unknown_launcher_fails_gates_compose_and_inputs(self):
    upstream = self.variant("launch_chffrplus.sh", b"#!/bin/bash\n# incompatible launcher\n")
    with self.assertRaisesRegex(ValueError, "no launcher patch applies"):
      compose.select_launcher_patch(self.repo, upstream)
    for script, args, prefix in (
      ("gates.py", ("--skip-download",), "G3"),
      ("compose.py", (), "compose"),
      ("compose.py", ("--inputs-only",), "compose"),
    ):
      with self.subTest(script=script, args=args):
        result = self.cli(script, upstream, *args, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{prefix}: FAIL: no launcher patch applies:", result.stderr)
        for launcher_patch in compose.LAUNCHER_PATCHES:
          self.assertIn(f"{launcher_patch.name}: git ", result.stderr)
        self.assertEqual(result.stderr.count("error: launch_chffrplus.sh: patch does not apply"), 2)

  def test_ambiguous_launcher_patches_fail(self):
    duplicate = self.work / "duplicate-launcher.patch"
    duplicate.write_bytes(compose.LAUNCHER_PATCHES[0].read_bytes())
    with patch.object(compose, "LAUNCHER_PATCHES", (compose.LAUNCHER_PATCHES[0], duplicate)):
      with self.assertRaisesRegex(ValueError, "more than one launcher patch applies") as error:
        compose.select_launcher_patch(self.repo, self.upstream)
      for launcher_patch in compose.LAUNCHER_PATCHES:
        self.assertIn(f"{launcher_patch.name}: applies cleanly", str(error.exception))
      with self.assertRaisesRegex(ValueError, "more than one launcher patch applies"):
        compose.compose(self.repo, self.upstream, self.resolved)
      with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO) as stderr:
        self.assertEqual(gates.run_gates(self.repo, self.upstream, self.pin_file, skip_download=True), 1)
        self.assertIn("G3: FAIL: more than one launcher patch applies:", stderr.getvalue())

  def test_inputs_hash_uses_chosen_launcher_patch(self):
    nightly_patch, release_patch = compose.LAUNCHER_PATCHES
    self.assertEqual(compose.inputs_hash(self.upstream, self.resolved, nightly_patch), self.inputs)
    self.assertNotEqual(compose.inputs_hash(self.upstream, self.resolved, release_patch), self.inputs)
    unused = self.work / release_patch.name
    unused.write_bytes(release_patch.read_bytes())
    with patch.object(compose, "LAUNCHER_PATCHES", (nightly_patch, unused)):
      unused.write_bytes(unused.read_bytes() + b"\n# unused patch changed\n")
      self.assertEqual(compose.select_launcher_patch(self.repo, self.upstream), nightly_patch)
      self.assertEqual(compose.inputs_hash(self.upstream, self.resolved, nightly_patch), self.inputs)

  def test_g6_published_tag_hash_invariant(self):
    tag, digest = self.pin["tag"], self.pin["boot"]["hash_raw"]
    for old_tag, old_hash, expected in (
      (tag, digest, "OK"), (tag, "f" * 64, "FAIL"),
      ("wpa3.sae=1", digest, "FAIL"),
      ("wpa3.sae=1", "18c888b86f8846cd49bf3312b2c02fb60fc3f5e2f165d3a77417a7ad4e2c5549", "OK"), ("", "", "SKIP"),
    ):
      with self.subTest(old_tag=old_tag, old_hash=old_hash):
        script = compose.blob(self.repo, self.upstream, "launch_env.sh")
        script += f'\nexport WPA3_BOOT_TAG="{old_tag}"\nexport WPA3_BOOT_HASH="{old_hash}"\n'.encode()
        published = self.variant("launch_env.sh", script)
        result = self.cli("gates.py", self.upstream, "--skip-download", "--published", published, check=False)
        self.assertEqual(result.returncode, 1 if expected == "FAIL" else 0, result.stdout + result.stderr)
        self.assertIn(f"G6: {expected}:", result.stdout + result.stderr)
        if expected == "FAIL":
          self.assertIn(published, result.stderr)

  def test_deterministic_commit_and_inputs(self):
    result = self.cli("compose.py", self.upstream)
    self.assertEqual(result.stdout.strip().splitlines(), [self.commit, self.inputs])
    self.assertEqual(self.cli("compose.py", self.upstream, "--inputs-only").stdout.strip(), self.inputs)
    self.assertEqual(compose.git(self.repo, "show", "-s", "--format=%P", self.commit).decode().strip(), self.upstream)
    self.assertEqual(compose.git(self.repo, "show", "-s", "--format=%aI %cI", self.commit),
                     compose.git(self.repo, "show", "-s", "--format=%cI %cI", self.upstream))
    message = compose.git(self.repo, "show", "-s", "--format=%B", self.commit).decode()
    self.assertEqual(message.strip(), f"Synthetic upstream + WPA3\n\nUpstream-Commit: {self.upstream}\n"
                     f"WPA3-Inputs: {self.inputs}\nWPA3-AGNOS: {self.pin['release_tag']}\nWPA3-Pin: pinned 19.8\n"
                     "WPA3-Launcher-Patch: launcher-wpa3.patch\nWPA3-Boot-Build: manual")
    self.assertEqual(compose.git(self.repo, "show", "-s", "--format=%an <%ae>|%cn <%ce>", self.commit).decode().strip(),
                     "openpilot-wpa3-bot <shunnag@users.noreply.github.com>|openpilot-wpa3-bot <shunnag@users.noreply.github.com>")
    print(f"\nDeterministic compose SHA (two runs): {self.commit}\nWPA3-Inputs: {self.inputs}")

  def test_publish_requires_non_shallow_upstream(self):
    def bare(name):
      repo = self.work / f"{name}.git"
      subprocess.run(["git", "init", "--bare", str(repo)], check=True, capture_output=True, env={**os.environ, **compose.LFS_ENV})
      return repo

    branch = "refs/heads/nightly-chestnut"
    fetch = ("fetch", "--no-tags", "--no-recurse-submodules")
    compose.git(self.repo, "update-ref", branch, self.upstream)
    for name, depth in (("shallow", ["--depth=1"]), ("full", [])):
      with self.subTest(fetch=name):
        publisher, remote = bare(name), bare(f"{name}-remote")
        compose.git(publisher, *fetch, *depth, self.repo.as_uri(), self.upstream)
        new, _ = compose.compose(publisher, self.upstream, self.resolved)
        push = ("push", f"--force-with-lease={branch}:", remote.as_uri(), f"{new}:{branch}")
        if depth:
          self.assertIn(self.upstream, (publisher / "shallow").read_text().splitlines())
          with self.assertRaises(subprocess.CalledProcessError) as rejected:
            compose.git(publisher, *push, env={"LC_ALL": "C"})
          self.assertIn(b"shallow update not allowed", rejected.exception.stderr)
          self.assertEqual(compose.git(remote, "for-each-ref", branch), b"")
        else:
          self.assertFalse((publisher / "shallow").exists())
          compose.git(publisher, *push)
          self.assertEqual(compose.git(remote, "rev-parse", branch).decode().strip(), new)
          full_remote, first = remote, new

    # Next day's root is fetched fully before the current fork is fetched shallowly.
    upstream = self.variant(".github/keep.txt", b"next day's upstream\n")
    compose.git(self.repo, "update-ref", branch, upstream)
    publisher = bare("next-day")
    compose.git(publisher, *fetch, self.repo.as_uri(), upstream)
    compose.git(publisher, *fetch, "--depth=1", full_remote.as_uri(), branch)
    self.assertNotIn(upstream, (publisher / "shallow").read_text().splitlines())
    second, _ = compose.compose(publisher, upstream, self.resolved)
    self.assertNotEqual(first, second)
    lease = f"--force-with-lease={branch}:{first}"
    compose.git(publisher, "push", lease, full_remote.as_uri(), f"{second}:{branch}")
    with self.assertRaises(subprocess.CalledProcessError) as rejected:
      compose.git(publisher, "push", lease, full_remote.as_uri(), f"{first}:{branch}", env={"LC_ALL": "C"})
    self.assertIn(b"stale info", rejected.exception.stderr)
    self.assertEqual(compose.git(full_remote, "rev-parse", branch).decode().strip(), second)

  def test_launch_environment_and_runtime_patch(self):
    script = compose.blob(self.repo, self.commit, "launch_env.sh")
    self.assertEqual(compose.launch_values(script), ("19.8", self.pin["tag"], self.pin["boot"]["hash_raw"],
                                                   self.pin["wpa_supplicant"]["stock_sha256"]))
    self.assertNotIn(b"__WPA3_", script)
    launcher = compose.blob(self.repo, self.commit, "launch_chffrplus.sh")
    self.assertIn(b'if [ "$(< "${WPA3_VERSION_PATH:-/VERSION}")" != "$AGNOS_VERSION" ] || wpa3_boot_needed; then', launcher)
    self.assertIn(b'    done\n  fi\n\n  wpa3_supplicant_override\n}\n\nfunction launch {', launcher)
    updated = compose.blob(self.repo, self.commit, UPDATED)
    self.assertIn(b"cur_version == updated_version and not wpa3_needed", updated)
    self.assertIn(b"unset WPA3_BOOT_TAG", updated)
    self.assertIn(b"unset WPA3_BOOT_HASH", updated)

  def assert_supplicant_files(self, commit):
    for path, (key, mode) in compose.SUPPLICANT_FILES.items():
      data = (ROOT / self.pin["wpa_supplicant"][key]).read_bytes()
      oid = compose.git(self.repo, "hash-object", "--stdin", data=data).decode().strip()
      self.assertEqual(compose.git(self.repo, "ls-tree", commit, "--", path).decode(), f"{mode} blob {oid}\t{path}\n")
      self.assertEqual(compose.blob(self.repo, commit, path), data)
      if key == "path":
        self.assertEqual(hashlib.sha256(data).hexdigest(), self.pin["wpa_supplicant"]["sha256"])

  def test_supplicant_files(self):
    self.assert_supplicant_files(self.commit)

  def test_supplicant_post_checks_reject_content_and_mode_drift(self):
    for path, (key, mode) in compose.SUPPLICANT_FILES.items():
      original = (ROOT / self.pin["wpa_supplicant"][key]).read_bytes()
      for data, wrong_mode in ((original + b"drift", mode), (original, "100644" if mode == "100755" else "100755")):
        with self.subTest(path=path, mode=wrong_mode), compose.temporary_index(self.repo, self.commit) as (env, scratch):
          compose.put_blob(self.repo, env, path, data, mode=wrong_mode)
          tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
          with self.assertRaisesRegex(ValueError, f"composed {path} must match"):
            compose.post_checks(self.repo, self.upstream, tree, self.resolved, scratch)

  def test_supplicant_launch_value_post_check(self):
    with compose.temporary_index(self.repo, self.commit) as (env, scratch):
      data = compose.blob(self.repo, self.commit, "launch_env.sh")
      data = data.replace(self.pin["wpa_supplicant"]["stock_sha256"].encode(), b"0" * 64)
      compose.put_blob(self.repo, env, "launch_env.sh", data)
      tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
      with self.assertRaisesRegex(ValueError, "values do not match"):
        compose.post_checks(self.repo, self.upstream, tree, self.resolved, scratch)

  def write_resolved(self, resolved, name="supplicant-pin.json"):
    pin_file = self.work / name
    pin_file.write_text(json.dumps(resolved))
    return pin_file

  def test_pin_without_supplicant(self):
    resolved = deepcopy(self.resolved)
    del resolved["pin"]["wpa_supplicant"]
    pin_file = self.write_resolved(resolved)
    result = self.cli("gates.py", self.upstream, "--skip-download", pin_file=pin_file)
    self.assertIn("G7: SKIP: pin has no wpa_supplicant", result.stdout)
    commit = self.cli("compose.py", self.upstream, pin_file=pin_file).stdout.splitlines()[0]
    self.assertEqual(compose.launch_values(compose.blob(self.repo, commit, "launch_env.sh"))[-1], "")
    self.assertEqual(compose.git(self.repo, "ls-tree", "-r", commit, "--", "wpa3"), b"")

  def supplicant_variant(self, data, digest=None):
    binary = self.work / "variant-supplicant"
    binary.write_bytes(data)
    resolved = deepcopy(self.resolved)
    resolved["pin"]["wpa_supplicant"].update(path=str(binary.relative_to(ROOT)),
                                            sha256=digest or hashlib.sha256(data).hexdigest())
    return resolved

  def test_wrong_supplicant_sha_fails_compose(self):
    resolved = self.supplicant_variant(b"wrong binary", self.pin["wpa_supplicant"]["sha256"])
    result = self.cli("compose.py", self.upstream, pin_file=self.write_resolved(resolved), check=False)
    self.assertEqual(result.returncode, 1)
    self.assertIn("wpa_supplicant SHA-256 differs from pin", result.stderr)

  def test_g7_rejects_invalid_supplicant(self):
    binary = (ROOT / self.pin["wpa_supplicant"]["path"]).read_bytes()
    for label, data, digest, reason in (
      ("digest", binary, "0" * 64, "SHA-256 differs"),
      ("non-ELF", b"#!/bin/sh\nexit 0\n", None, "ELF64"),
      ("truncated", binary[:32], None, "ELF64"),
      ("ELF32", binary[:4] + b"\x01" + binary[5:], None, "ELF64"),
      ("big-endian", binary[:5] + b"\x02" + binary[6:], None, "ELF64"),
      ("machine", binary[:18] + b"\x3e\x00" + binary[20:], None, "aarch64"),
      ("relocatable", binary[:16] + b"\x01\x00" + binary[18:], None, "executable"),
    ):
      with self.subTest(label=label):
        resolved = self.supplicant_variant(data, digest)
        result = self.cli("gates.py", self.upstream, "--skip-download", pin_file=self.write_resolved(resolved), check=False)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("G7: FAIL:", result.stderr)
        self.assertIn(reason, result.stderr)
    resolved = deepcopy(self.resolved)
    resolved["pin"]["wpa_supplicant"]["copyright"] = str((self.work / "missing.copyright").relative_to(ROOT))
    result = self.cli("gates.py", self.upstream, "--skip-download", pin_file=self.write_resolved(resolved), check=False)
    self.assertEqual(result.returncode, 1)
    self.assertIn("G7: FAIL:", result.stderr)
    self.assertIn("missing.copyright", result.stderr)

  def test_supplicant_inputs_cover_binary_and_copyright(self):
    resolved = deepcopy(self.resolved)
    resolved["pin"]["wpa_supplicant"]["sha256"] = "0" * 64
    self.assertNotEqual(compose.inputs_hash(self.upstream, resolved, compose.LAUNCHER_PATCHES[0]), self.inputs)
    copyright_file = self.work / "variant.copyright"
    resolved = deepcopy(self.resolved)
    resolved["pin"]["wpa_supplicant"]["copyright"] = str(copyright_file.relative_to(ROOT))
    copyright_file.write_text("license one\n")
    before = compose.inputs_hash(self.upstream, resolved, compose.LAUNCHER_PATCHES[0])
    copyright_file.write_text("license two\n")
    self.assertNotEqual(compose.inputs_hash(self.upstream, resolved, compose.LAUNCHER_PATCHES[0]), before)

  def test_manifest_and_symlink(self):
    original = compose.blob(self.repo, self.upstream, compose.MANIFEST)
    self.assertEqual(compose.blob(self.repo, self.commit, compose.STOCK_MANIFEST), original)
    self.assertTrue(compose.git(self.repo, "ls-tree", self.commit, "--", compose.STOCK_MANIFEST).startswith(b"100644 blob "))
    entries = json.loads(compose.blob(self.repo, self.commit, compose.MANIFEST))
    self.assertEqual([p for p in entries if p["name"] == "boot"], [self.pin["boot"]])
    old_boot = next(p for p in json.loads(original) if p["name"] == "boot")
    self.assertEqual(compose.manifest_bytes([old_boot if p["name"] == "boot" else p for p in entries]), original)
    self.assertEqual(compose.git(self.repo, "ls-tree", self.commit, "--", MANIFEST_LINK),
                     compose.git(self.repo, "ls-tree", self.upstream, "--", MANIFEST_LINK))
    self.assertTrue(compose.git(self.repo, "ls-tree", self.commit, "--", MANIFEST_LINK).startswith(b"120000 blob "))

  def test_stock_manifest_post_checks_reject_content_and_mode_drift(self):
    original = compose.blob(self.repo, self.upstream, compose.MANIFEST)
    for data, mode, reason in ((original + b"\n", "100644", "differs"), (original, "100755", "mode 100644")):
      with self.subTest(mode=mode), compose.temporary_index(self.repo, self.commit) as (env, scratch):
        compose.put_blob(self.repo, env, compose.STOCK_MANIFEST, data, mode=mode)
        tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
        with self.assertRaisesRegex(ValueError, reason):
          compose.post_checks(self.repo, self.upstream, tree, self.resolved, scratch)

  def test_only_allowed_paths_change_and_no_lfs(self):
    changed = set(compose.git(self.repo, "diff-tree", "--no-commit-id", "-r", "--name-only", self.upstream, self.commit).decode().splitlines())
    self.assertEqual(changed, compose.ALLOWED | {".github/workflows/upstream.yml"})
    self.assertEqual(compose.git(self.repo, "ls-tree", "-r", self.commit, "--", ".github/workflows"), b"")
    self.assertFalse((self.repo / "lfs").exists())
    self.assertFalse((self.repo / "index").exists())
    self.assertFalse((self.repo / "launch_env.sh").exists())

  def test_ui_patch_already_applied(self):
    with compose.temporary_index(self.repo, self.upstream) as (env, _):
      compose.apply_ui(self.repo, env)
      tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
      upstream = compose.git(self.repo, "commit-tree", tree, data=b"Upstream includes UI patch\n", env=self.identity).decode().strip()
    self.assertIn("G5: OK: UI patch already applied", self.cli("gates.py", upstream, "--skip-download").stdout)
    new_commit = self.cli("compose.py", upstream).stdout.splitlines()[0]
    self.assertEqual(compose.git(self.repo, "rev-parse", f"{new_commit}^{{tree}}"),
                     compose.git(self.repo, "rev-parse", f"{self.commit}^{{tree}}"))

  def test_gates_reject_drift(self):
    manifest = json.loads(compose.blob(self.repo, self.upstream, compose.MANIFEST))
    variants = [
      ("G1", "launch_env.sh", compose.blob(self.repo, self.upstream, "launch_env.sh").replace(b'"19.8"', b'"20.0"')),
      ("G3", compose.AGNOS_PY, compose.blob(self.repo, self.upstream, compose.AGNOS_PY) + b"# drift\n"),
      ("G3", "launch_chffrplus.sh", b"#!/bin/bash\n# incompatible launcher\n"),
      ("G5", "openpilot/system/ui/lib/networkmanager.py", b"# incompatible UI\n"),
    ]
    for name in ("boot", "system"):
      entries = [dict(p, hash_raw="0" * 64) if p["name"] == name else p for p in manifest]
      variants.append(("G2", compose.MANIFEST, compose.manifest_bytes(entries)))
    for gate, path, data in variants:
      with self.subTest(gate=gate, path=path):
        result = self.cli("gates.py", self.variant(path, data), "--skip-download", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"{gate}: FAIL:", result.stderr)

  def test_manifest_format_drift_is_rejected(self):
    original = compose.blob(self.repo, self.upstream, compose.MANIFEST)
    upstream = self.variant(compose.MANIFEST, json.dumps(json.loads(original)).encode())
    result = self.cli("compose.py", upstream, check=False)
    self.assertEqual(result.returncode, 1)
    self.assertIn("round-trips byte-for-byte", result.stderr)

  def test_manifest_without_trailing_newline_is_preserved(self):
    original = compose.blob(self.repo, self.upstream, compose.MANIFEST).removesuffix(b"\n")
    upstream = self.variant(compose.MANIFEST, original)
    commit = self.cli("compose.py", upstream).stdout.splitlines()[0]
    self.assertEqual(compose.blob(self.repo, commit, compose.STOCK_MANIFEST), original)
    composed = compose.blob(self.repo, commit, compose.MANIFEST)
    self.assertFalse(composed.endswith(b"\n"))
    entries = json.loads(composed)
    self.assertEqual([p for p in entries if p["name"] == "boot"], [self.pin["boot"]])
    self.assertEqual([p for p in entries if p["name"] != "boot"],
                     [p for p in json.loads(original) if p["name"] != "boot"])

  def test_resolved_json_is_canonical_and_inputs_include_resolution(self):
    resolved = json.loads(self.pin_file.read_text())
    self.assertEqual(self.pin_file.read_text(), json.dumps(resolved, sort_keys=True, indent=2) + "\n")
    reordered = self.work / "reordered.json"
    reordered.write_text(json.dumps(resolved, sort_keys=False))
    self.assertEqual(self.cli("compose.py", self.upstream, pin_file=reordered).stdout.splitlines(), [self.commit, self.inputs])
    different = {**resolved, "mode": "derived", "base": "19.7"}
    self.assertNotEqual(compose.inputs_hash(self.upstream, resolved, compose.LAUNCHER_PATCHES[0]), compose.inputs_hash(self.upstream, different, compose.LAUNCHER_PATCHES[0]))

  def resolved_variant(self, native=False):
    base_stock, new_stock = identity_pair()
    if native:
      new_stock = boot_image(sae=4, rsnxe=True)
    entries = json.loads(compose.blob(self.repo, self.upstream, compose.MANIFEST))
    for entry in entries:
      if entry["name"] == "boot":
        entry.update(url="https://example.invalid/new.img.xz", hash_raw=hashlib.sha256(new_stock).hexdigest(), size=len(new_stock))
      if entry["name"] == "system":
        entry["hash_raw"] = "9" * 64
    changes = {
      "launch_env.sh": compose.blob(self.repo, self.upstream, "launch_env.sh").replace(b'"19.8"', b'"19.9"'),
      compose.MANIFEST: compose.manifest_bytes(entries),
    }
    if native:
      # Native no longer depends on the pinned AGNOS flashing implementation.
      changes[compose.AGNOS_PY] = b"# new native updater\n"
    upstream = self.variant_many(changes)
    base_pin = deepcopy(self.pin)
    base_pin["derived_from"]["boot_hash_raw"] = hashlib.sha256(base_stock).hexdigest()
    base_pin["derived_from"]["boot_url"] = "https://example.invalid/base.img.xz"

    def fake_fetch(url, digest, size):
      data = {"https://example.invalid/base.img.xz": base_stock, "https://example.invalid/new.img.xz": new_stock}[url]
      self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
      if size is not None:
        self.assertEqual(len(data), size)
      return data

    resolved = pins.resolve(lambda path: compose.blob(self.repo, upstream, path), {"19.8": base_pin}, fake_fetch)
    self.assertEqual(resolved["mode"], "native" if native else "derived")
    pin_file = self.work / f"{resolved['mode']}.json"
    pin_file.write_text(json.dumps(resolved, sort_keys=True, indent=2) + "\n")
    return upstream, resolved, pin_file

  def test_derived_resolve_gates_and_compose(self):
    upstream, resolved, pin_file = self.resolved_variant()
    gates_result = self.cli("gates.py", upstream, "--skip-download", pin_file=pin_file)
    for gate in ("G1", "G2", "G3", "G5", "G7"):
      self.assertIn(f"{gate}: OK:", gates_result.stdout)
    result = self.cli("compose.py", upstream, pin_file=pin_file).stdout
    self.assertEqual(result, self.cli("compose.py", upstream, pin_file=pin_file).stdout)
    commit, inputs = result.splitlines()
    self.assertEqual(inputs, self.cli("compose.py", upstream, "--inputs-only", pin_file=pin_file).stdout.strip())
    self.assertEqual(compose.launch_values(compose.blob(self.repo, commit, "launch_env.sh")),
                     ("19.9", self.pin["tag"], self.pin["boot"]["hash_raw"], self.pin["wpa_supplicant"]["stock_sha256"]))
    self.assert_supplicant_files(commit)
    self.assertEqual(resolved["pin"]["wpa_supplicant"], self.pin["wpa_supplicant"])
    message = compose.git(self.repo, "show", "-s", "--format=%B", commit).decode()
    self.assertIn(f"WPA3-AGNOS: {self.pin['release_tag']}\nWPA3-Pin: derived 19.9 from 19.8\n", message)
    changed = set(compose.git(self.repo, "diff-tree", "--no-commit-id", "-r", "--name-only", upstream, commit).decode().splitlines())
    self.assertEqual(changed, compose.ALLOWED | {".github/workflows/upstream.yml"})
    entries = json.loads(compose.blob(self.repo, commit, compose.MANIFEST))
    self.assertEqual(next(entry for entry in entries if entry["name"] == "boot"), self.pin["boot"])
    self.assertEqual(next(entry for entry in entries if entry["name"] == "system")["hash_raw"], "9" * 64)
    drifted = self.variant_many({compose.AGNOS_PY: b"# drift\n"}, upstream)
    self.assertIn("G3: FAIL:", self.cli("gates.py", drifted, "--skip-download", pin_file=pin_file, check=False).stderr)
    self.assertEqual(resolved["pin"]["boot"], self.pin["boot"])
    self.assertEqual(compose.blob(self.repo, commit, compose.STOCK_MANIFEST), compose.blob(self.repo, upstream, compose.MANIFEST))

  def test_native_resolve_gates_and_compose_with_override(self):
    upstream, resolved, pin_file = self.resolved_variant(native=True)
    self.assertEqual(resolved["base"], "19.8")
    self.assertEqual(resolved["wpa_supplicant"], self.pin["wpa_supplicant"])
    # No skip-download: native G4 must skip on its own, without network access.
    result = self.cli("gates.py", upstream, pin_file=pin_file)
    self.assertIn("native SAE/H2E in stock boot", result.stdout)
    for gate in ("G2", "G3", "G4", "G6"):
      self.assertIn(f"{gate}: SKIP:", result.stdout)
    self.assertIn("G5: OK:", result.stdout)
    self.assertIn("G7: OK:", result.stdout)
    self.assertIn("G3: SKIP: pinned agnos.py check in native mode; launcher patch launcher-wpa3.patch applies", result.stdout)
    self.assertIn("G6: SKIP: native mode", self.cli("gates.py", upstream, "--published", self.commit, pin_file=pin_file).stdout)
    result = self.cli("compose.py", upstream, pin_file=pin_file).stdout
    self.assertEqual(result, self.cli("compose.py", upstream, pin_file=pin_file).stdout)
    commit, inputs = result.splitlines()
    self.assertEqual(inputs, self.cli("compose.py", upstream, "--inputs-only", pin_file=pin_file).stdout.strip())
    changed = set(compose.git(self.repo, "diff-tree", "--no-commit-id", "-r", "--name-only", upstream, commit).decode().splitlines())
    self.assertEqual(changed, compose.NATIVE_ALLOWED | {".github/workflows/upstream.yml"})
    self.assertEqual(compose.git(self.repo, "ls-tree", "-r", commit, "--", ".github/workflows"), b"")
    self.assertEqual(compose.git(self.repo, "ls-tree", commit, "--", compose.STOCK_MANIFEST), b"")
    self.assert_supplicant_files(commit)
    self.assertEqual(compose.launch_values(compose.blob(self.repo, commit, "launch_env.sh")),
                     ("19.9", "", "", self.pin["wpa_supplicant"]["stock_sha256"]))
    for path in (compose.MANIFEST, compose.AGNOS_PY):
      self.assertEqual(compose.blob(self.repo, commit, path), compose.blob(self.repo, upstream, path))
    for path in ("launch_chffrplus.sh", UPDATED):
      self.assertEqual(compose.blob(self.repo, commit, path), compose.blob(self.repo, self.commit, path))
    message = compose.git(self.repo, "show", "-s", "--format=%B", commit).decode()
    self.assertIn("WPA3-AGNOS: none\nWPA3-Pin: native 19.9\n", message)
    drifted = self.variant_many({"openpilot/system/ui/lib/networkmanager.py": b"# incompatible UI\n"}, upstream)
    self.assertIn("G5: FAIL:", self.cli("gates.py", drifted, pin_file=pin_file, check=False).stderr)

  def test_native_requires_launcher_patch_applicability(self):
    upstream, _, pin_file = self.resolved_variant(native=True)
    for path in ("launch_chffrplus.sh", "launch_env.sh", UPDATED):
      with self.subTest(path=path):
        original = compose.blob(self.repo, upstream, path)
        data = b"#!/bin/bash\n# incompatible launcher\n" if path.endswith(".sh") else b"# incompatible updater\n"
        if path == "launch_env.sh":
          data += b'if [ -z "$AGNOS_VERSION" ]; then\n  export AGNOS_VERSION="19.9"\nfi\n'
        self.assertNotEqual(data, original)
        drifted = self.variant_many({path: data}, upstream)
        result = self.cli("gates.py", drifted, pin_file=pin_file, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("G3: FAIL:", result.stderr)
        self.assertEqual(self.cli("compose.py", drifted, pin_file=pin_file, check=False).returncode, 1)

  def test_native_supplicant_validation_and_inputs(self):
    upstream, resolved, _ = self.resolved_variant(native=True)
    for key, value in (("sha256", "0" * 64), ("copyright", str((self.work / "missing.copyright").relative_to(ROOT)))):
      changed = deepcopy(resolved)
      changed["wpa_supplicant"][key] = value
      pin_file = self.write_resolved(changed)
      with self.subTest(key=key):
        result = self.cli("gates.py", upstream, pin_file=pin_file, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("G7: FAIL:", result.stderr)
        self.assertEqual(self.cli("compose.py", upstream, pin_file=pin_file, check=False).returncode, 1)
    for key, value in (("stock_sha256", "invalid"), ("path", "../outside")):
      changed = deepcopy(resolved)
      changed["wpa_supplicant"][key] = value
      with self.subTest(key=key), self.assertRaises(ValueError):
        compose.load_pin(self.repo, upstream, self.write_resolved(changed))
    original_inputs = compose.inputs_hash(upstream, resolved, compose.LAUNCHER_PATCHES[0])
    changed = deepcopy(resolved)
    changed["wpa_supplicant"]["sha256"] = "0" * 64
    self.assertNotEqual(original_inputs, compose.inputs_hash(upstream, changed, compose.LAUNCHER_PATCHES[0]))
    copyright_file = self.work / "native.copyright"
    changed["wpa_supplicant"]["copyright"] = str(copyright_file.relative_to(ROOT))
    copyright_file.write_text("license one\n")
    original_inputs = compose.inputs_hash(upstream, changed, compose.LAUNCHER_PATCHES[0])
    copyright_file.write_text("license two\n")
    self.assertNotEqual(original_inputs, compose.inputs_hash(upstream, changed, compose.LAUNCHER_PATCHES[0]))

  def test_native_post_checks_protect_manifest_and_runtime(self):
    upstream, resolved, pin_file = self.resolved_variant(native=True)
    commit = self.cli("compose.py", upstream, pin_file=pin_file).stdout.splitlines()[0]
    changes = [
      (compose.MANIFEST, b"[]\n", "100644", "unexpected composed change"),
      (compose.STOCK_MANIFEST, b"[]\n", "100644", "unexpected composed change"),
      ("launch_env.sh", b'if [ -z "$AGNOS_VERSION" ]; then\n  export AGNOS_VERSION="19.9"\nfi\nexport WPA3_BOOT_TAG="wpa3.sae=2"\n', "100644", "values do not match"),
    ]
    for path, (key, mode) in compose.SUPPLICANT_FILES.items():
      data = (ROOT / self.pin["wpa_supplicant"][key]).read_bytes()
      changes += [(path, data + b"drift", mode, "must match the pinned file"),
                  (path, data, "100644" if mode == "100755" else "100755", "must match the pinned file")]
    for path, data, mode, reason in changes:
      with self.subTest(path=path, mode=mode), compose.temporary_index(self.repo, commit) as (env, scratch):
        compose.put_blob(self.repo, env, path, data, mode=mode)
        tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
        with self.assertRaisesRegex(ValueError, reason):
          compose.post_checks(self.repo, upstream, tree, resolved, scratch)

  def test_native_without_optional_supplicant(self):
    upstream, resolved, _ = self.resolved_variant(native=True)
    del resolved["wpa_supplicant"]
    pin_file = self.write_resolved(resolved)
    self.assertIn("G7: SKIP:", self.cli("gates.py", upstream, pin_file=pin_file).stdout)
    commit = self.cli("compose.py", upstream, pin_file=pin_file).stdout.splitlines()[0]
    self.assertEqual(compose.launch_values(compose.blob(self.repo, commit, "launch_env.sh")), ("19.9", "", "", ""))
    self.assertEqual(compose.git(self.repo, "ls-tree", "-r", commit, "--", "wpa3"), b"")

  def test_launcher_bash_unit(self):
    launcher = self.work / "launch_chffrplus.sh"
    launcher.write_bytes(compose.blob(self.repo, self.commit, "launch_chffrplus.sh"))
    result = subprocess.run(["bash", str(ROOT / "scripts/test_wpa3_boot_needed.sh"), str(launcher), str(self.work)],
                            capture_output=True, text=True)
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn("PASS: wpa3_boot_needed", result.stdout)
    self.assertIn("PASS: wpa3_update_manifest", result.stdout)
    print("\n" + result.stdout.strip())

  def test_supplicant_bash_unit(self):
    launcher = self.work / "supplicant-launcher.sh"
    launcher.write_bytes(compose.blob(self.repo, self.commit, "launch_chffrplus.sh"))
    result = subprocess.run(["bash", str(ROOT / "scripts/test_wpa3_supplicant_override.sh"), str(launcher), str(self.work)],
                            capture_output=True, text=True, timeout=30)
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn("PASS: wpa3_supplicant_override", result.stdout)
    print("\n" + result.stdout.strip())

  def test_updated_trigger_is_read_only_and_preserves_version_updates(self):
    # Execute just this function: no device dependencies or filesystem access.
    module = ast.parse(compose.blob(self.repo, self.commit, UPDATED))
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "handle_agnos_update")
    agnos = types.ModuleType("openpilot.common.hardware.comma.agnos")
    agnos.flash_agnos_update = Mock()
    agnos.get_target_slot_number = Mock(return_value=1)
    cases = [
      ("19.8", "wpa3.sae=1", "quiet wpa3.sae=1", "hash-a 2", True, None),
      ("19.8", "", "quiet", None, True, None),
      ("19.8", "wpa3.sae=1", "quiet wpa3.sae=10", None, True, "wpa3"),
      ("19.8", "wpa3.sae=1", "quiet", "hash-a 2", True, "wpa3"),
      ("19.8", "wpa3.sae=1", "quiet", "hash-a 3", True, None),
      ("19.8", "wpa3.sae=1", "quiet", "hash-a 300", True, None),
      ("19.8", "wpa3.sae=1", "quiet", "hash-old 3", True, "wpa3"),
      ("19.8", "wpa3.sae=1", "quiet", "hash-a invalid", True, None),
      ("19.7", "wpa3.sae=1", "quiet wpa3.sae=1", "hash-a 3", True, "wpa3"),
      ("19.7", "", "quiet", "hash-a 3", True, "wpa3"),
      ("19.7", "wpa3.sae=1", "quiet", None, True, "wpa3"),
      ("19.7", "wpa3.sae=1", "quiet", "hash-a 0", True, "wpa3"),
      ("19.7", "wpa3.sae=1", "quiet", "hash-a 1", True, "wpa3"),
      ("19.7", "wpa3.sae=1", "quiet", "hash-a 2", True, "wpa3"),
      ("19.7", "wpa3.sae=1", "quiet", "hash-a 3", True, "stock"),
      ("19.7", "wpa3.sae=1", "quiet", "hash-a 300", True, "stock"),
      ("19.7", "wpa3.sae=1", "quiet", "hash-old 3", True, "wpa3"),
      ("19.7", "wpa3.sae=1", "quiet", "hash-a invalid", True, "stock"),
      ("19.7", "wpa3.sae=1", "quiet", "hash-a", True, "stock"),
      ("19.7", "wpa3.sae=1", "quiet", "hash-a 2\njunk", True, "stock"),
      ("19.7", "wpa3.sae=1", "quiet", "hash-a 3", False, "wpa3"),
      ("19.7", "wpa3.sae=1", "quiet", b"hash-a 2\x00", True, "wpa3"),
      ("19.7", "wpa3.sae=1", "quiet", b"\x00hash-a 3", True, "stock"),
      ("19.8", "wpa3.sae=1", "quiet", b"\x00hash-a 3", True, None),
    ]
    for bad in (b"hash-a 2\r\n", b"hash-a 2\x0c", b"hash-a \xff2", ValueError("bad attempts")):
      cases += [("19.7", "wpa3.sae=1", "quiet", bad, True, "stock"),
                ("19.8", "wpa3.sae=1", "quiet", bad, True, None)]
    for current, tag, cmdline, attempts, stock_exists, expected in cases:
      with self.subTest(current=current, tag=tag, cmdline=cmdline, attempts=attempts, stock_exists=stock_exists):
        path = Mock()
        path.return_value.read_text.return_value = cmdline
        raw = attempts.encode() if isinstance(attempts, str) else attempts
        path.return_value.read_bytes.side_effect = [FileNotFoundError() if raw is None else raw]
        path.return_value.is_file.return_value = stock_exists
        namespace = {"Path": path, "os": os, "OVERLAY_MERGED": "/staged", "HARDWARE": Mock(get_os_version=Mock(return_value=current)),
                     "run": Mock(side_effect=["19.8", tag, "hash-a"]), "cloudlog": Mock(), "set_consistent_flag": Mock()}
        agnos.flash_agnos_update.reset_mock()
        with patch.dict(sys.modules, {agnos.__name__: agnos}):
          exec(compile(ast.Module(body=[function], type_ignores=[]), UPDATED, "exec"), namespace)
          namespace["handle_agnos_update"]()
        self.assertEqual(agnos.flash_agnos_update.called, expected is not None)
        self.assertEqual(namespace["set_consistent_flag"].called, expected is not None)
        if expected:
          manifest = compose.STOCK_MANIFEST if expected == "stock" else MANIFEST_LINK
          self.assertEqual(agnos.flash_agnos_update.call_args.args[0], "/staged/" + manifest)
        self.assertTrue(all(call[0] in ("read_text", "read_bytes", "is_file") for call in path.return_value.method_calls))


  def test_auto_release_notice_and_withdrawal_render_in_device_first_block(self):
    import follow_state as fs
    from fixtures.openpilot_markdown import parse_markdown
    from test_follow_state import automatic_pin, withdrawal
    original = b'Version 0.11.2 (2026-08-12)\n===========================\n* Upstream notes\n\nOlder version\n'
    with compose.temporary_index(self.repo, self.upstream) as (env, _):
      compose.put_blob(self.repo, env, 'RELEASES.md', original, mode='100644')
      tree = compose.git(self.repo, 'write-tree', env=env).decode().strip()
      upstream = compose.git(self.repo, 'commit-tree', tree, data=b'With release notes\n', env=self.identity).decode().strip()
    auto = automatic_pin(fs.load(), '19.8')
    auto['derived_from'] = deepcopy(self.pin['derived_from'])
    auto['wpa_supplicant'] = deepcopy(self.pin['wpa_supplicant'])
    for withdrawn in (False, True):
      pin = deepcopy(auto)
      if withdrawn:
        pin['withdrawn'] = withdrawal()
        pin.update(deepcopy(pin['revert']))
      resolved = {'mode': 'pinned', 'version': '19.8', 'pin': pin}
      pin_file = self.write_resolved(resolved)
      commit = self.cli('compose.py', upstream, pin_file=pin_file).stdout.splitlines()[0]
      data = compose.blob(self.repo, commit, 'RELEASES.md')
      self.assertEqual(data, compose.release_notice(resolved) + original)
      self.assertNotIn(b'\n\n', compose.release_notice(resolved))
      self.assertIn('WPA3-Boot-Build: auto', compose.git(self.repo, 'show', '-s', '--format=%B', commit).decode())
      # Execute upstream's actual function, isolated from its hardware imports.
      module = ast.parse(compose.blob(self.repo, upstream, UPDATED))
      function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'parse_release_notes')
      namespace = {'os': os, 'parse_markdown': parse_markdown, 'cloudlog': Mock()}
      exec(compile(ast.Module(body=[function], type_ignores=[]), UPDATED, 'exec'), namespace)
      with tempfile.TemporaryDirectory(dir=self.work) as directory:
        (Path(directory) / 'RELEASES.md').write_bytes(data)
        rendered = namespace['parse_release_notes'](directory).decode()
      self.assertIn('was withdrawn' if withdrawn else 'has NOT been tested on any device', rendered)
      self.assertIn('<h1>Version 0.11.2 (2026-08-12)</h1>', rendered)
      self.assertIn('Upstream notes', rendered)
      self.assertNotIn('Older version', rendered)
      for changed in (original, data + b'extra\n', data.replace(b'Upstream notes', b'changed')):
        with compose.temporary_index(self.repo, commit) as (env, scratch):
          compose.put_blob(self.repo, env, 'RELEASES.md', changed)
          tree = compose.git(self.repo, 'write-tree', env=env).decode().strip()
          with self.assertRaisesRegex(ValueError, 'exactly the one prepended notice'):
            compose.post_checks(self.repo, upstream, tree, resolved, scratch)
      with compose.temporary_index(self.repo, commit) as (env, scratch):
        compose.put_blob(self.repo, env, 'RELEASES.md', data, mode='100755')
        tree = compose.git(self.repo, 'write-tree', env=env).decode().strip()
        with self.assertRaisesRegex(ValueError, 'mode changed'):
          compose.post_checks(self.repo, upstream, tree, resolved, scratch)
    manual = self.cli('compose.py', upstream).stdout.splitlines()[0]
    self.assertEqual(compose.blob(self.repo, manual, 'RELEASES.md'), original)
    self.assertNotIn('RELEASES.md', compose.ALLOWED)
    with compose.temporary_index(self.repo, manual) as (env, scratch):
      compose.put_blob(self.repo, env, 'RELEASES.md', b'unsolicited notice\n' + original)
      tree = compose.git(self.repo, 'write-tree', env=env).decode().strip()
      with self.assertRaisesRegex(ValueError, 'unexpected composed change: RELEASES.md'):
        compose.post_checks(self.repo, upstream, tree, self.resolved, scratch)

  def test_g8_cli_enforcement_and_revoke_override(self):
    upstream, _, pin_file = self.resolved_variant()
    for mode in ('off', 'dryrun', 'state', 'on'):
      result = self.cli('gates.py', upstream, '--skip-download', '--follow-mode', mode, pin_file=pin_file, check=False)
      self.assertEqual(result.returncode, 0 if mode in ('off', 'dryrun') else 1)
      self.assertIn('G8: WARN:' if result.returncode == 0 else 'G8: FAIL:', result.stdout + result.stderr)
      revoked = self.cli('gates.py', upstream, '--skip-download', '--follow-mode', mode, '--revoke', pin_file=pin_file)
      self.assertIn('G8: WARN:', revoked.stdout)


class TestLaunchParser(unittest.TestCase):
  def setUp(self):
    self.valid = b'#!/usr/bin/env bash\nexport OMP_NUM_THREADS=1\nif [ -z "$AGNOS_VERSION" ]; then\n  export AGNOS_VERSION="19.9"\nfi\n'

  def test_literals_only_and_no_shell_process(self):
    with patch('compose.subprocess.run', side_effect=AssertionError('shell execution')):
      self.assertEqual(compose.launch_values(self.valid), ('19.9', '', '', ''))
      script = self.valid + b'export WPA3_BOOT_TAG="wpa3.sae=10"\nexport WPA3_BOOT_HASH="' + b'a' * 64 + b'"\n'
      self.assertEqual(compose.launch_values(script), ('19.9', 'wpa3.sae=10', 'a' * 64, ''))

  def test_forbidden_commands_even_when_not_executed(self):
    for command in (b'source /tmp/evil', b'  . /tmp/evil', b'eval "anything"', b'$(touch /tmp/evil)',
                    b'echo hi; source /tmp/evil', b'false || eval true', b'export OTHER="$(touch /tmp/evil)"',
                    b'export OTHER=`id`', b'eval\\\n echo anything'):
      with self.subTest(command=command), self.assertRaisesRegex(ValueError, 'prohibited'):
        compose.launch_values(self.valid + command + b'\n')

  def test_missing_duplicated_indirect_or_unrecognized_assignments_fail_closed(self):
    for script in (b'export OTHER=1\n', b'export AGNOS_VERSION="19.9"\n', self.valid * 2,
                   self.valid + b'export AGNOS_VERSION="20"\n', self.valid + b'# AGNOS_VERSION\n',
                   self.valid + b'unset WPA3_BOOT_HASH\n', self.valid.replace(b'19.9', b'19..9'),
                   self.valid.replace(b'19.9', b'$(id)'), self.valid.replace(b'19.9', b'19.9;id'),
                   self.valid + b'export WPA3_BOOT_TAG="wpa3.sae=4"\n' * 2,
                   self.valid + b'export WPA3_BOOT_HASH="malformed"\n',
                   self.valid + b'WPA3_BOOT_TAG="wpa3.sae=4"\n'):
      with self.subTest(script=script), self.assertRaises(ValueError):
        compose.launch_values(script)


class TestG8(unittest.TestCase):
  def test_modes_for_missing_probe_missing_wpa_and_mismatch(self):
    import follow_state as fs
    from contextlib import redirect_stdout
    for problem in ('probe', 'wpa', 'mismatch', 'version'):
      state = fs.load()
      pin = deepcopy(state['manual']['19.9'])
      resolved = {'mode': 'pinned', 'version': '19.9', 'pin': pin}
      digest = pin['derived_from']['system_hash_raw']
      if problem == 'probe':
        state['system_probe'] = {}
      elif problem == 'wpa':
        state['supplicants'] = {}
      elif problem == 'mismatch':
        pin['wpa_supplicant']['sha256'] = '0' * 64
      else:
        state['system_probe'][digest]['dpkg_version'] = '2:2.10-21ubuntu0.5'
      for mode in fs.MODES:
        for revoke in (False, True):
          stdout = io.StringIO()
          with self.subTest(problem=problem, mode=mode, revoke=revoke), redirect_stdout(stdout):
            if mode in ('state', 'on') and not revoke:
              with self.assertRaises(ValueError):
                gates.check_g8(resolved, digest, state, mode, revoke)
            else:
              gates.check_g8(resolved, digest, state, mode, revoke)
              self.assertIn('G8: WARN:', stdout.getvalue())

  def test_known_probe_and_stock_policy_agree_with_resolved_files(self):
    import follow_state as fs
    from contextlib import redirect_stdout
    state = fs.load()
    pin = deepcopy(state['manual']['19.9'])
    resolved = {'mode': 'pinned', 'version': '19.9', 'pin': pin}
    digest = pin['derived_from']['system_hash_raw']
    for mode in fs.MODES:
      stdout = io.StringIO()
      with redirect_stdout(stdout):
        gates.check_g8(resolved, digest, state, mode)
      self.assertIn('G8: OK:' if mode in ('state', 'on') else 'G8: WARN:', stdout.getvalue())
    state['supplicants'] = {}
    state['policy']['on_unknown_stock_wpa'] = 'stock'
    with self.assertRaisesRegex(ValueError, 'does not match G8'):
      gates.check_g8(resolved, digest, state, 'state')
    del pin['wpa_supplicant']
    with redirect_stdout(io.StringIO()):
      gates.check_g8(resolved, digest, state, 'state')


class TestBootDownload(unittest.TestCase):
  def test_streamed_xz_hash_size_and_corruption(self):
    raw = b"synthetic boot\0" * 100000
    boot = {"url": "https://example.invalid/boot.img.xz", "hash_raw": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
    compressed = lzma.compress(raw)
    with patch("boot_download.urllib.request.urlopen", return_value=io.BytesIO(compressed)):
      gates.check_download(boot)
    for data, changed in ((compressed, {"hash_raw": "0" * 64}), (compressed, {"size": len(raw) - 1}),
                          (compressed, {"size": len(raw) + 1}), (compressed[:-10], {})):
      with self.subTest(changed=changed, compressed_size=len(data)):
        with patch("boot_download.urllib.request.urlopen", return_value=io.BytesIO(data)) as opener, patch("boot_download.time.sleep") as sleep:
          with self.assertRaises((ValueError, EOFError, lzma.LZMAError)):
            gates.check_download({**boot, **changed})
          opener.assert_called_once()
          sleep.assert_not_called()

  def test_network_errors_retry_with_backoff(self):
    raw = b"boot" * 10000
    digest = hashlib.sha256(raw).hexdigest()
    url = "https://example.invalid/boot.img.xz"
    errors = (urllib.error.URLError("CDN unavailable"), TimeoutError("read timeout"), ConnectionResetError("reset"),
              urllib.error.HTTPError(url, 503, "unavailable", {}, None), urllib.error.HTTPError(url, 429, "slow down", {}, None))
    for error in errors:
      with self.subTest(error=error):
        with patch("boot_download.urllib.request.urlopen", side_effect=[error, error, io.BytesIO(lzma.compress(raw))]) as opener:
          with patch("boot_download.time.sleep") as sleep:
            self.assertEqual(boot_download.fetch_boot(url, digest, len(raw)), raw)
            self.assertEqual(opener.call_count, 3)
            self.assertEqual(sleep.call_args_list, [call(5), call(15)])
    with patch("boot_download.urllib.request.urlopen", side_effect=errors[0]) as opener, patch("boot_download.time.sleep") as sleep:
      with self.assertRaises(urllib.error.URLError):
        boot_download.fetch_boot(url, digest, len(raw))
      self.assertEqual(opener.call_count, 3)
      self.assertEqual(sleep.call_args_list, [call(5), call(15)])
    with patch("boot_download.urllib.request.urlopen", side_effect=urllib.error.HTTPError(url, 404, "missing", {}, None)) as opener:
      with patch("boot_download.time.sleep") as sleep:
        with self.assertRaises(urllib.error.HTTPError):
          boot_download.fetch_boot(url, digest, len(raw))
        opener.assert_called_once()
        sleep.assert_not_called()

  def test_midstream_network_error_restarts_download(self):
    raw = b"synthetic boot" * 100000
    compressed = lzma.compress(raw)

    class BrokenStream(io.BytesIO):
      def read(self, size=-1):
        if self.tell():
          raise ConnectionResetError("interrupted body")
        return super().read(len(compressed) // 2)

    with patch("boot_download.urllib.request.urlopen", side_effect=[BrokenStream(compressed), io.BytesIO(compressed)]) as opener:
      with patch("boot_download.time.sleep") as sleep:
        self.assertEqual(boot_download.fetch_boot("https://example.invalid/boot.img.xz", hashlib.sha256(raw).hexdigest(), len(raw)), raw)
        self.assertEqual(opener.call_count, 2)
        sleep.assert_called_once_with(5)

  def test_unknown_size_hash_and_cap(self):
    raw = b"raw boot bytes" * 100
    digest = hashlib.sha256(raw).hexdigest()
    url = "https://example.invalid/boot.img.xz"
    with patch("boot_download.urllib.request.urlopen", return_value=io.BytesIO(lzma.compress(raw))):
      self.assertEqual(boot_download.fetch_boot(url, digest, None), raw)
    with patch("boot_download.urllib.request.urlopen", return_value=io.BytesIO(lzma.compress(raw))):
      with self.assertRaisesRegex(ValueError, "mismatch"):
        boot_download.fetch_boot(url, "0" * 64, None)
    with patch("boot_download.MAX_BOOT_SIZE", len(raw) - 1):
      with patch("boot_download.urllib.request.urlopen", return_value=io.BytesIO(lzma.compress(raw))):
        with self.assertRaisesRegex(ValueError, "exceeds"):
          boot_download.fetch_boot(url, digest, None)
    for digest, size in (("", None), ("0" * 64, 0), ("0" * 64, boot_download.MAX_BOOT_SIZE + 1)):
      with patch("boot_download.urllib.request.urlopen") as opener:
        with self.assertRaises(ValueError):
          boot_download.fetch_boot(url, digest, size)
        opener.assert_not_called()


if __name__ == "__main__":
  unittest.main()
