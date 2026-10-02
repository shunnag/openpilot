#!/usr/bin/env python3
"""Pull-only, data-only Mac mini runner. Never grants the VM a host mount or token."""
import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from system_probe import require, sha_file
from wpa_classify import deb_member
from wpa_request import ASSETS, TESTS, download, read_json, validate, verify_assets

PROFILE = 'wpa3hwsim'
REMOTE = 'https://github.com/shunnag/wpa3-test-results.git'
SUITE_FILES = {'suite.py': 'userspace/wpa-build/hwsim/suite.py', 'vm_run.sh': 'follow/macmini/vm_run.sh'}


def run(*args, **kwargs):
  kwargs.setdefault('check', True)
  return subprocess.run([str(a) for a in args], **kwargs)


def output(*args):
  return subprocess.check_output([str(a) for a in args], text=True).strip()


def stamp():
  return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def pinned_suite(repo, commit, directory):
  require(re.fullmatch('[0-9a-f]{40}', commit or ''), '--suite-commit must be a reviewed full git commit')
  require(output('git', '-C', repo, 'rev-parse', commit + '^{commit}') == commit, 'suite commit not present locally')
  for name, path in SUITE_FILES.items():
    data = subprocess.check_output(['git', '-C', str(repo), 'show', f'{commit}:{path}'])
    (directory / name).write_bytes(data)


def discover(work, commit, results):
  requests = []
  for page in range(1, 11):
    target = work / 'releases.json'
    download(f'https://api.github.com/repos/shunnag/openpilot/releases?per_page=100&page={page}', target, 8 * 1024**2)
    releases = read_json(target)
    require(isinstance(releases, list), 'invalid releases API response')
    for release in releases:
      tag = release.get('tag_name', '')
      if release.get('draft') or not re.fullmatch(r'wpa-test-wpa3-[0-9]+-[0-9a-f]{12}', tag):
        continue
      request_id = tag.removeprefix('wpa-test-')
      if (results / 'results' / (request_id + '.json')).exists():
        continue
      assets = [a for a in release['assets'] if a['name'] == 'test-request.json']
      if len(assets) != 1:
        continue
      url = f'https://github.com/shunnag/openpilot/releases/download/{tag}/test-request.json'
      require(assets[0]['browser_download_url'] == url, 'request asset URL mismatch')
      path = work / (request_id + '.json')
      download(url, path, 65536)
      request = read_json(path)
      try:
        validate(request, commit)
        require(request['id'] == request_id, 'release/request id mismatch')
      except ValueError as error:
        print(f'REJECT {request_id}: {error}', flush=True)
        continue
      requests.append(request)
    if len(releases) < 100:
      return sorted(requests, key=lambda r: r['created_at'])
  raise ValueError('release discovery page cap reached; no partial processing')


