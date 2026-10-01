#!/usr/bin/env python3
from copy import deepcopy
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

# Also support the design's `python3 -m unittest scripts/test_dt_wifi.py -v`.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from boot_fixture import PAGE, boot_image
import dt_wifi as dw
import kernel_equiv as ke


def cells(*values):
  return struct.pack(f">{len(values)}I", *values)


def blob(tree, strings=b"", reservations=bytes(16)):
  start = 40 + len(reservations)
  total = start + len(tree) + len(strings)
  return cells(0xd00dfeed, total, start, start + len(tree), 40, 17, 16, 0,
               len(strings), len(tree)) + reservations + tree + strings


def begin(name):
  raw = name.encode("ascii") + b"\0"
  return cells(1) + raw + bytes(-len(raw) % 4)


def prop(offset, value):
  return cells(3, len(value), offset) + value + bytes(-len(value) % 4)


def fdt(nodes, reverse=False, nops=False):
  names = sorted({name for props in nodes.values() for name in props}, reverse=reverse)
  strings, offsets = b"", {}
  for name in names:
    offsets[name] = len(strings)
    strings += name.encode("ascii") + b"\0"

  def subtree(path):
    tree = begin(path.rsplit("/", 1)[-1])
    for name, value in sorted(nodes[path].items(), reverse=reverse):
      tree += (cells(4) if nops else b"") + prop(offsets[name], value)
    children = [p for p in nodes if p != "/" and (p.rpartition("/")[0] or "/") == path]
    for child in sorted(children, reverse=reverse):
      tree += subtree(child)
    return tree + cells(2)

  return blob(subtree("/") + cells(9), strings)


def fixture(shift=0, board=33):
  supply, clock, outside, other = (n + shift for n in (0xa001, 0xb001, 0xc001, 0xd001))
  return {
    "/": {"qcom,msm-id": cells(321, 0x20000), "qcom,board-id": cells(board, 0)},
    "/reserved-memory": {"#address-cells": cells(2), "#size-cells": cells(2), "ranges": b""},
    "/reserved-memory/region@90000000": {"reg": cells(0, 0x90000000, 0, 0x100000)},
    "/soc": {},
    "/soc/wlan@1000": {"compatible": b"vendor,wifi\0", "status": b"okay\0",
                       "references": cells(supply, 0x77777777, supply) + b"\xff"},
    "/soc/wlan@1000/calibration": {"data": b"\x01\x02\x03"},
    "/supply": {"phandle": cells(supply), "linux,phandle": cells(supply),
                "upstream": cells(clock), "microvolts": cells(800000)},
    "/clock": {"phandle": cells(clock), "upstream": cells(outside), "frequency": cells(19200000)},
    "/outside": {"phandle": cells(outside), "value": cells(8)},
    "/other": {"phandle": cells(other)},
    "/usb": {"status": b"okay\0"},
  }


def boot(*dtbs):
  raw = boot_image()
  image = ke.split(raw)[1]
  header = bytearray(raw[:PAGE])
  kernel = image + b"".join(dtbs)
  struct.pack_into("<I", header, 8, len(kernel))
  return bytes(header) + kernel + bytes(-len(kernel) % PAGE)


def word(raw, offset, value):
  changed = bytearray(raw)
  struct.pack_into(">I", changed, offset, value)
  return bytes(changed)


