#!/usr/bin/env python3
"""K0 and K2-K4: byte-derived shape, recipe, tree-diff and risk checks."""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import fnmatch
import gzip
from pathlib import Path
import re
import shlex
import subprocess
import sys

import bootimg
import kernel_equiv as ke
from kernel_common import (ROOT, Gates, blob_id, git, git_text, read_bytes,
                           read_json, require, sha256, write_json)


def stock_facts(stock):
  fields = bootimg.parse(stock)
  _, image, chain = ke.split(stock)
  return {'schema': 1, 'hash_raw': sha256(stock), 'cmdline': fields['cmdline'],
          'ikconfig_gzip_base64': base64.b64encode(gzip.compress(ke.ikconfig(image), mtime=0)).decode(),
          'dtb_sha256': sorted(sha256(dtb) for dtb in ke.dtb_blobs(chain))}


def config_bytes(facts):
  encoded = base64.b64decode(facts['ikconfig_gzip_base64'], validate=True)
  _, raw = ke.gunzip_member(encoded)
  return raw


def k0(stock, manifest, agnos_py_blob, expected_blob, key, policy):
  require(isinstance(manifest, list), 'manifest is not a partition array')
  shape = []
  for entry in manifest:
    expected_keys = set(policy['manifest_keys']) - (set() if entry['sparse'] else {'alt'})
    require(set(entry) == expected_keys, 'manifest entry key set changed')
    if 'alt' in entry:
      require(isinstance(entry['alt'], dict) and set(entry['alt']) == {'hash', 'url', 'size'}, 'manifest alt shape changed')
    shape.append({k: entry[k] for k in ('name', 'sparse', 'full_check', 'has_ab')})
  require(shape == policy['manifest_shape'], 'manifest partition shape/flags changed')
  boot = next(entry for entry in manifest if entry['name'] == 'boot')
  require(boot['sparse'] is False and boot['full_check'] is True and boot['has_ab'] is True,
          'boot must be raw, full_check and has_ab')
  require(sha256(stock) == boot['hash_raw'] == boot['hash'] and len(stock) == boot['size'], 'stock manifest hash/size mismatch')
  require(agnos_py_blob == expected_blob, 'agnos.py changed')
  fields = bootimg.parse(stock)
  ke.split(stock)
  require(not any(token.startswith('wpa3.') for token in fields['cmdline'].split()), 'stock contains wpa3 token')
  require(len((fields['cmdline'] + ' wpa3.sae=99').encode()) < 512, 'no room for cmdline tag')
  public = bootimg._openssl('rsa', '-in', key, '-pubout')
  require(bootimg.pubkey_sha256(public) == policy['vble_public_key_sha256'], 'wrong vble public key')
  require(bootimg.verify(stock, public), 'invalid stock signature')
  require(bootimg.selftest(stock, key), 'stock repack self-test differs')
  require(ke.native_sae(stock)[0] == 'none', 'stock is native or partial SAE; not a kernel follow item')
  return 'shape, agnos.py, hash, signature and byte-identical repack'


CMDLINE = r'--cmdline "(?:\\.|[^"\\\n])*"'


def normalize_recipe(script):
  functions = re.findall(r'^build_kernel\(\) \{\n.*?^\}\n', script, re.M | re.S)
  require(len(functions) == 1, 'expected one build_kernel() function')
  body, count = re.subn(CMDLINE, '--cmdline "<CMDLINE>"', functions[0])
  require(count == 1, 'expected exactly one literal --cmdline')
  return body


def recipe_cmdline(script):
  # Read the argument only from the fingerprinted function, not arbitrary shell.
  normalize_recipe(script)
  body = re.search(r'^build_kernel\(\) \{\n.*?^\}\n', script, re.M | re.S)[0]
  argument = re.search(CMDLINE, body)[0]
  require('$' not in argument and '`' not in argument, 'cmdline must be literal shell text')
  return shlex.split(argument)[1]


def recipe_files(builder, commit):
  return {path: git(builder, 'show', f'{commit}:{path}') for path in (
    'build_kernel.sh', 'Dockerfile.builder', 'tools/mkbootimg', 'vble-qti.key', 'tools/aarch64-linux-gnu-gcc.tar.gz')}


def k2(files, policy):
  require(normalize_recipe(files['build_kernel.sh'].decode()) == policy['build_kernel_normalized'], 'build_kernel() recipe changed')
  for path, expected in policy['recipe'].items():
    if path != 'build_kernel.sh':
      require(blob_id(files[path]) == expected, f'recipe blob changed: {path}')
  pointer = files['tools/aarch64-linux-gnu-gcc.tar.gz'].decode()
  expected = policy['toolchain']
  require(pointer == f"version https://git-lfs.github.com/spec/v1\noid sha256:{expected['gcc_lfs_oid']}\nsize {expected['gcc_lfs_size']}\n",
          'GCC LFS pointer changed (pointer only; LFS must never be downloaded)')
  return 'normalized function, recipe blobs and GCC pointer equal policy'


