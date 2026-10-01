#!/usr/bin/env python3
from itertools import combinations
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from boot_fixture import BANNER, CERT, CONFIG, IMAGE_SIZE, INITRAMFS, NOTE, PAGE, SYMBOL, UTS, boot_image, fdt, identity_pair, mutate
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

  # Standalone #N regression tests; independent of rebuild mode.
  def test_uts_build_numbers_keep_stock_bounds(self):
    def numbered(number):
      changed = bytearray(self.base)
      image = ke.split(self.base)[1]
      for start, end in ke.cstr_spans(image, b"#1 SMP PREEMPT "):
        value = image[start:end].replace(b"#1 ", f"#{number} ".encode(), 1)
        changed[PAGE + start:PAGE + start + len(value)] = value
      return bytes(changed)

    for number in (2, 10, 999999):
      with self.subTest(number=number):
        stock = numbered(number)
        for base, new in ((self.base, stock), (stock, self.base)):
          self.assertTrue(ke.equivalent(base, new)[0])
          for offset in (PAGE + 12, 64, PAGE + IMAGE_SIZE + 60):
            self.assertFalse(ke.equivalent(base, mutate(new, offset))[0])
    self.assertFalse(ke.equivalent(self.base, numbered(1000000))[0])
    stock = bytearray(numbered(2))
    end = stock.index(0, PAGE + UTS)
    stock[end:end + 18] = b"X" * 17 + b"\0"
    self.assertFalse(ke.equivalent(self.base, bytes(stock))[0])

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