class TestFdtParser(unittest.TestCase):
  def test_round_trip_tokens_and_reordering(self):
    nodes = fixture()
    for reverse, nops in ((False, False), (True, True)):
      self.assertEqual(dw.parse(fdt(nodes, reverse, nops)), nodes)
    self.assertEqual(dw.parse(fdt({"/": {}})), {"/": {}})
    reserved = blob(begin("") + cells(2, 9), reservations=struct.pack(">4Q", 4096, 8192, 0, 0))
    self.assertEqual(dw.parse(reserved), {"/": {}})

  def test_header_bounds_and_layout_fail_closed(self):
    raw = fdt(fixture())
    invalid = [b"", raw[:39], raw[:-1], raw + b"\0", raw + raw]
    for offset, value in ((0, 0), (4, 39), (4, len(raw) + 1), (8, len(raw)),
                          (8, 39), (8, 57), (12, len(raw) + 1), (12, 0),
                          (16, 41), (16, len(raw)), (20, 16), (20, 18),
                          (24, 18), (32, len(raw)), (36, len(raw)), (36, 0), (36, 3)):
      invalid.append(word(raw, offset, value))
    for index, data in enumerate(invalid):
      with self.subTest(index=index):
        with self.assertRaises(ValueError):
          dw.parse(data)

  def test_overlapping_blocks_and_unterminated_reservations(self):
    raw = fdt(fixture())
    tree, strings = struct.unpack_from(">2I", raw, 8)
    invalid = (word(raw, 12, tree), word(raw, 16, tree), word(raw, 8, 40),
               raw[:40] + b"\xff" * 16 + raw[56:], word(raw, 16, (strings + 7) & ~7))
    for data in invalid:
      with self.assertRaises(ValueError):
        dw.parse(data)

  def test_nesting_limit_includes_root(self):
    for depth in (64, 65):
      tree = begin("") + begin("child") * (depth - 1) + cells(2) * depth + cells(9)
      if depth == 64:
        self.assertEqual(len(dw.parse(blob(tree))), depth)
      else:
        with self.assertRaisesRegex(ValueError, "64 levels"):
          dw.parse(blob(tree))

  def test_malformed_token_streams(self):
    cases = {
      "unknown": begin("") + cells(5, 2, 9),
      "unmatched close": cells(2, 9),
      "no root": cells(9),
      "unclosed root": begin("") + cells(9),
      "no end": begin("") + cells(2),
      "extra end": begin("") + cells(2, 9, 9),
      "named root": begin("root") + cells(2, 9),
      "second root": begin("") + cells(2) + begin("") + cells(2, 9),
      "empty child": begin("") + begin("") + cells(2, 2, 9),
      "path traversal": begin("") + begin("..") + cells(2, 2, 9),
      "slash": begin("") + begin("a/b") + cells(2, 2, 9),
      "duplicate node": begin("") + (begin("a") + cells(2)) * 2 + cells(2, 9),
      "truncated name": cells(1) + b"xxxx",
      "nonascii name": cells(1) + b"\xff\0\0\0" + cells(2, 9),
      "property outside root": prop(0, b"") + begin("") + cells(2, 9),
      "property after child": begin("") + begin("a") + cells(2) + prop(0, b"") + cells(2, 9),
      "truncated prop header": begin("") + cells(3, 0),
      "truncated prop value": begin("") + cells(3, 1000, 0, 2, 9),
      "bad name offset": begin("") + prop(2, b"") + cells(2, 9),
      "duplicate prop": begin("") + prop(0, b"") * 2 + cells(2, 9),
    }
    for name, tree in cases.items():
      with self.subTest(name=name):
        with self.assertRaises(ValueError):
          dw.parse(blob(tree, b"x\0"))

  def test_property_names_are_bounded_by_strings_block(self):
    tree = begin("") + prop(0, b"") + cells(2, 9)
    for strings in (b"", b"x", b"\0", b"bad/name\0", b"\xff\0"):
      with self.subTest(strings=strings):
        with self.assertRaises(ValueError):
          dw.parse(blob(tree, strings))