def vm(work):
  """The sole VM adapter; all transferred commands come from the pinned suite."""
  # A previously running profile must be stopped so mount=none takes effect.
  run('colima', 'stop', PROFILE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
  try:
    run('colima', 'start', PROFILE, '--vm-type', 'vz', '--arch', 'aarch64', '--runtime', 'containerd',
        '--mount=none', '--ssh-agent=false', '--port-forwarder=none')
    mounts = subprocess.run(['colima', 'ssh', PROFILE, '--', 'findmnt', '-rn', '-t', 'virtiofs,9p,fuse.sshfs'],
                            capture_output=True, text=True)
    require(mounts.returncode == 1 and not mounts.stdout.strip(), 'VM still has host mounts; refusing candidate execution')
    run('colima', 'ssh', PROFILE, '--', 'sudo', 'rm', '-rf', '/tmp/wpa3-hwsim')
    run('colima', 'ssh', PROFILE, '--', 'sudo', 'mkdir', '-p', '/tmp/wpa3-hwsim')
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as tar:
      for name in ('candidate', 'stock', 'suite.py', 'vm_run.sh'):
        tar.add(work / name, arcname=name, recursive=False)
    run('colima', 'ssh', PROFILE, '--', 'sudo', 'tar', '-xf', '-', '-C', '/tmp/wpa3-hwsim', input=payload.getvalue())
    with (work / 'private-vm.log').open('wb') as log:
      result = subprocess.run(['colima', 'ssh', PROFILE, '--', 'sudo', 'bash', '/tmp/wpa3-hwsim/vm_run.sh'],
                              stdout=log, stderr=subprocess.STDOUT, timeout=1200)
    suite_text = output('colima', 'ssh', PROFILE, '--', 'sudo', 'cat', '/tmp/wpa3-hwsim/suite-result.json')
    kernel = output('colima', 'ssh', PROFILE, '--', 'uname', '-r')
    suite = json.loads(suite_text)
    require(result.returncode == 0 or suite.get('passed') is False, 'VM command failed without suite failure')
    return suite, kernel
  finally:
    run('colima', 'stop', PROFILE)


def results_clone(directory):
  if not directory.exists():
    run('git', '-c', 'credential.helper=', 'clone', REMOTE, directory)
  require(output('git', '-C', directory, 'remote', 'get-url', 'origin') == REMOTE, 'unexpected results remote')
  require(output('git', '-C', directory, 'branch', '--show-current') == 'main', 'results clone must be on main')
  require(not output('git', '-C', directory, 'status', '--porcelain'), 'results clone is dirty; review local results first')
  run('git', '-C', directory, '-c', 'credential.helper=', 'pull', '--ff-only', 'origin', 'main')


def write_result(request, suite, kernel, directory, colima):
  # Publish a positive allowlist, not raw hostapd/supplicant or VM output.
  require(isinstance(suite.get('tests'), list) and len(suite['tests']) == len(TESTS)
          and {t.get('name') for t in suite['tests']} == TESTS, 'invalid suite case list')
  require(re.fullmatch(r'[A-Za-z0-9_.+-]{1,100}', kernel), 'invalid VM kernel version')
  tests = [{'name': t['name'], 'passed': t.get('passed') is True} for t in suite['tests']]
  log = ''.join(f"{t['name']}: {'PASS' if t['passed'] else 'FAIL'}\n" for t in tests)
  result = {'schema': 1, 'request_id': request['id'], 'suite_commit': request['suite_commit'],
            'assets': {n: a['sha256'] for n, a in request['assets'].items()}, 'tested_at': stamp(),
            'colima_version': colima, 'kernel_version': kernel, 'tests': tests,
            'passed': suite.get('passed') is True and all(t['passed'] for t in tests)}
  directory.mkdir(parents=True, exist_ok=True)
  path = directory / (request['id'] + '.log')
  path.write_text(log)
  result['log_sha256'] = sha_file(path)
  (directory / (request['id'] + '.json')).write_text(json.dumps(result, indent=2) + '\n')
  print(log, end='', flush=True)
  return result


def push_result(directory, request_id):
  require(output('git', '-C', directory, 'remote', 'get-url', '--push', 'origin') == REMOTE, 'unexpected results push URL')
  run('git', '-C', directory, 'add', '--', f'results/{request_id}.json', f'results/{request_id}.log')
  staged = output('git', '-C', directory, 'diff', '--cached', '--name-only').splitlines()
  require(set(staged) == {f'results/{request_id}.json', f'results/{request_id}.log'}, 'unexpected staged results paths')
  run('git', '-C', directory, '-c', 'core.hooksPath=/dev/null', '-c', 'user.name=WPA3 hwsim',
      '-c', 'user.email=wpa3-hwsim@localhost', '-c', 'commit.gpgsign=false', 'commit', '-m', f'T3 results: {request_id}')
  # Git asks the keychain helper for the password only on this exact repository.
  # The token is never a command argument, environment variable, URL or log line.
  env = {k: v for k, v in os.environ.items() if not k.startswith(('GIT_TRACE', 'GIT_CONFIG'))
         and k not in ('GIT_CURL_VERBOSE', 'GH_TOKEN', 'GITHUB_TOKEN')}
  env.update({'GIT_ASKPASS': str(ROOT / 'follow/macmini/keychain_askpass.sh'), 'GIT_TERMINAL_PROMPT': '0'})
  run('git', '-C', directory, '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null',
      '-c', 'http.followRedirects=false', 'push', REMOTE, 'HEAD:main', env=env)


def self_test(work, commit):
  deb = work / 'reference.deb'
  download('https://github.com/shunnag/openpilot/releases/download/agnos-19.8-wpa3.2/'
           'wpasupplicant_2.10-21ubuntu0.4+agnos1_arm64.deb', deb)
  require(sha_file(deb) == '6c25f12556be3245f74cf57c6dc4640716ecd20b9ddc7cf24deb571befdf14f2', 'reference deb changed')
  (work / 'candidate').write_bytes(deb_member(deb, 'usr/sbin/wpa_supplicant'))
  (work / 'candidate.copyright').write_bytes(deb_member(deb, 'usr/share/doc/wpasupplicant/copyright'))
  require(sha_file(work / 'candidate') == '139be31dde5f000d99af5f2692b792989bb3d6cbe332d662b2ddf822de89fd93', 'reference binary changed')
  stock_deb = work / 'stock.deb'
  download('https://snapshot.ubuntu.com/ubuntu/20260925T120000Z/pool/main/w/wpa/wpasupplicant_2.10-21ubuntu0.4_arm64.deb', stock_deb)
  require(sha_file(stock_deb) == 'dbb661fe2e7e84bfc3c5d57aa81a558fbdb5f7b8a857221805791af35a7df117', 'reference stock deb changed')
  (work / 'stock').write_bytes(deb_member(stock_deb, 'usr/sbin/wpa_supplicant'))
  (work / 'stock.copyright').write_bytes(deb_member(stock_deb, 'usr/share/doc/wpasupplicant/copyright'))
  require(sha_file(work / 'stock') == 'b0f1c8ee9bb32153faed468c68390db4691b252ffd6a90e6d3d7b49f4d106bdd', 'reference stock changed')
  return {'id': 'self-test-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'), 'suite_commit': commit,
          'assets': {n: {'sha256': sha_file(work / n)} for n in ('candidate', 'candidate.copyright', 'stock', 'stock.copyright')}}


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--dry-run', action='store_true')
  parser.add_argument('--self-test', action='store_true')
  parser.add_argument('--suite-commit', default=os.environ.get('WPA3_SUITE_COMMIT'))
  parser.add_argument('--suite-repo', type=Path, default=ROOT)
  parser.add_argument('--state-dir', type=Path, default=Path.home() / 'Library/Application Support/wpa3-hwsim')
  parser.add_argument('--results-repo', type=Path, default=Path.home() / 'wpa3-test-results')
  args = parser.parse_args()
  def interrupted(_signum, _frame):
    raise InterruptedError('runner interrupted; stopping VM')
  signal.signal(signal.SIGTERM, interrupted)
  args.state_dir.mkdir(parents=True, exist_ok=True)
  lock = args.state_dir / 'poll.lock'
  try:
    lock.mkdir()
  except FileExistsError:
    print('Another poll is running (or stale poll.lock needs review)')
    return 0
  try:
    with tempfile.TemporaryDirectory(prefix='run-', dir=args.state_dir) as temporary:
      work = Path(temporary)
      pinned_suite(args.suite_repo, args.suite_commit, work)
      colima = output('colima', 'version')
      if args.self_test:
        requests = [self_test(work, args.suite_commit)]
      else:
        results_clone(args.results_repo)
        requests = discover(work, args.suite_commit, args.results_repo)
        print(f'OPEN REQUESTS: {len(requests)}', flush=True)
      for request in requests:
        if not args.self_test:
          validate(request, args.suite_commit)
          for name in sorted(ASSETS):
            download(request['assets'][name]['url'], work / name, request['assets'][name]['size'])
          verify_assets(request, work)
        try:
          suite, kernel = vm(work)
        except Exception as error:
          print(f"INFRA: {type(error).__name__}; no pass result written", file=sys.stderr)
          raise
        destination = args.state_dir / 'self-tests' if args.self_test else args.results_repo / 'results'
        result = write_result(request, suite, kernel, destination, colima)
        if not args.dry_run and not args.self_test:
          push_result(args.results_repo, request['id'])
        print(f"Result: {destination / (request['id'] + '.json')}", flush=True)
        if args.self_test and not result['passed']:
          return 1
      return 0
  finally:
    lock.rmdir()


if __name__ == '__main__':
  try:
    sys.exit(main())
  except Exception as error:
    print(f'RUNNER: FAIL: {error}', file=sys.stderr)
    sys.exit(1)