def parse_diff(names, numstat):
  fields = names.decode().split('\0')
  require(fields[-1] == '', 'unterminated name-status')
  paths = []
  index = 0
  while index < len(fields) - 1:
    status = fields[index]
    count = 2 if status.startswith(('R', 'C')) else 1
    require(status[:1] in 'ACDMRTUXB', f'invalid diff status: {status}')
    paths.extend(fields[index + 1:index + 1 + count])
    index += 1 + count
  stats = []
  for row in numstat.decode().rstrip('\0').split('\0'):
    if not row:
      continue
    added, removed, path = row.split('\t', 2)
    require(path, 'numstat must use --no-renames')
    stats.append({'path': path, 'added': None if added == '-' else int(added),
                  'removed': None if removed == '-' else int(removed)})
  require(set(paths) == {row['path'] for row in stats}, 'name-status/numstat paths differ')
  return sorted(set(paths)), stats


def content_diff(kernel, baseline, candidate, ancestry=None):
  # Two tree endpoints, deliberately NOT baseline...candidate.
  names = git(kernel, 'diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--name-status', '-z', baseline, candidate, '--')
  stats = git(kernel, 'diff', '--no-ext-diff', '--no-textconv', '--no-renames', '--numstat', '-z', baseline, candidate, '--')
  paths, rows = parse_diff(names, stats)
  if ancestry is None:
    try:
      git(kernel, 'merge-base', '--is-ancestor', baseline, candidate)
      ancestor = True
    except subprocess.CalledProcessError as error:
      if error.returncode != 1:
        raise
      require(git_text(kernel, 'rev-parse', '--is-shallow-repository') == 'false', 'negative ancestry needs full history or compare response')
      ancestor = False
    commits = int(git_text(kernel, 'rev-list', '--count', f'{baseline}..{candidate}')) if ancestor else None
  else:
    require(type(ancestry.get('behind_by')) is int and type(ancestry.get('total_commits')) is int,
            'invalid ancestry compare response')
    ancestor = ancestry['behind_by'] == 0
    commits = ancestry['total_commits'] if ancestor else None
  return {'paths': paths, 'numstat': rows, 'ancestor': ancestor, 'commits': commits,
          'baseline': baseline, 'candidate': candidate}


def k3(diff, policy):
  require(all(row['added'] is not None and row['removed'] is not None for row in diff['numstat']), 'binary file changed')
  lines = sum(row['added'] + row['removed'] for row in diff['numstat'])
  require(lines <= policy['max_changed_lines'], f"{lines} changed lines exceeds cap {policy['max_changed_lines']}")
  if diff['ancestor']:
    require(diff['commits'] <= policy['max_commits'], 'ancestor commit cap exceeded')
  return f"{lines} changed lines; ancestor={diff['ancestor']}; commits={diff['commits']}"


def brakes(status, auto_pins, policy):
  require(status['paused'] is None, f"paused: {status['paused']}")
  tested = status['device_tested']
  # Count the chain after the newest tested release, never reset it at an auto pin.
  tested_tags = [int(tag.rsplit('.', 1)[1]) for tag in tested]
  newest = max(tested_tags, default=0)
  chain = sum(int(pin['tag'].split('=')[1]) > newest for pin in auto_pins.values())
  cap = policy['max_untested_chain']
  require(cap is None or chain < cap, f'untested chain {chain} reached {cap}')
  return f'not paused; untested chain={chain}'


def k12(status, auto_pins, policy, now):
  detail = brakes(status, auto_pins, policy)
  last = status['last_auto_publish_at']
  if last:
    last = datetime.fromisoformat(last.replace('Z', '+00:00'))
    until = last + timedelta(days=policy['min_publish_interval_days'])
    require(now >= until, f'deferred until {until.isoformat()}')
  return detail + '; publish interval satisfied'


def risk_gates(gates, stock, reference, diff, policy, status, auto_pins, deps=None, builder_cmdline=None):
  facts = stock_facts(stock)
  def paths():
    hits = [path for path in diff['paths'] if any(fnmatch.fnmatchcase(path, pattern) for pattern in policy['risk_paths'])]
    require(not hits, f'risk paths: {hits}')
    return 'no risk paths (both sides of renames included)'
  gates.check('K4(a)', paths, 'risk')
  def config():
    require(config_bytes(reference) == config_bytes(facts), 'stock ikconfig changed (any option is a hold)')
    return 'stock ikconfig unchanged'
  gates.check('K4(b)', config, 'risk')
  def dtbs():
    # Strict interim rule; dt_wifi qualification is a separate reviewed change.
    require(reference['dtb_sha256'] == facts['dtb_sha256'], 'DTB multiset changed; dt_wifi is not qualified')
    return 'DTB multiset unchanged (strict interim rule)'
  gates.check('K4(c)', dtbs, 'risk')
  gates.check('K4(d)', lambda: brakes(status, auto_pins, policy), 'brake')
  if deps is None:
    gates.skip('K4(e)', 'TODO Q1: reviewed Wi-Fi dependency reference missing; dryrun only')
  else:
    def dependencies():
      require(bool(deps), 'empty dependency reference')
      hits = sorted(set(diff['paths']) & set(deps))
      require(not hits, f'Wi-Fi dependencies changed: {hits}')
      return 'Wi-Fi dependency closure unchanged'
    gates.check('K4(e)', dependencies, 'risk')
  def cmdline():
    require(reference['cmdline'] == facts['cmdline'], 'stock boot cmdline changed')
    if builder_cmdline is not None:
      require(builder_cmdline == facts['cmdline'], 'builder cmdline differs from stock/tested firmware path')
    return 'stock and builder cmdline unchanged'
  gates.check('K4(f)', cmdline, 'risk')