class TestWifiDigest(unittest.TestCase):
  def setUp(self):
    self.nodes = fixture()
    self.raw = fdt(self.nodes)
    self.digest = dw.wifi_digest(self.raw)

  def test_phandle_renumbering_and_serialization_order(self):
    self.assertEqual(len(self.digest), 64)
    for shift in (0, 0x100, 0x100000):
      with self.subTest(shift=shift):
        self.assertEqual(self.digest, dw.wifi_digest(fdt(fixture(shift), reverse=True, nops=True)))

  def test_selected_properties_and_two_reference_levels(self):
    for path, name, value in (("/soc/wlan@1000", "status", b"disabled\0"),
                               ("/soc/wlan@1000/calibration", "data", b"\x01\x03\x03"),
                               ("/reserved-memory", "#size-cells", cells(1)),
                               ("/reserved-memory/region@90000000", "reg", cells(0, 0x91000000, 0, 0x100000)),
                               ("/supply", "microvolts", cells(900000)),
                               ("/clock", "frequency", cells(24000000))):
      with self.subTest(path=path):
        changed = deepcopy(self.nodes)
        changed[path][name] = value
        self.assertNotEqual(self.digest, dw.wifi_digest(fdt(changed)))

  def test_third_level_and_unrelated_changes_are_outside_selection(self):
    for path in ("/outside", "/usb"):
      changed = deepcopy(self.nodes)
      changed[path]["value"] = cells(999999)
      self.assertEqual(self.digest, dw.wifi_digest(fdt(changed)))
    paths = dw.wifi_nodes(self.raw)
    self.assertIn("/supply", paths)
    self.assertIn("/clock", paths)
    self.assertNotIn("/outside", paths)
    self.assertNotIn("/usb", paths)

  def test_references_on_second_level_still_normalize(self):
    changed = deepcopy(self.nodes)
    changed["/clock"]["upstream"] = changed["/other"]["phandle"]
    self.assertNotEqual(self.digest, dw.wifi_digest(fdt(changed)))

  def test_compatible_substrings_select_nodes(self):
    for compatible in (b"vendor,thing\0qcom,icnss\0", b"qcom,cnss-qca6290\0"):
      nodes = {"/": {}, "/radio": {"compatible": compatible, "value": b"before"}}
      before = dw.wifi_digest(fdt(nodes))
      nodes["/radio"]["value"] = b"after"
      self.assertNotEqual(before, dw.wifi_digest(fdt(nodes)))

  def test_added_removed_or_renamed_nodes_and_properties(self):
    for kind in ("add node", "remove node", "rename node", "add prop", "remove prop"):
      changed = deepcopy(self.nodes)
      if kind == "add node":
        changed["/reserved-memory/empty"] = {}
      elif kind == "remove node":
        del changed["/reserved-memory/region@90000000"]
      elif kind == "rename node":
        changed["/supply-new"] = changed.pop("/supply")
      elif kind == "add prop":
        changed["/soc/wlan@1000"]["empty"] = b""
      else:
        del changed["/soc/wlan@1000"]["status"]
      with self.subTest(kind=kind):
        self.assertNotEqual(self.digest, dw.wifi_digest(fdt(changed)))

  def test_cycles_are_bounded(self):
    self.nodes["/clock"]["upstream"] = self.nodes["/supply"]["phandle"]
    selected = dw.wifi_nodes(fdt(self.nodes))
    self.assertEqual(len(selected), 6)

  def test_every_aligned_matching_cell_is_a_reference_including_plain_values(self):
    # No binding whitelist: a plain scalar's accidental reference adds a hold.
    self.nodes["/soc/wlan@1000"]["ordinary-number"] = self.nodes["/other"]["phandle"]
    before = dw.wifi_digest(fdt(self.nodes))
    self.nodes["/other"]["value"] = b"changed"
    self.assertNotEqual(before, dw.wifi_digest(fdt(self.nodes)))
    # Matching at offset 1 is not aligned; a trailing byte remains significant.
    nodes = {"/": {}, "/wlan": {"raw": b"x" + cells(0xa001)},
             "/target": {"phandle": cells(0xa001), "value": b"before"}}
    before = dw.wifi_digest(fdt(nodes))
    nodes["/target"]["value"] = b"after"
    self.assertEqual(before, dw.wifi_digest(fdt(nodes)))
    nodes["/wlan"]["raw"] = b"x" + cells(0xa002)
    self.assertNotEqual(before, dw.wifi_digest(fdt(nodes)))

  def test_plain_value_blind_spot_during_phandle_renumbering(self):
    # FDT erased the types: a plain value changing from 0xa001 to 0xa101
    # looks exactly like a reference renumbered to the same equivalent node.
    # This documented theoretical blind spot is deliberate, not an assertion
    # that conservative matching can prove equality of every plain number.
    old, new = fixture(), fixture(shift=0x100)
    old["/soc/wlan@1000"]["ordinary-number"] = cells(0xa001)
    new["/soc/wlan@1000"]["ordinary-number"] = cells(0xa101)
    self.assertNotEqual(old["/soc/wlan@1000"]["ordinary-number"], new["/soc/wlan@1000"]["ordinary-number"])
    self.assertEqual(dw.wifi_digest(fdt(old)), dw.wifi_digest(fdt(new)))

  def test_invalid_phandles_fail_closed_even_outside_selection(self):
    for value in (b"", cells(0), cells(0xffffffff), cells(1, 2), cells(0xa001)):
      changed = deepcopy(self.nodes)
      changed["/other"]["phandle"] = value
      with self.subTest(value=value):
        with self.assertRaises(ValueError):
          dw.wifi_digest(fdt(changed))
    self.nodes["/supply"]["linux,phandle"] = cells(0xe001)
    with self.assertRaises(ValueError):
      dw.wifi_digest(fdt(self.nodes))


