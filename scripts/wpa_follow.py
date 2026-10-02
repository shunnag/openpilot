#!/usr/bin/env python3
"""Part 3 artifact-only probe/classify/build/test orchestration; no remote writes."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import gzip
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

import follow_state
from compose import MANIFEST
from system_probe import probe, require, sha_file
import wpa_classify as classify
import wpa_request as protocol

ROOT = Path(__file__).resolve().parents[1]


def write(path, data):
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def bundle(path, source, name):
  """Stable transport bytes let a later dryrun verify an earlier T3 result."""
  with path.open('wb') as stream, gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0) as compressed:
    with tarfile.open(fileobj=compressed, mode='w') as tar:
      for entry in [source, *sorted(source.rglob('*'))]:
        if '__pycache__' in entry.parts or entry.suffix == '.pyc':
          continue
        require(not entry.is_symlink(), 'symlink in trusted recipe bundle')
        info = tar.gettarinfo(str(entry), arcname=str(Path(name) / entry.relative_to(source)))
        info.uid = info.gid = info.mtime = 0
        info.uname = info.gname = ''
        info.mode = 0o755 if entry.is_dir() or info.mode & 0o111 else 0o644
        if entry.is_file():
          with entry.open('rb') as data:
            tar.addfile(info, data)
        else:
          tar.addfile(info)


def get_json(url):
  with urllib.request.urlopen(url, timeout=120) as response:
    return json.load(response)


def unique_systems(manifests):
  systems = {}
  for manifest in manifests:
    found = [item for item in manifest if item['name'] == 'system']
    require(len(found) == 1, 'exactly one system partition required')
    system = found[0]
    require(system.get('sparse') is True, 'unsupported non-sparse system')
    for name in ('hash', 'hash_raw'):
      require(re.fullmatch('[0-9a-f]{64}', system[name]), 'invalid manifest hash')
    if system['hash_raw'] in systems:
      require(systems[system['hash_raw']]['hash'] == system['hash'], 'conflicting sparse hashes for one raw hash')
    systems[system['hash_raw']] = system
  return systems


def probe_plan(out, replay, mode, reference=False):
  state = follow_state.load()
  follow_state.mode_value(mode)
  out.mkdir(parents=True, exist_ok=True)
  plan = {'schema': 1, 'mode': 'dryrun' if mode != 'off' or replay not in ('', 'latest') else 'off',
          'items': [], 'probes': {}, 'kernel_holds': []}
  if plan['mode'] == 'off':
    manifests = []
  elif replay in ('19.8', '19.9', 'neg-caff1d8d'):
    version = '19.9' if replay == 'neg-caff1d8d' else replay
    manifests = [json.loads((ROOT / f'follow/replay/{version}.json').read_text())['manifest']]
  else:
    manifests = [get_json(f'https://raw.githubusercontent.com/commaai/openpilot/{branch}/{MANIFEST}')
                 for branch in state['policy']['allowed_branches']]
  seen_stock = set()
  for digest, system in unique_systems(manifests).items():
    cached = state['system_probe'].get(digest)
    if cached is None:
      with urllib.request.urlopen(system['url'], timeout=120) as compressed, lzma.LZMAFile(compressed) as stream:
        facts = probe(stream, system['hash'], digest)
      cached = {k: v for k, v in facts.items() if k not in ('hash', 'hash_raw')}
    plan['probes'][digest] = cached
    if cached['kernel_modules_present']:
      plan['kernel_holds'].append(digest)
      print(f'K*: HOLD: system {digest} contains nonempty /lib/modules/4.9.*')
    stock = cached['stock_wpa_sha256']
    if '+agnos' in cached['dpkg_version']:
      raise ValueError('G8: native +agnos requires qualification; hold in v1')
    if stock in state['supplicants'] and not reference:
      print(f'G8: WARN: {digest}: known stock/override; dryrun')
      continue
    if stock not in seen_stock:
      plan['items'].append({'id': stock[:16], 'system': system, 'probe': cached, 'reference': reference})
      seen_stock.add(stock)
  write(out / 'plan.json', plan)
  write(out / 'system_probe.json', plan['probes'])
  matrix = {'include': [{'id': item['id']} for item in plan['items']]}
  if os.environ.get('GITHUB_OUTPUT'):
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
      stream.write('matrix=' + json.dumps(matrix) + '\n')
      stream.write('build=' + str(bool(plan['items'])).lower() + '\n')
  print('PROBE: dryrun; ' + str(len(plan['items'])) + ' distinct stock builds; no state changes')


def item_for(inputs, identity):
  require(re.fullmatch('[0-9a-f]{16}', identity), 'invalid item id')
  found = [x for x in protocol.read_json(inputs / 'plan.json')['items'] if x['id'] == identity]
  require(len(found) == 1, 'unknown/ambiguous item id')
  return found[0]


def classify_item(inputs, identity, out):
  item = item_for(inputs, identity)
  policy = follow_state.load()['policy']['wpa']
  out.mkdir(parents=True, exist_ok=True)
  archive = out / 'archive'
  version = item['probe']['dpkg_version']
  require(re.fullmatch(policy['version_regex'], version), 'W2: unsupported version')
  classify.online(archive, version, classify.KEYRING)
  reference = out / 'reference'
  classify.download_archive(reference, f"https://snapshot.ubuntu.com/ubuntu/{policy['snapshot']}",
                            'noble-updates', classify.REFERENCE, classify.KEYRING)
  result = classify.classify(archive, item['probe']['stock_wpa_sha256'], version, classify.KEYRING, policy, reference)
  write(out / 'classification.json', result)
  write(out / 'input.json', item)


def build(inputs, out):
  inputs, out = inputs.resolve(), out.resolve()
  policy = follow_state.load()['policy']['wpa']
  data = protocol.read_json(inputs / 'classification.json')
  item = protocol.read_json(inputs / 'input.json')
  # Reverify downloads at the job/artifact boundary, before container execution.
  checked = classify.classify(inputs / 'archive', item['probe']['stock_wpa_sha256'], item['probe']['dpkg_version'],
                              classify.KEYRING, policy, inputs / 'reference')
  require(checked == data, 'classification artifact differs from recomputed W1-W3')
  classify.classify(inputs / 'reference', policy['reference_stock_sha256'], classify.REFERENCE,
                    classify.KEYRING, policy, inputs / 'reference')
  for directory in ('archive', 'reference'):
    orig = inputs / directory / 'wpa_2.10.orig.tar.xz'
    require(sha_file(orig) == policy['orig_tarball_sha256'], 'orig tarball hash mismatch')
  out.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix='wpa-recipe-') as temporary:
    recipe = Path(temporary)
    # Minimal Ubuntu images need CA roots before their first HTTPS apt update.
    # Bootstrap from the trusted hosted runner, never from a candidate artifact.
    shutil.copyfile('/etc/ssl/certs/ca-certificates.crt', recipe / 'bootstrap-ca.crt')
    # Copy trusted recipe only. The compiler container never sees .git.
    for name in ('scripts/system_probe.py', 'scripts/wpa_patch.py'):
      (recipe / name).parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(ROOT / name, recipe / name)
    shutil.copytree(ROOT / 'userspace/wpa-build', recipe / 'userspace/wpa-build')
    subprocess.run(['docker', 'pull', policy['base_image']], check=True)
    inspection = subprocess.check_output(['docker', 'image', 'inspect', policy['base_image']])
    (out / 'base-image.json').write_bytes(inspection)
    for attempt in (1, 2):
      target = out / f'build-{attempt}'
      target.mkdir()
      command = ['docker', 'run', '--rm', '--platform', 'linux/arm64', '--security-opt=no-new-privileges',
                 '-v', f'{inputs}:/input:ro', '-v', f'{recipe}:/recipe:ro', '-v', f'{target}:/output',
                 '-e', 'WPA_VERSION=' + data['version'], '-e', 'DSC_SHA256=' + data['dsc_sha256'],
                 '-e', 'WPA_SNAPSHOT=' + policy['snapshot'], '-e', 'CHANGELOG_DATE=' + data['changelog_date'],
                 policy['base_image'], 'bash', '/recipe/userspace/wpa-build/compile-wpasupplicant.sh']
      with (out / f'build-{attempt}.log').open('wb') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    first, second = out / 'build-1', out / 'build-2'
    require(sha_file(first / 'candidate') == sha_file(second / 'candidate'), 'R1: binary builds differ')
    for name in ('candidate', 'candidate.deb', 'candidate.copyright'):
      shutil.copyfile(first / name, out / name)
    for name, member in (('stock', 'usr/sbin/wpa_supplicant'), ('stock.copyright', 'usr/share/doc/wpasupplicant/copyright')):
      (out / name).write_bytes(classify.deb_member(inputs / 'archive/stock.deb', member))
    bundle(out / 'test-suite.tar.gz', ROOT / 'userspace/wpa-build/hwsim', 'hwsim')
    bundle(out / 'patches-and-recipe.tar.gz', ROOT / 'userspace/wpa-build', 'wpa-build')
    write(out / 'input.json', item)
    write(out / 'classification.json', data)
    reference = sha_file(out / 'candidate') == policy['reference_sha256'] and data['version'] == classify.REFERENCE
    write(out / 'build-report.json', {'R1': 'PASS', 'ci_reproduced_reference': reference,
                                     'auto_publish': False, 'device_tested': False,
                                     'bootstrap_ca_sha256': sha_file(recipe / 'bootstrap-ca.crt')})
    # Debian tree delta, plus the function-context diff emitted inside the build.
    delta = subprocess.run(['diff', '-u', str(inputs / 'reference/wpa_2.10-21ubuntu0.4.dsc'),
                            str(inputs / ('archive/wpa_' + data['version'].split(':')[-1] + '.dsc'))], capture_output=True)
    require(delta.returncode in (0, 1), 'descriptor diff failed')
    (out / 'descriptor.diff').write_bytes(delta.stdout)
  print(f'R1: PASS; R0 reproduced reference: {reference}; auto_publish=false')


def runtime_tests(inputs):
  item = protocol.read_json(inputs / 'input.json')
  system = item['system']
  with tempfile.TemporaryDirectory(prefix='wpa-t1-') as tmp:
    keep = Path(tmp) / 'probe'
    with urllib.request.urlopen(system['url'], timeout=120) as compressed, lzma.LZMAFile(compressed) as stream:
      facts = probe(stream, system['hash'], system['hash_raw'], keep=keep)
    require(facts['stock_wpa_sha256'] == sha_file(inputs / 'stock'), 'test stock differs from system')
    require(hashlib.sha256(classify.deb_member(inputs / 'candidate.deb', 'usr/sbin/wpa_supplicant')).hexdigest()
            == sha_file(inputs / 'candidate'), 'candidate deb/binary differ')
    for name in ('candidate', 'stock'):
      (inputs / name).chmod(0o755)
    subprocess.run(['bash', str(ROOT / 'scripts/wpa_test.sh'), str(inputs / 'candidate'),
                    str(inputs / 'stock'), str(keep / 'system.raw')], check=True)
  write(inputs / 'test-report.json', {'T0': 'PASS', 'T1': 'PASS', 'T2': 'PASS', 'T3': 'PENDING (dryrun)'})


def request(inputs, commit, run_id):
  require(re.fullmatch('[0-9a-f]{40}', commit), 'full suite commit required')
  require(re.fullmatch('[0-9]+', run_id), 'numeric workflow run id required')
  now = datetime.now(timezone.utc)
  identity = f'wpa3-{run_id}-{sha_file(inputs / "candidate")[:12]}'
  result = {'schema': 1, 'id': identity, 'suite_commit': commit,
            'created_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'deadline': (now + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%SZ'), 'assets': {}}
  for name in sorted(protocol.ASSETS):
    result['assets'][name] = {'sha256': sha_file(inputs / name), 'size': (inputs / name).stat().st_size,
                              'url': f'https://github.com/shunnag/openpilot/releases/download/wpa-test-{identity}/{name}'}
  protocol.validate(result, commit)
  write(inputs / 'test-request.json', result)
  (inputs / 'SHA256SUMS').write_text(''.join(f'{sha_file(p)}  {p.name}\n' for p in sorted(inputs.iterdir()) if p.is_file() and p.name != 'SHA256SUMS'))
  print(f'REQUEST: {identity}: ARTIFACT ONLY; URLs are reserved for Part 4a, not published')


def result_request(requests, result_id, directory):
  require(re.fullmatch(r'wpa3-[0-9]+-[0-9a-f]{12}', result_id), 'invalid supplied result id')
  matches = [r for r in requests if r['id'] == result_id]
  if matches:
    require(len(matches) == 1, 'ambiguous result id')
    return matches[0]
  # A previous run's public request is usable only for exactly these rebuilt
  # artifacts and suite. This reads data only; request publication is Part 4a.
  path = directory / 'test-request.json'
  protocol.download(f'https://github.com/shunnag/openpilot/releases/download/wpa-test-{result_id}/test-request.json', path, 65536)
  previous = protocol.read_json(path)
  require(previous['id'] == result_id, 'public request id differs')
  def identities(data):
    return {n: (a['sha256'], a['size']) for n, a in data['assets'].items()}
  matches = [r for r in requests if r['suite_commit'] == previous['suite_commit'] and identities(r) == identities(previous)]
  require(len(matches) == 1, 'supplied result does not match rebuilt assets and suite')
  protocol.validate(previous, matches[0]['suite_commit'], protocol.utc(previous['created_at']))
  return previous


def publish(probes, builds, result_id=None):
  state = follow_state.load()  # R0 validation is independently enforced here.
  require(state['policy']['wpa']['auto_publish'] is False, 'Part 3 refuses auto_publish=true')
  plan = protocol.read_json(probes / 'plan.json')
  require(not plan['kernel_holds'], 'kernel hold: system contains 4.9 modules')
  requests = []
  for path in sorted(builds.glob('*/test-request.json')):
    data = protocol.read_json(path)
    # The request may now be past its deadline, but the supplied result must have
    # been completed within it. Validate structure at its creation time.
    protocol.validate(data, os.environ.get('GITHUB_SHA', data['suite_commit']), protocol.utc(data['created_at']))
    protocol.verify_assets(data, path.parent)
    require(protocol.read_json(path.parent / 'test-report.json') ==
            {'T0': 'PASS', 'T1': 'PASS', 'T2': 'PASS', 'T3': 'PENDING (dryrun)'}, 'T0-T2 incomplete')
    require(protocol.read_json(path.parent / 'build-report.json')['R1'] == 'PASS', 'R1 incomplete')
    require(sha_file(path.parent / 'build-1/candidate') == sha_file(path.parent / 'build-2/candidate')
            == sha_file(path.parent / 'candidate'), 'R1: artifact binaries differ')
    metadata = protocol.read_json(path.parent / 'input.json')
    require(metadata in plan['items'], 'candidate does not belong to probed plan')
    require(sha_file(path.parent / 'stock') == metadata['probe']['stock_wpa_sha256'], 'stock does not match probe')
    binary = classify.deb_member(path.parent / 'candidate.deb', 'usr/sbin/wpa_supplicant')
    copyright_data = classify.deb_member(path.parent / 'candidate.deb', 'usr/share/doc/wpasupplicant/copyright')
    require(hashlib.sha256(binary).hexdigest() == sha_file(path.parent / 'candidate')
            and hashlib.sha256(copyright_data).hexdigest() == sha_file(path.parent / 'candidate.copyright'),
            'candidate binary/copyright does not match deb')
    requests.append(data)
  require(len(requests) == len(plan['items']), 'missing WPA build/test artifacts')
  if not result_id:
    print('T3: PENDING (dryrun)')
    return
  with tempfile.TemporaryDirectory(prefix='wpa-result-') as tmp:
    expected = result_request(requests, result_id, Path(tmp))
    result, log = Path(tmp) / 'result.json', Path(tmp) / 'result.log'
    protocol.download(protocol.RESULTS + 'results/' + result_id + '.json', result, 65536)
    protocol.download(protocol.RESULTS + 'results/' + result_id + '.log', log, 1024 * 1024)
    protocol.verify_result(expected, protocol.read_json(result), log.read_bytes())
  print(f'T3: PASS: {result_id}: matched all asset hashes, suite commit, tests, deadline and log')
  if len(requests) > 1:
    print(f'T3: PENDING (dryrun): {len(requests) - 1} other candidate(s)')
  print('DRYRUN ONLY: no release/state/dispatch; policy.wpa.auto_publish=false')


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('command', choices=('probe', 'classify', 'build', 'test', 'request', 'publish'))
  parser.add_argument('--inputs', type=Path)
  parser.add_argument('--out', type=Path)
  parser.add_argument('--id')
  parser.add_argument('--replay', default='')
  parser.add_argument('--mode', default='dryrun')
  parser.add_argument('--reference', action='store_true')
  parser.add_argument('--suite-commit')
  parser.add_argument('--run-id')
  parser.add_argument('--builds', type=Path)
  parser.add_argument('--result-id')
  args = parser.parse_args()
  try:
    if args.command == 'probe':
      probe_plan(args.out, args.replay, args.mode, args.reference)
    elif args.command == 'classify':
      classify_item(args.inputs, args.id, args.out)
    elif args.command == 'build':
      build(args.inputs, args.out)
    elif args.command == 'test':
      runtime_tests(args.inputs)
    elif args.command == 'request':
      request(args.inputs, args.suite_commit, args.run_id)
    else:
      publish(args.inputs, args.builds, args.result_id)
    return 0
  except Exception as error:
    print(f'WPA: HOLD: {error}', file=sys.stderr)
    return 1


if __name__ == '__main__':
  sys.exit(main())
