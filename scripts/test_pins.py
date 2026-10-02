#!/usr/bin/env python3
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import Mock, patch

from boot_fixture import PAGE, boot_image, identity_pair, mutate
import compose
import pins


class TestResolver(unittest.TestCase):
  def setUp(self):
    self.base, self.stock = identity_pair()
    self.base_url = "https://example.invalid/base.img.xz"
    self.stock_url = "https://example.invalid/upstream.img.xz"
    self.agnos_py = pins.git_blob_id(b"agnos.py\n")
    pin = deepcopy(json.loads((compose.ROOT / "agnos/pins.json").read_text())["19.8"])
    pin["derived_from"].update(boot_url=self.base_url, boot_hash_raw=hashlib.sha256(self.base).hexdigest(),
                               agnos_py_blob=self.agnos_py)
    self.pins = {"19.8": pin}
    self.version = "19.9"
    self.calls = []
    self.downloads = {self.base_url: self.base}
    self.manifest = [
      {"name": "boot", "url": self.stock_url, "hash_raw": hashlib.sha256(self.stock).hexdigest(), "size": len(self.stock)},
      {"name": "system", "hash_raw": "c" * 64},
    ]
    self.addCleanup(patch.stopall)
    patch("pins.blob", side_effect=self.blob).start()

  def blob(self, repo, upstream, path):
    if path == "launch_env.sh":
      return f'if [ -z "$AGNOS_VERSION" ]; then\n  export AGNOS_VERSION="{self.version}"\nfi\n'.encode()
    if path == compose.MANIFEST:
      return json.dumps(self.manifest).encode()
    if path == compose.AGNOS_PY:
      return b"agnos.py\n" if self.agnos_py == pins.git_blob_id(b"agnos.py\n") else b"drift\n"
    raise AssertionError(path)

  def fetch(self, url, digest, size):
    self.calls.append((url, digest, size))
    raw = self.stock if url == self.stock_url else self.downloads[url]
    if hashlib.sha256(raw).hexdigest() != digest or (size is not None and size != len(raw)):
      raise ValueError("boot download mismatch: hash/size")
    return raw

  def set_stock(self, stock):
    self.stock = stock
    self.manifest[0].update(hash_raw=hashlib.sha256(stock).hexdigest(), size=len(stock))

  def resolve(self):
    return pins.resolve(lambda path: self.blob(None, None, path), self.pins, self.fetch)

  def test_pinned_has_no_downloads(self):
    self.version = "19.8"
    self.manifest = None  # Neither manifest nor agnos.py is needed for resolution.
    self.assertEqual(self.resolve(), {"mode": "pinned", "version": "19.8", "pin": self.pins["19.8"]})
    self.assertEqual(self.calls, [])

  def test_repository_198_and_199_pins_resolve_with_distinct_tag_hash_pairs(self):
    self.pins = json.loads((compose.ROOT / "agnos/pins.json").read_text())
    self.manifest = None
    for version, tag, digest in (
      ("19.8", "wpa3.sae=2", "862b653d80c9d7ac933a60d2bb748371a3267f658194e6ca7273f33c2973de94"),
      ("19.9", "wpa3.sae=3", "f94c88e80909c556f20c426898cebced72e2470f520606282448c1275b68dd8d"),
    ):
      with self.subTest(version=version):
        self.version = version
        resolved = self.resolve()  # Validate the tag/hash invariant across both real pins.
        self.assertEqual(resolved, {"mode": "pinned", "version": version, "pin": self.pins[version]})
        self.assertEqual(resolved["pin"]["tag"], tag)
        self.assertEqual(resolved["pin"]["boot"]["hash_raw"], digest)
        self.assertEqual(resolved["pin"]["release_tag"], f"agnos-{version}-wpa3.{tag[-1]}")
    self.assertEqual(self.pins["19.9"]["wpa_supplicant"], self.pins["19.8"]["wpa_supplicant"])
    self.assertEqual(self.calls, [])

  def test_derived_preserves_tested_pin_and_replaces_origin(self):
    original = deepcopy(self.pins)
    resolved = self.resolve()
    self.assertEqual({key: resolved[key] for key in ("mode", "version", "base")},
                     {"mode": "derived", "version": "19.9", "base": "19.8"})
    for key in ("boot", "tag", "release_tag", "wpa_supplicant"):
      self.assertEqual(resolved["pin"][key], original["19.8"][key])
    self.assertEqual(resolved["pin"]["derived_from"], {
      "boot_hash_raw": self.manifest[0]["hash_raw"], "boot_url": self.stock_url,
      "system_hash_raw": "c" * 64, "agnos_py_blob": self.agnos_py,
    })
    self.assertEqual(self.pins, original)
    self.assertEqual([call[0] for call in self.calls], [self.stock_url, self.base_url])
    self.assertEqual(self.calls[0][2], self.manifest[0]["size"])
    self.assertIsNone(self.calls[1][2])

  def test_bases_are_numeric_descending(self):
    self.pins["19.10"] = deepcopy(self.pins["19.8"])
    url = "https://example.invalid/19.10.img.xz"
    self.downloads[url] = mutate(self.base, PAGE + 12)
    self.pins["19.10"]["derived_from"].update(boot_url=url, boot_hash_raw=hashlib.sha256(self.downloads[url]).hexdigest())
    self.assertEqual(self.resolve()["base"], "19.8")
    self.assertEqual([call[0] for call in self.calls], [self.stock_url, url, self.base_url])

  def test_equivalent_with_agnos_py_change_holds(self):
    self.agnos_py = "b" * 40
    with self.assertRaisesRegex(ValueError, "agnos.py changed since 19.8"):
      self.resolve()

  def test_native_does_not_download_bases_or_require_agnos_py(self):
    self.set_stock(boot_image(sae=4, rsnxe=True))
    self.agnos_py = "changed"
    self.assertEqual(self.resolve(), {"mode": "native", "version": "19.9", "base": "19.8",
                                     "wpa_supplicant": self.pins["19.8"]["wpa_supplicant"]})
    self.assertEqual([call[0] for call in self.calls], [self.stock_url])

  def test_native_uses_supplicant_from_newest_pin(self):
    self.set_stock(boot_image(sae=4, rsnxe=True))
    self.pins["19.10"] = deepcopy(self.pins["19.8"])
    self.pins["19.10"]["wpa_supplicant"]["stock_sha256"] = "d" * 64
    original = deepcopy(self.pins)
    resolved = self.resolve()
    self.assertEqual(resolved["base"], "19.10")
    self.assertEqual(resolved["wpa_supplicant"], self.pins["19.10"]["wpa_supplicant"])
    resolved["wpa_supplicant"]["stock_sha256"] = "e" * 64
    self.assertEqual(self.pins, original)
    self.assertEqual([call[0] for call in self.calls], [self.stock_url])
    del self.pins["19.10"]["wpa_supplicant"]
    self.assertEqual(self.resolve(), {"mode": "native", "version": "19.9", "base": "19.10"})

  def test_sae_without_rsnxe_holds_without_base_download(self):
    self.set_stock(boot_image(sae=4))
    with self.assertRaisesRegex(ValueError, r"stock kernel has SAE but no RSNXE \(H2E\); add a pin"):
      self.resolve()
    self.assertEqual([call[0] for call in self.calls], [self.stock_url])

  def test_partial_sae_holds_without_base_download(self):
    for rsnxe in (False, True):
      with self.subTest(rsnxe=rsnxe):
        self.calls.clear()
        self.set_stock(boot_image(sae=2, rsnxe=rsnxe))
        with self.assertRaisesRegex(ValueError, "partial SAE markers"):
          self.resolve()
        self.assertEqual([call[0] for call in self.calls], [self.stock_url])

  def test_all_pins_are_validated_before_fetch_in_every_mode(self):
    original = deepcopy(self.pins["19.8"])
    for version, stock in (("19.8", self.stock), ("19.9", self.stock), ("19.9", boot_image(sae=4, rsnxe=True))):
      self.version = version
      self.set_stock(stock)
      for group, keys in (("derived_from", ("boot_url", "boot_hash_raw", "system_hash_raw", "agnos_py_blob")),
                          ("boot", compose.BOOT_KEYS),
                          ("wpa_supplicant", ("path", "sha256", "copyright", "stock_sha256"))):
        for key in keys:
          with self.subTest(version=version, group=group, key=key):
            invalid = deepcopy(original)
            del invalid[group][key]
            self.pins = {"19.8": deepcopy(original), "19.7": invalid}
            with self.assertRaisesRegex(ValueError, f"pin 19.7: missing {group}.{key}"):
              self.resolve()
            self.assertEqual(self.calls, [])

  def test_pin_tag_hash_mapping_is_one_to_one(self):
    original = deepcopy(self.pins["19.8"])
    for version, stock in (("19.8", self.stock), ("19.9", boot_image(sae=4, rsnxe=True))):
      self.version = version
      self.set_stock(stock)
      for conflict in ("tag", "hash"):
        with self.subTest(version=version, conflict=conflict):
          other = deepcopy(original)
          if conflict == "tag":
            other["boot"].update(hash="f" * 64, hash_raw="f" * 64)
          else:
            other["tag"] = "wpa3.sae=1"
          self.pins = {"19.8": original, "19.7": other}
          with self.assertRaisesRegex(ValueError, "pins 19.8 and 19.7:"):
            self.resolve()
          self.assertEqual(self.calls, [])
    self.version = "19.8"
    self.pins = {"19.8": original, "19.7": deepcopy(original)}
    self.assertEqual(self.resolve()["mode"], "pinned")
    # A new tag and new hash together are a valid pin v2 transition.
    self.pins["19.7"]["tag"] = "wpa3.sae=1"
    self.pins["19.7"]["boot"].update(hash="18c888b86f8846cd49bf3312b2c02fb60fc3f5e2f165d3a77417a7ad4e2c5549",
                                    hash_raw="18c888b86f8846cd49bf3312b2c02fb60fc3f5e2f165d3a77417a7ad4e2c5549")
    self.assertEqual(self.resolve()["mode"], "pinned")

  def test_changed_kernel_holds_with_first_reason(self):
    self.set_stock(mutate(self.stock, PAGE + 12))
    with self.assertRaisesRegex(ValueError, r"kernel changed since 19.8: 19.8: .*outside build identity"):
      self.resolve()

  def test_hash_failure_holds_for_upstream_and_base(self):
    for target in (self.manifest[0], self.pins["19.8"]["derived_from"]):
      key = "hash_raw" if target is self.manifest[0] else "boot_hash_raw"
      with self.subTest(key=key), patch.dict(target, {key: "0" * 64}):
        with self.assertRaisesRegex(ValueError, "boot download failed: .*mismatch"):
          self.resolve()

  def test_download_failure_holds(self):
    with self.assertRaisesRegex(ValueError, "upstream AGNOS 19.9 boot download failed: unavailable"):
      pins.resolve(lambda path: self.blob(None, None, path), self.pins, Mock(side_effect=OSError("unavailable")))

  def test_invalid_stock_holds(self):
    self.set_stock(b"truncated")
    with self.assertRaisesRegex(ValueError, "truncated Android boot header"):
      self.resolve()

  def test_cli_canonical_output_and_hold_diagnostics(self):
    (compose.ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=compose.ROOT / ".tmp") as directory:
      root = Path(directory)
      (root / "agnos").mkdir()
      (root / "agnos/pins.json").write_text(json.dumps(self.pins))
      shutil.copytree(compose.ROOT / "agnos/auto", root / "agnos/auto")
      shutil.copytree(compose.ROOT / "follow", root / "follow")
      output = root / "pin.json"
      with patch("pins.ROOT", root), patch("pins.resolve_commit", return_value="upstream"), patch("pins.fetch_boot", self.fetch):
        args = ["pins.py", "--repo", "unused.git", "--upstream", "upstream", "--out", str(output)]
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", args), redirect_stdout(stdout), redirect_stderr(stderr):
          self.assertEqual(pins.main(), 0)
        self.assertEqual(stdout.getvalue(), "PIN: OK: derived 19.9 from 19.8\n")
        self.assertIn("G8: WARN:", stderr.getvalue())
        stderr.seek(0)
        stderr.truncate()
        self.assertEqual(output.read_text(), json.dumps(json.loads(output.read_text()), sort_keys=True, indent=2) + "\n")
        output.unlink()
        self.set_stock(boot_image(sae=1))
        with patch("sys.argv", args), redirect_stdout(stdout), redirect_stderr(stderr):
          self.assertEqual(pins.main(), 1)
        self.assertTrue(stderr.getvalue().startswith("PIN: FAIL: partial SAE markers"))
        self.assertFalse(output.exists())