class TestBoardComparison(unittest.TestCase):
  def test_pair_by_both_board_ids_independent_of_order(self):
    first, second = fdt(fixture()), fdt(fixture(board=34))
    self.assertTrue(dw.compare(boot(first, second), boot(second, first))[0])
    for name in dw.BOARD_IDS:
      changed = fixture()
      changed["/"][name] = cells(999, 0)
      ok, reasons = dw.compare(boot(first), boot(fdt(changed)))
      self.assertFalse(ok)
      self.assertTrue(any("missing" in reason for reason in reasons))
      self.assertTrue(any("added" in reason for reason in reasons))

  def test_missing_added_duplicate_and_invalid_boards_fail_closed(self):
    first, second = fdt(fixture()), fdt(fixture(board=34))
    for a, b in ((boot(first), boot(first, second)), (boot(first, second), boot(first)),
                 (boot(first, first), boot(first, first)), (b"broken", boot(first))):
      self.assertFalse(dw.compare(a, b)[0])
    for name in dw.BOARD_IDS:
      for value in (None, b"", b"abc"):
        changed = fixture()
        if value is None:
          del changed["/"][name]
        else:
          changed["/"][name] = value
        self.assertFalse(dw.compare(boot(first), boot(fdt(changed)))[0])

  def test_differing_node_paths_are_reported(self):
    old, new = fixture(), fixture()
    new["/soc/wlan@1000"]["status"] = b"disabled\0"
    new["/supply"]["microvolts"] = cells(900000)
    ok, reasons = dw.compare(boot(fdt(old)), boot(fdt(new)))
    self.assertFalse(ok)
    self.assertIn("differing node paths: /soc/wlan@1000, /supply", reasons[0])

  def test_cli_success_difference_and_invalid_input(self):
    script = Path(__file__).with_name("dt_wifi.py")
    with tempfile.TemporaryDirectory() as work:
      base, new = Path(work) / "base.img", Path(work) / "new.img"
      raw = boot(fdt(fixture()))
      base.write_bytes(raw)
      changed = fixture()
      changed["/soc/wlan@1000"]["status"] = b"disabled\0"
      for data, code, expected in ((boot(fdt(fixture(shift=0x100))), 0, "EQUAL"),
                                   (boot(fdt(changed)), 1, "/soc/wlan@1000"),
                                   (b"broken", 1, "parse failed"), (None, 1, "DIFFERENT")):
        if data is None:
          new.unlink()
        else:
          new.write_bytes(data)
        result = subprocess.run([sys.executable, str(script), str(base), str(new)], capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertIn(expected, result.stdout)
        self.assertFalse(result.stderr)
      self.assertEqual(base.read_bytes(), raw)


@unittest.skipUnless(Path("/Volumes/agnos").is_dir(), "/Volumes/agnos is not mounted")
class TestMountedWifi(unittest.TestCase):
  def test_identical_stock_dtbs_and_usb_only_change(self):
    base = Path("/Volumes/agnos/ref199/boot-335c1757.img").read_bytes()
    root = Path(__file__).resolve().parents[1]
    paths = (Path("/Volumes/agnos/ref199/boot-b9c9b926.img"),
             root / ".autofollow_1001/kernel_src/boots/boot-f716b81d.img")
    for index, path in enumerate(paths):
      with self.subTest(path=path):
        new = path.read_bytes()
        self.assertEqual(ke.split(base)[2] == ke.split(new)[2], index == 0)
        ok, reasons = dw.compare(base, new)
        self.assertTrue(ok, "\n".join(reasons))


if __name__ == "__main__":
  unittest.main()
