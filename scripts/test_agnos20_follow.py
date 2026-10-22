#!/usr/bin/env python3
"""Offline regression coverage for following AGNOS 20.x from the 20.1 pin."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import unittest
from unittest.mock import patch

from boot_fixture import PAGE, boot_image, mutate
import compose
import follow_state as fs
import pins
import test_modem_agnos20 as modem_fixture


class TestAgnos20Follow(unittest.TestCase):
  setUpClass = classmethod(modem_fixture.TestAgnos20Compose.setUpClass.__func__)
  cli = classmethod(modem_fixture.TestAgnos20Compose.cli.__func__)
  variant_many = modem_fixture.TestAgnos20Compose.variant_many
  apn_upstream = modem_fixture.TestAgnos20Compose.apn_upstream
  modern_fixture = modem_fixture.TestAgnos20Compose.modern_fixture

  def setUp(self):
    self.modern_upstream, _ = self.modern_fixture()
    self.state = fs.load()
    self.real_pin = deepcopy(self.state["manual"]["20.1"])
    self.base = boot_image()
    self.system_hash = "9" * 64
    self.assertNotIn(self.system_hash, self.state["system_probe"])
    self.downloads, self.calls = {}, []
    self.agnos_py = pins.git_blob_id(compose.blob(self.repo, self.modern_upstream, compose.AGNOS_PY))
    # Substitute only stock provenance; keep the real release/WPA3 boot and
    # userspace blocks. All three bases deliberately have equivalent boots.
    for version in self.state["manual"]:
      self.set_base_stock(version, self.base)
    self.future_upstream = self.follow_upstream("20.2", self.base)

  def set_base_stock(self, version, stock):
    url = f"https://example.invalid/agnos-{version}.img.xz"
    self.downloads[url] = stock
    self.state["manual"][version]["derived_from"].update(
      boot_url=url, boot_hash_raw=hashlib.sha256(stock).hexdigest(), agnos_py_blob=self.agnos_py)

  def follow_upstream(self, version, stock):
    url = f"https://example.invalid/upstream-{version}.img.xz"
    self.downloads[url] = stock
    manifest = json.loads(compose.blob(self.repo, self.modern_upstream, compose.MANIFEST))
    for entry in manifest:
      if entry["name"] == "boot":
        entry.update(url=url, hash_raw=hashlib.sha256(stock).hexdigest(), size=len(stock))
      elif entry["name"] == "system":
        entry["hash_raw"] = self.system_hash
    launch = compose.blob(self.repo, self.modern_upstream, "launch_env.sh").replace(b'"20.1"', f'"{version}"'.encode())
    return self.variant_many({"launch_env.sh": launch, compose.MANIFEST: compose.manifest_bytes(manifest)},
                             self.modern_upstream)

  def fetch(self, url, digest, size):
    self.calls.append(url)
    stock = self.downloads[url]
    self.assertEqual(hashlib.sha256(stock).hexdigest(), digest)
    if size is not None:
      self.assertEqual(len(stock), size)
    return stock

  def resolve_cli(self, mode="off", upstream=None):
    output = self.work / f"{self._testMethodName}-{mode}.json"
    args = ["pins.py", "--repo", str(self.repo), "--upstream", upstream or self.future_upstream,
            "--out", str(output), "--follow-mode", mode, "--branch", "nightly"]
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch("sys.argv", args), patch("pins.load", return_value=self.state), \
         patch("pins.fetch_boot", self.fetch), redirect_stdout(stdout), redirect_stderr(stderr):
      rc = pins.main()
    return rc, stdout.getvalue(), stderr.getvalue(), output

  def test_202_same_boot_cli_derives_from_201_and_warns(self):
    original = deepcopy(self.state)
    rc, stdout, stderr, output = self.resolve_cli()
    self.assertEqual(rc, 0, stdout + stderr)
    self.assertEqual(stdout, "PIN: OK: derived 20.2 from 20.1\n")
    self.assertEqual(stderr, "G8: WARN: system image has not been probed\n")
    resolved = json.loads(output.read_text())
    self.assertEqual({key: resolved[key] for key in ("mode", "version", "base")},
                     {"mode": "derived", "version": "20.2", "base": "20.1"})
    pin = resolved["pin"]
    self.assertEqual(pin["release_tag"], "agnos-20.1-wpa3.4")
    self.assertEqual(pin["tag"], "wpa3.sae=4")
    self.assertEqual(pin["boot"]["hash_raw"], "cc3ce53477e58056309a0cab1ddcbd052ba69f9d8eb38e131a375db2c8cb9744")
    for key in ("boot", "modem", "wpa_supplicant"):
      self.assertEqual(pin[key], self.real_pin[key])
    self.assertEqual(pin["derived_from"], {
      "boot_url": "https://example.invalid/upstream-20.2.img.xz",
      "boot_hash_raw": hashlib.sha256(self.base).hexdigest(),
      "system_hash_raw": self.system_hash, "agnos_py_blob": self.agnos_py,
    })
    self.assertNotEqual(pin["derived_from"]["system_hash_raw"], self.real_pin["derived_from"]["system_hash_raw"])
    self.assertEqual(self.calls, [pin["derived_from"]["boot_url"], self.state["manual"]["20.1"]["derived_from"]["boot_url"]])
    self.assertEqual(self.state, original)

  def test_202_derived_compose_uses_agnos20_bundle_for_both_apn_families(self):
    rc, stdout, stderr, pin_file = self.resolve_cli()
    self.assertEqual(rc, 0, stdout + stderr)
    resolved = json.loads(pin_file.read_text())
    for family in ("nightly", "release"):
      with self.subTest(family=family):
        upstream = self.future_upstream
        if family == "release":
          upstream = self.variant_many({"launch_chffrplus.sh": (compose.ROOT / "ref/release-staging/launch_chffrplus.sh").read_bytes()},
                                       upstream)
        patch_file = compose.ROOT / f"patches/apn-auth-{family}-agnos20.patch"
        self.assertEqual(compose.select_apn_patch(self.repo, upstream, family), patch_file)
        flags = ("--follow-mode", "off", "--apn", "auto", "--apn-family", family)
        result = self.cli("gates.py", upstream, "--skip-download", *flags, pin_file=pin_file)
        for gate in ("G1", "G2", "G3", "G5", "G7", "G9"):
          self.assertIn(f"{gate}: OK:", result.stdout)
        self.assertIn("G8: WARN: system image has not been probed", result.stdout)
        self.assertIn(f"G5: OK: APN patch {patch_file.name} applies cleanly", result.stdout)
        commit, _ = self.cli("compose.py", upstream, "--apn", "auto", "--apn-family", family,
                             pin_file=pin_file).stdout.splitlines()
        launch = compose.blob(self.repo, commit, "launch_env.sh")
        self.assertIn(b'AGNOS_VERSION="20.2"', launch)
        self.assertEqual(compose.launch_values(launch),
                         ("20.2", "wpa3.sae=4", self.real_pin["boot"]["hash_raw"], self.real_pin["wpa_supplicant"]["stock_sha256"]))
        self.assertEqual(compose.blob(self.repo, commit, "wpa3/modem.py"), modem_fixture.MODEM.read_bytes())
        compose.check_modem_bundle(self.repo, commit, resolved, required=True)
        with compose.temporary_index(self.repo, commit) as (env, _):
          compose.git(self.repo, "apply", "--cached", "--reverse", "--check", str(patch_file), env=env)
          compose.git(self.repo, "apply", "--cached", "--reverse", "--check", "--include=launch_chffrplus.sh",
                      str(compose.ROOT / "patches/launcher-modem-agnos20.patch"), env=env)
        message = compose.git(self.repo, "show", "-s", "--format=%B", commit).decode()
        self.assertIn("WPA3-AGNOS: agnos-20.1-wpa3.4\nWPA3-Pin: derived 20.2 from 20.1\n", message)
        self.assertIn(f"WPA3-APN-Patch: {patch_file.name} applied\n", message)
        manifest = json.loads(compose.blob(self.repo, commit, compose.MANIFEST))
        self.assertEqual(next(entry for entry in manifest if entry["name"] == "boot"), self.real_pin["boot"])
        self.assertEqual(next(entry for entry in manifest if entry["name"] == "system")["hash_raw"], self.system_hash)

  def test_202_changed_stock_kernel_holds(self):
    upstream = self.follow_upstream("20.2", mutate(self.base, PAGE + 12))
    rc, stdout, stderr, output = self.resolve_cli(upstream=upstream)
    self.assertEqual(rc, 1, stdout + stderr)
    self.assertEqual(stdout, "")
    self.assertIn("PIN: FAIL: kernel changed since 20.1, 19.9, 19.8:", stderr)
    self.assertIn("outside build identity", stderr)
    self.assertNotIn("PIN: OK:", stderr)
    self.assertFalse(output.exists())

  def test_20x_derived_base_selection_is_numeric_and_requires_equivalent_boot(self):
    self.assertEqual(sorted(("20.2", "20.10", "20.1"), key=pins.version_key), ["20.1", "20.2", "20.10"])
    for version in ("20.2", "20.10", "20.11"):
      self.state["manual"][version] = deepcopy(self.state["manual"]["20.1"])
      self.set_base_stock(version, self.base)
    changed = mutate(self.base, PAGE + 12)
    self.set_base_stock("20.11", changed)
    upstream = self.follow_upstream("20.12", self.base)
    for expected, compared in (("20.10", ("20.11", "20.10")),
                               ("20.2", ("20.11", "20.10", "20.2")),
                               ("20.1", ("20.11", "20.10", "20.2", "20.1"))):
      with self.subTest(base=expected):
        self.calls.clear()
        resolved = pins.resolve(lambda name: compose.blob(self.repo, upstream, name), self.state["manual"], self.fetch,
                                state=self.state, mode="off", branch="nightly")
        self.assertEqual((resolved["mode"], resolved["version"], resolved["base"]), ("derived", "20.12", expected))
        self.assertIsNone(resolved["pin"].get("withdrawn"))
        self.assertEqual(self.calls, ["https://example.invalid/upstream-20.12.img.xz"] +
                         [self.state["manual"][version]["derived_from"]["boot_url"] for version in compared])
        self.set_base_stock(expected, changed)

  def test_202_unprobed_system_is_pending_in_state_and_on(self):
    original = deepcopy(self.state)
    for mode in ("state", "on"):
      with self.subTest(mode=mode):
        rc, stdout, stderr, output = self.resolve_cli(mode)
        self.assertEqual(rc, 3, stdout + stderr)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, f"PIN: FOLLOW: probe {self.system_hash} system image has not been probed\n")
        self.assertFalse(output.exists())
        self.assertEqual(self.state, original)


if __name__ == "__main__":
  unittest.main()
