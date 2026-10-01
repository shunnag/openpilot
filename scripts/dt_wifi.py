#!/usr/bin/env python3
"""Compare per-board Wi-Fi device-tree content in Android boot images.

FDT values have no type metadata. Conservatively treat EVERY aligned 32-bit
cell equal to a phandle declared in the same FDT as a reference, even in plain
numbers or strings. Follow these references for two levels and normalize them
to absolute node paths. Extra references can add false holds in the later gate.
One theoretical blind spot remains: a plain value changing between two numbers
that happen to be phandles of equivalent nodes (the same canonical path across
the two trees) is indistinguishable from phandle renumbering and can be hidden.

The initial selection includes /reserved-memory and the subtrees of nodes whose
name starts with wlan or compatible contains qcom,icnss or qcom,cnss. Referenced
nodes contribute their own properties; only two reference edges are followed.
Every property, including phandle declarations, is retained and normalized.
This module is standalone and does not enable or replace any gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from kernel_equiv import dtb_blobs, split

PHANDLES = ("phandle", "linux,phandle")
BOARD_IDS = ("qcom,msm-id", "qcom,board-id")


def parse(dtb):
  """Return {absolute node path: {property name: raw bytes}} for one FDT v17.

  Validate all blocks and tokens, including nodes outside the Wi-Fi selection.
  The root counts as the first of at most 64 simultaneously open nodes.
  """
  if len(dtb_blobs(dtb)) != 1:
    raise ValueError("expected one FDT blob")
  _, total, tree, strings, reserve, version, compatible, _, nstrings, ntree = struct.unpack_from(">10I", dtb)
  if version != 17 or compatible not in (16, 17):
    raise ValueError("expected FDT v17 with compatible version 16 or 17")
  blocks = [(0, 40)]
  for name, start, size in (("structure", tree, ntree), ("strings", strings, nstrings)):
    if start < 40 or start > total or size > total - start:
      raise ValueError(f"FDT {name} block outside blob")
    blocks.append((start, start + size))
  if tree % 4 or not ntree or ntree % 4 or reserve < 40 or reserve % 8 or reserve >= total:
    raise ValueError("invalid FDT block alignment or size")
  # The reservation map has no length field; bound it by the next block.
  limit = min([start for start, _ in blocks if start >= reserve] + [total])
  pos = reserve
  while pos + 16 <= limit:
    address, size = struct.unpack_from(">2Q", dtb, pos)
    pos += 16
    if address == size == 0:
      break
  else:
    raise ValueError("truncated FDT reservation map")
  blocks.append((reserve, pos))
  occupied = sorted((start, end) for start, end in blocks if start != end)
  if any(end > next_start for (_, end), (next_start, _) in zip(occupied, occupied[1:])):
    raise ValueError("overlapping FDT blocks")

  def cstring(start, end):
    nul = dtb.find(b"\0", start, end)
    if nul < 0:
      raise ValueError("unterminated FDT name")
    try:
      name = dtb[start:nul].decode("ascii")
    except UnicodeDecodeError as error:
      raise ValueError("non-ASCII FDT name") from error
    if "/" in name or any(ord(c) <= 32 or ord(c) >= 127 for c in name):
      raise ValueError("invalid FDT name")
    return name, nul + 1

  nodes, stack = {}, []
  pos, end = tree, tree + ntree
  while pos + 4 <= end:
    token = struct.unpack_from(">I", dtb, pos)[0]
    pos += 4
    if token == 1:  # FDT_BEGIN_NODE
      name, pos = cstring(pos, end)
      pos = (pos + 3) & ~3
      if pos > end or len(stack) >= 64:
        raise ValueError("truncated FDT node or nesting exceeds 64 levels")
      if stack:
        if not name or name in (".", ".."):
          raise ValueError("invalid FDT child name")
        stack[-1][1] = True
        path = stack[-1][0].rstrip("/") + "/" + name
      else:
        if name or nodes:
          raise ValueError("expected one unnamed FDT root")
        path = "/"
      if path in nodes:
        raise ValueError(f"duplicate FDT node: {path}")
      nodes[path] = {}
      stack.append([path, False])
    elif token == 2:  # FDT_END_NODE
      if not stack:
        raise ValueError("unmatched FDT_END_NODE")
      stack.pop()
    elif token == 3:  # FDT_PROP
      if not stack or stack[-1][1] or pos + 8 > end:
        raise ValueError("misplaced or truncated FDT property")
      size, offset = struct.unpack_from(">2I", dtb, pos)
      pos += 8
      if size > end - pos or offset >= nstrings:
        raise ValueError("FDT property value or name outside block")
      name, _ = cstring(strings + offset, strings + nstrings)
      props = nodes[stack[-1][0]]
      if not name or name in props:
        raise ValueError(f"empty or duplicate FDT property: {name!r}")
      props[name] = dtb[pos:pos + size]
      pos = (pos + size + 3) & ~3
    elif token == 4:  # FDT_NOP
      continue
    elif token == 9:  # FDT_END
      if stack or not nodes or pos != end:
        raise ValueError("unclosed FDT nodes or data after FDT_END")
      return nodes
    else:
      raise ValueError(f"unknown FDT token: {token}")
  raise ValueError("missing FDT_END")


def _phandles(nodes):
  targets = {}
  for path, props in nodes.items():
    values = []
    for name in PHANDLES:
      if name in props:
        if len(props[name]) != 4:
          raise ValueError(f"invalid {name} at {path}")
        values.append(int.from_bytes(props[name], "big"))
    if not values:
      continue
    value = values[0]
    if value in (0, 0xffffffff) or any(other != value for other in values) or value in targets:
      raise ValueError(f"invalid, conflicting or duplicate phandle at {path}")
    targets[value] = path
  return targets


def _value(value, targets):
  """Canonical tagged byte spans/path references, plus the referenced paths."""
  parts, refs, start = [], set(), 0
  for offset in range(0, len(value) - 3, 4):
    target = targets.get(struct.unpack_from(">I", value, offset)[0])
    if target is not None:
      if start < offset:
        parts.append(("bytes", value[start:offset].hex()))
      parts.append(("path", target))
      refs.add(target)
      start = offset + 4
  if start < len(value):
    parts.append(("bytes", value[start:].hex()))
  return parts, refs


def _wifi_nodes(nodes):
  targets = _phandles(nodes)
  roots = {path for path, props in nodes.items()
           if path == "/reserved-memory" or path.rsplit("/", 1)[-1].startswith("wlan")
           or any(marker in props.get("compatible", b"") for marker in (b"qcom,icnss", b"qcom,cnss"))}
  selected = set()
  # Include seed subtrees (in particular all reserved-memory regions). Walk
  # ancestors instead of comparing every node with every possible seed.
  for path in nodes:
    parent = path
    while parent:
      if parent in roots:
        selected.add(path)
        break
      if parent == "/":
        break
      parent = parent.rpartition("/")[0] or "/"
  result, frontier = {}, selected
  for depth in range(3):
    following = set()
    for path in sorted(frontier):
      props = {}
      for name, value in sorted(nodes[path].items()):
        props[name], refs = _value(value, targets)
        following.update(refs)
      result[path] = props
    if depth < 2:
      frontier = following - result.keys()
  return result


def wifi_nodes(dtb):
  """Return canonical {path: properties} for digesting and difference reports."""
  return _wifi_nodes(parse(dtb))


def _digest(nodes):
  encoded = json.dumps(nodes, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
  return hashlib.sha256(encoded).hexdigest()


def wifi_digest(dtb):
  """Return the SHA-256 hex digest of the canonical Wi-Fi selection of one FDT."""
  return _digest(wifi_nodes(dtb))


def _boards(boot):
  boards = {}
  for dtb in dtb_blobs(split(boot)[2]):
    nodes = parse(dtb)
    key = tuple(nodes["/"].get(name, b"") for name in BOARD_IDS)
    if any(not value or len(value) % 4 for value in key):
      raise ValueError("missing or invalid qcom,msm-id / qcom,board-id at /")
    if key in boards:
      raise ValueError("duplicate board identity; cannot pair DTBs unambiguously")
    boards[key] = _wifi_nodes(nodes)
  return boards


def compare(base, new):
  """Return (equal, diagnostics) for boots, pairing by both complete board IDs.

  DTB order is irrelevant; missing/added boards and ambiguous duplicate IDs
  fail closed. Parse errors are reported as DIFFERENT, never as empty digests.
  """
  try:
    old, current = _boards(base), _boards(new)
  except ValueError as error:
    return False, [f"boot/FDT parse failed: {error}"]
  reasons = []
  for key in sorted(old.keys() | current.keys()):
    board = " ".join(f"{name}={value.hex()}" for name, value in zip(BOARD_IDS, key))
    if key not in old or key not in current:
      reasons.append(f"board {board}: {'added' if key not in old else 'missing'}")
      continue
    before, after = old[key], current[key]
    if _digest(before) != _digest(after):
      paths = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
      reasons.append(f"board {board}: differing node paths: {', '.join(paths)}")
  return not reasons, reasons or [f"{len(old)} boards; Wi-Fi digests match"]


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("base", type=Path)
  parser.add_argument("new", type=Path)
  args = parser.parse_args()
  try:
    ok, reasons = compare(args.base.read_bytes(), args.new.read_bytes())
  except OSError as error:
    ok, reasons = False, [str(error)]
  print("EQUAL" if ok else "DIFFERENT")
  for reason in reasons:
    print(reason)
  return 0 if ok else 1


if __name__ == "__main__":
  sys.exit(main())
