#!/usr/bin/env python3
from itertools import combinations
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from boot_fixture import BANNER, CERT, CONFIG, IMAGE_SIZE, INITRAMFS, NOTE, PAGE, SYMBOL, UTS, boot_image, identity_pair, mutate
import kernel_equiv as ke


class TestKernelEquiv(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.base, cls.new = identity_pair()

  def test_identity_only_with_date_and_initramfs_length_changes(self):
    image_a = ke.split(self.base)[1]
    image_b = ke.split(self.new)[1]
    self.assertEqual(ke.initramfs(image_b)[1], ke.initramfs(image_a)[1] + 1)
    self.assertTrue(ke.equivalent(self.base, self.new)[0], ke.equivalent(self.base, self.new)[1])
    self.assertTrue(ke.equivalent(self.new, self.base)[0])
    self.assertTrue(ke.equivalent(self.base, self.base)[0])

  def test_mutations_fail_closed(self):
    image = ke.split(self.base)[1]
    ram_size = ke.initramfs(image)[1]
    banner_end = image.index(b"\n", BANNER) + 1
    for name, offset in (
      ("code", PAGE + 12), ("cmdline", 64), ("DTB", PAGE + IMAGE_SIZE + 60),
      ("after banner", PAGE + banner_end), ("next to pointer", PAGE + SYMBOL + 4),
      ("wrong pointer", PAGE + SYMBOL), ("after initramfs span", PAGE + INITRAMFS + ram_size + 32),
      ("corrupt ikconfig", PAGE + CONFIG + 8),
      ("corrupt initramfs", PAGE + INITRAMFS + ram_size - 5),
    ):
      with self.subTest(name=name):
        same, reasons = ke.equivalent(self.base, mutate(self.base, offset))
        self.assertFalse(same)
        self.assertTrue(reasons)
    same, reasons = ke.equivalent(self.base, boot_image(config=b"CONFIG_TEST=n\n"))
    self.assertFalse(same)
    self.assertIn("kernel config differs", reasons)

  def test_cert_and_buildid_mutations_are_identity(self):
    for offset in (PAGE + NOTE + len(ke.BUILD_ID), PAGE + CERT + 150):
      with self.subTest(offset=offset):
        self.assertTrue(ke.equivalent(self.base, mutate(self.base, offset))[0])

  def test_invalid_headers_and_fdt_chains(self):
    variants = [b"", self.base[:32], self.base[:PAGE + IMAGE_SIZE + 50]]
    for offset, value in ((36, 0), (8, len(self.base)), (40, 1)):
      changed = bytearray(self.base)
      struct.pack_into("<I", changed, offset, value)
      variants.append(bytes(changed))
    # Zero totalsize must not loop, oversize/truncated chains must not pass.
    for size in (0, 8, 65, 10000):
      changed = bytearray(self.base)
      struct.pack_into(">I", changed, PAGE + IMAGE_SIZE + 64 + 4, size)
      variants.append(bytes(changed))
    for boot in variants:
      with self.subTest(length=len(boot)):
        same, reasons = ke.equivalent(self.base, boot)
        self.assertFalse(same)
        self.assertTrue(reasons)

  def test_bad_ikconfig_even_in_both_images_is_rejected(self):
    broken = mutate(self.base, PAGE + CONFIG + 8)
    same, reasons = ke.equivalent(broken, broken)
    self.assertFalse(same)
    self.assertIn("boot parse failed", reasons[0])

  def test_identity_markers_cannot_authorize_new_masks(self):
    image = ke.split(self.base)[1]
    cert_start, cert_end = ke.cert_spans(image)[0]
    banner_end = image.index(b"\n", BANNER)
    cases = (
      ("stray DER header before certificate", [(CERT - 40, b"\x30\x82\xff\xff"), (cert_end + 256, b"evil")]),
      ("stray DER header alone", [(CERT - 40, b"\x30\x82\xff\xff")]),
      ("fake cert marker", [(8000, b"\x30\x82\x01\x00" + bytes(16) + ke.CERT_MARKER)]),
      ("fake well-formed certificate", [(8000, image[cert_start:cert_end])]),
      ("fake GNU build-id", [(8000, ke.BUILD_ID + b"x" * 20)]),
      ("fake banner", [(8000, b"Linux version evil\n")]),
      ("fake UTS", [(8000, b"#1 SMP PREEMPT evil\0")]),
      ("removed banner terminator", [(banner_end, b"X" * 18)]),
      ("changed banner terminator kind", [(banner_end, b"X")]),
      ("overlong banner", [(BANNER, b"Linux version " + b"X" * 256 + b"\n")]),
      ("overlong UTS", [(UTS, b"#1 SMP PREEMPT " + b"X" * 256 + b"\0")]),
    )
    for name, edits in cases:
      with self.subTest(name=name):
        changed = bytearray(self.base)
        for offset, data in edits:
          changed[PAGE + offset:PAGE + offset + len(data)] = data
        for base, new in ((self.base, bytes(changed)), (bytes(changed), self.base)):
          same, reasons = ke.equivalent(base, new)
          self.assertFalse(same, reasons)

  def test_cert_shape_and_length_must_match(self):
    image = ke.split(self.base)[1]
    start, end = ke.cert_spans(image)[0]
    for offset, value in ((start + 4, 0x31), (end - 67, 0x04)):
      changed = bytearray(self.base)
      changed[PAGE + offset] = value
      same, reasons = ke.equivalent(self.base, bytes(changed))
      self.assertFalse(same, reasons)
    changed = bytearray(self.base)
    # Extend the signatureValue by one byte and update both lengths: valid DER,
    # but the certificate's exact span is no longer the same as the base.
    changed[PAGE + end] = 0
    changed[PAGE + end - 66] += 1
    struct.pack_into(">H", changed, PAGE + start + 2, end - start - 4 + 1)
    same, reasons = ke.equivalent(self.base, bytes(changed))
    self.assertFalse(same)
    self.assertIn("cert identity span ends differ", reasons)

  def test_initramfs_non_mtime_content_change(self):
    raw = bytearray(ke.initramfs(ke.split(self.base)[1])[2])
    raw[14:22] = b"000041ff"  # Valid newc, different c_mode.
    same, reasons = ke.equivalent(self.base, boot_image(cpio=bytes(raw)))
    self.assertFalse(same)
    self.assertIn("initramfs content differs", reasons)

  def test_initramfs_gzip_headers_cannot_expand_mask_over_data(self):
    image = ke.split(self.base)[1]
    offset, size, raw = ke.initramfs(image)
    member = image[offset:offset + size]
    target = offset + size + 64  # Beyond the former 32-byte slack allowance.
    for flag in (8, 4):  # FNAME and FEXTRA both preserve the decompressed cpio.
      with self.subTest(flag=flag):
        header = bytearray(member[:10])
        header[3] = flag
        if flag == 8:
          extra = b"X" * 256 + b"\0"
        else:
          payload = bytearray(image[offset + 12:offset + 12 + 256])
          payload[target - offset - 12] ^= 1
          extra = struct.pack("<H", len(payload)) + payload
        stretched = bytes(header) + extra + member[10:]
        changed = bytearray(self.base)
        changed[PAGE + offset:PAGE + offset + len(stretched)] = stretched
        end = offset + len(stretched)
        word = (end + 3) & ~3
        changed[PAGE + end:PAGE + word] = bytes(word - end)
        struct.pack_into("<Q", changed, PAGE + word, len(stretched))
        self.assertNotEqual(changed[PAGE + target], self.base[PAGE + target])
        self.assertEqual(ke.initramfs(ke.split(changed)[1])[2], raw)
        for base, new in ((self.base, bytes(changed)), (bytes(changed), self.base)):
          same, reasons = ke.equivalent(base, new)
          self.assertFalse(same)
          self.assertIn("initramfs compressed length delta too large", reasons)

  def test_initramfs_flags_and_size_word_slot(self):
    image = ke.split(self.base)[1]
    offset, size, raw = ke.initramfs(image)
    member = image[offset:offset + size]

    def with_header(flag, extra):
      header = bytearray(member[:10])
      header[3] = flag
      rebuilt = bytes(header) + extra + member[10:]
      end = offset + len(rebuilt)
      word = (end + 3) & ~3
      changed = bytearray(self.base)
      changed[PAGE + offset:PAGE + word + 8] = rebuilt + bytes(word - end) + struct.pack("<Q", len(rebuilt))
      struct.pack_into("<I", changed, PAGE + SYMBOL, end - 0x14)
      self.assertEqual(ke.initramfs(ke.split(changed)[1])[2], raw)
      return bytes(changed)

    # Equal-length optional fields keep the size slot fixed, isolating the FLG
    # check from the separate slot-movement check. Only FNAME is kernel-parsable.
    fname = with_header(0x08, b"x\0")
    cases = (
      ("FEXTRA", fname, with_header(0x04, b"\0\0"), "initramfs gzip flags the kernel cannot parse"),
      ("FCOMMENT", fname, with_header(0x10, b"x\0"), "initramfs gzip flags the kernel cannot parse"),
      ("FNAME moves size word", self.base, with_header(0x08, b"abc\0"), "__initramfs_size word moved"),
    )
    for name, base, new, reason in cases:
      with self.subTest(name=name):
        for first, second in ((base, new), (new, base)):
          same, reasons = ke.equivalent(first, second)
          self.assertFalse(same)
          self.assertIn(reason, reasons)

  def test_initramfs_size_word_must_match_member(self):
    offset, size, _ = ke.initramfs(ke.split(self.base)[1])
    word = (offset + size + 3) & ~3
    for value in (0, 0x10000):
      with self.subTest(value=value):
        changed = bytearray(self.base)
        struct.pack_into("<Q", changed, PAGE + word, value)
        same, reasons = ke.equivalent(self.base, bytes(changed))
        self.assertFalse(same)
        self.assertIn("__initramfs_size word or alignment padding invalid", reasons)

  def test_initramfs_padding_and_former_slack_are_checked(self):
    for boot in (self.base, self.new):
      offset, size, _ = ke.initramfs(ke.split(boot)[1])
      end = offset + size
      word = (end + 3) & ~3
      for pos in range(end, end + 32):
        if word <= pos < word + 8:
          continue
        with self.subTest(size=size, pos=pos):
          same, reasons = ke.equivalent(boot, mutate(boot, PAGE + pos))
          self.assertFalse(same, reasons)
          if pos < word:
            self.assertIn("__initramfs_size word or alignment padding invalid", reasons)

  def test_build_strings_may_only_grow_into_nul_padding(self):
    image = ke.split(self.base)[1]
    for prefix, start in ((b"Linux version ", BANNER), (b"#1 SMP PREEMPT ", UTS)):
      end = next(end for offset, end in ke.cstr_spans(image, prefix) if offset == start)
      base = bytearray(self.base)
      base[PAGE + end + 6:PAGE + end + 6 + 16] = b"neighbor-string\0"
      for growth in (6, 7, 15):
        with self.subTest(prefix=prefix, growth=growth):
          changed = bytearray(base)
          changed[PAGE + end - 1:PAGE + end + growth] = b"X" * growth + image[end - 1:end]
          for first, second in ((base, changed), (changed, base)):
            same, reasons = ke.equivalent(bytes(first), bytes(second))
            self.assertEqual(same, growth == 6, reasons)

  def test_added_initramfs_member_is_not_identity(self):
    image = ke.split(self.base)[1]
    offset, size, _ = ke.initramfs(image)
    for target in (3000, 8000):
      with self.subTest(target=target):
        changed = bytearray(self.base)
        changed[PAGE + target:PAGE + target + size] = image[offset:offset + size]
        same, reasons = ke.equivalent(self.base, bytes(changed))
        self.assertFalse(same)
        self.assertIn("initramfs identity span starts differ", reasons)

  def test_only_one_pointer_word_may_track_initramfs(self):
    changed = []
    for boot in (self.base, self.new):
      offset, size, _ = ke.initramfs(ke.split(boot)[1])
      data = bytearray(boot)
      struct.pack_into("<I", data, PAGE + 8000, offset + size - 0x14)
      changed.append(bytes(data))
    for base, new in (changed, changed[::-1]):
      same, reasons = ke.equivalent(base, new)
      self.assertFalse(same)
      self.assertIn("outside build identity", reasons[-1])

  def test_differing_run_crosses_pointer_word_boundary(self):
    changed = bytearray(self.new)
    changed[PAGE + SYMBOL:PAGE + SYMBOL + 5] = b"\xf0" * 5
    same, reasons = ke.equivalent(self.base, bytes(changed))
    self.assertFalse(same)
    self.assertIn("outside build identity", reasons[-1])

  def test_native_sae(self):
    for number, expected in ((0, "none"), (1, "partial"), (3, "partial"), (4, "all")):
      with self.subTest(number=number):
        state, counts = ke.native_sae(boot_image(sae=number))
        self.assertEqual(state, expected)
        self.assertEqual(list(counts.values()), [1] * number + [0] * (4 - number))

  def test_rsnxe_marker_in_kernel(self):
    for sae in (0, 1, 4):
      for rsnxe in (False, True):
        with self.subTest(sae=sae, rsnxe=rsnxe):
          self.assertEqual(ke.has_rsnxe(boot_image(sae=sae, rsnxe=rsnxe)), rsnxe)
    boot = bytearray(boot_image(sae=4))
    boot[64:64 + len(ke.RSNXE_MARKER)] = ke.RSNXE_MARKER
    self.assertFalse(ke.has_rsnxe(boot), "a command-line string is not kernel support")

  def test_cli(self):
    root = Path(__file__).resolve().parents[1]
    (root / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root / ".tmp") as work:
      base, new = Path(work) / "base.img", Path(work) / "new.img"
      base.write_bytes(self.base)
      for data, code, prefix in ((self.new, 0, "EQUIVALENT"), (b"broken", 1, "DIFFERENT")):
        new.write_bytes(data)
        result = subprocess.run([sys.executable, str(root / "scripts/kernel_equiv.py"), str(base), str(new)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertTrue(result.stdout.startswith(prefix), result.stdout)


@unittest.skipUnless(os.environ.get("WPA3_REAL_BOOTS_DIR"), "set WPA3_REAL_BOOTS_DIR for real stock/WPA3 images")
class TestRealBoots(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    directory = Path(os.environ["WPA3_REAL_BOOTS_DIR"])
    hashes = (
      "b30f5eef65ec3878f3aa3dcaf2cc95c09e2c1e661cd3a38e94da37dee76f68bd",
      "6ecf6f987cd11968104abcccabbe268485d329cdb73012dfd3c381a6b8deb27d",
      "335c17579879614a3b6f9b58c867aa2e66609530258e12d9174d6007494fdb11",
      "18c888b86f8846cd49bf3312b2c02fb60fc3f5e2f165d3a77417a7ad4e2c5549",
    )
    cls.stock = [directory.joinpath(f"boot-{digest}.img").read_bytes() for digest in hashes[:3]]
    cls.wpa3 = directory.joinpath(f"boot-{hashes[3]}.img").read_bytes()

  def test_three_stock_pairs(self):
    for (a, base), (b, new) in combinations(enumerate(self.stock, 6), 2):
      for first, second, versions in ((base, new, (a, b)), (new, base, (b, a))):
        with self.subTest(versions=versions):
          same, reasons = ke.equivalent(first, second)
          self.assertTrue(same, reasons)

  def test_stock_vs_wpa3(self):
    for stock in self.stock:
      self.assertFalse(ke.equivalent(stock, self.wpa3)[0])

  def test_real_sae_markers(self):
    self.assertEqual(ke.native_sae(self.wpa3), ("all", {marker.decode(): 1 for marker in ke.SAE_MARKERS}))
    self.assertFalse(ke.has_rsnxe(self.wpa3), "v1 has SAE but no RSNXE")
    for stock in self.stock:
      self.assertEqual(ke.native_sae(stock), ("none", {marker.decode(): 0 for marker in ke.SAE_MARKERS}))
      self.assertFalse(ke.has_rsnxe(stock))


if __name__ == "__main__":
  unittest.main()
