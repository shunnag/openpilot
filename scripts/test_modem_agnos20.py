#!/usr/bin/env python3
"""Offline coverage for the AGNOS 20 APN bundle and its secret boundary."""
import ast
from copy import deepcopy
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
  apn_upstream = compose_fixture.TestCompose.apn_upstream

  def modern_fixture(self, variant="nightly-v0113"):
    upstream = self.apn_upstream(variant)
    with compose.temporary_index(self.repo, upstream) as (env, _):
      compose.put_blob(self.repo, env, "launch_env.sh", compose.blob(self.repo, upstream, "launch_env.sh").replace(b'"19.8"', b'"20.1"'))
      compose.git(self.repo, "update-index", "--index-info", data=b"0 " + b"0" * 40 + b"\topenpilot/common/hardware/comma/modem.py\n", env=env)
      # Both real nightly and release trees carry this marker.
      compose.put_blob(self.repo, env, "prebuilt", b"", mode="100644")
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
      for candidate in (p for paths in compose.APN_AGNOS20_PATCHES.values() for p in paths):
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
    upstream, _ = self.modern_fixture()
    pin = json.loads((ROOT / "agnos/pins.json").read_text())["20.1"]
    expected = {
      "boot": "6171465bb58806a62cf24c1d415f0be7cc9a364f9fa996bf337bd1104267bdc4",
      "system": "7300706856a09243c7667add29e88904b09b6d989a4159b766e16ef2ee3c81dd",
    }
    manifest = json.loads(compose.blob(self.repo, upstream, compose.MANIFEST))
    for entry in manifest:
      if entry["name"] in expected:
        entry["hash_raw"] = expected[entry["name"]]
        self.assertEqual(pin["derived_from"][f'{entry["name"]}_hash_raw'], entry["hash_raw"])
    upstream = self.variant_many({compose.MANIFEST: json.dumps(manifest).encode()}, upstream)
    pin_file = self.work / "real-201-pin.json"
    pin_file.write_text(json.dumps({"mode": "pinned", "version": "20.1", "pin": pin}))
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
    for base, launcher in zip((upstream, release, self.v0112_variant(upstream), self.v0112_variant(release)), compose.LAUNCHER_PATCHES):
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
    for candidate in (p for paths in compose.APN_AGNOS20_PATCHES.values() for p in paths):
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
  def setUp(self):
    self.module = runpy.run_path(str(MODEM), run_name="modem_test")
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


if __name__ == "__main__":
  unittest.main()