def prebuild(stock, manifest, agnos_blob, expected_blob, key, files, diff, reference,
             policy, status, auto_pins, deps=None):
  gates = Gates()
  gates.check('K0', lambda: k0(stock, manifest, agnos_blob, expected_blob, key, policy))
  gates.check('K2', lambda: k2(files, policy))
  gates.check('K3', lambda: k3(diff, policy), 'risk')
  risk_gates(gates, stock, reference, diff, policy, status, auto_pins, deps,
             recipe_cmdline(files['build_kernel.sh'].decode()))
  return {'gates': gates.rows, 'diff': diff, 'integrity_hold': gates.failed('integrity'),
          'risk_hold': gates.failed('risk'), 'brake': gates.failed('brake')}


def normalize_diff(diff):
  return re.sub(r'^@@ -[^ ]+ \+[^ ]+ @@', '@@ @@',
                re.sub(r'^index .*\n', '', diff, flags=re.M), flags=re.M)


def patch_paths(diff):
  paths = re.findall(r'^diff --git a/(.+) b/(.+)$', diff, re.M)
  require(len(paths) == 7 and all(a == b and '..' not in Path(a).parts and not a.startswith('/') for a, b in paths),
          'expected seven unchanged patch paths')
  return sorted(a for a, _ in paths)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--stock', type=Path, required=True)
  parser.add_argument('--candidate', required=True)
  parser.add_argument('--baseline', required=True)
  parser.add_argument('--policy', type=Path, default=ROOT / 'follow/policy.json')
  parser.add_argument('--kernel', type=Path, default=Path('/Volumes/agnos/agnos-builder-199/agnos-kernel-sdm845'))
  parser.add_argument('--builder', type=Path, default=ROOT / '.autofollow_1001/kernel_src/b.git')
  parser.add_argument('--builder-commit')
  parser.add_argument('--manifest', type=Path)
  parser.add_argument('--agnos-py-blob')
  parser.add_argument('--reference', type=Path)
  parser.add_argument('--deps', type=Path)
  parser.add_argument('--out', type=Path)
  args = parser.parse_args()
  try:
    import follow_state
    import tempfile
    state = follow_state.load()
    stock = read_bytes(args.stock)
    # The concise DESIGN command is a known-stock offline replay. Unknown
    # stocks must supply all contexts explicitly, never borrow a guessed one.
    fixture = {}
    for path in (ROOT / 'follow/replay').glob('19.*.json'):
      recorded = read_json(path)
      if next(row for row in recorded['manifest'] if row['name'] == 'boot')['hash_raw'] == sha256(stock):
        fixture = recorded
    builder_commit = args.builder_commit or fixture.get('builder_commit')
    manifest = read_json(args.manifest) if args.manifest else fixture.get('manifest')
    agnos_blob = args.agnos_py_blob or fixture.get('agnos_py_blob')
    reference_path = args.reference
    if reference_path is None:
      matches = [tag for tag, entry in state['status']['device_tested'].items() if entry['kernel_commit'].startswith(args.baseline)]
      require(len(matches) == 1, 'supply --reference for this baseline')
      reference_path = ROOT / 'follow/reference' / f'{matches[0]}.stock.json'
    require(builder_commit and manifest and agnos_blob, 'unknown stock: supply builder-commit, manifest and agnos-py-blob')
    files = recipe_files(args.builder, builder_commit)
    with tempfile.TemporaryDirectory() as work:
      key = Path(work) / 'key'
      key.write_bytes(files['vble-qti.key'])
      newest = max((p for p in [*state['manual'].values(), *state['pins'].values()] if not p.get('withdrawn')),
                   key=lambda p: int(p['tag'].split('=')[1]))
      result = prebuild(stock, manifest, agnos_blob,
                        newest['derived_from']['agnos_py_blob'], key, files,
                        content_diff(args.kernel, args.baseline, args.candidate), read_json(reference_path),
                        read_json(args.policy), state['status'], state['pins'],
                        args.deps.read_text().splitlines() if args.deps else None)
    if args.out:
      write_json(args.out, result)
    return int(result['integrity_hold'] or result['risk_hold'] or result['brake'])
  except Exception as error:
    print(f'K*: FAIL: {error}', file=sys.stderr)
    return 1


if __name__ == '__main__':
  sys.exit(main())
