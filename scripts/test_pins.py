#!/usr/bin/env python3
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
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
    self.agnos_py = "a" * 40
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
    patch("pins.git", side_effect=lambda *args: (self.agnos_py + "\n").encode()).start()

  def blob(self, repo, upstream, path):
    if path == "launch_env.sh":
      return f'export AGNOS_VERSION="{self.version}"\n'.encode()
    if path == compose.MANIFEST:
      return json.dumps(self.manifest).encode()
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
    return pins.resolve("unused.git", "upstream", self.pins, self.fetch)

  def test_pinned_has_no_downloads(self):
    self.version = "19.8"
    self.manifest = None  # Neither manifest nor agnos.py is needed for resolution.
    self.assertEqual(self.resolve(), {"mode": "pinned", "version": "19.8", "pin": self.pins["19.8"]})
    self.assertEqual(self.calls, [])
    pins.git.assert_not_called()

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
    pins.git.assert_not_called()

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
    pins.git.assert_not_called()

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
      pins.resolve("unused.git", "upstream", self.pins, Mock(side_effect=OSError("unavailable")))

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
      output = root / "pin.json"
      with patch("pins.ROOT", root), patch("pins.resolve_commit", return_value="upstream"), patch("pins.fetch_boot", self.fetch):
        args = ["pins.py", "--repo", "unused.git", "--upstream", "upstream", "--out", str(output)]
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("sys.argv", args), redirect_stdout(stdout), redirect_stderr(stderr):
          self.assertEqual(pins.main(), 0)
        self.assertEqual(stdout.getvalue(), "PIN: OK: derived 19.9 from 19.8\n")
        self.assertEqual(stderr.getvalue(), "")
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


if __name__ == "__main__":
  unittest.main()