class TestPinValidation(unittest.TestCase):
  def setUp(self):
    self.pin = json.loads((compose.ROOT / "agnos/pins.json").read_text())["19.8"]

  def test_supplicant_is_optional(self):
    pins.validate_pin("19.8", self.pin)
    del self.pin["wpa_supplicant"]
    pins.validate_pin("19.8", self.pin)

  def test_supplicant_keys_and_object(self):
    for value in (None, [], "binary"):
      with self.subTest(value=value), self.assertRaisesRegex(ValueError, "must be an object"):
        pins.validate_pin("19.8", {**self.pin, "wpa_supplicant": value})
    for key in self.pin["wpa_supplicant"]:
      invalid = deepcopy(self.pin)
      del invalid["wpa_supplicant"][key]
      with self.subTest(key=key), self.assertRaisesRegex(ValueError, f"missing wpa_supplicant.{key}"):
        pins.validate_pin("19.8", invalid)
    self.pin["wpa_supplicant"]["extra"] = "unexpected"
    with self.assertRaisesRegex(ValueError, "unexpected wpa_supplicant keys"):
      pins.validate_pin("19.8", self.pin)

  def test_supplicant_digests(self):
    for key in ("sha256", "stock_sha256"):
      for value in ("", "a" * 63, "a" * 65, "z" * 64, "a" * 64 + "\n", None, 123):
        invalid = deepcopy(self.pin)
        invalid["wpa_supplicant"][key] = value
        with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, f"wpa_supplicant.{key}.*SHA-256"):
          pins.validate_pin("19.8", invalid)

  def test_supplicant_paths_stay_inside_repo(self):
    for key in ("path", "copyright"):
      for value in ("", ".", "/usr/sbin/wpa_supplicant", "../outside", "userspace/../../outside", "bad\0path", None, 123):
        invalid = deepcopy(self.pin)
        invalid["wpa_supplicant"][key] = value
        with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "relative files inside the repo"):
          pins.validate_pin("19.8", invalid)
    (compose.ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=compose.ROOT / ".tmp") as directory:
      link = Path(directory) / "escape"
      link.symlink_to("/private/tmp")
      for key in ("path", "copyright"):
        invalid = deepcopy(self.pin)
        invalid["wpa_supplicant"][key] = str((link / "outside").relative_to(compose.ROOT))
        with self.subTest(key=key), self.assertRaisesRegex(ValueError, "stay inside the repo"):
          pins.validate_pin("19.8", invalid)

