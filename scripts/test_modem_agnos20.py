#!/usr/bin/env python3
"""Offline coverage for the AGNOS 20 APN bundle and its secret boundary."""
import ast
from copy import deepcopy
import difflib
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import compose
import test_compose as compose_fixture

ROOT = compose.ROOT
MODEM = ROOT / "userspace/modem/agnos-20/modem.py"
STOCK_SHA256 = "c4ceaa996ede974fee9ce4c23dfdf8f5f37345d357c8c0ca0144b9539beea2bf"
SERVICE_SHA256 = "371ce23460b7d13a365fb78e27202fbf43c95762a6d9d6b1003f0edd26924dc4"
# AGNOS 20.4/20.5 stock modem.py (agnos-builder #711: modem.py links /dev/modem_at0|1 itself).
MODEM_205 = ROOT / "userspace/modem/agnos-20.5/modem.py"
STOCK_205_SHA256 = "9e35f0d5ea0f3a2d40bfc22881dbe34ca78f29130865daf9bed67568cc29e325"
STOCK_REFERENCE = ROOT / "follow/reference/agnos20/modem.py"
STOCK_205_REFERENCE = ROOT / "follow/reference/agnos20.5/modem.py"
# AGNOS 20.6 stock modem.py from system ec939431 (agnos-builder 5b865b6c): #761 adds _initializing, so _at
# waits for the AT lock while initializing, and moves the body of _do_initializing into _initialize.
MODEM_206 = ROOT / "userspace/modem/agnos-20.6/modem.py"
STOCK_206_SHA256 = "71b602d872b978781add8d50894f4904fbca757058f9cfeb505f7a9000add5b4"
STOCK_206_REFERENCE = ROOT / "follow/reference/agnos20.6/modem.py"


def modem_pin():
  return {"path": str(MODEM.relative_to(ROOT)), "sha256": hashlib.sha256(MODEM.read_bytes()).hexdigest(),
          "stock_sha256": STOCK_SHA256, "service_sha256": SERVICE_SHA256}