class TestRebuildEquiv(unittest.TestCase):
  @staticmethod
  def with_dtbs(boot, chain):
    _, img, _ = ke.split(boot)
    header = bytearray(boot[:PAGE])
    kernel = img + chain
    struct.pack_into("<I", header, 8, len(kernel))
    return bytes(header) + kernel + bytes(-len(kernel) % PAGE)

  def test_dtb_order_is_rebuild_only(self):
    base, new = identity_pair()
    blobs = ke.dtb_blobs(ke.split(new)[2])
    changed = self.with_dtbs(new, b"".join(reversed(blobs)))
    for a, b in ((base, changed), (changed, base)):
      self.assertTrue(ke.rebuild_equivalent(a, b)[0], ke.rebuild_equivalent(a, b)[1])
      self.assertFalse(ke.equivalent(a, b)[0])
    self.assertTrue(ke.equivalent(base, new)[0], "rebuild mode must not mutate the stock comparator")

  def test_dtb_multiset_retains_duplicates_and_exact_bytes(self):
    base = boot_image()
    one, two = ke.dtb_blobs(ke.split(base)[2])
    base = self.with_dtbs(base, one + two + one)
    for chain, expected in ((two + one + one, True), (one + two, False),
                            (one + two + one + one, False), (one + two + two, False),
                            (one + two + mutate(one, 60), False)):
      with self.subTest(count=len(chain) // len(one), expected=expected):
        changed = self.with_dtbs(base, chain)
        for a, b in ((base, changed), (changed, base)):
          self.assertEqual(ke.rebuild_equivalent(a, b)[0], expected)

  def test_dtb_blobs_rejects_invalid_chains(self):
    good = fdt(b"test")
    for chain in (b"", good[:39], good[:-1], good + b"\0", mutate(good, 0),
                  good[:4] + struct.pack(">I", 0) + good[8:],
                  good[:4] + struct.pack(">I", 65) + good[8:]):
      with self.subTest(chain=chain[:8]):
        with self.assertRaises(ValueError):
          ke.dtb_blobs(chain)

  def test_proc_banner_mask_is_bounded_and_rebuild_only(self):
    start = PAGE + 8000
    proc = b"%s version %s (user@docker) compiler %s\n"
    base = bytearray(boot_image())
    base[start:start + 256] = proc.ljust(256, b"\0")
    base = bytes(base)
    for growth, expected in ((0, True), (16, True), (17, False)):
      new = bytearray(base)
      value = proc.replace(b"user", b"test")[:-1] + b"X" * growth + b"\n"
      new[start:start + len(value)] = value
      for a, b in ((base, bytes(new)), (bytes(new), base)):
        with self.subTest(growth=growth):
          ok, reasons = ke.rebuild_equivalent(a, b)
          self.assertEqual(ok, expected, reasons)
          self.assertFalse(ke.equivalent(a, b)[0])
    for name, offset, value in (
      ("terminator", start + len(proc) - 1, b"\0"),
      ("outside", start + len(proc), b"X"),
      ("missing", start, b"!"),
      ("extra", start + 512, proc),
      ("overlong", start, proc[:-1] + b"X" * 256 + b"\n"),
    ):
      new = bytearray(base)
      new[offset:offset + len(value)] = value
      with self.subTest(name=name):
        self.assertFalse(ke.rebuild_equivalent(base, bytes(new))[0])
        self.assertFalse(ke.rebuild_equivalent(bytes(new), base)[0])
    # Growth cannot swallow a nonzero neighbor, even within the 16-byte cap.
    narrow = bytearray(base)
    narrow[start + len(proc) + 6] = ord("N")
    for growth in (6, 7):
      new = bytearray(narrow)
      value = proc[:-1] + b"X" * growth + b"\n"
      new[start:start + len(value)] = value
      for a, b in ((narrow, new), (new, narrow)):
        self.assertEqual(ke.rebuild_equivalent(bytes(a), bytes(b))[0], growth == 6)

  def test_rebuild_preserves_other_stock_requirements(self):
    base, new = identity_pair()
    for offset in (12, 64, PAGE + 12, PAGE + CONFIG + 8, PAGE + SYMBOL,
                   PAGE + INITRAMFS + 20, PAGE + IMAGE_SIZE + 60):
      with self.subTest(offset=offset):
        self.assertFalse(ke.rebuild_equivalent(base, mutate(new, offset))[0])
    self.assertFalse(ke.rebuild_equivalent(base, boot_image(config=b"CONFIG_TEST=n\n"))[0])
    self.assertFalse(ke.rebuild_equivalent(base, b"broken")[0])

  def test_cli_modes(self):
    root = Path(__file__).resolve().parents[1]
    base = boot_image()
    new = self.with_dtbs(base, b"".join(reversed(ke.dtb_blobs(ke.split(base)[2]))))
    with tempfile.TemporaryDirectory() as work:
      a, b = Path(work) / "a.img", Path(work) / "b.img"
      a.write_bytes(base)
      b.write_bytes(new)
      for mode, code, prefix in (([], 1, "DIFFERENT"), (["--mode", "stock"], 1, "DIFFERENT"),
                                 (["--mode", "rebuild"], 0, "REBUILD-EQUIVALENT")):
        result = subprocess.run([sys.executable, str(root / "scripts/kernel_equiv.py"), *mode, str(a), str(b)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertTrue(result.stdout.startswith(prefix), result.stdout)


class TestKernelHelpers(unittest.TestCase):
  def test_ikconfig_delta_exact(self):
    def img(config):
      return ke.split(boot_image(config=config))[1]

    old = img(b'# comment\n# CONFIG_WLAN_FEATURE_SAE is not set\nCONFIG_KEEP=m\nCONFIG_OLD=y\nCONFIG_TEXT="a=b"\n')
    new = img(b'CONFIG_TEXT="a=c"\nCONFIG_NEW=0x10\nCONFIG_KEEP=m\nCONFIG_WLAN_FEATURE_SAE=y\n')
    expected = {"CONFIG_WLAN_FEATURE_SAE": ("n", "y"), "CONFIG_OLD": ("y", None),
                "CONFIG_NEW": (None, "0x10"), "CONFIG_TEXT": ('"a=b"', '"a=c"')}
    self.assertEqual(ke.ikconfig_delta(old, new), expected)
    self.assertEqual(ke.ikconfig_delta(new, old), {key: (b, a) for key, (a, b) in expected.items()})
    self.assertEqual(ke.ikconfig_delta(old, old), {})
    stock = img(b"# CONFIG_MODULE_SIG_FORCE is not set\n# CONFIG_WLAN_FEATURE_SAE is not set\n")
    wpa3 = img(b"# CONFIG_MODULE_SIG_FORCE is not set\nCONFIG_WLAN_FEATURE_SAE=y\n")
    self.assertEqual(ke.ikconfig_delta(stock, wpa3), {"CONFIG_WLAN_FEATURE_SAE": ("n", "y")})
    for bad in (b"CONFIG_A=y\nCONFIG_A=m\n", b"invalid\n"):
      with self.assertRaises(ValueError):
        ke.ikconfig_delta(old, img(bad))

  def test_banner_identity(self):
    banner = b"Linux version 4.9.103 (batman@docker) (gcc version 8.2.1 (arm)) #10 SMP PREEMPT Sun Sep 27 17:29:45 UTC 2026\n"
    self.assertEqual(ke.banner_identity(banner), ("batman", "docker", 10, "Sun Sep 27 17:29:45 UTC 2026"))
    for bad in (b"", banner + banner, banner[:-1], banner.replace(b"@", b"-"),
                banner.replace(b"#10", b"#1000000"), banner[:-1] + b"X" * 256 + b"\n"):
      with self.subTest(bad=bad[:40]):
        with self.assertRaises(ValueError):
          ke.banner_identity(bad)

  def test_image_layout(self):
    img = bytearray(20 + 256)
    img[:16] = b"UNCOMPRESSED_IMG"
    struct.pack_into("<I", img, 16, len(img) - 20)
    struct.pack_into("<3Q", img, 28, 0x80000, 0x395f000, 0xa)
    img[76:80] = b"ARM\x64"
    self.assertEqual(ke.image_layout(img), {"length": 256, "header_offset": 20, "text_offset": 0x80000,
                                           "image_size": 0x395f000, "flags": 0xa})
    for bad in (img[:80], img[:-1], mutate(img, 0), mutate(img, 16), mutate(img, 76)):
      with self.assertRaises(ValueError):
        ke.image_layout(bad)
    changed = bytearray(img)
    struct.pack_into("<Q", changed, 28, 0x90000)
    self.assertEqual(ke.image_layout(changed)["text_offset"], 0x90000)


@unittest.skipUnless(Path("/Volumes/agnos").is_dir(), "/Volumes/agnos is not mounted")
class TestMountedRebuilds(unittest.TestCase):
  def test_reference_rebuilds_and_negatives(self):
    root = Path("/Volumes/agnos")
    stock199 = root.joinpath("ref199/boot-b9c9b926.img").read_bytes()
    stock198 = root.joinpath("ref199/boot-335c1757.img").read_bytes()
    rebuilt199 = root.joinpath("ref199/our-stock-199.img").read_bytes()
    stock195 = Path(__file__).resolve().parents[1] / ".autofollow_1001/kernel_src/boots/boot-f716b81d.img"
    pairs = (
      (stock199, rebuilt199, True),
      (stock198, root.joinpath("cmp/control-gcc8.img").read_bytes(), True),
      (stock198, root.joinpath("cmp/control-gcc9.img").read_bytes(), False),
      (stock199, stock198, False),
      (stock198, stock195.read_bytes(), False),
    )
    for a, b, expected in pairs:
      with self.subTest(expected=expected, sizes=(len(a), len(b))):
        ok, reasons = ke.rebuild_equivalent(a, b)
        self.assertEqual(ok, expected, reasons)
    self.assertFalse(ke.equivalent(stock199, rebuilt199)[0])
    self.assertEqual(ke.banner_identity(ke.split(stock199)[1]),
                     ("batman", "docker", 10, "Sun Sep 27 17:29:45 UTC 2026"))


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