class TestFollowResolver(unittest.TestCase):
  def setUp(self):
    import follow_state as fs
    from test_follow_state import automatic_pin
    self.state = fs.reserve_tags(fs.load(), 2)
    self.auto = automatic_pin(self.state)
    self.base, self.stock = identity_pair()
    self.source = b'# synthetic agnos implementation\n'
    origin = self.auto['derived_from']
    origin['boot_hash_raw'] = hashlib.sha256(self.base).hexdigest()
    origin['boot_url'] = f'https://commadist.azureedge.net/agnosupdate/boot-{origin["boot_hash_raw"]}.img.xz'
    origin['agnos_py_blob'] = pins.git_blob_id(self.source)
    self.system_hash = origin['system_hash_raw']
    self.state['pins'] = {'19.10': self.auto}
    self.state['manual'] = {}
    self.version = '19.10'
    self.calls = []
    self.warnings = []

  def reader(self, path):
    if path == 'launch_env.sh':
      return f'if [ -z "$AGNOS_VERSION" ]; then\n  export AGNOS_VERSION="{self.version}"\nfi\n'.encode()
    if path == compose.AGNOS_PY:
      return self.source
    if path == compose.MANIFEST:
      digest = hashlib.sha256(self.stock).hexdigest()
      return json.dumps([{'name': 'boot', 'url': f'https://commadist.azureedge.net/agnosupdate/boot-{digest}.img.xz',
                          'hash_raw': digest, 'size': len(self.stock)}, {'name': 'system', 'hash_raw': self.system_hash}]).encode()
    raise AssertionError(path)

  def fetch(self, url, digest, size):
    self.calls.append(url)
    data = self.base if url == self.auto['derived_from']['boot_url'] else self.stock
    self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
    if size is not None:
      self.assertEqual(len(data), size)
    return data

  def resolve(self, mode='off', branch='nightly'):
    return pins.resolve(self.reader, self.state['manual'], self.fetch, state=self.state, mode=mode, branch=branch,
                        warn=self.warnings.append)

  def test_withdrawn_direct_and_derived_never_wait_for_probe_wpa_or_attempt(self):
    import follow_state as fs
    from test_follow_state import attempt, withdrawal
    self.auto['withdrawn'] = withdrawal()
    self.state['status']['paused'] = withdrawal()
    self.state['status']['attempts'][hashlib.sha256(self.stock).hexdigest()] = attempt()
    # Exercise both an absent probe and a known stock binary with no override.
    for missing in ('probe', 'wpa'):
      self.state[{'probe': 'system_probe', 'wpa': 'supplicants'}[missing]] = {}
      for mode in fs.MODES:
        for version in ('19.10', '19.11'):
          for branch in (*fs.BRANCHES, 'unlisted'):
            with self.subTest(mode=mode, version=version, missing=missing, branch=branch):
              self.version = version
              resolved = self.resolve(mode, branch)
              self.assertEqual(resolved['mode'], 'pinned' if version == '19.10' else 'derived')
              self.assertEqual(resolved['pin']['boot'], self.auto['revert']['boot'])
              self.assertEqual(resolved['pin']['tag'], self.auto['revert']['tag'])
              self.assertIn('G8: WARN:', self.warnings[-1])
      self.state['system_probe'] = fs.load()['system_probe']

  def test_withdrawn_derived_base_precedes_unrelated_newer_download(self):
    from test_follow_state import withdrawal
    self.auto['withdrawn'] = withdrawal()
    newer = deepcopy(pins.load()['manual']['19.9'])
    newer['derived_from']['boot_url'] = 'https://example.invalid/unavailable.img.xz'
    self.state['manual'] = {'20.0': newer}
    self.version = '19.11'
    resolved = self.resolve('off')
    self.assertEqual(resolved['base'], '19.10')
    self.assertEqual(resolved['pin']['boot'], self.auto['revert']['boot'])
    self.assertNotIn(newer['derived_from']['boot_url'], self.calls)

  def test_manual_fix_overrides_withdrawn_derived_base(self):
    from test_follow_state import withdrawal
    self.auto['withdrawn'] = withdrawal()
    fixed = deepcopy(self.auto)
    for key in ('auto', 'revert', 'withdrawn'):
      del fixed[key]
    fixed['tag'] = 'wpa3.sae=6'
    fixed['release_tag'] = 'agnos-19.10-wpa3.6'
    fixed['boot'].update(hash='6' * 64, hash_raw='6' * 64)
    self.state['manual'] = {'19.10': fixed}
    self.version = '19.11'
    for mode in ('off', 'dryrun', 'state', 'on'):
      resolved = self.resolve(mode)
      self.assertEqual(resolved['base'], '19.10')
      self.assertEqual(resolved['pin']['boot'], fixed['boot'])
      self.assertNotIn('auto', resolved['pin'])

  def test_live_auto_ignored_until_on_then_all_four_adopt(self):
    from follow_state import BRANCHES, FollowNeeded
    for mode in ('off', 'dryrun', 'state'):
      with self.assertRaises(FollowNeeded) as caught:
        self.resolve(mode)
      self.assertEqual(caught.exception.kind, 'kernel')
    for branch in BRANCHES:
      resolved = self.resolve('on', branch)
      self.assertEqual(resolved['pin']['boot'], self.auto['boot'])
      self.assertIn('wpa_supplicant', resolved['pin'])
    with self.assertRaises(FollowNeeded):
      self.resolve('on', 'unlisted')

  def use_manual(self):
    self.state['manual'] = deepcopy(pins.load()['manual'])
    self.state['pins'] = {}
    self.version = '19.9'
    self.system_hash = self.state['manual'][self.version]['derived_from']['system_hash_raw']

  def test_probe_and_wpa_not_raised_off_dryrun_json_unchanged(self):
    self.use_manual()
    expected = {'mode': 'pinned', 'version': '19.9', 'pin': self.state['manual']['19.9']}
    for mode in ('off', 'dryrun'):
      for field in ('system_probe', 'supplicants'):
        with patch.dict(self.state, {field: {}}):
          self.assertEqual(self.resolve(mode), expected)
          self.assertTrue(self.warnings[-1].startswith('G8: WARN:'))
    self.assertEqual(self.calls, [])

  def test_g8_explicit_manual_mismatch_and_probe_pending(self):
    from follow_state import FollowNeeded
    self.use_manual()
    for mode in ('state', 'on'):
      with patch.dict(self.state, {'system_probe': {}}):
        with self.assertRaises(FollowNeeded) as caught:
          self.resolve(mode)
        self.assertEqual(caught.exception.kind, 'probe')
        self.assertEqual(caught.exception.key, self.system_hash)
      self.state['manual']['19.9']['wpa_supplicant']['sha256'] = '0' * 64
      with self.assertRaisesRegex(ValueError, 'explicit wpa_supplicant differs'):
        self.resolve(mode)

  def test_known_supplicant_resolves_independently_from_base_in_enforced_modes(self):
    self.version = '19.11'
    resolved = self.resolve('on')
    self.assertEqual(resolved['base'], '19.10')
    self.assertIn('wpa_supplicant', resolved['pin'])
    # A manual base's override must not be copied blindly to a new system.
    manual = deepcopy(self.auto)
    for key in ('auto', 'revert', 'withdrawn'):
      del manual[key]
    manual['wpa_supplicant'] = deepcopy(pins.load()['manual']['19.9']['wpa_supplicant'])
    manual['wpa_supplicant']['stock_sha256'] = '1' * 64
    self.state['manual'] = {'19.10': manual}
    self.state['pins'] = {}
    self.assertEqual(self.resolve('off')['pin']['wpa_supplicant'], manual['wpa_supplicant'])
    for mode in ('state', 'on'):
      self.assertNotEqual(self.resolve(mode)['pin']['wpa_supplicant'], manual['wpa_supplicant'])

  def test_unknown_stock_policy_and_stage_b(self):
    from follow_state import FollowNeeded
    self.use_manual()
    probe = self.state['system_probe'][self.system_hash]
    probe['stock_wpa_sha256'] = '9' * 64
    for mode in ('state', 'on'):
      with self.assertRaises(FollowNeeded) as caught:
        self.resolve(mode)
      self.assertEqual(caught.exception.kind, 'wpa')
    self.state['policy']['on_unknown_stock_wpa'] = 'stock'
    for mode in ('state', 'on'):
      self.assertNotIn('wpa_supplicant', self.resolve(mode)['pin'])
    self.state['policy']['wpa']['auto_publish'] = True
    reference = self.state['policy']['wpa']['reference_stock_sha256']
    self.state['supplicants'][reference]['ci_reproduced_reference'] = True
    with self.assertRaises(FollowNeeded):
      self.resolve('on')
    self.assertNotIn('wpa_supplicant', self.resolve('state')['pin'])

  def test_native_agnos_requires_qualification_and_known_stock_needs_no_base(self):
    self.state['pins'] = {}
    self.stock = boot_image(sae=4, rsnxe=True)
    for mode in ('state', 'on'):
      resolved = self.resolve(mode)
      self.assertEqual(resolved['mode'], 'native')
      self.assertNotIn('base', resolved)
      self.assertIn('wpa_supplicant', resolved)
    self.state['system_probe'][self.system_hash]['dpkg_version'] += '+agnos1'
    for mode in ('state', 'on'):
      with self.assertRaisesRegex(ValueError, 'runtime qualification'):
        self.resolve(mode)
    for mode in ('off', 'dryrun'):
      self.assertEqual(self.resolve(mode), {'mode': 'native', 'version': '19.10'})

  def test_state_validation_precedes_reader_and_fetch_even_in_off(self):
    self.state['pins']['19.10']['auto']['published_at'] = 'not a date'
    with patch.object(self, 'reader') as reader, patch.object(self, 'fetch') as fetch:
      with self.assertRaises(ValueError):
        self.resolve()
      reader.assert_not_called()
      fetch.assert_not_called()


