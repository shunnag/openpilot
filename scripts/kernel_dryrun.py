#!/usr/bin/env python3
"""Offline 19.9 discovery/pre-build replay against cached, read-only inputs.

Defaults use the research caches and /Volumes/agnos. No network or compilation.
Use --assemble as well to check the known Mac stock rebuild and tag3 bytes.
"""
import argparse
import os
from pathlib import Path
import sys

import follow_state
import kernel_assemble as assembly
from kernel_common import ROOT, read_bytes, read_json, require, write_json
from kernel_discover import discover, local_membership
from kernel_follow import baseline, expected_agnos_blob
from kernel_gates import content_diff, prebuild, recipe_files


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--builder', type=Path, default=ROOT / '.autofollow_1001/kernel_src/b.git')
  parser.add_argument('--history', type=Path, default=ROOT / '.autofollow_1001/kernel_src/k.git')
  parser.add_argument('--kernel', type=Path, default=Path('/Volumes/agnos/agnos-builder-199/agnos-kernel-sdm845'))
  parser.add_argument('--volume', type=Path, default=Path('/Volumes/agnos'))
  parser.add_argument('--out', type=Path, required=True)
  parser.add_argument('--assemble', action='store_true')
  args = parser.parse_args()
  os.environ.pop('KERNEL_FOLLOW_NETWORK', None)
  try:
    args.out.mkdir(parents=True, exist_ok=True)
    state = follow_state.load()
    replay = ROOT / 'follow/replay'
    stock = read_bytes(args.volume / 'ref199/boot-b9c9b926.img')
    fixture = read_json(replay / '19.9.json')
    heads = read_json(replay / 'kernel-heads.json')
    found = discover(args.builder, args.history, '19.9', stock, read_json(replay / 'builder-prs.json'), heads,
                     state['policy'], fallback=lambda c, h: local_membership(args.history, c, h))
    write_json(args.out / 'candidates.json', found)
    candidate = found['candidates'][0]
    require(candidate['commit'] == '8b0e4d289b246a5cc1b0484b25a3f9f8d4772544', 'unexpected first replay candidate')
    print(f"K1: OK: {candidate['commit']} from {candidate['builder_ref']}@{candidate['builder_commit']}; {candidate['branch']}")
    tag, base = baseline(state, '19.9')
    files = recipe_files(args.builder, candidate['builder_commit'])
    key = args.out / 'vble-qti.key'
    key.write_bytes(files['vble-qti.key'])
    deps = ROOT / 'follow/reference' / f'{tag}.wifi-deps.txt'
    result = prebuild(stock, fixture['manifest'], fixture['agnos_py_blob'], expected_agnos_blob(state), key,
      files, content_diff(args.kernel, base, candidate['commit'], read_json(replay / 'compare-eccd1465-8b0e4d28.json')),
      read_json(ROOT / 'follow/reference' / f'{tag}.stock.json'), state['policy'], state['status'], state['pins'],
      deps.read_text().splitlines() if deps.exists() else None)
    write_json(args.out / 'prebuild.json', result)
    require(not any(result[k] for k in ('integrity_hold', 'risk_hold', 'brake')), 'replay held')
    if args.assemble:
      import kernel_equiv as ke
      manual = {v: read_bytes(args.volume / path) for v, path in (
        ('19.8', 'bootH2E/boot-wpa3-sae-h2e-19.8-tag2.img'),
        ('19.9', 'boot199/boot-wpa3-sae-h2e-19.9-tag3.img'))}
      wpa, revert, facts = assembly.assemble(stock, read_bytes(args.volume / 'ref199/our-stock-199.Image-dtb'),
        ke.split(manual['19.9'])[1], key, state['policy'], 3, state['manual'], manual,
        local=True, replay_image=manual['19.9'], status=state['status'], auto_pins=state['pins'])
      facts['K10'] = 'historical tag 3, revert 4; local artifacts only; no reservation'
      assembly.write_artifacts(args.out / 'verified', wpa, revert, facts)
    print('DRYRUN: OK: cached 19.9 replay; no network, build, remote write or state change')
    return 0
  except Exception as error:
    print(f'K*: FAIL: {error}', file=sys.stderr)
    return 1


if __name__ == '__main__':
  sys.exit(main())