class TestModemPin(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    (ROOT / ".tmp").mkdir(exist_ok=True)

  def test_optional_and_validated_in_normal_and_native_pin(self):
    pin = json.loads((ROOT / "agnos/pins.json").read_text())["19.9"]
    compose.validate_pin("20", pin)
    pin["modem"] = modem_pin()
    compose.validate_pin("20", pin)
    for value, reason in ((None, "must be an object"), ([], "must be an object"),
                          ({}, "missing modem"), ({**modem_pin(), "extra": 1}, "unexpected modem keys")):
      with self.subTest(value=value), self.assertRaisesRegex(ValueError, reason):
        compose.validate_pin("20", {**pin, "modem": value})
    for key in ("sha256", "stock_sha256", "service_sha256"):
      for value in (None, 3, "", "g" * 64, "f" * 63, "f" * 64 + "\n"):
        with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, f"modem.{key}.*SHA-256"):
          compose.validate_pin("20", {**pin, "modem": {**modem_pin(), key: value}})
    for value in (None, "", ".", "../outside", "/tmp/modem.py", "bad\0path"):
      with self.subTest(path=value), self.assertRaises(ValueError):
        compose.validate_pin("20", {**pin, "modem": {**modem_pin(), "path": value}})
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
      link = Path(directory) / "escape"
      link.symlink_to("/private/tmp")
      with self.assertRaisesRegex(ValueError, "stay inside the repo"):
        compose.validate_modem({**modem_pin(), "path": str((link / "modem.py").relative_to(ROOT))})

  def test_hash_and_fixed_import_allowlist(self):
    self.assertEqual(compose.modem_source({"modem": modem_pin()}), MODEM.read_bytes())
    with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
      compose.modem_source({"modem": {**modem_pin(), "sha256": "0" * 64}})
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
      source = Path(directory) / "modem.py"
      for code in ("import openpilot\n", "from cereal import log\n", "import requests\n", "from . import modem\n",
                   "import json, openpilot.common\n", "import sys\n"):
        source.write_text(code)
        pin = {**modem_pin(), "path": str(source.relative_to(ROOT)), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        with self.subTest(code=code), self.assertRaisesRegex(ValueError, "outside stdlib allowlist"):
          compose.modem_source({"modem": pin})


class TestAgnos20Compose(unittest.TestCase):
  setUpClass = classmethod(compose_fixture.TestCompose.setUpClass.__func__)
  cli = classmethod(compose_fixture.TestCompose.cli.__func__)
  variant_many = compose_fixture.TestCompose.variant_many
  variant = compose_fixture.TestCompose.variant
  v0112_variant = compose_fixture.TestCompose.v0112_variant
  snd_variant = compose_fixture.TestCompose.snd_variant
  apn_upstream = compose_fixture.TestCompose.apn_upstream

  def modern_fixture(self, variant="nightly-v0113", *, raylib_nb=False):
    upstream = self.apn_upstream(variant)
    with compose.temporary_index(self.repo, upstream) as (env, _):
      compose.put_blob(self.repo, env, "launch_env.sh", compose.blob(self.repo, upstream, "launch_env.sh").replace(b'"19.8"', b'"20.1"'))
      compose.git(self.repo, "update-index", "--index-info", data=b"0 " + b"0" * 40 + b"\topenpilot/common/hardware/comma/modem.py\n", env=env)
      # Both real nightly and release trees carry this marker.
      compose.put_blob(self.repo, env, "prebuilt", b"", mode="100644")
      if raylib_nb:
        for path in ("openpilot/system/ui/widgets/network.py", "openpilot/system/ui/widgets/keyboard.py"):
          source = compose.git(self.repo, "show", ":" + path, env=env)
          compose.put_blob(self.repo, env, path, source.replace(b"import pyray as rl", b"import raylib_nb as rl"))
      tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
      upstream = compose.git(self.repo, "commit-tree", tree, data=b"AGNOS 20.1 fixture\n", env=self.identity).decode().strip()
    resolved = deepcopy(self.resolved)
    resolved.update(version="20.1")
    resolved["pin"]["modem"] = modem_pin()
    return upstream, resolved

  def test_explicit_family_selection_with_prebuilt_in_both_fixtures(self):
    self.assertTrue(compose.agnos20("20.1"))
    old = self.apn_upstream("nightly-v0113")
    old = self.variant_many({"launch_env.sh": compose.blob(self.repo, old, "launch_env.sh").replace(b'"19.8"', b'"19.9"')}, old)
    self.assertEqual(compose.select_apn_patch(self.repo, old), compose.APN_PATCHES[2])
    for family in ("nightly", "release"):
      upstream, resolved = self.modern_fixture()
      for candidate in (paths[0] for paths in compose.APN_AGNOS20_PATCHES.values()):
        with compose.temporary_index(self.repo, upstream) as (env, _):
          compose.git(self.repo, "apply", "--cached", "--check", str(candidate), env=env)
      selected = compose.select_apn_patch(self.repo, upstream, family)
      self.assertEqual(selected, compose.APN_AGNOS20_PATCHES[family][0])
      commit, inputs = compose.compose(self.repo, upstream, resolved, tether="apply", apn="auto", apn_family=family)
      self.assertEqual(inputs, compose.compose_inputs(self.repo, upstream, resolved, tether="apply", apn="auto", apn_family=family))
      self.assertEqual(compose.blob(self.repo, commit, compose.MODEM_PATH), MODEM.read_bytes())
      self.assertEqual(compose.modem_values(compose.blob(self.repo, commit, "launch_env.sh")),
                       (STOCK_SHA256, SERVICE_SHA256, modem_pin()["sha256"]))
      self.assertFalse(compose.git(self.repo, "ls-tree", commit, "--", "openpilot/common/hardware/comma/modem.py"))
      pin_file = self.work / "modem-pin.json"
      pin_file.write_text(json.dumps(resolved))
      for native in (False, True):
        check = {"mode": "native", "version": "20.1", "modem": modem_pin()} if native else resolved
        pin_file.write_text(json.dumps(check))
        self.assertEqual(compose.load_pin(self.repo, upstream, pin_file), check)
        if native:
          native_commit, _ = compose.compose(self.repo, upstream, check, apn="auto", apn_family=family)
          compose.check_modem_bundle(self.repo, native_commit, check, required=True)
      pin_file.write_text(json.dumps(resolved))
      result = self.cli("gates.py", upstream, "--skip-download", "--tether", "apply", "--apn", "auto", "--apn-family", family, pin_file=pin_file)
      self.assertIn("G9: OK:", result.stdout)
      # --apn off does not ship any modem override or modem launcher additions.
      off, _ = compose.compose(self.repo, upstream, resolved)
      self.assertFalse(compose.git(self.repo, "ls-tree", off, "--", compose.MODEM_PATH))
      self.assertNotIn(b"wpa3_modem_override", compose.blob(self.repo, off, "launch_chffrplus.sh"))

  def test_real_201_pin_g2_hashes_and_g8_probe(self):
    self.check_real_pin_g2_hashes_and_g8_probe("20.1", {
      "boot": "6171465bb58806a62cf24c1d415f0be7cc9a364f9fa996bf337bd1104267bdc4",
      "system": "7300706856a09243c7667add29e88904b09b6d989a4159b766e16ef2ee3c81dd",
    })

  def test_real_202_pin_g2_hashes_and_g8_probe(self):
    self.check_real_pin_g2_hashes_and_g8_probe("20.2", {
      "boot": "e5dd1f6f515c96b08571678ce00119a7682b72a12ccab02ecd780bf2a305c882",
      "system": "8faed425880ec5a7ca9f57ba6a783544ce19e0c7836f0e8c13abc5d2210b6258",
    })

  def test_real_205_pin_g2_hashes_and_g8_probe(self):
    self.check_real_pin_g2_hashes_and_g8_probe("20.5", {
      "boot": "b457040d21dbce63938a4ba7c9adc87a5de1486cf26f46a0a780032be28a0b6e",
      "system": "193e949cd7a1f3b285ee6efbf7168686c77122d1f89966d9d911ad5afa7ad371",
    })

  def test_real_205_pin_ships_override_rebuilt_on_stock_205(self):
    pin = json.loads((ROOT / "agnos/pins.json").read_text())["20.5"]
    self.assertEqual(pin["modem"], {"path": "userspace/modem/agnos-20.5/modem.py",
                                    "sha256": hashlib.sha256(MODEM_205.read_bytes()).hexdigest(),
                                    "stock_sha256": STOCK_205_SHA256, "service_sha256": SERVICE_SHA256})
    self.assertEqual(hashlib.sha256(STOCK_205_REFERENCE.read_bytes()).hexdigest(), pin["modem"]["stock_sha256"])
    self.assertEqual(hashlib.sha256((ROOT / "follow/reference/agnos20/modem.service").read_bytes()).hexdigest(),
                     pin["modem"]["service_sha256"])
    upstream, _ = self.modern_fixture()
    manifest = json.loads(compose.blob(self.repo, upstream, compose.MANIFEST))
    for entry in manifest:
      if entry["name"] in ("boot", "system"):
        entry["hash_raw"] = pin["derived_from"][f'{entry["name"]}_hash_raw']
    launch = compose.blob(self.repo, upstream, "launch_env.sh").replace(b'"20.1"', b'"20.5"')
    upstream = self.variant_many({"launch_env.sh": launch, compose.MANIFEST: compose.manifest_bytes(manifest)}, upstream)
    resolved = {"mode": "pinned", "version": "20.5", "pin": pin}
    pin_file = self.work / "real-20.5-modem.json"
    pin_file.write_text(json.dumps(resolved))
    for family in ("nightly", "release"):
      with self.subTest(family=family):
        result = self.cli("gates.py", upstream, "--skip-download", "--tether", "apply", "--apn", "auto",
                          "--apn-family", family, pin_file=pin_file)
        self.assertIn("G9: OK: AGNOS-20 APN UI, stdlib modem override and pinned launcher bundle verified", result.stdout)
        commit, _ = compose.compose(self.repo, upstream, deepcopy(resolved), tether="apply", apn="auto", apn_family=family)
        self.assertEqual(compose.blob(self.repo, commit, compose.MODEM_PATH), MODEM_205.read_bytes())
        self.assertNotEqual(compose.blob(self.repo, commit, compose.MODEM_PATH), MODEM.read_bytes())
        self.assertEqual(compose.modem_values(compose.blob(self.repo, commit, "launch_env.sh")),
                         (STOCK_205_SHA256, SERVICE_SHA256, pin["modem"]["sha256"]))
        compose.check_modem_bundle(self.repo, commit, resolved, required=True)

  def test_real_206_pin_g2_hashes_and_g8_probe(self):
    self.check_real_pin_g2_hashes_and_g8_probe("20.6", {
      "boot": "2388598cda7c5c09a44b8f2683ff473d7ce8096a545a1c4ea2ff1cff65456c5a",
      "system": "ec939431c59751372e34d669fce1b08494b391019534b5d7f690b87991ea159e",
    })

  def test_real_206_pin_ships_override_rebuilt_on_stock_206(self):
    pins = json.loads((ROOT / "agnos/pins.json").read_text())
    pin = pins["20.6"]
    self.assertEqual(pin["modem"], {"path": "userspace/modem/agnos-20.6/modem.py",
                                    "sha256": hashlib.sha256(MODEM_206.read_bytes()).hexdigest(),
                                    "stock_sha256": STOCK_206_SHA256, "service_sha256": SERVICE_SHA256})
    self.assertEqual(hashlib.sha256(STOCK_206_REFERENCE.read_bytes()).hexdigest(), pin["modem"]["stock_sha256"])
    self.assertEqual(hashlib.sha256((ROOT / "follow/reference/agnos20/modem.service").read_bytes()).hexdigest(),
                     pin["modem"]["service_sha256"])
    # Only the stock modem.py changed: the supplicant and modem.service are those of 20.5.
    self.assertEqual(pin["wpa_supplicant"], pins["20.5"]["wpa_supplicant"])
    self.assertEqual(pin["modem"]["service_sha256"], pins["20.5"]["modem"]["service_sha256"])
    self.assertNotEqual(pin["modem"]["sha256"], pins["20.5"]["modem"]["sha256"])
    upstream, _ = self.modern_fixture()
    manifest = json.loads(compose.blob(self.repo, upstream, compose.MANIFEST))
    for entry in manifest:
      if entry["name"] in ("boot", "system"):
        entry["hash_raw"] = pin["derived_from"][f'{entry["name"]}_hash_raw']
    launch = compose.blob(self.repo, upstream, "launch_env.sh").replace(b'"20.1"', b'"20.6"')
    upstream = self.variant_many({"launch_env.sh": launch, compose.MANIFEST: compose.manifest_bytes(manifest)}, upstream)
    resolved = {"mode": "pinned", "version": "20.6", "pin": pin}
    pin_file = self.work / "real-20.6-modem.json"
    pin_file.write_text(json.dumps(resolved))
    for family in ("nightly", "release"):
      with self.subTest(family=family):
        result = self.cli("gates.py", upstream, "--skip-download", "--tether", "apply", "--apn", "auto",
                          "--apn-family", family, pin_file=pin_file)
        self.assertIn("G9: OK: AGNOS-20 APN UI, stdlib modem override and pinned launcher bundle verified", result.stdout)
        commit, _ = compose.compose(self.repo, upstream, deepcopy(resolved), tether="apply", apn="auto", apn_family=family)
        self.assertEqual(compose.blob(self.repo, commit, compose.MODEM_PATH), MODEM_206.read_bytes())
        for other in (MODEM, MODEM_205):
          self.assertNotEqual(compose.blob(self.repo, commit, compose.MODEM_PATH), other.read_bytes())
        launch = compose.blob(self.repo, commit, "launch_env.sh")
        self.assertEqual(compose.launch_values(launch), ("20.6", "wpa3.sae=7", pin["boot"]["hash_raw"],
                                                         pin["wpa_supplicant"]["stock_sha256"]))
        self.assertEqual(compose.modem_values(launch), (STOCK_206_SHA256, SERVICE_SHA256, pin["modem"]["sha256"]))
        compose.check_modem_bundle(self.repo, commit, resolved, required=True)

  def check_real_pin_g2_hashes_and_g8_probe(self, version, expected):
    upstream, _ = self.modern_fixture()
    pin = json.loads((ROOT / "agnos/pins.json").read_text())[version]
    launch = compose.blob(self.repo, upstream, "launch_env.sh").replace(b'"20.1"', f'"{version}"'.encode())
    manifest = json.loads(compose.blob(self.repo, upstream, compose.MANIFEST))
    for entry in manifest:
      if entry["name"] in expected:
        entry["hash_raw"] = expected[entry["name"]]
        self.assertEqual(pin["derived_from"][f'{entry["name"]}_hash_raw'], entry["hash_raw"])
    upstream = self.variant_many({"launch_env.sh": launch, compose.MANIFEST: json.dumps(manifest).encode()}, upstream)
    pin_file = self.work / f"real-{version}-pin.json"
    pin_file.write_text(json.dumps({"mode": "pinned", "version": version, "pin": pin}))
    result = self.cli("gates.py", upstream, "--skip-download", pin_file=pin_file)
    self.assertIn("G2: OK: stock boot/system hashes match derived_from", result.stdout)
    self.assertIn("G8: WARN: probed stock wpa_supplicant and override agree", result.stdout)
    self.assertNotIn("has not been probed", result.stdout + result.stderr)
    for name, digest in expected.items():
      changed = deepcopy(manifest)
      next(entry for entry in changed if entry["name"] == name)["hash_raw"] = "0" * 64
      drift = self.variant_many({compose.MANIFEST: json.dumps(changed).encode()}, upstream)
      with self.subTest(partition=name):
        result = self.cli("gates.py", drift, "--skip-download", pin_file=pin_file, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"G2: FAIL: upstream {name}.hash_raw differs from derived_from ({digest})", result.stderr)

  def test_family_is_hashed_and_only_one_candidate_in_family_may_apply(self):
    import gates
    import io
    upstream, resolved = self.modern_fixture()
    nightly = compose.compose_inputs(self.repo, upstream, resolved, apn="auto", apn_family="nightly")
    release = compose.compose_inputs(self.repo, upstream, resolved, apn="auto", apn_family="release")
    self.assertNotEqual(nightly, release)
    # With APN off both runs use identical patches: only the family can differ.
    self.assertNotEqual(compose.compose_inputs(self.repo, upstream, resolved, apn_family="nightly"),
                        compose.compose_inputs(self.repo, upstream, resolved, apn_family="release"))
    for invalid in (None, "", "prebuilt"):
      with self.subTest(family=invalid), self.assertRaisesRegex(ValueError, "unknown APN family"):
        compose.select_apn_patch(self.repo, upstream, invalid)
    candidate = compose.APN_AGNOS20_PATCHES["nightly"][0]
    pin_file = self.work / "family-pin.json"
    pin_file.write_text(json.dumps(resolved))
    for candidates, reason in (((candidate, candidate), "more than one APN patch applies"), ((), "no APN patch applies")):
      with patch.object(compose, "APN_AGNOS20_PATCHES", {**compose.APN_AGNOS20_PATCHES, "nightly": candidates}):
        for action in (compose.compose, compose.compose_inputs):
          with self.assertRaisesRegex(ValueError, reason):
            action(self.repo, upstream, resolved, apn="auto", apn_family="nightly")
        with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO) as stderr:
          self.assertEqual(gates.run_gates(self.repo, upstream, pin_file, skip_download=True, apn="auto", apn_family="nightly"), 1)
        self.assertIn("G5: FAIL: " + reason, stderr.getvalue())
    # Reverse checks still cover the other family.
    with compose.temporary_index(self.repo, upstream) as (env, _):
      compose.git(self.repo, "apply", "--cached", str(compose.APN_AGNOS20_PATCHES["release"][0]), env=env)
      tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
      with self.assertRaisesRegex(ValueError, "APN patch already upstream"):
        compose.select_apn_patch(self.repo, tree, "nightly")

  def test_release_v0112_ui_holds_at_g5(self):
    upstream, resolved = self.modern_fixture("release")
    pin_file = self.work / "release-v0112.json"
    pin_file.write_text(json.dumps(resolved))
    result = self.cli("gates.py", upstream, "--skip-download", "--apn", "auto", "--apn-family", "release", pin_file=pin_file, check=False)
    self.assertEqual(result.returncode, 1)
    self.assertIn("G5: FAIL: no APN patch applies", result.stderr)

  def test_199_byte_identical_to_prechange_baseline(self):
    upstream = self.apn_upstream("nightly-v0113")
    upstream = self.variant_many({"launch_env.sh": compose.blob(self.repo, upstream, "launch_env.sh").replace(b"19.8", b"19.9")}, upstream)
    resolved = deepcopy(self.resolved)
    resolved["version"] = "19.9"
    self.assertEqual(upstream, "393b3965156bc0167df24d0ee1929cacfb8c931e")
    # Captured with the unmodified composer before implementing AGNOS 20.
    for tether, apn, commit, inputs, tree in (
      ("off", "off", "872ced54da0b217dfcedc4141f2c60b173d1526e", "7bce39b7e3868db24ec55be43b53f311dfb15c945e790a47b5e42ed2c5bdeb12", "f95808467a2487dfe6e1707daa90d9cecd708d00"),
      ("apply", "auto", "06e21baf3407a7feb1707788d931cd0ba0731748", "b9ee61c97ee877bf227bc4bc6febfa9db84d449359e7f896ffefc4b3f0c2e854", "e86ca75649454e30b8599c5e64ef93c0beab13ca"),
    ):
      with self.subTest(tether=tether, apn=apn):
        actual = compose.compose(self.repo, upstream, resolved, tether, apn, apn_family="release")
        self.assertEqual(actual, (commit, inputs))
        self.assertEqual(compose.compose(self.repo, upstream, resolved, tether, apn, apn_family="nightly"), actual)
        self.assertEqual(compose.git(self.repo, "rev-parse", actual[0] + "^{tree}").decode().strip(), tree)

  def test_modem_patch_stacks_on_every_launcher_variant(self):
    upstream, resolved = self.modern_fixture()
    release = self.variant_many({"launch_chffrplus.sh": (compose_fixture.RELEASE_REF / "launch_chffrplus.sh").read_bytes()}, upstream)
    bases = (upstream, release, self.v0112_variant(upstream), self.v0112_variant(release), self.snd_variant(upstream))
    self.assertEqual(len(bases), len(compose.LAUNCHER_PATCHES))
    for base, launcher in zip(bases, compose.LAUNCHER_PATCHES):
      with self.subTest(launcher=launcher.name):
        self.assertEqual(compose.select_launcher_patch(self.repo, base), launcher)
        commit, _ = compose.compose(self.repo, base, resolved, apn="auto")
        compose.check_modem_bundle(self.repo, commit, resolved, required=True)

  def test_ui_requires_pinned_override_and_launcher_in_same_tree(self):
    upstream, resolved = self.modern_fixture()
    invalid = deepcopy(resolved)
    del invalid["pin"]["modem"]
    pin_file = self.work / "missing-modem.json"
    pin_file.write_text(json.dumps(invalid))
    result = self.cli("gates.py", upstream, "--skip-download", "--apn", "auto", pin_file=pin_file, check=False)
    self.assertEqual(result.returncode, 1)
    self.assertIn("G9: FAIL: AGNOS >= 20 APN auto requires a pinned modem override", result.stderr)
    for action in (compose.compose, compose.compose_inputs):
      with self.assertRaisesRegex(ValueError, "requires a pinned modem"):
        action(self.repo, upstream, invalid, apn="auto")
    with compose.temporary_index(self.repo, upstream) as (env, _):
      compose.git(self.repo, "apply", "--cached", str(compose.select_apn_patch(self.repo, upstream)), env=env)
      tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
      with self.assertRaisesRegex(ValueError, "requires the pinned modem override"):
        compose.check_modem_bundle(self.repo, tree, resolved)
      compose.put_blob(self.repo, env, compose.MODEM_PATH, MODEM.read_bytes(), mode="100644")
      tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
      with self.assertRaisesRegex(ValueError, "requires launcher-modem patch"):
        compose.check_modem_bundle(self.repo, tree, resolved)
      # Even --apn off holds if an upstream tree already has the unbundled UI.
      for action in (compose.compose, compose.compose_inputs):
        with self.assertRaises(ValueError):
          action(self.repo, tree, resolved)
    commit, _ = compose.compose(self.repo, upstream, resolved, apn="auto")
    with compose.temporary_index(self.repo, commit) as (env, scratch):
      # The exact old modem path is not allowed for AGNOS 20.
      compose.put_blob(self.repo, env, "openpilot/common/hardware/comma/modem.py", b"pass\n", mode="100644")
      tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
      with self.assertRaisesRegex(ValueError, "unexpected composed change"):
        compose.post_checks(self.repo, upstream, tree, resolved, scratch, apn_result="applied")

  def test_ui_note_is_conditional_and_translated(self):
    upstream, resolved = self.modern_fixture()
    for candidate in (paths[0] for paths in compose.APN_AGNOS20_PATCHES.values()):
      with compose.temporary_index(self.repo, upstream) as (env, _):
        compose.git(self.repo, "apply", "--cached", str(candidate), env=env)
        source = compose.git(self.repo, "show", ":openpilot/common/hardware/comma/apn_auth_store.py", env=env)
        namespace = {}
        exec(source, namespace)
        for value, expected in ((None, False), ("active abc\n", False), ("inactive stock-hash\n", True)):
          opened = Mock(side_effect=FileNotFoundError) if value is None else unittest.mock.mock_open(read_data=value)
          with patch("builtins.open", opened):
            self.assertEqual(namespace["modem_inactive"](), expected)
        for path in ("openpilot/selfdrive/ui/mici/layouts/settings/network/network_layout.py", "openpilot/system/ui/widgets/network.py"):
          code = compose.git(self.repo, "show", ":" + path, env=env)
          self.assertIn(b"tr(\"APN auth off: stock modem service\")", code)
          self.assertIn(b"set_visible(apn_auth_store.modem_inactive)", code)
          ast.parse(code)
        ja = compose.git(self.repo, "show", ":openpilot/selfdrive/ui/translations/app_ja.po", env=env).decode()
        self.assertIn('msgid "APN auth off: stock modem service"\nmsgstr "通常のモデム使用中: APNログインはオフ"', ja)

  def test_launcher_runtime(self):
    upstream, resolved = self.modern_fixture()
    commit, _ = compose.compose(self.repo, upstream, resolved, apn="auto")
    launcher = self.work / "modem-launcher.sh"
    launcher.write_bytes(compose.blob(self.repo, commit, "launch_chffrplus.sh"))
    result = subprocess.run(["bash", str(ROOT / "scripts/test_wpa3_modem_override.sh"), str(launcher), str(self.work)],
                            text=True, capture_output=True, timeout=30)
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn("PASS: wpa3_modem_override", result.stdout)


