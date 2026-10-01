#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import bootimg
from boot_fixture import PAGE, boot_image, mutate
import kernel_equiv as ke


class TestBootimg(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.work = tempfile.TemporaryDirectory(prefix="test-bootimg-")
    cls.addClassCleanup(cls.work.cleanup)
    cls.key = Path(cls.work.name) / "key.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                    "-out", str(cls.key)], check=True, capture_output=True)
    cls.public = subprocess.run(["openssl", "rsa", "-in", str(cls.key), "-pubout"],
                                check=True, capture_output=True).stdout
    cls.fixture = boot_image()
    cls.fields = bootimg.parse(cls.fixture)
    cls.boot = bootimg.repack(cls.fixture, cls.fields["kernel"], cls.fields["cmdline"], cls.key)

  def test_repack_round_trip_and_header_fields(self):
    fields = bootimg.parse(self.boot)
    self.assertTrue(bootimg.selftest(self.boot, self.key))
    self.assertFalse(bootimg.selftest(self.fixture, self.key))
    self.assertEqual(fields["kernel"], self.fields["kernel"])
    self.assertEqual(fields["cmdline"], "console=tty0")
    self.assertEqual(fields["kernel_addr"], 0x80008000)
    self.assertEqual(fields["header_version"], 0)
    self.assertEqual(fields["signature"][256:], bytes(2048 - 256))
    self.assertEqual(len(fields["signature"]), 2048)
    self.assertEqual(self.fields["signature"], b"")
    expected = hashlib.sha1()
    for payload in (fields["kernel"], b"", b""):
      expected.update(payload)
      expected.update(struct.pack("<I", len(payload)))
    self.assertEqual(fields["id"], expected.digest() + bytes(12))
    for key in bootimg.FIELDS:
      self.assertEqual(fields[key], self.fields[key])
    self.assertEqual(self.boot[1632:PAGE], bytes(PAGE - 1632))
    end = PAGE + fields["kernel_size"]
    self.assertEqual(self.boot[end:-2048], bytes(-fields["kernel_size"] % PAGE))

  def test_repack_preserves_template_and_changes_kernel(self):
    header = bytearray(self.fields["header"])
    header[48:64] = b"test-board".ljust(16, b"\0")
    struct.pack_into("<I", header, 44, 0x12345678)
    image, chain = ke.split_kernel(self.fields["kernel"])
    kernel = image + chain + ke.dtb_blobs(chain)[0]
    raw = bootimg.repack(bytes(header), kernel, "new=cmdline", self.key)
    fields = bootimg.parse(raw)
    self.assertEqual(fields["kernel_size"], len(kernel))
    self.assertEqual(fields["kernel"], kernel)
    self.assertEqual(fields["cmdline"], "new=cmdline")
    for start, end in ((0, 8), (12, 64), (608, 1632)):
      self.assertEqual(raw[start:end], header[start:end])
    self.assertTrue(bootimg.verify(raw, self.public))
    self.assertTrue(bootimg.selftest(raw, self.key))

  def test_repack_rejects_unsupported_headers(self):
    for offset, value in ((40, 1), (40, 2), (16, 1), (24, 1), (36, 2048), (36, 8192), (36, 0)):
      header = bytearray(self.fields["header"])
      struct.pack_into("<I", header, offset, value)
      with self.subTest(offset=offset, value=value):
        with self.assertRaises(ValueError):
          bootimg.repack(bytes(header), self.fields["kernel"], "x", self.key)
    for header in (b"", self.fields["header"][:100], mutate(self.fields["header"], 0),
                   mutate(self.fields["header"], 608)):
      with self.assertRaises(ValueError):
        bootimg.repack(header, self.fields["kernel"], "x", self.key)

  def test_repack_cmdline_byte_limit_and_nuls(self):
    for cmdline in ("x" * 512, "é" * 256, b"x\0y"):
      with self.subTest(length=len(cmdline)):
        with self.assertRaises(ValueError):
          bootimg.repack(self.fixture, self.fields["kernel"], cmdline, self.key)
    for cmdline in ("x" * 511, "é" * 255 + "x", ""):
      raw = bootimg.repack(self.fixture, self.fields["kernel"], cmdline, self.key)
      self.assertEqual(bootimg.parse(raw)["cmdline"], cmdline)
      self.assertTrue(bootimg.verify(raw, self.public))

  def test_repack_rejects_invalid_fdt_tails(self):
    kernel = self.fields["kernel"]
    image, chain = ke.split_kernel(kernel)
    bad_chain = bytearray(chain)
    struct.pack_into(">I", bad_chain, len(bad_chain) - 64 + 4, 0)
    for invalid in (b"", image, kernel[:-1], kernel + b"\0", image + bytes(bad_chain)):
      with self.subTest(length=len(invalid)):
        with self.assertRaises(ValueError):
          bootimg.repack(self.fixture, invalid, "x", self.key)

  def test_parse_rejects_truncation_and_extra_data(self):
    for invalid in (b"", self.boot[:40], self.boot[:PAGE], self.boot[:PAGE + 64],
                    self.boot[:-1], self.boot + b"\0", self.fixture[:-1]):
      with self.subTest(length=len(invalid)):
        with self.assertRaises(ValueError):
          bootimg.parse(invalid)
        self.assertFalse(bootimg.verify(invalid, self.public))
    self.assertFalse(bootimg.verify(self.fixture, self.public))

  def test_signature_verification_and_tampering(self):
    self.assertTrue(bootimg.verify(self.boot, self.public))
    for offset in (64, 576, PAGE + 12, PAGE + self.fields["kernel_size"],
                   len(self.boot) - 2048, len(self.boot) - 1):
      with self.subTest(offset=offset):
        self.assertFalse(bootimg.verify(mutate(self.boot, offset), self.public))
    self.assertFalse(bootimg.verify(self.boot, b"not a key"))
    other = Path(self.work.name) / "other.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
                    "-out", str(other)], check=True, capture_output=True)
    public = subprocess.run(["openssl", "rsa", "-in", str(other), "-pubout"],
                            check=True, capture_output=True).stdout
    self.assertFalse(bootimg.verify(self.boot, public))

  def test_pubkey_hash_is_spki_pem(self):
    self.assertEqual(bootimg.pubkey_sha256(self.public), hashlib.sha256(self.public).hexdigest())
    with self.assertRaises(ValueError):
      bootimg.pubkey_sha256(b"invalid")

  def test_ondevice_hash_padding(self):
    for size in (0, 1, 4095, 4096, 4097, 6144):
      raw = b"X" * size
      padded = raw.ljust(((size + 4095) // 4096) * 4096, b"\0")
      self.assertEqual(bootimg.ondevice_hash(raw), hashlib.sha256(padded).hexdigest())

  def test_with_tag_preserves_kernel_and_other_cmdline_tokens(self):
    tagged = bootimg.with_tag(self.boot, "wpa3.sae=2", self.key)
    fields = bootimg.parse(tagged)
    self.assertEqual(fields["cmdline"], "console=tty0 wpa3.sae=2")
    self.assertEqual(fields["kernel"], self.fields["kernel"])
    self.assertEqual(fields["id"], bootimg.parse(self.boot)["id"])
    self.assertTrue(bootimg.verify(tagged, self.public))
    self.assertEqual(bootimg.with_tag(tagged, "wpa3.sae=2", self.key), tagged)
    self.assertEqual(bootimg.parse(bootimg.with_tag(tagged, "wpa3.sae=10", self.key))["cmdline"],
                     "console=tty0 wpa3.sae=10")
    spaced = bootimg.repack(self.fixture, self.fields["kernel"], "a=1  wpa3.sae=2  b=3", self.key)
    self.assertEqual(bootimg.parse(bootimg.with_tag(spaced, "wpa3.sae=3", self.key))["cmdline"],
                     "a=1  wpa3.sae=3  b=3")
    duplicate = bootimg.repack(self.fixture, self.fields["kernel"], "wpa3.sae=1 wpa3.sae=2", self.key)
    with self.assertRaises(ValueError):
      bootimg.with_tag(duplicate, "wpa3.sae=3", self.key)
    for bad in ("2", "wpa3.sae=0", "wpa3.sae=-1", "wpa3.sae=2 extra=1", "wpa3.sae=3\n"):
      with self.assertRaises(ValueError):
        bootimg.with_tag(self.boot, bad, self.key)

  def test_cli(self):
    script = Path(__file__).with_name("bootimg.py")
    with tempfile.TemporaryDirectory() as work:
      boot, public, out = (Path(work) / name for name in ("boot.img", "public.pem", "tagged.img"))
      boot.write_bytes(self.boot)
      public.write_bytes(self.public)
      cases = (
        (["selftest", str(boot), "--key", str(self.key)], "IDENTICAL"),
        (["verify", str(boot), "--pubkey", str(public)], "VERIFIED"),
        (["tag", str(boot), "--tag", "wpa3.sae=3", "--key", str(self.key), "--out", str(out)], "TAGGED"),
      )
      for args, prefix in cases:
        result = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith(prefix), result.stdout)
      self.assertEqual(boot.read_bytes(), self.boot)
      self.assertTrue(bootimg.verify(out.read_bytes(), self.public))
      boot.write_bytes(mutate(self.boot, PAGE + 12))
      for args, prefix in ((cases[0][0], "DIFFERENT"), (cases[1][0], "INVALID")):
        result = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue(result.stdout.startswith(prefix), result.stdout)
      boot.write_bytes(b"broken")
      result = subprocess.run([sys.executable, str(script), *cases[0][0]], capture_output=True, text=True)
      self.assertEqual(result.returncode, 1)
      self.assertTrue(result.stderr.startswith("FAIL:"), result.stderr)


@unittest.skipUnless(Path("/Volumes/agnos").is_dir(), "/Volumes/agnos is not mounted")
class TestMountedBootimg(unittest.TestCase):
  root = Path("/Volumes/agnos")
  paths = ("ref199/boot-b9c9b926.img", "ref199/boot-335c1757.img",
           "boot199/boot-wpa3-sae-h2e-19.9-tag3.img", "bootH2E/boot-wpa3-sae-h2e-19.8-tag2.img")

  def test_four_identical_repacks_signatures_and_layouts(self):
    key = self.root / "agnos-builder-199/vble-qti.key"
    public = subprocess.run(["openssl", "rsa", "-in", str(key), "-pubout"],
                            check=True, capture_output=True).stdout
    self.assertEqual(bootimg.pubkey_sha256(public),
                     "544dace4ea7d5abc07780b02a4355ad82d0a07cf149ffe82e86a07b12fd5414e")
    for name in self.paths:
      with self.subTest(name=name):
        raw = self.root.joinpath(name).read_bytes()
        self.assertTrue(bootimg.selftest(raw, key))
        self.assertTrue(bootimg.verify(raw, public))
        layout = ke.image_layout(ke.split(raw)[1])
        self.assertEqual((layout["header_offset"], layout["text_offset"], layout["flags"]), (20, 0x80000, 0xa))

  def test_manual_pin_ondevice_hashes(self):
    pins = json.loads(Path(__file__).resolve().parents[1].joinpath("agnos/pins.json").read_text())
    for version, name in (("19.9", self.paths[2]), ("19.8", self.paths[3])):
      with self.subTest(version=version):
        raw = self.root.joinpath(name).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), pins[version]["boot"]["hash_raw"])
        self.assertEqual(bootimg.ondevice_hash(raw), pins[version]["boot"]["ondevice_hash"])


if __name__ == "__main__":
  unittest.main()
