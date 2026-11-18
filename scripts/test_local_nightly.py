"""Run the local nightly runner and its launcher with offline git/gh/build stand-ins."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

from follow_state import BRANCHES
from test_publish_branch import FAKE

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'ghp_' + 'LocalRunnerSentinel0' * 2
REAL_GIT = shutil.which('git')
REAL_MV = shutil.which('mv')
STAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z')

# Prefix for the git stand-in: records the git configuration environment and can
# break the run in ways publish_branch.sh never does itself.
RECORD_GIT = r'''
import json as _json
import os as _os
import signal as _signal
from pathlib import Path as _Path
import sys as _sys
if _os.environ.get('RECORD_GIT_ENV'):
  with open(_os.environ['RECORD_GIT_ENV'], 'a') as _log:
    _log.write(_json.dumps({_k: _v for _k, _v in _os.environ.items() if _k.startswith('GIT_')}) + '\n')
if _sys.argv[1:3] == ['init', '--bare'] and _sys.argv[3].endswith('/wpa3.git'):
  if _os.environ.get('NO_RESULT_BRANCH'):
    # A branch folder publish_branch.sh cannot write: it stops before its EXIT trap.
    _path = _Path(_os.environ['RUNNER_TEMP']) / _os.environ['NO_RESULT_BRANCH']
    _path.mkdir()
    _path.chmod(0o500)
  if _os.environ.get('KILL_WORKER'):
    _os.kill(_os.getppid(), _signal.SIGKILL)
if _os.environ.get('RECORD_URL_CONFIG') and _sys.argv[1:2] == ['ls-remote']:
  # What a real git would see from here: url.* rules of any repository it discovers.
  import subprocess as _subprocess
  _seen = _subprocess.run([_os.environ['REAL_GIT'], 'config', '--get-regexp', r'^url\.'], capture_output=True, text=True).stdout
  with open(_os.environ['RECORD_URL_CONFIG'], 'a') as _log:
    _log.write(_seen)
'''

# Prefix for the python3 stand-in: records what issues.py would see.
RECORD_ISSUES = r'''
import json as _json
import os as _os
import sys as _sys
if _sys.argv[1:2] == ['scripts/issues.py'] and _os.environ.get('RECORD_ISSUES'):
  _args = _sys.argv[1:]
  _log_path = _args[_args.index('--log') + 1] if '--log' in _args else ''
  _keys = ('WPA3_LOCAL_RUN', 'WPA3_LOCAL_RUN_ID', 'RUNNER_TEMP', 'WPA3_WORK_ROOT', 'WPA3_EXPORT_DIR', 'TMPDIR', 'GITHUB_RUN_ID')
  with open(_os.environ['RECORD_ISSUES'], 'a') as _log:
    _log.write(_json.dumps({'args': _args, 'env': {_k: _os.environ.get(_k) for _k in _keys},
                            'log': open(_log_path).read() if _log_path and _os.path.exists(_log_path) else None}) + '\n')
'''

# Moves the lock as asked, but first lets another run take it, once.
MV = r'''
import os
from pathlib import Path
import sys
args = sys.argv[1:]
if os.environ.get('SWAP_OWNER') and len(args) == 2 and args[0].endswith('/lock') and '.stale.' in args[1]:
  Path(args[0], 'owner').write_text(os.environ['SWAP_OWNER'])
os.execv(os.environ['REAL_MV'], [os.environ['REAL_MV'], *args])
'''

GH = r'''
import json
import os
from pathlib import Path
import subprocess
import sys
import time

args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as log:
  log.write(json.dumps(['gh', *args]) + '\n')

def fail(stage):
  branch = os.environ.get('BRANCH', '')
  if os.environ.get('FAIL_STAGE') == stage and os.environ.get('FAIL_BRANCH', branch) == branch:
    print('fixture failure: ' + stage, file=sys.stderr)
    sys.exit(17)

if args[0] == 'api':
  endpoint = next(a for a in args if a.startswith('repos/'))
  if endpoint.endswith('/actions/workflows/nightly.yml'):
    if os.environ.get('HANG_STATE_PID'):
      child = subprocess.Popen(['sleep', '300'])
      Path(os.environ['HANG_STATE_PID']).write_text(str(child.pid))
      time.sleep(300)
    fail('workflow-state')
    states = os.environ.get('WORKFLOW_STATES', os.environ.get('WORKFLOW_STATE', 'active')).split(',')
    counter = Path(os.environ['CALLS'] + '.states')
    seen = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(seen + 1))
    print(states[min(seen, len(states) - 1)])
  elif '/git/commits/' in endpoint:
    print('wpa3-evaluated\n\nBranch: ' + os.environ['BRANCH'] + '\nHead: ' + os.environ['WPA3_CI_HEAD'] +
          '\nMode: ' + os.environ['WPA3_FOLLOW_MODE'] + '\nUpstream: ' + os.environ.get('MARKER_UPSTREAM', 'd' * 40) +
          '\nFork: ' + 'b' * 40 + '\n')
  elif '/commits/' in endpoint:
    if os.environ.get('HANG_PID'):
      child = subprocess.Popen(['sleep', '300'])
      Path(os.environ['HANG_PID']).write_text(str(child.pid))
      time.sleep(300)
    print('0')
  else:
    sys.exit(98)
elif args[:2] == ['variable', 'get']:
  mode = os.environ.get('VARIABLE_MODE')
  if mode is None:
    print('variable WPA3_FOLLOW_MODE was not found', file=sys.stderr)
    sys.exit(1)
  if mode == 'error':
    print('failed to get variable WPA3_FOLLOW_MODE: HTTP 502', file=sys.stderr)
    sys.exit(1)
  print(mode)
elif args[:2] == ['variable', 'list']:
  if os.environ.get('VARIABLE_LIST') == 'error':
    sys.exit(1)
  print(os.environ.get('VARIABLE_LIST', 'OTHER_VARIABLE'))
elif args[:2] == ['workflow', 'run']:
  fail('dispatch')
else:
  sys.exit(98)
'''


def lstart(pid):
  return subprocess.run(['bash', '-c', 'ps -o lstart= -p "$1" | tr -s " " | sed "s/^ //; s/ $//"', '_', str(pid)],
                        env={**os.environ, 'LC_ALL': 'C'}, capture_output=True, text=True, check=True).stdout.strip()


def gone(pid, seconds=5):
  for _ in range(seconds * 10):
    try:
      os.kill(pid, 0)
    except ProcessLookupError:
      return True
    time.sleep(0.1)
  return False


class LocalNightlyTests(unittest.TestCase):
  def setUp(self):
    (ROOT / '.tmp').mkdir(exist_ok=True)
    tmp = tempfile.TemporaryDirectory(dir=ROOT / '.tmp', prefix='test-local-')
    self.addCleanup(tmp.cleanup)
    self.addCleanup(lambda: subprocess.run(['chmod', '-R', 'u+w', tmp.name]))
    self.work = Path(tmp.name)
    self.bin = self.work / 'bin'
    self.bin.mkdir()
    for name, body in (('git', RECORD_GIT + textwrap.dedent(FAKE)), ('gh', GH), ('mv', MV),
                       ('python3', RECORD_ISSUES + textwrap.dedent(FAKE)), ('curl', textwrap.dedent(FAKE))):
      path = self.bin / name
      path.write_text(f'#!{sys.executable}\n' + body)
      path.chmod(0o755)
    self.log = self.work / 'calls'
    self.log.write_text('')
    self.root = self.work / 'root'
    self.git_env = self.work / 'git-env'
    self.issue_env = self.work / 'issue-env'
    self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                'CALLS': str(self.log), 'GH_REPO': 'example/openpilot', 'GH_TOKEN': TOKEN,
                'WPA3_CI_HEAD': 'f' * 40, 'WPA3_WORK_ROOT': str(self.root), 'VARIABLE_MODE': 'off',
                'LOCAL_NIGHTLY_LOCK_WAIT': '0', 'RECORD_GIT_ENV': str(self.git_env),
                'RECORD_ISSUES': str(self.issue_env), 'REAL_MV': REAL_MV, 'REAL_GIT': REAL_GIT,
                # Left over from an Actions-like shell; the runner must ignore all of these.
                'GITHUB_RUN_ID': '3', 'GITHUB_OUTPUT': str(self.work / 'stray-output'), 'BARE_REPO': '/nonexistent',
                'DRY_WORKFLOW_STATE': 'disabled_manually', 'WPA3_FOLLOW_MODE': 'on', 'GIT_CONFIG_GLOBAL': '/nonexistent'}

  def environment(self, env):
    return {key: value for key, value in {**self.env, **env}.items() if value is not None}

  def run_local(self, **env):
    return subprocess.run(['bash', 'scripts/local_nightly.sh'], cwd=ROOT, timeout=300,
                          env=self.environment(env), capture_output=True, text=True)

  def calls(self, tool=None):
    rows = [json.loads(row) for row in self.log.read_text().splitlines()]
    return [row for row in rows if not tool or row[0] == tool]

  def issue_calls(self, kind):
    return [row[3:] for row in self.calls('python3') if row[1:3] == ['scripts/issues.py', kind]]

  def issue_records(self):
    return [json.loads(row) for row in self.issue_env.read_text().splitlines()] if self.issue_env.exists() else []

  def failure(self):
    failure, = [row for row in self.issue_calls('local-runner') if '--reason' in row]
    return failure

  def pushes(self):
    return [row for row in self.calls('git') if 'push' in row]

  def dispatches(self):
    return [row for row in self.calls('gh') if row[1:3] == ['workflow', 'run']]

  def summary(self, result):
    return [line for line in result.stdout.splitlines() if line.startswith('- ')]

  def assert_clean_work_root(self):
    self.assertEqual(list((self.root / 'runs').iterdir()), [])
    self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.startswith('lock')), [])

  def test_four_branches_publish_and_close_the_failure_issue(self):
    result = self.run_local()
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertEqual(self.summary(result), [f'- {branch}: success' for branch in BRANCHES])
    self.assertEqual([line[4:] for line in result.stdout.splitlines() if line.startswith('=== ')], list(BRANCHES))
    leases = [row for row in self.pushes() if any(arg.startswith('--force-with-lease=') for arg in row)]
    self.assertEqual([row[-1].split(':refs/heads/')[1] for row in leases], list(BRANCHES))
    self.assertEqual(self.issue_calls('local-runner'), [['--token-check'], ['--close']])
    self.assertEqual(self.dispatches(), [])
    creates = [row for row in self.calls('python3') if row[1:3] == ['scripts/nightly_skip.py', 'create']]
    self.assertTrue(all(row[row.index('--mode') + 1] == 'off' for row in creates))
    self.assertEqual(len(creates), 4)
    # issues.py sees the local-run marker, one run id, and no Actions run id.
    records = self.issue_records()
    self.assertGreaterEqual(len(records), 2)
    ids = {record['env']['WPA3_LOCAL_RUN_ID'] for record in records}
    self.assertEqual(len(ids), 1)
    self.assertRegex(ids.pop(), STAMP)
    self.assertTrue(all(record['env']['WPA3_LOCAL_RUN'] == '1' and record['env']['GITHUB_RUN_ID'] is None
                        and record['env']['WPA3_WORK_ROOT'] == str(self.root) for record in records))
    self.assert_clean_work_root()
    self.assertFalse((self.work / 'stray-output').exists())

  def test_held_branch_fails_the_run_after_every_other_branch(self):
    result = self.run_local(FAIL_STAGE='gates', FAIL_BRANCH='nightly')
    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
    summary = self.summary(result)
    self.assertTrue(summary[0].startswith('- nightly: held/failed'))
    self.assertEqual(summary[1:], [f'- {branch}: success' for branch in BRANCHES[1:]])
    # Each published branch pushes lastgood, the branch with a lease and its marker.
    self.assertEqual(len(self.pushes()), 3 * 3)
    self.assertEqual(self.issue_calls('hold')[0][:2], ['--branch', 'nightly'])
    # The branch hold is publish_branch.sh's own report: no runner issue and no closure.
    self.assertEqual(self.issue_calls('local-runner'), [['--token-check']])
    kept = self.root / 'last-failed'
    self.assertIn('held/failed', (kept / 'nightly/result').read_text())
    self.assertTrue((kept / 'runner.log').exists())
    self.assertFalse(any(path.name.endswith('.git') for path in kept.rglob('*')))
    self.assert_clean_work_root()

  def test_disabled_nightly_pauses_every_branch(self):
    for scenario in ({'WORKFLOW_STATE': 'disabled_manually', 'PENDING': '1'},
                     {'WORKFLOW_STATE': 'disabled_fork', 'PENDING': '1'},
                     {'WORKFLOW_STATE': 'disabled_inactivity', 'PENDING': '1'},
                     {'WORKFLOW_STATES': 'active,disabled_manually'}):
      with self.subTest(scenario=scenario):
        self.log.write_text('')
        Path(str(self.log) + '.states').unlink(missing_ok=True)
        result = self.run_local(**scenario)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.summary(result), [f'- {branch}: skipped (nightly disabled)' for branch in BRANCHES])
        self.assertEqual(self.pushes(), [])
        self.assertEqual(self.dispatches(), [])
        self.assertFalse(any(row[1] == 'scripts/issues.py' and row[2] != 'local-runner' for row in self.calls('python3')))
        if 'WORKFLOW_STATES' not in scenario:
          # A paused nightly runs nothing, as a disabled workflow on Actions.
          self.assertEqual(self.calls('git'), [])

  def test_pending_branches_request_follow_once(self):
    expected = [['gh', 'workflow', 'run', 'follow.yml', '--ref', 'wpa3-ci', '--repo', 'example/openpilot',
                 '-f', 'reason=nightly-pending']]
    result = self.run_local(PENDING='1')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertEqual(self.summary(result), [f'- {branch}: pending' for branch in BRANCHES])
    self.assertEqual(self.dispatches(), expected)
    self.log.write_text('')
    result = self.run_local(PENDING_BRANCH=BRANCHES[-1])
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertEqual(self.summary(result), [f'- {branch}: success' for branch in BRANCHES[:-1]] + [f'- {BRANCHES[-1]}: pending'])
    self.assertEqual(self.dispatches(), expected)
    self.log.write_text('')
    result = self.run_local(PENDING='1', FAIL_STAGE='dispatch')
    self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
    self.assertEqual(self.failure()[:2], ['--reason', 'follow.yml dispatch for pending branches failed; the token needs Actions write for it'])

  def test_matching_markers_skip_every_branch_early(self):
    # Each branch has its own marker, as on GitHub; GITHUB_REF must be the runner's.
    result = self.run_local(MARKER_UPSTREAM='a' * 40, MARKER_PER_BRANCH='1')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertEqual(result.stdout.count('early-skip: unchanged'), len(BRANCHES))
    self.assertEqual(self.summary(result), [f'- {branch}: unchanged' for branch in BRANCHES])
    self.assertFalse(any('fetch' in row or 'push' in row for row in self.calls('git')))

  def test_failure_issue_opens_on_a_runner_failure_and_closes_after_a_good_run(self):
    result = self.run_local(FAIL_STAGE='workflow-state')
    self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
    self.assertEqual(self.calls('git'), [])
    self.assertEqual(self.issue_calls('local-runner'), [['--token-check'], ['--reason', 'nightly workflow state could not be read']])
    self.log.write_text('')
    result = self.run_local()
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertEqual(self.issue_calls('local-runner'), [['--token-check'], ['--close']])

  def test_branch_without_a_result_is_reported_with_the_log(self):
    result = self.run_local(NO_RESULT_BRANCH='nightly-chestnut')
    self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
    summary = self.summary(result)
    self.assertRegex(summary[1], r'^- nightly-chestnut: failed \(\d+\)$')
    self.assertEqual([line for i, line in enumerate(summary) if i != 1],
                     [f'- {branch}: success' for branch in BRANCHES if branch != 'nightly-chestnut'])
    failure = self.failure()
    self.assertRegex(failure[1], r'^publish_branch.sh ended without a result for nightly-chestnut \(\d+\)$')
    self.assertEqual(failure[2], '--log')
    record, = [r for r in self.issue_records() if r['args'][1] == 'local-runner' and '--reason' in r['args']]
    self.assertIn('=== nightly-chestnut', record['log'])
    self.assertIn('=== release-tizi-staging', record['log'])

  def test_worker_crash_is_reported_without_a_local_failure_file(self):
    result = self.run_local(KILL_WORKER='1')
    self.assertEqual(result.returncode, 137, result.stdout + result.stderr)
    self.assertEqual(self.pushes(), [])
    failure = self.failure()
    self.assertEqual(failure[:3], ['--reason', 'runner stopped (137)', '--log'])
    self.assertTrue((self.root / 'last-failed/runner.log').exists())
    self.assert_clean_work_root()

  def test_lock_held_by_a_live_run_stops_a_second_instance(self):
    lock = self.root / 'lock'
    lock.mkdir(parents=True)
    owner = f'{os.getpid()} {lstart(os.getpid())}\n'
    (lock / 'owner').write_text(owner)
    result = self.run_local()
    self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
    self.assertEqual(self.calls('git'), [])
    self.assertFalse(any(row[1] == 'variable' for row in self.calls('gh')))
    self.assertEqual(self.issue_calls('local-runner'), [['--reason', 'another local nightly run still holds the lock']])
    self.assertEqual((lock / 'owner').read_text(), owner)

  def test_a_live_limiter_keeps_the_lock_held(self):
    lock = self.root / 'lock'
    lock.mkdir(parents=True)
    owner = f'{os.getpid()} Thu Jan 1 00:00:00 1970\n'
    (lock / 'owner').write_text(owner)
    (lock / 'limiter').write_text(f'{os.getpid()} {lstart(os.getpid())}\n')
    result = self.run_local()
    self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
    self.assertEqual((lock / 'owner').read_text(), owner)
    self.assertEqual(self.calls('git'), [])

  def test_a_lock_without_a_written_owner_is_not_acquired(self):
    real = shutil.which('mkdir')
    stub = self.bin / 'mkdir'
    stub.write_text(f'#!{sys.executable}\n' + textwrap.dedent(f'''\
      import os, sys
      if sys.argv[1:] and sys.argv[-1].endswith('/lock') and len(sys.argv) == 2:
        os.mkdir(sys.argv[1], 0o500)  # created, but the owner file cannot be written
        sys.exit(0)
      os.execv({real!r}, [{real!r}, *sys.argv[1:]])
      '''))
    stub.chmod(0o755)
    result = self.run_local()
    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
    self.assertIn('the lock owner could not be written', result.stdout)
    self.assertFalse((self.root / 'lock').exists())
    self.assertEqual(self.issue_calls('local-runner'), [['--reason', 'the lock cannot be created']])
    self.assertEqual(self.calls('git'), [])

  def test_git_never_reads_an_enclosing_repository(self):
    enclosing = self.work / 'enclosing'
    export = enclosing / 'export'
    subprocess.run([REAL_GIT, 'init', '-q', str(enclosing)], check=True)
    subprocess.run([REAL_GIT, '-C', str(enclosing), 'config', 'url.file:///nowhere/.insteadOf', 'https://github.com/'], check=True)
    files = subprocess.run([REAL_GIT, 'ls-files', '-co', '--exclude-standard', '-z'], cwd=ROOT, check=True,
                           capture_output=True).stdout.decode().split('\0')
    for name in filter(None, files):
      (export / name).parent.mkdir(parents=True, exist_ok=True)
      shutil.copy2(ROOT / name, export / name)
    seen = self.work / 'url-config'
    result = subprocess.run(['bash', 'scripts/local_nightly.sh'], cwd=export, timeout=300, capture_output=True, text=True,
                            env=self.environment({'RECORD_URL_CONFIG': str(seen)}))
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertTrue(seen.exists())
    self.assertEqual(seen.read_text(), '')
    ceiling = json.loads(self.git_env.read_text().splitlines()[0])['GIT_CEILING_DIRECTORIES']
    self.assertEqual(ceiling, f'{enclosing.resolve()}:{self.root}')

  def test_time_limits_without_leading_zeros(self):
    for env in ({'LOCAL_NIGHTLY_TIME_LIMIT': '0900'}, {'LOCAL_NIGHTLY_CALL_LIMIT': '0'},
                {'LOCAL_NIGHTLY_LOCK_WAIT': '1234567'}):
      with self.subTest(env=env):
        self.log.write_text('')
        result = self.run_local(**env)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

  def test_stale_lock_from_a_reused_pid_is_replaced(self):
    lock = self.root / 'lock'
    lock.mkdir(parents=True)
    (lock / 'owner').write_text(f'{os.getpid()} Thu Jan 1 00:00:00 1970\n')
    result = self.run_local()
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn('removed stale lock', result.stdout)
    self.assert_clean_work_root()

  def test_ownerless_lock_is_stale_only_after_a_minute(self):
    lock = self.root / 'lock'
    lock.mkdir(parents=True)
    result = self.run_local()
    self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
    self.assertTrue(lock.is_dir())
    self.assertEqual(self.calls('git'), [])
    past = time.time() - 120
    os.utime(lock, (past, past))
    result = self.run_local()
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn('removed stale lock (no owner)', result.stdout)
    self.assert_clean_work_root()

  def test_lock_taken_between_check_and_rename_is_put_back(self):
    lock = self.root / 'lock'
    lock.mkdir(parents=True)
    (lock / 'owner').write_text(f'{os.getpid()} Thu Jan 1 00:00:00 1970\n')
    live = f'{os.getpid()} {lstart(os.getpid())}\n'
    result = self.run_local(SWAP_OWNER=live)
    self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
    self.assertIn('changed hands meanwhile', result.stdout)
    self.assertEqual((lock / 'owner').read_text(), live)
    self.assertEqual([p.name for p in self.root.iterdir() if '.stale.' in p.name], [])
    self.assertEqual(self.calls('git'), [])

  def test_lock_that_cannot_be_created_fails_at_once(self):
    (self.root / 'runs').mkdir(parents=True)
    self.root.chmod(0o500)
    try:
      start = time.monotonic()
      result = self.run_local(LOCAL_NIGHTLY_LOCK_WAIT='40')
    finally:
      self.root.chmod(0o700)
    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
    self.assertLess(time.monotonic() - start, 30)
    self.assertEqual(self.issue_calls('local-runner'), [['--reason', 'the lock cannot be created']])
    self.assertEqual(self.calls('git'), [])

  def test_token_reaches_git_only_through_the_environment_helper(self):
    result = self.run_local(FAIL_STAGE='gates', FAIL_BRANCH='nightly')
    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
    self.assertFalse(any(row[1] == 'auth' for row in self.calls('gh')))
    self.assertNotIn(TOKEN, self.log.read_text())
    self.assertNotIn(TOKEN, self.issue_env.read_text())
    self.assertNotIn(TOKEN, result.stdout + result.stderr)
    for path in self.root.rglob('*'):
      if path.is_file():
        self.assertNotIn(TOKEN.encode(), path.read_bytes(), path)
    envs = [json.loads(row) for row in self.git_env.read_text().splitlines()]
    self.assertTrue(envs)
    env = envs[0]
    self.assertTrue(all(e == env for e in envs))
    self.assertNotIn(TOKEN, json.dumps(envs))
    self.assertEqual(env['GIT_CONFIG_NOSYSTEM'], '1')
    self.assertEqual(env['GIT_CONFIG_GLOBAL'], '/dev/null')
    self.assertEqual(env['GIT_TERMINAL_PROMPT'], '0')
    self.assertEqual((env['GIT_CONFIG_COUNT'], env['GIT_CONFIG_KEY_0'], env['GIT_CONFIG_VALUE_0']), ('2', 'credential.helper', ''))
    self.assertEqual(env['GIT_CONFIG_KEY_1'], 'credential.https://github.com/example/openpilot.git.helper')
    self.assertIn('"password=$GH_TOKEN"', env['GIT_CONFIG_VALUE_1'])
    # The real git asks the helper for github.com only; the reset drops every host helper.
    real = {**{k: v for k, v in os.environ.items() if not k.startswith('GIT_')}, **env,
            'GH_TOKEN': TOKEN, 'HOME': str(self.work)}
    fill = subprocess.run([REAL_GIT, 'credential', 'fill'], input='protocol=https\nhost=github.com\npath=example/openpilot.git\n\n',
                          env=real, capture_output=True, text=True)
    self.assertEqual(fill.returncode, 0, fill.stderr)
    self.assertIn('username=x-access-token\n', fill.stdout)
    self.assertIn(f'password={TOKEN}\n', fill.stdout)
    # Only the fork: never commaai/openpilot, another github.com path, or another host.
    for request in ('host=example.com\n', 'host=github.com\npath=commaai/openpilot.git\n',
                    'host=github.com\npath=commaai/openpilot\n', 'host=github.com\n',
                    'host=github.com\npath=example/openpilot-other.git\n'):
      with self.subTest(request=request):
        other = subprocess.run([REAL_GIT, 'credential', 'fill'], input='protocol=https\n' + request + '\n',
                               env=real, capture_output=True, text=True)
        self.assertNotEqual(other.returncode, 0)
        self.assertNotIn(TOKEN, other.stdout + other.stderr)
    helpers = subprocess.run([REAL_GIT, 'config', '--get-all', 'credential.helper'], env=real, capture_output=True, text=True)
    self.assertEqual(helpers.stdout, '\n')
    helper = env['GIT_CONFIG_VALUE_1'][1:]
    for action, answers in (('get', True), ('store', False), ('erase', False)):
      output = subprocess.run(['sh', '-c', f'{helper} {action}'], env=real, capture_output=True, text=True).stdout
      self.assertEqual(TOKEN in output, answers, action)

  def test_follow_mode_variable_reads_fail_closed(self):
    for scenario, mode in (({'VARIABLE_MODE': None}, 'off'), ({'VARIABLE_MODE': 'dryrun'}, 'dryrun'),
                           ({'VARIABLE_MODE': ''}, 'off'),
                           ({'WPA3_FOLLOW_MODE_OVERRIDE': 'state', 'LOCAL_NIGHTLY_TEST': '1', 'VARIABLE_MODE': 'error'}, 'state'),
                           # Without the test marker or DRY_RUN=1 a live run ignores the override.
                           ({'WPA3_FOLLOW_MODE_OVERRIDE': 'state', 'VARIABLE_MODE': 'dryrun'}, 'dryrun'),
                           ({'VARIABLE_MODE': 'error', 'VARIABLE_LIST': 'error'}, None),
                           ({'VARIABLE_MODE': None, 'VARIABLE_LIST': 'WPA3_FOLLOW_MODE'}, None),
                           ({'VARIABLE_MODE': 'bogus'}, None)):
      with self.subTest(scenario=scenario):
        self.log.write_text('')
        result = self.run_local(**scenario)
        if mode is None:
          self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
          self.assertEqual(self.calls('git'), [])
          self.assertEqual(self.failure(), ['--reason', 'WPA3_FOLLOW_MODE could not be read'])
        else:
          self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
          creates = [row for row in self.calls('python3') if row[1:3] == ['scripts/nightly_skip.py', 'create']]
          self.assertEqual({row[row.index('--mode') + 1] for row in creates}, {mode})
          self.assertEqual(any(row[1] == 'variable' for row in self.calls('gh')), 'LOCAL_NIGHTLY_TEST' not in scenario)
    result = self.run_local(DRY_RUN='1', WPA3_FOLLOW_MODE_OVERRIDE='state', VARIABLE_MODE='error')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn('WPA3_FOLLOW_MODE=state', result.stdout)

  def test_time_limit_stops_the_whole_process_group(self):
    hang = self.work / 'hang.pid'
    start = time.monotonic()
    result = self.run_local(HANG_PID=str(hang), LOCAL_NIGHTLY_TIME_LIMIT='3')
    self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
    self.assertLess(time.monotonic() - start, 60)
    self.assertTrue(gone(int(hang.read_text())), 'a process outlived the time limit')
    self.assertEqual(self.pushes(), [])
    self.assertEqual(self.failure()[:3], ['--reason', 'time limit reached after 3 seconds', '--log'])
    self.assertTrue((self.root / 'last-failed/runner.log').exists())
    self.assert_clean_work_root()

  def test_signal_stops_the_worker_group_before_cleanup(self):
    hang = self.work / 'hang.pid'
    process = subprocess.Popen(['bash', 'scripts/local_nightly.sh'], cwd=ROOT, env=self.environment({'HANG_PID': str(hang)}),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
      for _ in range(300):
        if hang.exists() and hang.read_text():
          break
        time.sleep(0.1)
      else:
        self.fail('the worker never reached the hanging call')
      # The limiter is recorded in the lock, so a later run sees the worker as live.
      for _ in range(50):
        if (self.root / 'lock/limiter').exists():
          break
        time.sleep(0.1)
      limiter = (self.root / 'lock/limiter').read_text().split(' ', 1)
      os.kill(int(limiter[0]), 0)
      self.assertEqual(limiter[1].strip(), lstart(int(limiter[0])))
      process.send_signal(signal.SIGTERM)
      output, _ = process.communicate(timeout=60)
    finally:
      if process.poll() is None:
        process.kill()
    self.assertEqual(process.returncode, 143, output)
    self.assertTrue(gone(int(hang.read_text())), 'a worker process outlived the signal')
    self.assertIn('received SIGTERM', output)
    self.assertTrue((self.root / 'last-failed/runner.log').exists())
    self.assertEqual(self.pushes(), [])
    self.assertEqual(self.failure()[:3], ['--reason', 'stopped by SIGTERM', '--log'])
    self.assert_clean_work_root()

  def test_a_stalled_call_before_the_worker_cannot_hold_the_lock(self):
    hang = self.work / 'hang-state.pid'
    start = time.monotonic()
    result = self.run_local(HANG_STATE_PID=str(hang), LOCAL_NIGHTLY_CALL_LIMIT='2')
    self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
    self.assertLess(time.monotonic() - start, 60)
    self.assertTrue(gone(int(hang.read_text())), 'a process outlived the call limit')
    self.assertEqual(self.calls('git'), [])
    self.assertEqual(self.failure(), ['--reason', 'nightly workflow state could not be read'])
    self.assert_clean_work_root()

  def test_setup_failures_never_fall_back_to_a_checkout(self):
    result = self.run_local(WPA3_CI_HEAD=None)
    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
    self.assertEqual(self.calls('git'), [])
    self.assertEqual(self.issue_calls('local-runner'), [['--reason', 'WPA3_CI_HEAD is not a commit SHA']])
    self.log.write_text('')
    result = self.run_local(GH_TOKEN=None)
    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
    self.assertEqual(self.calls(), [])

  def test_dry_run_prints_every_runner_write(self):
    result = self.run_local(DRY_RUN='1', GH_TOKEN=None, PENDING='1')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn('DRY_RUN: gh workflow run follow.yml --ref wpa3-ci --repo example/openpilot -f reason=nightly-pending', result.stdout)
    self.assertIn('DRY_RUN: python3 scripts/issues.py local-runner --close', result.stdout)
    self.assertEqual(self.dispatches(), [])
    self.assertFalse(any(row[1] == 'scripts/issues.py' for row in self.calls('python3')))
    self.log.write_text('')
    result = self.run_local(DRY_RUN='1', FORCE='true', PREVIOUS_INPUTS='inputs')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn('DRY_RUN: python3 scripts/issues.py local-runner --token-check', result.stdout)
    self.assertEqual(result.stdout.count('--force-with-lease='), 4)
    self.assertEqual(self.pushes(), [])
    self.assertFalse(any(row[1] == 'scripts/issues.py' for row in self.calls('python3')))

  def test_branch_list_is_the_nightly_workflow_list(self):
    workflow = (ROOT / '.github/workflows/nightly.yml').read_text()
    self.assertIn("      BRANCHES: '" + ' '.join(BRANCHES) + "'\n", workflow)


class LauncherTests(unittest.TestCase):
  def setUp(self):
    (ROOT / '.tmp').mkdir(exist_ok=True)
    tmp = tempfile.TemporaryDirectory(dir=ROOT / '.tmp', prefix='test-launcher-')
    self.addCleanup(tmp.cleanup)
    self.addCleanup(lambda: subprocess.run(['chmod', '-R', 'u+w', tmp.name]))
    self.work = Path(tmp.name)
    self.base = self.work / 'base'
    self.base.mkdir(mode=0o700)
    self.launcher = self.base / 'local_nightly_launcher.sh'
    shutil.copyfile(ROOT / 'scripts/local_nightly_launcher.sh', self.launcher)
    self.secret = self.work / 'secret'
    self.secret.mkdir(mode=0o700)
    self.token = self.secret / 'token'
    self.token.write_text(TOKEN + '\n')
    self.token.chmod(0o600)
    self.root = self.base / 'work'
    self.calls = self.work / 'calls'
    self.calls.write_text('')
    self.bin = self.work / 'bin'
    self.bin.mkdir()
    self.source = self.work / 'source.git'
    self.report = self.work / 'report.json'
    # The fake fetches from a local repository instead of github.com and records argv.
    git = self.bin / 'git'
    git.write_text(f'#!{sys.executable}\n' + textwrap.dedent(f'''\
      import json, os, sys
      args = [a.replace('https://github.com/example/openpilot.git', 'file://{self.source}') for a in sys.argv[1:]]
      with open({str(self.calls)!r}, 'a') as log:
        log.write(json.dumps(sys.argv[1:]) + '\\n')
      if os.environ.get('FAIL_FETCH') and 'fetch' in args:
        sys.exit(128)
      if os.environ.get('EMPTY_FETCH') and 'fetch' in args:
        sys.exit(0)  # reports success without fetching anything
      if os.environ.get('HANG_FETCH') and 'fetch' in args:
        import subprocess, time
        child = subprocess.Popen(['sleep', '300'])
        with open(os.environ['HANG_FETCH'], 'a') as pids:
          pids.write(f'{{os.getpid()}}\\n{{child.pid}}\\n')
        time.sleep(300)
      os.execv({REAL_GIT!r}, [{REAL_GIT!r}, *args])
      '''))
    git.chmod(0o755)
    self.config = self.base / 'local_nightly.conf'
    self.write_config()

  def write_config(self, **changes):
    values = {'GH_REPO': 'example/openpilot', 'WORK_ROOT': str(self.root), 'TOKEN_FILE': str(self.token),
              'PATH': f'{self.bin}:/usr/bin:/bin', 'TIME_LIMIT_MINUTES': '7', **changes}
    self.config.write_text('# test\n' + ''.join(f'{key}={value}\n' for key, value in values.items()))
    self.config.chmod(0o600)

  def make_source(self, rc=0, runner=True):
    tree = self.work / 'tree'
    (tree / 'scripts').mkdir(parents=True)
    (tree / ('scripts/local_nightly.sh' if runner else 'scripts/other.sh')).write_text(textwrap.dedent(f'''\
      printf '%s\\n' "$0" "$@" "$(ps -o args= -p $$)" > "$REPORT.argv"
      python3 - "$PWD" <<'PY'
      import hashlib, json, os, sys
      keys = ('WPA3_CI_HEAD', 'GH_REPO', 'WPA3_WORK_ROOT', 'DRY_RUN', 'LOCAL_NIGHTLY_TIME_LIMIT', 'LOCAL_NIGHTLY_LOCK_WAIT',
              'WPA3_FOLLOW_MODE_OVERRIDE', 'LOCAL_NIGHTLY_TEST')
      report = {{key: os.environ.get(key) for key in keys}}
      report.update(cwd=sys.argv[1], writable=os.access(sys.argv[1], os.W_OK),
                    token=hashlib.sha256(os.environ.get('GH_TOKEN', '').encode()).hexdigest())
      open(os.environ['REPORT'], 'w').write(json.dumps(report))
      PY
      echo ran local_nightly.sh
      exit {rc}
      '''))
    env = {**{k: v for k, v in os.environ.items() if not k.startswith('GIT_')}, 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com'}
    for args in (['init', '-q', '-b', 'wpa3-ci', str(tree)], ['-C', str(tree), 'add', '.'],
                 ['-C', str(tree), 'commit', '-q', '-m', 'test'], ['clone', '-q', '--bare', str(tree), str(self.source)]):
      subprocess.run([REAL_GIT, *args], env=env, check=True, capture_output=True)
    return subprocess.run([REAL_GIT, '-C', str(tree), 'rev-parse', 'HEAD'], env=env, check=True,
                          capture_output=True, text=True).stdout.strip()

  def run_launcher(self, launcher=None, **env):
    environment = {'HOME': str(self.work), 'PATH': '/usr/bin:/bin', 'REPORT': str(self.report),
                   'GH_TOKEN': 'from-the-caller', 'GIT_DIR': '/nonexistent', 'WPA3_FOLLOW_MODE_OVERRIDE': 'on',
                   'LOCAL_NIGHTLY_TEST': '1', **env}
    return subprocess.run(['/bin/bash', '-c', 'umask 022; exec /bin/bash "$0"', str(launcher or self.launcher)],
                          env=environment, capture_output=True, text=True, timeout=120)

  def assert_refused(self, result, word):
    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
    self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)
    self.assertIn(word, result.stderr)
    self.assertNotIn(str(self.work), result.stderr)
    self.assertNotIn(TOKEN, result.stderr)
    self.assertEqual(self.calls.read_text(), '')
    self.assertFalse(self.report.exists())

  def test_refuses_group_or_other_access(self):
    for path, mode, word in ((self.token, 0o640, 'token file'), (self.token, 0o604, 'token file'),
                             (self.token, 0o620, 'token file'), (self.token, 0o602, 'token file'),
                             (self.config, 0o640, 'local_nightly.conf'), (self.config, 0o620, 'local_nightly.conf'),
                             (self.config, 0o602, 'local_nightly.conf'), (self.base, 0o750, 'launcher folder'),
                             (self.base, 0o730, 'launcher folder'), (self.base, 0o701, 'launcher folder'),
                             (self.secret, 0o750, 'token folder'), (self.secret, 0o701, 'token folder')):
      with self.subTest(path=path.name, mode=oct(mode)):
        original = path.stat().st_mode & 0o777
        path.chmod(mode)
        try:
          result = self.run_launcher()
        finally:
          path.chmod(original)
        self.assert_refused(result, word)
        self.assertFalse(self.root.exists())

  @unittest.skipUnless(platform.system() == 'Darwin', 'macOS ACLs')
  def test_refuses_an_acl_with_or_without_extended_attributes(self):
    for path, entry, word in ((self.token, 'everyone allow read', 'token file'),
                              (self.base, 'everyone allow list', 'launcher folder')):
      for xattr in (False, True):
        with self.subTest(path=path.name, xattr=xattr):
          subprocess.run(['xattr', '-c', str(path)], check=False)
          subprocess.run(['chmod', '+a', entry, str(path)], check=True)
          try:
            if xattr:
              subprocess.run(['xattr', '-w', 'com.example.test', '1', str(path)], check=True)
            listing = subprocess.run(['ls', '-ldn', str(path)], capture_output=True, text=True).stdout
            self.assertTrue(listing.split()[0].endswith('@' if xattr else '+'), listing)
            result = self.run_launcher()
          finally:
            subprocess.run(['chmod', '-a', entry, str(path)], check=True)
            subprocess.run(['xattr', '-c', str(path)], check=False)
          self.assert_refused(result, word)

  def test_refuses_writable_folders_above(self):
    original = self.work.stat().st_mode & 0o7777
    for mode in (0o770, 0o707, 0o1777):
      with self.subTest(mode=oct(mode)):
        self.work.chmod(mode)
        try:
          result = self.run_launcher()
        finally:
          self.work.chmod(original)
        self.assert_refused(result, 'folder above')

  @unittest.skipUnless(platform.system() == 'Darwin', 'macOS mount flags')
  def test_refuses_a_volume_that_ignores_ownership(self):
    point = subprocess.run(['df', '-P', str(self.base)], capture_output=True, text=True,
                           check=True).stdout.splitlines()[1].split(None, 5)[5]
    mount = self.bin / 'mount'
    mount.write_text(f'#!/bin/sh\necho "/dev/disk9s9 on {point} (apfs, local, noowners)"\n')
    mount.chmod(0o755)
    self.assert_refused(self.run_launcher(), 'ignores ownership')
    mount.write_text(f'#!/bin/sh\necho "/dev/disk9s9 on {point} (apfs, local, journaled)"\n')
    self.make_source(rc=0)
    result = self.run_launcher()
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

  def test_numbers_without_leading_zeros(self):
    for key, value, word in (('TIME_LIMIT_MINUTES', '090', 'whole numbers'), ('TIME_LIMIT_MINUTES', '12345', 'whole numbers'),
                             ('FETCH_LIMIT_SECONDS', '007', 'whole numbers'), ('KEEP_DAYS', '0', 'at least 1')):
      with self.subTest(key=key, value=value):
        self.write_config(**{key: value})
        self.assert_refused(self.run_launcher(), word)

  def test_commit_without_the_runner_runs_nothing(self):
    self.make_source(runner=False)
    result = self.run_launcher()
    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
    self.assertFalse(self.report.exists())
    log, = (self.root / 'logs').iterdir()
    self.assertIn('has no scripts/local_nightly.sh; nothing was run', log.read_text())

  def test_pruning_passes_paths_with_newlines_as_arguments(self):
    self.make_source(rc=0)
    exports = self.root / 'exports'
    self.root.mkdir(mode=0o700)
    exports.mkdir(mode=0o700)
    keep = exports / 'keep'
    keep.mkdir()
    old = exports / 'keep\nold'
    old.mkdir()
    (old / 'file').write_text('old')
    old.chmod(0o500)
    past = time.time() - 20 * 86400
    os.utime(old, (past, past))
    result = self.run_launcher()
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertTrue(keep.is_dir())
    self.assertFalse(old.exists())

  def test_a_stalled_fetch_is_stopped_and_nothing_runs(self):
    self.make_source(rc=0)
    self.write_config(FETCH_LIMIT_SECONDS='2')
    pids = self.work / 'fetch.pids'
    start = time.monotonic()
    result = self.run_launcher(HANG_FETCH=str(pids))
    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
    self.assertLess(time.monotonic() - start, 40)
    self.assertFalse(self.report.exists())
    numbers = [int(pid) for pid in pids.read_text().split()]
    self.assertEqual(len(numbers), 4)  # the stalled fetch and its retry, each with a child
    for pid in numbers:
      self.assertTrue(gone(pid), f'process {pid} outlived the fetch limit')

  def test_broken_mirror_never_touches_an_enclosing_repository(self):
    self.make_source(rc=0)
    # Outside this worktree: a failure here must never reach a real repository.
    top = Path(tempfile.mkdtemp(prefix='wpa3-enclosing-')).resolve()
    self.addCleanup(lambda: (subprocess.run(['chmod', '-R', 'u+w', str(top)]), shutil.rmtree(top, True)))
    env = {**{k: v for k, v in os.environ.items() if not k.startswith('GIT_')}, 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com'}
    (top / 'x').write_text('x')
    for args in (['init', '-q', '-b', 'wpa3-ci', str(top)], ['-C', str(top), 'add', 'x'], ['-C', str(top), 'commit', '-q', '-m', 'x']):
      subprocess.run([REAL_GIT, *args], env=env, check=True, capture_output=True)
    def enclosing_ref():
      return subprocess.run([REAL_GIT, '-C', str(top), 'rev-parse', 'refs/heads/wpa3-ci'], env=env,
                            capture_output=True, text=True).stdout.strip()
    before = enclosing_ref()
    base = top / 'launcher'
    base.mkdir(mode=0o700)
    launcher = base / 'local_nightly_launcher.sh'
    shutil.copyfile(self.launcher, launcher)
    work = base / 'work'
    self.config = base / 'local_nightly.conf'
    self.write_config(WORK_ROOT=str(work))
    for head in (None, 'ref: refs/heads/main\n'):
      with self.subTest(head=head):
        shutil.rmtree(work, ignore_errors=True)
        subprocess.run(['chmod', '-R', 'u+w', str(base)])
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(mode=0o700)
        (work / 'mirror.git').mkdir()
        if head:
          (work / 'mirror.git/HEAD').write_text(head)  # looks like a repository, is not one
        self.report.unlink(missing_ok=True)
        result = self.run_launcher(launcher)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.report.exists())
        self.assertEqual(enclosing_ref(), before)
        self.assertTrue((work / 'mirror.git/objects').is_dir())
        if head is None:
          log, = (work / 'logs').iterdir()
          self.assertNotIn('rebuilding', log.read_text())

  def test_refuses_symlinks(self):
    link = self.secret / 'link'
    link.symlink_to(self.token)
    if hasattr(os, 'lchmod'):
      os.lchmod(link, 0o600)  # macOS: a symlink can look private to ls -l itself
    self.write_config(TOKEN_FILE=str(link))
    self.assert_refused(self.run_launcher(), 'token file')
    self.write_config()
    real = self.work / 'real.conf'
    self.config.rename(real)
    self.config.symlink_to(real)
    self.assert_refused(self.run_launcher(), 'local_nightly.conf')
    self.config.unlink()
    real.rename(self.config)
    alias = self.work / 'alias'
    alias.symlink_to(self.base)
    self.assert_refused(self.run_launcher(alias / self.launcher.name), 'symlink')
    linked = self.work / 'linked.sh'
    linked.symlink_to(self.launcher)
    self.assert_refused(self.run_launcher(linked), 'symlink')

  def test_work_root_must_be_private_and_inside_the_launcher_folder(self):
    self.root.mkdir(mode=0o755)
    self.root.chmod(0o755)
    self.assert_refused(self.run_launcher(), 'WORK_ROOT')
    self.root.rmdir()
    outside = self.work / 'outside'
    for value in (str(outside), str(self.base / '..' / 'outside'), str(self.base) + '/./work'):
      with self.subTest(value=value):
        self.write_config(WORK_ROOT=value)
        self.assert_refused(self.run_launcher(), 'WORK_ROOT')
    outside.mkdir(mode=0o700)
    (self.base / 'work').symlink_to(outside)
    self.write_config()
    self.assert_refused(self.run_launcher(), 'WORK_ROOT')

  def test_runs_the_fetched_commit_from_a_read_only_export_and_prunes(self):
    sha = self.make_source(rc=1)
    self.root.mkdir(mode=0o700)
    old_export = self.root / 'exports' / 'old'
    old_export.parent.mkdir(mode=0o700)
    old_export.mkdir()
    (old_export / 'file').write_text('old')
    old_export.chmod(0o500)
    old_log = self.root / 'logs' / 'nightly-20000101.log'
    old_log.parent.mkdir(mode=0o700)
    old_log.write_text('old')
    past = time.time() - 20 * 86400
    for path in (old_export, old_log):
      os.utime(path, (past, past))
    result = self.run_launcher()
    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
    report = json.loads(self.report.read_text())
    self.assertEqual(report['WPA3_CI_HEAD'], sha)
    self.assertEqual(report['GH_REPO'], 'example/openpilot')
    self.assertEqual(report['WPA3_WORK_ROOT'], str(self.root / 'runner'))
    self.assertEqual((report['DRY_RUN'], report['LOCAL_NIGHTLY_TIME_LIMIT'], report['LOCAL_NIGHTLY_LOCK_WAIT']), ('0', '420', '1800'))
    # Test-only knobs from the caller never reach the runner.
    self.assertEqual((report['WPA3_FOLLOW_MODE_OVERRIDE'], report['LOCAL_NIGHTLY_TEST']), (None, None))
    self.assertEqual(report['token'], hashlib.sha256(TOKEN.encode()).hexdigest())
    self.assertFalse(report['writable'])
    self.assertEqual(Path(report['cwd']).parent, (self.root / 'exports').resolve())
    self.assertIn('-' + sha[:12] + '-', Path(report['cwd']).name)
    argv = Path(str(self.report) + '.argv').read_text()
    self.assertIn('scripts/local_nightly.sh', argv)
    self.assertNotIn(TOKEN, argv)
    self.assertFalse(old_export.exists())
    self.assertFalse(old_log.exists())
    log, = (self.root / 'logs').iterdir()
    text = log.read_text()
    self.assertIn('launcher sha256 ' + hashlib.sha256(self.launcher.read_bytes()).hexdigest(), text)
    self.assertIn('ran local_nightly.sh', text)
    self.assertNotIn(TOKEN, text + self.calls.read_text() + result.stdout + result.stderr)
    self.assertEqual(result.stderr, f'local nightly launcher: failed (exit 1); see {log.name}\n')
    self.assertEqual(log.stat().st_mode & 0o777, 0o600)

  def test_unwritable_log_stops_before_anything_runs(self):
    self.make_source(rc=0)
    (self.root / 'logs').mkdir(parents=True, mode=0o700)
    self.root.chmod(0o700)
    (self.root / 'logs').chmod(0o500)
    self.assert_refused(self.run_launcher(), 'log')

  def test_created_folders_are_private_under_umask_022(self):
    self.make_source(rc=0)
    result = self.run_launcher()
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertEqual(result.stderr, '')
    for path in (self.root, self.root / 'logs', self.root / 'exports', self.root / 'mirror.git'):
      self.assertEqual(path.stat().st_mode & 0o777, 0o700, path)
    log, = (self.root / 'logs').iterdir()
    self.assertEqual(log.stat().st_mode & 0o777, 0o600)

  def test_fetch_failure_runs_nothing_and_rebuilds_the_mirror(self):
    self.make_source(rc=0)
    self.assertEqual(self.run_launcher().returncode, 0)
    log, = (self.root / 'logs').iterdir()
    # A fetch that claims success never falls back to the commit fetched before.
    self.report.unlink()
    result = self.run_launcher(EMPTY_FETCH='1')
    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
    self.assertFalse(self.report.exists())
    self.assertIn('wpa3-ci did not resolve to a commit', log.read_text())
    self.calls.write_text('')
    result = self.run_launcher(FAIL_FETCH='1')
    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
    self.assertFalse(self.report.exists())
    rows = [json.loads(row) for row in self.calls.read_text().splitlines()]
    self.assertEqual(len([row for row in rows if 'fetch' in row]), 2)
    self.assertEqual(len([row for row in rows if row[:2] == ['init', '--bare']]), 1)
    self.assertFalse(any('archive' in row for row in rows))
    self.assertIn('failed again; nothing was run', log.read_text())
    self.assertEqual(result.stderr, f'local nightly launcher: failed (exit 2); see {log.name}\n')

if __name__ == '__main__':
  unittest.main()