class TestModemAuth(unittest.TestCase):
  modem_file = MODEM

  def setUp(self):
    self.module = runpy.run_path(str(self.modem_file), run_name="modem_test")
    self.auth_reader = self.module["_read_auth_store"]
    self.globals = self.auth_reader.__globals__
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.work = Path(self.temp.name)
    self.store = self.work / "settings.json"
    self.globals["AUTH_STORE_PATH"] = str(self.store)

  def test_reader_and_validation_match_store(self):
    self.assertEqual(self.auth_reader(), ("", "", ""))
    for value in ([], None, 3, {"auth": "chap", "user": 3}, {"auth": "pap", "password": None}):
      self.store.write_text(json.dumps(value))
      self.assertEqual(self.auth_reader(), ("", "", ""))
    self.store.write_text('{invalid')
    self.assertEqual(self.auth_reader(), ("", "", ""))
    resolve = self.module["_resolve_auth"]
    for value in ('space bad', 'bad"', 'bad\\', 'bad,', 'あ', 'a' * 65):
      with self.subTest(value=value), self.assertRaises(ValueError):
        resolve("chap", value, "secret")
    self.assertIsNone(resolve("", "", ""))
    self.assertEqual(resolve("none", "", ""), (0, "", ""))

  def test_secret_never_reaches_argv_log_or_status(self):
    secret, user = "unique-password-9385", "unique-user-4938"
    self.store.write_text(json.dumps({"auth": "chap", "user": user, "password": secret}))
    os.chmod(self.store, 0o600)
    modem = self.module["Modem"]()
    modem._auth_store = self.auth_reader()
    modem._auth = modem._read_auth(modem._auth_store)
    modem._auth_command = "CGAUTH"
    modem._at = Mock(return_value=[])
    modem._read_auth_profile = Mock(return_value=(2, user, secret))
    status = self.work / "modem"
    self.globals["STATE_PATH"] = str(status)
    original_tempfile = tempfile.NamedTemporaryFile
    original_mkstemp = tempfile.mkstemp
    def named(*args, **kwargs):
      return original_tempfile(*args, **{**kwargs, "dir": self.work})
    def mkstemp(*args, **kwargs):
      return original_mkstemp(*args, **{**kwargs, "dir": self.work})
    with patch("tempfile.NamedTemporaryFile", side_effect=named), patch("tempfile.mkstemp", side_effect=mkstemp), \
         patch("subprocess.Popen") as popen, patch("subprocess.run") as run, self.assertLogs(level="INFO") as logs:
      modem._write_auth()
      modem._ppp.start(modem._auth)
      options = Path(modem._ppp._auth_path)
      self.assertEqual(options.stat().st_mode & 0o777, 0o600)
      self.assertIn(secret, options.read_text())
      modem._publish_state()
      self.assertEqual(json.loads(status.read_text())["fork_apn_auth"], "chap")
      modem._ppp.kill()
      self.assertFalse(options.exists())
    exposed = repr(popen.call_args_list) + repr(run.call_args_list) + repr(logs.output) + status.read_text()
    self.assertNotIn(secret, exposed)
    self.assertNotIn(user, exposed)
    shown = modem._at.call_args.kwargs["shown"]
    self.assertNotIn(secret, shown)
    # Modem error text may echo a command; sensitive AT failures redact it too.
    real_modem = self.module["Modem"]()
    lock = self.work / "lock"
    self.globals["AT_LOCK"] = str(lock)
    with patch.dict(self.globals, {"_serial_port": Mock(side_effect=OSError(secret))}), self.assertLogs(level="INFO") as errors:
      real_modem._at("AT+CGAUTH=" + secret, shown="AT+CGAUTH=<redacted>")
    self.assertNotIn(secret, repr(errors.output))

  def test_every_modem_hunk_was_ported(self):
    # Apply the original behavioural hunks to the old reference, then compare
    # the entire module after only the inline reader, license and marker edits.
    path = "openpilot/common/hardware/comma/modem.py"
    with tempfile.TemporaryDirectory() as directory:
      dest = Path(directory) / path
      dest.parent.mkdir(parents=True)
      dest.write_bytes((ROOT / "ref/apn-auth/nightly" / path).read_bytes())
      subprocess.run(["git", "apply", "--unsafe-paths", "--include=" + path, str(ROOT / "patches/apn-auth-nightly-v0113.patch")],
                     cwd=directory, check=True, capture_output=True)
      expected = dest.read_text().replace('from openpilot.common.esim.base import WEBBING_ICCID_PREFIX\nfrom openpilot.common.hardware.comma import apn_auth_store',
                                          'WEBBING_ICCID_PREFIX = "8985235"').replace('apn_auth_store.read()', '_read_auth_store()')
    actual = MODEM.read_text()
    header = actual.split('import csv')[0].removeprefix('#!/usr/bin/env python3\n')
    actual = actual.replace(header, '', 1)
    start = actual.index('AUTH_STORE_PATH = ')
    end = actual.index('def _resolve_auth(', start)
    actual = actual[:start] + actual[end:]
    actual = actual.replace('    self.S["fork_apn_auth"] = AUTH_PROTOCOLS.get(self._auth[0], "none") if self._auth is not None else "none"\n', '')
    self.assertEqual(actual, expected)
    # Removing exactly the auth hunks must restore the pinned stock bytes.
    stock = (ROOT / "ref/apn-auth/nightly" / path).read_text().replace('from openpilot.common.esim.base import WEBBING_ICCID_PREFIX', 'WEBBING_ICCID_PREFIX = "8985235"')
    stock = stock.replace('#!/usr/bin/env python3\n', '#!/usr/bin/env python3\n' + header, 1)
    self.assertEqual(hashlib.sha256(stock.encode()).hexdigest(), STOCK_SHA256)


