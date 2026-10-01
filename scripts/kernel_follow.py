#!/usr/bin/env python3
"""Read-only workflow driver: detect, verify and report. No remote write API.

Network reads are allowed only in Actions. Local replays use kernel_dryrun.py.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from boot_download import fetch_boot
import bootimg
import follow_state
import kernel_assemble as assembly
from kernel_common import (KERNEL_URL, ROOT, api, git, git_text, network_only_in_workflow,
                           read_bytes, read_json, require, sha256, write_json)
from kernel_discover import discover, fetch_inputs, local_membership
from kernel_gates import content_diff, patch_paths, prebuild, recipe_files


def effective_mode(mode, replay):
  follow_state.mode_value(mode)
  # Part 2 cannot enter state/on, even when a repository variable says on.
  return 'dryrun' if replay or mode != 'off' else 'off'


def expected_agnos_blob(state):
  pins = [p for p in [*state['manual'].values(), *state['pins'].values()] if not p.get('withdrawn')]
  return max(pins, key=lambda p: int(p['tag'].split('=')[1]))['derived_from']['agnos_py_blob']


def baseline(state, replay):
  tag = 'agnos-19.8-wpa3.2' if replay else max(state['status']['device_tested'],
      key=lambda t: (state['status']['device_tested'][t]['at'], int(t.rsplit('.', 1)[1])))
  entry = state['status']['device_tested'][tag]
  return tag, entry['kernel_commit']


def upstream_items(state, replay, branch):
  import pins
  from compose import AGNOS_PY, MANIFEST, launch_values
  if replay:
    version = '19.9' if replay == 'neg-caff1d8d' else replay
    fixture = read_json(ROOT / 'follow/replay' / f'{version}.json')
    return [{**fixture, 'branches': ['replay'], 'replay': replay}]
  result = {}
  branches = state['policy']['allowed_branches'] if branch == 'all' else [branch]
  for name in branches:
    require(name in state['policy']['allowed_branches'], 'branch not allowed')
    # Read an immutable upstream commit, then use the existing resolver's trigger.
    commit = api(f'repos/commaai/openpilot/commits/{name}')['sha']
    def reader(path):
      import base64
      data = api(f'repos/commaai/openpilot/contents/{path}?ref={commit}')
      require(data['encoding'] == 'base64', 'unexpected contents encoding')
      return base64.b64decode(data['content'], validate=False)
    try:
      pins.resolve(reader, state['manual'], fetch_boot, state=state, mode='dryrun', branch=name)
    except follow_state.FollowNeeded as needed:
      require(needed.kind == 'kernel', 'not a kernel follow item')
      manifest = json.loads(reader(MANIFEST))
      boot = pins.partition(manifest, 'boot')
      item = result.setdefault(needed.key, {'version': launch_values(reader('launch_env.sh'))[0],
        'manifest': manifest, 'agnos_py_blob': pins.git_blob_id(reader(AGNOS_PY)),
        'branches': [], 'replay': '', 'upstream': {}})
      item['branches'].append(name)
      item['upstream'][name] = commit
      require(boot['hash_raw'] == needed.key, 'resolver/manifest stock differs')
    else:
      print(f'K0: SKIP: {name}: pinned, derived or native; no kernel follow needed')
  return list(result.values())


def detect(out, replay, mode, branch, force=False):
  network_only_in_workflow()
  os.environ['KERNEL_FOLLOW_NETWORK'] = '1'
  state = follow_state.load()
  out.mkdir(parents=True, exist_ok=True)
  mode = effective_mode(mode, replay)
  plan = {'schema': 1, 'mode': mode, 'replay': replay, 'matrix': {'include': []}, 'items': [],
          'gate_version': follow_state.gate_version(), 'deferred': []}
  write_json(out / 'plan.json', plan)
  if mode == 'off':
    print('K0: SKIP: follow mode off; no builds')
    return plan
  items = upstream_items(state, replay, branch)
  if not items:
    return plan
  require(state['status']['paused'] is None, 'paused; replay/force cannot bypass the brake')
  (out / 'manual').mkdir()
  for version, pin in state['manual'].items():
    (out / 'manual' / f'{version}.img').write_bytes(fetch_boot(pin['boot']['url'], pin['boot']['hash_raw'], pin['boot']['size']))
  # Release names are read for K10 collision detection; even dryrun never creates
  # a tag or drafts a release. Every release page, including drafts, is included.
  from kernel_common import run
  pages = json.loads(run('gh', 'api', '--paginate', '--slurp', f"repos/{state['policy']['repository']}/releases?per_page=100"))
  plan['release_names'] = [r['tag_name'] for page in pages for r in page]
  pages = json.loads(run('gh', 'api', '--paginate', '--slurp', f"repos/{state['policy']['repository']}/tags?per_page=100"))
  plan['tag_names'] = [tag['name'] for page in pages for tag in page]
  with tempfile.TemporaryDirectory(prefix='kernel-detect-') as temporary:
    temp = Path(temporary)
    builder, kernel = temp / 'builder.git', temp / 'kernel.git'
    prs, heads = fetch_inputs(builder, kernel)
    for item in items:
      boot = next(entry for entry in item['manifest'] if entry['name'] == 'boot')
      stock = fetch_boot(boot['url'], boot['hash_raw'], boot['size'])
      require(not any(pin.get('withdrawn') and pin['derived_from']['boot_hash_raw'] == sha256(stock)
                      for pin in state['pins'].values()), 'target withdrawn; force/replay cannot bypass')
      item_id = sha256(stock)[:12]
      directory = out / 'items' / item_id
      directory.mkdir(parents=True)
      (directory / 'stock.img').write_bytes(stock)
      tag, base = baseline(state, replay)
      forced = git_text(kernel, 'rev-parse', 'caff1d8d^{commit}') if replay == 'neg-caff1d8d' else None
      discovery = discover(builder, kernel, item['version'], stock, prs, heads, state['policy'],
        compare=lambda a, b: api(f'repos/commaai/agnos-kernel-sdm845/compare/{a}...{b}'),
        fallback=lambda c, h: local_membership(kernel, c, h), forced=forced)
      discovery['fetch_metrics'] = read_json(temp / 'fetch-metrics.json')
      old = state['status']['attempts'].get(sha256(stock))
      if old and not force and not replay and old.get('gate_version') == plan['gate_version']:
        attempted = datetime.fromisoformat(old['at'].replace('Z', '+00:00'))
        same_refs = old.get('refs_fingerprint') == discovery['refs_fingerprint']
        if old['result'] in ('held', 'risk_held') and same_refs and (datetime.now(timezone.utc) - attempted).days < 7:
          plan['deferred'].append({'stock': sha256(stock), 'reason': 'same held attempt younger than seven days'})
          continue
      item.update(stock_hash=sha256(stock), baseline_release=tag, baseline_commit=base,
                  discovery=discovery, pre={})
      diff_kernel = temp / f'diff-{item_id}'
      git(temp, 'init', '--bare', diff_kernel)
      git(diff_kernel, 'remote', 'add', 'origin', KERNEL_URL)
      git(diff_kernel, 'fetch', '--filter=blob:none', '--depth=1', 'origin', base,
          *(candidate['commit'] for candidate in discovery['candidates']))
      for candidate in discovery['candidates']:
        commit, builder_commit = candidate['commit'], candidate['builder_commit']
        files = recipe_files(builder, builder_commit)
        recipe = directory / builder_commit
        recipe.mkdir(exist_ok=True)
        for name, data in files.items():
          (recipe / name.replace('/', '_')).write_bytes(data)
        # K3 is a local, two-tree diff. The API supplies ancestry ONLY.
        ancestry = api(f'repos/commaai/agnos-kernel-sdm845/compare/{base}...{commit}')
        diff = content_diff(diff_kernel, base, commit, ancestry)
        deps = ROOT / 'follow/reference' / f'{tag}.wifi-deps.txt'
        pre = prebuild(stock, item['manifest'], item['agnos_py_blob'], expected_agnos_blob(state),
          recipe / 'vble-qti.key', files, diff, read_json(ROOT / 'follow/reference' / f'{tag}.stock.json'),
          state['policy'], state['status'], state['pins'], deps.read_text().splitlines() if deps.exists() else None)
        paths = patch_paths((ROOT / 'follow/kernel-patches/source.diff').read_text())
        pre['patched_blobs'] = {p: git_text(diff_kernel, 'rev-parse', f'{base}:{p}') for p in paths}
        item['pre'][commit] = pre
        print(f"K1: OK: {commit} from {candidate['builder_ref']}@{builder_commit}; branch {candidate['branch']}; proposal only")
      plan['items'].append(item_id)
      write_json(directory / 'input.json', item)
    # One global budget, including retries, across all matrix legs in this run.
    remaining = state['policy']['max_full_builds']
    for item_id in plan['items']:
      path = out / 'items' / item_id / 'input.json'
      item = read_json(path)
      eligible = [c for c in item['discovery']['candidates'] if not item['pre'][c['commit']]['integrity_hold']
                  and not item['pre'][c['commit']]['brake']]
      chosen = eligible[:remaining]
      item['discovery']['omitted_by_budget'] += eligible[remaining:]
      item['scheduled'] = [c['commit'] for c in chosen]
      for candidate in chosen:
        candidate['full_build_budget'] = 1
        remaining -= 1
        plan['matrix']['include'].append({'id': f"{item_id}-{candidate['commit'][:12]}",
                                         'item': item_id, 'commit': candidate['commit']})
      write_json(path, item)
    # A spare slot can fund one cert retry, never a fourth full build.
    for row in plan['matrix']['include']:
      if remaining:
        path = out / 'items' / row['item'] / 'input.json'
        item = read_json(path)
        next(c for c in item['discovery']['candidates'] if c['commit'] == row['commit'])['full_build_budget'] = 2
        write_json(path, item)
        remaining -= 1
  write_json(out / 'plan.json', plan)
  return plan


def verify_sums(directory):
  expected = {}
  for line in read_bytes(directory / 'SHA256SUMS', 1024 * 1024).decode().splitlines():
    digest, name = line.split('  ', 1)
    require(len(digest) == 64 and name == Path(name).name and name not in expected, 'invalid artifact checksum manifest')
    expected[name] = digest
  require(set(expected) == {p.name for p in directory.iterdir()} - {'SHA256SUMS'}, 'artifact file set differs from checksum manifest')
  for name, digest in expected.items():
    path = directory / name
    require(not path.is_symlink() and path.is_file(), 'artifact is not a regular file')
    require(path.stat().st_size <= (1024 ** 3 if name == 'source.tar.xz' else 64 * 1024 ** 2), 'artifact size limit')
    actual = hashlib.sha256()
    with path.open('rb') as stream:
      while chunk := stream.read(1024 * 1024):
        actual.update(chunk)
    require(actual.hexdigest() == digest, f'artifact checksum mismatch: {name}')


def publish(inputs, builds, out):
  state = follow_state.load()
  plan = read_json(inputs / 'plan.json')
  require(plan['mode'] in ('off', 'dryrun'), 'Part 2 accepts dryrun only')
  require(plan['gate_version'] == follow_state.gate_version(), 'gate version changed between jobs')
  out.mkdir(parents=True, exist_ok=True)
  if not plan['items']:
    print('K*: SKIP: no kernel work')
    return
  manual = {v: read_bytes(inputs / 'manual' / f'{v}.img') for v in state['manual']}
  spent = 0
  failures = []
  for item_id in plan['items']:
    try:
      directory = inputs / 'items' / item_id
      item = read_json(directory / 'input.json')
      candidates = [c for c in item['discovery']['candidates'] if c['commit'] in item['scheduled']]
      require(candidates, 'no scheduled candidate: pre-build hold or global build budget')
      stock = read_bytes(directory / 'stock.img')
      require(sha256(stock) == item['stock_hash'], 'detect stock bytes changed')
      results = {}
      for candidate in candidates:
        artifact = builds / f"kernel-{item_id}-{candidate['commit'][:12]}"
        verify_sums(artifact)
        result = read_json(artifact / 'result.json')
        require(type(result['full_builds']) is int and 0 <= result['full_builds'] <= candidate['full_build_budget'], 'full-build budget exceeded')
        spent += result['full_builds']
        require(spent <= state['policy']['max_full_builds'], 'global full-build cap exceeded')
        require(result['result'] in ('complete', 'rejected'), 'candidate job did not finish; uniqueness unresolved')
        require(result['full_builds'] >= 1, 'conclusive result without a recorded full build')
        key = directory / candidate['builder_commit'] / 'vble-qti.key'
        fields = bootimg.parse(stock)
        rebuilt_kernel = read_bytes(artifact / 'stock.Image-dtb')
        rebuilt = bootimg.repack(fields['header'], rebuilt_kernel, fields['cmdline'], key)
        import kernel_equiv as ke
        ok, why = ke.rebuild_equivalent(stock, rebuilt)
        print(f"K5: {'OK' if ok else 'FAIL'}: {candidate['commit']}: {'; '.join(why)}")
        results[candidate['commit']] = {'reproduced': ok, 'why': why}
      if item['replay'] == 'neg-caff1d8d':
        require(len(results) == 1 and not next(iter(results.values()))['reproduced'], 'negative replay unexpectedly reproduced')
        print('Q3: OK: forced parent rejected by rebuild equivalence')
        write_json(out / 'negative-replay.json', results)
        continue
      chosen = assembly.select_candidate(candidates, results)
      print(f"K1: OK: uniqueness resolved by K5: {chosen['commit']}")
      artifact = builds / f"kernel-{item_id}-{chosen['commit'][:12]}"
      key = directory / chosen['builder_commit'] / 'vble-qti.key'
      number, tag_note = assembly.dry_tags(state, item['replay'], plan['release_names'] + plan['tag_names'])
      # K0/K2 are rechecked on detect data, not claims from the build job.
      from kernel_gates import k0, k2
      k0(stock, item['manifest'], item['agnos_py_blob'], expected_agnos_blob(state), key, state['policy'])
      recipe = directory / chosen['builder_commit']
      k2({p: read_bytes(recipe / p.replace('/', '_')) for p in (*state['policy']['recipe'], 'tools/aarch64-linux-gnu-gcc.tar.gz')}, state['policy'])
      wpa, revert, facts = assembly.assemble(stock, read_bytes(artifact / 'stock.Image-dtb'),
        read_bytes(artifact / 'wpa3.Image'), key, state['policy'], number, state['manual'], manual,
        proof=read_json(artifact / 'patch-proof.json'), pre=item['pre'][chosen['commit']],
        manifests=read_json(artifact / 'manifests.json'), baseline_release=item['baseline_release'],
        status=state['status'], auto_pins=state['pins'], replay_image=manual.get(item['replay']), patch_dir=artifact)
      facts.update(candidate=chosen, stock_rebuild_results=results, prebuild=item['pre'][chosen['commit']],
                   K10=tag_note, proposed_tag=number, proposed_revert_tag=number + 1,
                   toolchain=state['policy']['toolchain'], recipe=state['policy']['recipe'],
                   base_image=state['policy']['builder_base_image'],
                   discovery_measurements={'fetch': item['discovery']['fetch_metrics'],
                                           'fallback': item['discovery']['fallback_measurements']},
                   gate_version=plan['gate_version'], refs_fingerprint=item['discovery']['refs_fingerprint'],
                   risk_hold=item['pre'][chosen['commit']]['risk_hold'], full_builds_spent=spent)
      dest = out / item_id
      dest.mkdir()
      # Copy data only, including source and future reviewed references.
      for name in ('source.tar.xz', 'source.diff', 'patch-proof.json', 'manifests.json', 'SOURCE.txt', 'stock-rebuild-report.txt', 'build.log',
                   'builder-image.json', 'dpkg.txt', 'metrics.txt', 'wifi-objects.json',
                   'rebuilt-objects.txt', 'wifi-deps.txt', 'stock.json', *state['policy']['patches']):
        if (artifact / name).exists():
          shutil.copyfile(artifact / name, dest / name)
      assembly.write_artifacts(dest, wpa, revert, facts)
      print(f'K10: OK: {tag_note}; N={number}, revert={number + 1}')
    except Exception as error:
      failures.append(f'{item_id}: {error}')
      print(f'K*: FAIL: {failures[-1]}')
  write_json(out / 'run.json', {'mode': 'dryrun', 'full_builds_spent': spent, 'failures': failures,
    'todos': ['Q1: review and commit dependency, rebuilt-object and Wi-Fi manifests from CI artifacts',
              'Q5: run the identical replay twice; compare wifi-objects.json before qualifying K8',
              'Q7: inspect metrics.txt for hosted runner wall time/free-space minimum; no local estimates used',
              'Q8/Q10: confirm job/concurrency/checkout behavior on GitHub; no write-token job exists in Part 2']})
  require(not failures, '; '.join(failures))


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  sub = parser.add_subparsers(dest='command', required=True)
  detect_parser = sub.add_parser('detect')
  detect_parser.add_argument('--replay', choices=('', 'latest', '19.9', '19.8', 'neg-caff1d8d'), default='')
  detect_parser.add_argument('--mode', choices=follow_state.MODES, default='off')
  detect_parser.add_argument('--branch', choices=('all', *follow_state.BRANCHES), default='all')
  detect_parser.add_argument('--force', action='store_true')
  detect_parser.add_argument('--out', type=Path, required=True)
  publish_parser = sub.add_parser('publish')
  publish_parser.add_argument('--inputs', type=Path, required=True)
  publish_parser.add_argument('--builds', type=Path, required=True)
  publish_parser.add_argument('--out', type=Path, required=True)
  args = parser.parse_args()
  try:
    if args.command == 'detect':
      plan = detect(args.out, '' if args.replay == 'latest' else args.replay, args.mode, args.branch, args.force)
      if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
          stream.write(f"matrix={json.dumps(plan['matrix'], separators=(',', ':'))}\n")
          stream.write(f"build={'true' if plan['matrix']['include'] else 'false'}\n")
    else:
      publish(args.inputs, args.builds, args.out)
    return 0
  except Exception as error:
    print(f'K*: FAIL: {error}', file=sys.stderr)
    return 1


if __name__ == '__main__':
  sys.exit(main())