class TestFollowCLI(unittest.TestCase):
  def setUp(self):
    import follow_state as fs
    self.state = fs.load()
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.out = Path(self.temp.name) / 'pin.json'

  def cli(self, needed, mode, *, state=None):
    args = ['pins.py', '--repo', 'unused.git', '--upstream', 'upstream', '--out', str(self.out), '--follow-mode', mode]
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch('sys.argv', args), patch('pins.load', return_value=state or self.state), patch('pins.resolve_commit', return_value='upstream'):
      with patch('pins.resolve', side_effect=needed), redirect_stdout(stdout), redirect_stderr(stderr):
        rc = pins.main()
    self.assertFalse(self.out.exists())
    return rc, stdout.getvalue(), stderr.getvalue()

  def test_every_mode_kind_cell_and_stage_b_policy(self):
    import follow_state as fs
    # G8's off/dryrun cells are exercised through the real resolver above.
    for mode in fs.MODES:
      for kind in ('kernel', 'probe', 'wpa'):
        for enabled in (False, True):
          for unknown in ('hold', 'stock'):
            state = deepcopy(self.state)
            state['policy']['wpa']['auto_publish'] = enabled
            state['policy']['on_unknown_stock_wpa'] = unknown
            needed = fs.FollowNeeded(kind, 'a' * 64, 'needs follow')
            if kind == 'kernel':
              expected = 3 if mode == 'on' else 1
            elif mode in ('off', 'dryrun'):
              expected = 0
            elif kind == 'probe' or (mode == 'on' and enabled):
              expected = 3
            else:
              expected = 0 if unknown == 'stock' else 1
            with self.subTest(mode=mode, kind=kind, enabled=enabled, unknown=unknown):
              self.assertEqual(fs.follow_exit(needed, mode, state['policy'], state['status']), expected)
              if expected:
                rc, stdout, stderr = self.cli(needed, mode, state=state)
                self.assertEqual(rc, expected)
                self.assertEqual(stdout, '')
                self.assertTrue(stderr.startswith('PIN: FOLLOW:' if expected == 3 else 'PIN: FAIL:'))
                if expected == 3:
                  self.assertIn(f'{kind} {needed.key} needs follow', stderr)

  def test_only_recorded_kernel_attempt_holds_escalate_without_time_policy(self):
    import follow_state as fs
    from test_follow_state import attempt
    needed = fs.FollowNeeded('kernel', 'a' * 64, 'kernel changed')
    for result in ('held', 'risk_held', 'deferred', 'error', 'published'):
      self.state['status']['attempts'][needed.key] = attempt(result)
      rc, _, stderr = self.cli(needed, 'on')
      self.assertEqual(rc, 1 if result in ('held', 'risk_held') else 3)
      if rc == 1:
        self.assertIn('PIN: FAIL: K4: risky driver change', stderr)
        self.assertIn(f'PIN: KEY: kernel {needed.key}', stderr)
    self.state['status']['attempts'] = {}
    self.state['status']['wpa_attempts'][needed.key] = attempt()
    self.assertEqual(self.cli(needed, 'on')[0], 3)

  def test_validate_state_cli_and_unknown_mode(self):
    for mode, expected in (('off', 0), ('canary', 1), ('ON', 1), ('', 1)):
      stdout, stderr = io.StringIO(), io.StringIO()
      with patch('sys.argv', ['pins.py', '--validate-state', '--follow-mode', mode]), redirect_stdout(stdout), redirect_stderr(stderr):
        self.assertEqual(pins.main(), expected)
      self.assertIn('PIN: OK: state valid' if expected == 0 else 'PIN: FAIL:', stdout.getvalue() + stderr.getvalue())

  def test_missing_or_malformed_state_cli_is_hold_in_every_mode(self):
    for mode in ('off', 'dryrun', 'state', 'on'):
      stdout, stderr = io.StringIO(), io.StringIO()
      with patch('sys.argv', ['pins.py', '--validate-state', '--follow-mode', mode]), patch('pins.ROOT', Path(self.temp.name)):
        with redirect_stdout(stdout), redirect_stderr(stderr):
          self.assertEqual(pins.main(), 1)
      self.assertTrue(stderr.getvalue().startswith('PIN: FAIL:'))


if __name__ == "__main__":
  unittest.main()
