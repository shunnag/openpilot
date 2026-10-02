#!/usr/bin/env python3
"""P1 quilt fuzz-zero application and P2 identity of functions touched by our patches."""
import argparse
import difflib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from system_probe import require


def patch_status(output, returncode):
  if re.search(r'Reversed \(or previously applied\)|previously applied|Unreversed patch', output, re.I):
    raise ValueError('P1: backported by Ubuntu; drop it')
  require(returncode == 0 and not re.search(r'\bfuzz\b|FAILED', output, re.I), 'P1: patch failed/fuzz')
  return [int(value) for value in re.findall(r'offset (-?\d+) lines?', output)]


def functions(text):
  """Conservative top-level C function spans; reject unrecognized touched declarations."""
  clean = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                 lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text, flags=re.S)
  spans = []
  # Hostap uses column-zero closing braces. Requiring that style fails closed.
  for match in re.finditer(r'(?m)^([A-Za-z_][\w\s*]*?\b([A-Za-z_]\w*)\([^;{}]*\))\s*\n\{', clean):
    depth, end = 1, match.end()
    while depth and end < len(clean):
      depth += (clean[end] == '{') - (clean[end] == '}')
      end += 1
    require(depth == 0, 'P2: unbalanced C function')
    name = match[2]
    spans.append((name, match.start(), end, text[match.start():end]))
  return spans


def compare_functions(before, patched, candidate):
  old, new = functions(before), functions(candidate)
  changes = [op for op in difflib.SequenceMatcher(None, before, patched, autojunk=False).get_opcodes() if op[0] != 'equal']
  touched = set()
  for _, start, end, _, _ in changes:
    enclosing = [name for name, a, b, _ in old if a <= start < b and end <= b]
    require(len(enclosing) == 1, 'P2: touched C text is not an unambiguous function')
    touched.add(enclosing[0])
  for name in touched:
    reference = [text for n, _, _, text in old if n == name]
    candidate_functions = [text for n, _, _, text in new if n == name]
    require(len(reference) == len(candidate_functions) == 1 and reference == candidate_functions,
            'P2: changed function ' + name + ' (or ambiguous conditional function)')
  return sorted(touched)


def apply_patch(tree, patch):
  reverse = subprocess.run(['patch', '--dry-run', '--force', '--fuzz=0', '-R', '-p1', '-i', str(patch)],
                           cwd=tree, text=True, capture_output=True)
  # --force prevents patch silently switching direction during the reverse check.
  if reverse.returncode == 0 and 'Ignoring -R' not in reverse.stdout and 'Unreversed' not in reverse.stdout:
    raise ValueError('P1: backported by Ubuntu; drop it: ' + patch.name)
  target = tree / 'debian/patches' / patch.name
  require(not target.exists(), 'P1: patch name already in Ubuntu: ' + patch.name)
  shutil.copyfile(patch, target)
  with (tree / 'debian/patches/series').open('a') as out:
    out.write('\n' + patch.name + '\n')
  env = {**os.environ, 'QUILT_PATCHES': 'debian/patches', 'QUILT_PATCH_OPTS': '--fuzz=0', 'LC_ALL': 'C'}
  result = subprocess.run(['quilt', '--quiltrc', '/dev/null', 'push', '--fuzz=0'], cwd=tree, env=env,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  print(patch.name + '\n' + result.stdout, flush=True)
  offsets = patch_status(result.stdout, result.returncode)
  if any(not path.endswith('.c') for path in re.findall(r'^\+\+\+ b/(.+)$', patch.read_text(), re.M)):
    require(all(abs(n) <= 100 for n in offsets), 'P1: non-function hunk moved more than 100 lines')


def qualify(reference, candidate, patches):
  files = sorted(patches.glob('*.patch'))
  require(len(files) == 7, 'P1: exactly seven patches required')
  with tempfile.TemporaryDirectory(prefix='wpa-p2-') as tmp:
    patched = Path(tmp) / 'reference'
    shutil.copytree(reference, patched)
    paths = set()
    for patch in files:
      paths.update(re.findall(r'^\+\+\+ b/(.+\.c)$', patch.read_text(), re.M))
      apply_patch(patched, patch)
    # Save the git function-context diff for review as required by the recipe.
    diff = subprocess.run(['git', 'diff', '--no-index', '-W', '--', str(reference), str(candidate)],
                          stdout=subprocess.PIPE, check=False)
    require(diff.returncode in (0, 1), 'P2: git diff failed')
    Path('/tmp/debian-function-diff.txt').write_bytes(re.sub(rb'@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@', b'@@ @@', diff.stdout))
    for path in sorted(paths):
      touched = compare_functions((reference / path).read_text(), (patched / path).read_text(), (candidate / path).read_text())
      print(f'P2: PASS: {path}: {", ".join(touched)}')
    for patch in files:
      apply_patch(candidate, patch)
  print('P1: PASS: all seven patches applied through quilt, fuzz 0')


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('reference', type=Path)
  parser.add_argument('candidate', type=Path)
  parser.add_argument('patches', type=Path)
  args = parser.parse_args()
  qualify(args.reference, args.candidate, args.patches.resolve())