class TestModemPort205(unittest.TestCase):
  """The AGNOS 20.5 override is the tested 20.1 override on stock 9e35f0d5, with no other edits."""
  modem_file = MODEM_205
  setUp = TestModemAuth.setUp
  test_reader_and_validation_match_store = TestModemAuth.test_reader_and_validation_match_store
  test_secret_never_reaches_argv_log_or_status = TestModemAuth.test_secret_never_reaches_argv_log_or_status

  def test_override_is_the_tested_override_merged_onto_stock_205(self):
    self.assertEqual(hashlib.sha256(STOCK_REFERENCE.read_bytes()).hexdigest(), STOCK_SHA256)
    self.assertEqual(hashlib.sha256(STOCK_205_REFERENCE.read_bytes()).hexdigest(), STOCK_205_SHA256)
    # git merge-file exits with the number of conflicts; check=True requires none.
    merged = subprocess.run(["git", "merge-file", "-p", str(MODEM), str(STOCK_REFERENCE), str(STOCK_205_REFERENCE)],
                            capture_output=True, check=True).stdout
    self.assertEqual(merged, MODEM_205.read_bytes())
    # Backwards: undoing the override update on the 20.5 stock gives the 20.1 stock,
    # except for the one import that #711 added and the old override already had.
    reverted = subprocess.run(["git", "merge-file", "-p", str(STOCK_205_REFERENCE), str(MODEM_205), str(MODEM)],
                              capture_output=True, check=True).stdout
    self.assertEqual(reverted.replace(b"import fcntl\nimport glob\n", b"import fcntl\n", 1), STOCK_REFERENCE.read_bytes())

  def test_fork_delta_is_unchanged_apart_from_the_now_stock_glob_import(self):
    def changed(old, new):
      diff = difflib.unified_diff(old.read_text().splitlines(), new.read_text().splitlines(), lineterm="", n=0)
      return [line for line in diff if line[:1] in "+-" and not line.startswith(("+++ ", "--- "))]
    old_delta = changed(STOCK_REFERENCE, MODEM)
    self.assertEqual(old_delta.count("+import glob"), 1)
    self.assertEqual(changed(STOCK_205_REFERENCE, MODEM_205), [line for line in old_delta if line != "+import glob"])
    stock_update = changed(STOCK_REFERENCE, STOCK_205_REFERENCE)
    self.assertIn("+  def _sync_ports(self) -> bool:", stock_update)
    self.assertEqual(changed(MODEM, MODEM_205), [line for line in stock_update if line != "+import glob"])

  def test_every_at_command_follows_port_sync(self):
    modem = self.module["Modem"]()
    order = []
    modem._at = Mock(side_effect=lambda cmd, shown=None: order.append(cmd) or [])
    modem._sync_ports = Mock(return_value=False)
    tty = self.globals["glob"]
    with patch.object(tty, "glob", return_value=[]), patch("subprocess.run") as run:
      self.assertEqual(modem._do_initializing(), self.module["State"].INITIALIZING)
    self.assertEqual((modem._sync_ports.call_count, order, run.call_count), (0, [], 0))
    with patch.object(tty, "glob", return_value=["/dev/ttyUSB2", "/dev/ttyUSB3"]), patch("subprocess.run"):
      self.assertEqual(modem._do_initializing(), self.module["State"].INITIALIZING)
    self.assertEqual((modem._sync_ports.call_count, order), (1, []))
    # The fork's auth-command probe retries return to INITIALIZING, so each
    # retry links the ports again before its first AT command.
    self.store.write_text(json.dumps({"auth": "chap", "user": "user", "password": "secret"}))
    modem._sync_ports = Mock(side_effect=lambda: order.append("sync") or True)
    modem._init_at_channel = Mock(side_effect=lambda: order.append("init") or True)
    modem._read_identity = Mock(return_value={"imei": "123456789012345", "iccid": "8981100000000000000",
                                              "mcc_mnc": "44020", "modem_version": "EG916Q"})
    modem._publish_state = Mock()
    with patch.object(tty, "glob", return_value=["/dev/ttyUSB2", "/dev/ttyUSB3"]), patch("subprocess.run"):
      states = [modem._do_initializing() for _ in range(4)]
    State = self.module["State"]
    self.assertEqual(states, [State.INITIALIZING] * 3 + [State.SEARCHING])
    self.assertTrue(modem._auth_unavailable)
    passes = [part for part in "|".join(order).split("sync") if part]
    self.assertEqual(len(passes), 4)
    self.assertEqual(order[0], "sync")
    self.assertTrue(all(part.startswith("|init|") for part in passes))

  def test_auth_marker_is_published_before_port_sync(self):
    modem = self.module["Modem"]()
    status = self.work / "modem"
    self.globals["STATE_PATH"] = str(status)
    seen = []
    def sync():
      seen.append(json.loads(status.read_text()))
      modem.running = False
      return False
    modem._sync_ports = sync
    original_tempfile = tempfile.NamedTemporaryFile
    def named(*args, **kwargs):
      return original_tempfile(*args, **{**kwargs, "dir": self.work})
    def ttys(pattern):
      return ["/dev/ttyUSB3"] if "ttyUSB" in pattern else []
    loops = []
    def sleep(_):
      # Bound the state loop so a regression fails instead of hanging.
      loops.append(1)
      modem.running = modem.running and len(loops) < 5
    with patch("tempfile.NamedTemporaryFile", side_effect=named), patch("subprocess.run"), patch("time.sleep", side_effect=sleep), \
         patch.object(self.globals["glob"], "glob", side_effect=ttys):
      modem.run()
    self.assertEqual(len(loops), 1)
    self.assertEqual(len(seen), 1)
    self.assertEqual((seen[0]["state"], seen[0]["fork_apn_auth"]), ("INITIALIZING", "none"))


