#!/usr/bin/env python3
import ast
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
from unittest.mock import Mock, patch

import compose
import gates

ROOT = compose.ROOT
REF = ROOT / "ref/nightly-chestnut"
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
    cls.version, cls.pin = compose.load_pin(cls.repo, cls.upstream)
    result = cls.cli("compose.py", cls.upstream)
    cls.commit, cls.inputs = result.stdout.strip().splitlines()

  @classmethod
  def cli(cls, script, upstream, *args, check=True):
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--repo", str(cls.repo), "--upstream", upstream, *args],
                            text=True, capture_output=True, env={**os.environ, **compose.LFS_ENV})
    if check and result.returncode:
      raise AssertionError(f"{script} failed:\n{result.stdout}{result.stderr}")
    return result

  def variant(self, path, data):
    with compose.temporary_index(self.repo, self.upstream) as (env, _):
      compose.put_blob(self.repo, env, path, data)
      tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
      return compose.git(self.repo, "commit-tree", tree, data=b"Upstream drift\n", env=self.identity).decode().strip()

  def test_offline_gates(self):
    result = self.cli("gates.py", self.upstream, "--skip-download")
    for gate in ("G1", "G2", "G3", "G5"):
      self.assertIn(f"{gate}: OK:", result.stdout)
    self.assertIn("G4: SKIP:", result.stdout)

  def test_deterministic_commit_and_inputs(self):
    result = self.cli("compose.py", self.upstream)
    self.assertEqual(result.stdout.strip().splitlines(), [self.commit, self.inputs])
    self.assertEqual(self.cli("compose.py", self.upstream, "--inputs-only").stdout.strip(), self.inputs)
    self.assertEqual(compose.git(self.repo, "show", "-s", "--format=%P", self.commit).decode().strip(), self.upstream)
    self.assertEqual(compose.git(self.repo, "show", "-s", "--format=%aI %cI", self.commit),
                     compose.git(self.repo, "show", "-s", "--format=%cI %cI", self.upstream))
    message = compose.git(self.repo, "show", "-s", "--format=%B", self.commit).decode()
    self.assertEqual(message.strip(), f"Synthetic upstream + WPA3\n\nUpstream-Commit: {self.upstream}\n"
                     f"WPA3-Inputs: {self.inputs}\nWPA3-AGNOS: {self.pin['release_tag']}")
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
        new, _ = compose.compose(publisher, self.upstream, self.version, self.pin)
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
    second, _ = compose.compose(publisher, upstream, self.version, self.pin)
    self.assertNotEqual(first, second)
    lease = f"--force-with-lease={branch}:{first}"
    compose.git(publisher, "push", lease, full_remote.as_uri(), f"{second}:{branch}")
    with self.assertRaises(subprocess.CalledProcessError) as rejected:
      compose.git(publisher, "push", lease, full_remote.as_uri(), f"{first}:{branch}", env={"LC_ALL": "C"})
    self.assertIn(b"stale info", rejected.exception.stderr)
    self.assertEqual(compose.git(full_remote, "rev-parse", branch).decode().strip(), second)

  def test_launch_environment_and_runtime_patch(self):
    script = compose.blob(self.repo, self.commit, "launch_env.sh")
    self.assertEqual(compose.launch_values(script), ("19.8", self.pin["tag"], self.pin["boot"]["hash_raw"]))
    self.assertNotIn(b"__WPA3_BOOT_", script)
    launcher = compose.blob(self.repo, self.commit, "launch_chffrplus.sh")
    self.assertIn(b'if [ "$(< /VERSION)" != "$AGNOS_VERSION" ] || wpa3_boot_needed; then', launcher)
    updated = compose.blob(self.repo, self.commit, UPDATED)
    self.assertIn(b"cur_version == updated_version and not wpa3_needed", updated)
    self.assertIn(b"unset WPA3_BOOT_TAG", updated)
    self.assertIn(b"unset WPA3_BOOT_HASH", updated)

  def test_manifest_and_symlink(self):
    original = compose.blob(self.repo, self.upstream, compose.MANIFEST)
    entries = json.loads(compose.blob(self.repo, self.commit, compose.MANIFEST))
    self.assertEqual([p for p in entries if p["name"] == "boot"], [self.pin["boot"]])
    old_boot = next(p for p in json.loads(original) if p["name"] == "boot")
    self.assertEqual(compose.manifest_bytes([old_boot if p["name"] == "boot" else p for p in entries]), original)
    self.assertEqual(compose.git(self.repo, "ls-tree", self.commit, "--", MANIFEST_LINK),
                     compose.git(self.repo, "ls-tree", self.upstream, "--", MANIFEST_LINK))
    self.assertTrue(compose.git(self.repo, "ls-tree", self.commit, "--", MANIFEST_LINK).startswith(b"120000 blob "))

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

  def test_launcher_bash_unit(self):
    launcher = self.work / "launch_chffrplus.sh"
    launcher.write_bytes(compose.blob(self.repo, self.commit, "launch_chffrplus.sh"))
    result = subprocess.run(["bash", str(ROOT / "scripts/test_wpa3_boot_needed.sh"), str(launcher), str(self.work)],
                            capture_output=True, text=True)
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn("PASS: wpa3_boot_needed", result.stdout)
    print("\n" + result.stdout.strip())

  def test_updated_trigger_is_read_only_and_preserves_version_updates(self):
    # Execute just this function: no device dependencies or filesystem access.
    module = ast.parse(compose.blob(self.repo, self.commit, UPDATED))
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "handle_agnos_update")
    agnos = types.ModuleType("openpilot.common.hardware.comma.agnos")
    agnos.flash_agnos_update = Mock()
    agnos.get_target_slot_number = Mock(return_value=1)
    cases = [
      ("19.8", "wpa3.sae=1", "quiet wpa3.sae=1", "hash-a 2", False),
      ("19.8", "", "quiet", None, False),
      ("19.8", "wpa3.sae=1", "quiet wpa3.sae=10", None, True),
      ("19.8", "wpa3.sae=1", "quiet", "hash-a 2", True),
      ("19.8", "wpa3.sae=1", "quiet", "hash-a 3", False),
      ("19.8", "wpa3.sae=1", "quiet", "hash-a 300", False),
      ("19.8", "wpa3.sae=1", "quiet", "hash-old 3", True),
      ("19.8", "wpa3.sae=1", "quiet", "hash-a invalid", False),
      ("19.7", "wpa3.sae=1", "quiet", "hash-a 3", True),
    ]
    for current, tag, cmdline, attempts, expected in cases:
      with self.subTest(current=current, tag=tag, cmdline=cmdline, attempts=attempts):
        path = Mock()
        path.return_value.read_text.side_effect = [cmdline, FileNotFoundError() if attempts is None else attempts]
        namespace = {"Path": path, "os": os, "OVERLAY_MERGED": "/staged", "HARDWARE": Mock(get_os_version=Mock(return_value=current)),
                     "run": Mock(side_effect=["19.8", tag, "hash-a"]), "cloudlog": Mock(), "set_consistent_flag": Mock()}
        agnos.flash_agnos_update.reset_mock()
        with patch.dict(sys.modules, {agnos.__name__: agnos}):
          exec(compile(ast.Module(body=[function], type_ignores=[]), UPDATED, "exec"), namespace)
          namespace["handle_agnos_update"]()
        self.assertEqual(agnos.flash_agnos_update.called, expected)
        self.assertEqual(namespace["set_consistent_flag"].called, expected)
        self.assertTrue(all(call[0] == "read_text" for call in path.return_value.method_calls))


class TestBootDownload(unittest.TestCase):
  def test_streamed_xz_hash_size_and_corruption(self):
    raw = b"synthetic boot\0" * 100000
    boot = {"url": "https://example.invalid/boot.img.xz", "hash_raw": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
    compressed = lzma.compress(raw)
    with patch("gates.urllib.request.urlopen", return_value=io.BytesIO(compressed)):
      gates.check_download(boot)
    for data, changed in ((compressed, {"hash_raw": "0" * 64}), (compressed, {"size": len(raw) - 1}),
                          (compressed, {"size": len(raw) + 1}), (compressed[:-10], {})):
      with self.subTest(changed=changed, compressed_size=len(data)):
        with patch("gates.urllib.request.urlopen", return_value=io.BytesIO(data)):
          with self.assertRaises((ValueError, EOFError, lzma.LZMAError)):
            gates.check_download({**boot, **changed})


if __name__ == "__main__":
  unittest.main()