def _functions(path):
  source = path.read_text()
  tree = ast.parse(source)
  functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
  for node in tree.body:
    if isinstance(node, ast.ClassDef):
      functions.update({f"{node.name}.{sub.name}": sub for sub in node.body if isinstance(sub, ast.FunctionDef)})
  return source, functions


def _self_calls(function):
  return sorted({node.func.attr for node in ast.walk(function) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"})


def _changed(old, new):
  """The +/- lines of a zero-context diff: what changed, independent of where."""
  diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
  return [line for line in diff if line[:1] in "+-" and not line.startswith(("+++ ", "--- "))]


def _touched(path, stock_path):
  """Functions that differ from stock, or that stock does not have."""
  source, functions = _functions(path)
  stock_source, stock = _functions(stock_path)
  segment = ast.get_source_segment
  return sorted(name for name, node in functions.items()
                if name not in stock or segment(source, node) != segment(stock_source, stock[name]))


class TestModemPort206(unittest.TestCase):
  """The AGNOS 20.6 override is the 20.5 override plus exactly the stock 20.5 -> 20.6 change (agnos-builder #761)."""
  modem_file = MODEM_206
  setUp = TestModemAuth.setUp
  test_reader_and_validation_match_store = TestModemAuth.test_reader_and_validation_match_store
  test_secret_never_reaches_argv_log_or_status = TestModemAuth.test_secret_never_reaches_argv_log_or_status
  test_every_at_command_follows_port_sync = TestModemPort205.test_every_at_command_follows_port_sync
  test_auth_marker_is_published_before_port_sync = TestModemPort205.test_auth_marker_is_published_before_port_sync

  def test_fork_delta_and_stock_update_are_both_unchanged(self):
    # Content identities, not a merge replay: they do not depend on merge.conflictStyle or diff3 output.
    pins = json.loads((ROOT / "agnos/pins.json").read_text())
    for path, digest in ((STOCK_205_REFERENCE, STOCK_205_SHA256), (STOCK_206_REFERENCE, STOCK_206_SHA256),
                         (MODEM_205, pins["20.5"]["modem"]["sha256"]), (MODEM_206, pins["20.6"]["modem"]["sha256"])):
      self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest, path)
    stock_205, stock_206 = STOCK_205_REFERENCE.read_text(), STOCK_206_REFERENCE.read_text()
    override_205, override_206 = MODEM_205.read_text(), MODEM_206.read_text()
    # The fork's own changes on top of stock are exactly those of the 20.5 override.
    fork_delta = _changed(stock_205, override_205)
    for landmark in ("-  def _at(self, cmd):", "+  def _at(self, cmd, shown=None):", '+      self._at("AT+COPS=0")',
                     "+def _read_auth_store() -> tuple[str, str, str]:"):
      self.assertIn(landmark, fork_delta)
    self.assertEqual(_changed(stock_206, override_206), fork_delta)
    # And the override moved by exactly the stock 20.5 -> 20.6 change.
    stock_update = _changed(stock_205, stock_206)
    for landmark in ("+    self._initializing = False  # see _at", "+  def _initialize(self):",
                     "+      fcntl.flock(fd, fcntl.LOCK_EX if self._initializing else fcntl.LOCK_EX | fcntl.LOCK_NB)"):
      self.assertIn(landmark, stock_update)
    self.assertEqual(_changed(override_205, override_206), stock_update)
    # The same holds per function: the fork touches the same functions, with _do_initializing's
    # hunks now in _initialize, and the 20.5 -> 20.6 override change is confined to stock's.
    self.assertEqual(_touched(MODEM_206, STOCK_206_REFERENCE),
                     sorted(name.replace("Modem._do_initializing", "Modem._initialize")
                            for name in _touched(MODEM_205, STOCK_205_REFERENCE)))
    self.assertEqual(_touched(MODEM_206, MODEM_205), _touched(STOCK_206_REFERENCE, STOCK_205_REFERENCE))
    self.assertEqual(_touched(STOCK_206_REFERENCE, STOCK_205_REFERENCE),
                     ["Modem.__init__", "Modem._at", "Modem._do_initializing", "Modem._initialize"])

  def test_initialize_holds_every_fork_hunk_and_the_wrapper_is_stock(self):
    stock_source, stock = _functions(STOCK_206_REFERENCE)
    source, override = _functions(MODEM_206)
    segment = ast.get_source_segment
    # The wrapper is byte-identical to stock: set the flag, run _initialize, reset it in finally.
    self.assertEqual(segment(source, override["Modem._do_initializing"]),
                     segment(stock_source, stock["Modem._do_initializing"]))
    guard, flag_on, wrapped = override["Modem._do_initializing"].body
    self.assertIn("glob.glob", ast.unparse(guard.test))
    self.assertEqual(ast.unparse(flag_on), "self._initializing = True")
    self.assertIsInstance(wrapped, ast.Try)
    self.assertEqual([ast.unparse(node) for node in wrapped.body], ["return self._initialize()"])
    self.assertEqual([ast.unparse(node) for node in wrapped.finalbody], ["self._initializing = False"])
    self.assertEqual((wrapped.handlers, wrapped.orelse), ([], []))
    self.assertEqual(_self_calls(override["Modem._do_initializing"]), ["_initialize"])
    # Every fork line of the tested 20.1 and the 20.5 _do_initializing is in _initialize, unchanged and in order.
    fork_initialize = _changed(segment(stock_source, stock["Modem._initialize"]), segment(source, override["Modem._initialize"]))
    self.assertIn('+      self._at("AT+COPS=0")', fork_initialize)
    for old_stock, old_override in ((STOCK_REFERENCE, MODEM), (STOCK_205_REFERENCE, MODEM_205)):
      with self.subTest(override=old_override.parent.name):
        (old_stock_source, old_stock_functions), (old_source, old_functions) = _functions(old_stock), _functions(old_override)
        self.assertEqual(_changed(segment(old_stock_source, old_stock_functions["Modem._do_initializing"]),
                                  segment(old_source, old_functions["Modem._do_initializing"])), fork_initialize)
    self.assertNotIn("_initializing", segment(source, override["Modem._initialize"]))
    self.assertEqual(source.count("self._initializing ="), 3)  # __init__ and the wrapper only

  def test_at_waits_only_while_initializing_and_sync_ports_never_waits(self):
    stock_source, stock = _functions(STOCK_206_REFERENCE)
    source, override = _functions(MODEM_206)
    segment = ast.get_source_segment
    # _sync_ports is stock's, non-blocking, whatever the flag; _at takes stock's conditional lock.
    self.assertEqual(segment(source, override["Modem._sync_ports"]), segment(stock_source, stock["Modem._sync_ports"]))
    sync_ports = segment(source, override["Modem._sync_ports"])
    self.assertIn("fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)", sync_ports)
    self.assertNotIn("_initializing", sync_ports)
    at = segment(source, override["Modem._at"])
    self.assertEqual([line.strip() for line in at.splitlines() if "fcntl.flock(" in line],
                     ["fcntl.flock(fd, fcntl.LOCK_EX if self._initializing else fcntl.LOCK_EX | fcntl.LOCK_NB)",
                      "fcntl.flock(fd, fcntl.LOCK_UN)"])
    modem = self.module["Modem"]()
    self.globals["AT_LOCK"] = str(self.work / "lock")
    lock, State = self.globals["fcntl"], self.module["State"]
    flags = []
    def flock(fd, flag):
      flags.append(flag)
      if flag != lock.LOCK_UN:
        raise BlockingIOError  # never reaches a serial port
    with patch.object(lock, "flock", side_effect=flock):
      self.assertFalse(modem._initializing)
      self.assertEqual(modem._at("AT"), [])
      modem._initializing = True
      self.assertEqual(modem._at("AT"), [])
      # _sync_ports takes the same lock without waiting, also while initializing.
      with patch.object(self.globals["glob"], "glob", return_value=["/dev/ttyUSB2", "/dev/ttyUSB3"]), patch("subprocess.run"):
        self.assertFalse(modem._sync_ports())
    self.assertEqual(flags, [lock.LOCK_EX | lock.LOCK_NB, lock.LOCK_EX, lock.LOCK_EX | lock.LOCK_NB])
    modem._initializing = False
    seen = []
    tty = self.globals["glob"]
    with patch.object(tty, "glob", return_value=[]):
      modem._initialize = Mock(side_effect=lambda: seen.append(modem._initializing) or State.SEARCHING)
      self.assertEqual(modem._do_initializing(), State.INITIALIZING)
    with patch.object(tty, "glob", return_value=["/dev/ttyUSB3"]):
      self.assertEqual(modem._do_initializing(), State.SEARCHING)
      self.assertFalse(modem._initializing)
      modem._initialize = Mock(side_effect=lambda: seen.append(modem._initializing) or State.INITIALIZING)
      self.assertEqual(modem._do_initializing(), State.INITIALIZING)
      self.assertFalse(modem._initializing)
      # The flag is reset in finally, also when _initialize raises.
      modem._initialize = Mock(side_effect=RuntimeError("modem gone"))
      with self.assertRaises(RuntimeError):
        modem._do_initializing()
    self.assertEqual(seen, [True, True])
    self.assertFalse(modem._initializing)

  def test_fork_at_commands_wait_while_initializing_and_not_after(self):
    self.store.write_text(json.dumps({"auth": "chap", "user": "user", "password": "secret"}))
    modem = self.module["Modem"]()
    replies = {"AT+CGMI": ["Quectel"], "AT+CGSN": ["123456789012345"], "AT+QCCID": ["+QCCID: 8981100000000000000"],
               "AT+CIMI": ["440200000000000"], "AT+GMR": ["EG916QGLLGR03A01M08"], "AT+COPS?": ["+COPS: 2"],
               "AT+CGAUTH=?": ["+CGAUTH: (1-15),(0-2),,"], "AT+CGAUTH?": ['+CGAUTH: 1,0,"",""'],
               "AT+CGDCONT?": ['+CGDCONT: 1,"IP","old","0.0.0.0",0,0']}
    sent = []
    def at(cmd, shown=None):
      sent.append((shown or cmd, modem._initializing))
      return replies.get(cmd, [])
    modem._at = Mock(side_effect=at)
    modem._sync_ports = Mock(return_value=True)
    modem._read_param = Mock(return_value="")
    published = []
    modem._publish_state = Mock(side_effect=lambda **kwargs: published.append(kwargs))
    with patch.object(self.globals["glob"], "glob", return_value=["/dev/ttyUSB2", "/dev/ttyUSB3"]), patch("subprocess.run"):
      self.assertEqual(modem._do_initializing(), self.module["State"].SEARCHING)
    commands = [cmd for cmd, _ in sent]
    for cmd in ("AT+COPS?", "AT+COPS=0", "AT+CGAUTH=?", "AT+CGAUTH?", "AT+CGDCONT?", 'AT+CGDCONT=1,"IP",""',
                "AT+CGAUTH=1,<redacted>"):
      self.assertIn(cmd, commands)
    self.assertTrue(all(initializing for _, initializing in sent), sent)
    # No registration= publish while initializing, so the fork's AT+CEER stays outside it.
    self.assertFalse(any("registration" in kwargs for kwargs in published))
    self.assertNotIn("AT+CEER", commands)
    self.assertFalse(modem._initializing)
    # The fork's SEARCHING re-attach keeps stock's non-blocking AT.
    sent.clear()
    modem._reattach_tries = 2
    modem._reattach()
    self.assertIn("AT+COPS=2", [cmd for cmd, _ in sent])
    self.assertFalse(any(initializing for _, initializing in sent), sent)

  def test_no_at_command_while_the_at_lock_is_held(self):
    # A blocking flock on a second file description in the same process would wait for itself.
    source, functions = _functions(MODEM_206)
    for name in ("Modem._at", "Modem._sync_ports"):
      self.assertEqual(_self_calls(functions[name]), [], name)
    holders = sorted(name for name, node in functions.items() if "AT_LOCK" in ast.unparse(node))
    self.assertEqual(holders, ["Modem._at", "Modem._sync_ports"])
    self.assertEqual(source.count("fcntl.flock("), 4)
    self.assertNotIn("threading", source)
    # SIGTERM only clears the loop flag; it sends no AT command of its own.
    handler = next(node for node in ast.walk(functions["main"]) if isinstance(node, ast.FunctionDef) and node.name == "_sig")
    self.assertEqual([ast.unparse(node) for node in handler.body], ["m.running = False"])


if __name__ == "__main__":
  unittest.main()
