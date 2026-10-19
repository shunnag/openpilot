"""Run the real publisher and job loop with offline git/gh/build stand-ins."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from follow_state import BRANCHES

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github/workflows/nightly.yml').read_text()


def workflow_script(name):
  step = next(s for s in WORKFLOW.split('      - ') if s.startswith(f'name: {name}\n'))
  return textwrap.dedent(step.split('        run: |\n', 1)[1].rstrip()) + '\n'


FAKE = r'''
import json
import os
from pathlib import Path
import sys

tool, args = Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ['CALLS'], 'a') as log:
  log.write(json.dumps([tool, *args]) + '\n')

def value(flag):
  return args[args.index(flag) + 1]

def fail(stage):
  if os.environ.get('FAIL_STAGE') == stage and os.environ.get('FAIL_BRANCH', os.environ['BRANCH']) == os.environ['BRANCH']:
    print('fixture failure: ' + stage, file=sys.stderr)
    sys.exit(17)

u, f, new = os.environ.get('UPSTREAM_SHA', 'a' * 40), 'b' * 40, 'c' * 40
if tool == 'git':
  if args[:2] == ['rev-parse', 'HEAD']:
    print(os.environ.get('CHECKOUT_HEAD', 'f' * 40))
  elif args[0] == 'ls-remote':
    for ref in args[2:]:
      sha = (u if 'commaai' in args[1] else
             os.environ.get('MARKER_SHA', 'd' * 40) if ref.startswith('refs/wpa3-evaluated/') else
             os.environ.get('FORK_SHA', f))
      if sha:
        print(sha + '\t' + ref)
  elif args[:2] == ['init', '--bare']:
    Path(args[2]).mkdir(parents=True, exist_ok=True)
  elif args[0] == '-C':
    operation = args[2]
    if operation == 'fetch':
      fail('blobless-fetch' if '--filter=blob:none' in args else 'full-fetch')
      if os.environ.get('SHALLOW_UPSTREAM') == '1' and '--filter=blob:none' not in args:
        (Path(args[1]) / 'shallow').write_text(u + '\n')
    elif operation == 'show':
      print(os.environ.get('PREVIOUS_INPUTS', 'different'))
    elif operation == 'push':
      fail('marker-push' if 'refs/wpa3-evaluated/' in args[-1] else 'push')
    elif operation not in ('remote', 'update-ref'):
      sys.exit(98)
  else:
    sys.exit(98)
elif tool == 'gh':
  if args[0] == 'api':
    endpoint = next(a for a in args if a.startswith('repos/'))
    if endpoint.endswith('/actions/workflows/nightly.yml'):
      fail('workflow-state')
      print(os.environ.get('WORKFLOW_STATE', 'active'))
    elif '/git/commits/' in endpoint:
      print(os.environ.get('MARKER_MESSAGE', 'wpa3-evaluated\n\nBranch: ' + os.environ['BRANCH'] +
        '\nHead: ' + os.environ.get('MARKER_HEAD', os.environ['WPA3_CI_HEAD']) + '\nMode: ' + os.environ.get('MARKER_MODE', os.environ['WPA3_FOLLOW_MODE']) +
        '\nUpstream: ' + os.environ.get('MARKER_UPSTREAM', 'd' * 40) + '\nFork: ' + os.environ.get('FORK_SHA', f) + '\n'))
    elif '/commits/' in endpoint:
      print('0')
    else:
      sys.exit(98)
  elif args[:2] != ['auth', 'setup-git']:
    sys.exit(98)
elif tool == 'python3':
  script = args[0]
  if script == 'scripts/nightly_skip.py' and args[1] == 'create':
    fail('marker-create')
    print('9' * 40)
  elif script in ('-', '-c', 'scripts/nightly_skip.py'):
    os.execv(sys.executable, [sys.executable, *args])
  elif script == 'scripts/pins.py':
    blobless = value('--repo').endswith('/check.git')
    fail('pin' if blobless else 'full-pin')
    if os.environ.get('PENDING') == '1' and blobless:
      print('PIN: FOLLOW: kernel ' + 'd' * 64 + ' waiting for follow')
      sys.exit(3)
    pin = {'mode': 'pinned', 'version': '19.9'}
    if not blobless and os.environ.get('PIN_MISMATCH') == '1':
      pin['version'] = '19.8'
    Path(value('--out')).write_text(json.dumps(pin))
    print('PIN: OK')
  elif script == 'scripts/compose.py':
    fail('inputs' if '--inputs-only' in args else 'compose')
    print('inputs' if '--inputs-only' in args else os.environ.get('NEW_SHA', new) + '\ninputs')
  elif script == 'scripts/gates.py':
    fail('gates')
    print('G1: OK')
  elif script == 'scripts/nightly.py':
    if args[1] == 'keep-lastgood':
      fail('lastgood')
      print(os.environ.get('KEEP_LASTGOOD', 'false'))
    else:
      print(os.environ.get('WITHDRAW_UPSTREAM', u))
  elif script == 'scripts/issues.py':
    if '--close' in args:
      fail('close-resolved')
    if args[1] == 'pending':
      fail('pending-issue')
  else:
    sys.exit(98)
elif tool == 'curl':
  fail('smoke')
  Path(value('-o')).write_bytes(b'\x7fELFgithub.com/example/openpilot.git')
  print('200')
else:
  sys.exit(98)
'''


class PublishBranchTests(unittest.TestCase):
  def setUp(self):
    # Keep every test-created file inside the authorised working directory.
    (ROOT / '.tmp').mkdir(exist_ok=True)
    tmp = tempfile.TemporaryDirectory(dir=ROOT / '.tmp', prefix='test-publish-')
    self.addCleanup(tmp.cleanup)
    self.work = Path(tmp.name)
    self.bin = self.work / 'bin'
    self.bin.mkdir()
    for name in ('git', 'gh', 'python3', 'curl'):
      path = self.bin / name
      path.write_text(f'#!{sys.executable}\n' + textwrap.dedent(FAKE))
      path.chmod(0o755)
    self.log = self.work / 'calls'
    self.log.write_text('')
    (self.work / 'wpa3.git').mkdir()
    self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                'CALLS': str(self.log), 'BRANCH': 'nightly', 'RUNNER_TEMP': str(self.work),
                'GH_REPO': 'example/openpilot', 'OWNER': 'example', 'WPA3_FOLLOW_MODE': 'off',
                'GITHUB_SHA': 'e' * 40, 'GITHUB_RUN_ID': '3', 'FORCE': 'false',
                'GITHUB_REF': 'refs/heads/wpa3-ci', 'WPA3_CI_HEAD': 'f' * 40,
                'UPSTREAM_SOURCE': 'latest', 'BARE_REPO': str(self.work / 'wpa3.git'),
                'GITHUB_OUTPUT': str(self.work / 'output'), 'GITHUB_STEP_SUMMARY': str(self.work / 'summary'),
                'DRY_RUN': '0', 'MARKER_UPSTREAM': 'd' * 40}

  def run_branch(self, **env):
    return subprocess.run(['bash', '-eu', '-o', 'pipefail', 'scripts/publish_branch.sh'], cwd=ROOT,
                          env={key: value for key, value in {**self.env, **env}.items() if value is not None},
                          capture_output=True, text=True)

  def calls(self, tool=None):
    rows = [json.loads(row) for row in self.log.read_text().splitlines()]
    return [row for row in rows if not tool or row[0] == tool]

  def marker_creates(self):
    return [row for row in self.calls('python3') if row[1:3] == ['scripts/nightly_skip.py', 'create']]

  def marker_pushes(self):
    return [row for row in self.calls('git') if 'push' in row and 'refs/wpa3-evaluated/' in row[-1]]

  def workflow_state_reads(self):
    return [row for row in self.calls('gh') if 'repos/example/openpilot/actions/workflows/nightly.yml' in row]

  def test_early_skip_has_no_fetch_and_closes_all_resolved_kinds(self):
    result = self.run_branch(MARKER_UPSTREAM='a' * 40)
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn('early-skip: unchanged', result.stdout)
    self.assertFalse(any('fetch' in row for row in self.calls('git')))
    issue_calls = [row for row in self.calls('python3') if row[1] == 'scripts/issues.py']
    self.assertEqual([row[2] for row in issue_calls], ['hold', 'pending', 'revoke-blocked'])
    self.assertTrue(all('--close' in row for row in issue_calls))
    self.assertFalse(any(row[1] in ('scripts/pins.py', 'scripts/gates.py', 'scripts/compose.py') for row in self.calls('python3')))
    self.assertEqual(self.marker_creates(), [])
    refs = [row for row in self.calls('git') if row[1] == 'ls-remote' and 'commaai' not in row[2]]
    self.assertEqual(len(refs), 1)
    self.assertEqual(refs[0][-2:], ['refs/heads/nightly', 'refs/wpa3-evaluated/nightly'])

  def test_pending_stops_before_full_fetch_and_preserves_distinct_outputs(self):
    for branch in BRANCHES:
      result = self.run_branch(BRANCH=branch, PENDING='1')
      self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
      self.assertEqual((self.work / branch / 'result').read_text(), 'pending\n')
      key = 'pending_' + branch.replace('-', '_')
      self.assertIn(f'{key}: ${{{{ steps.pin.outputs.{key} }}}}', WORKFLOW)
    self.assertEqual((self.work / 'output').read_text().splitlines(),
                     ['pending_' + branch.replace('-', '_') + '=true' for branch in BRANCHES])
    self.assertTrue(all('--filter=blob:none' in row for row in self.calls('git') if 'fetch' in row))
    builds = [row for row in self.calls('python3') if row[1] in ('scripts/gates.py', 'scripts/compose.py')]
    self.assertEqual(builds, [])
    self.assertTrue(all('--close' not in row for row in self.calls('python3') if row[1] == 'scripts/issues.py'))
    self.assertEqual(self.marker_creates(), [])

  def test_pin_mismatch_holds_before_gates_or_compose(self):
    result = self.run_branch(PIN_MISMATCH='1')
    self.assertNotEqual(result.returncode, 0)
    self.assertIn('pin mismatch between blobless and full fetch', result.stdout)
    self.assertFalse(any('push' in row for row in self.calls('git')))
    self.assertFalse(any(row[1] in ('scripts/gates.py', 'scripts/compose.py') for row in self.calls('python3')))
    hold = next(row for row in self.calls('python3') if row[1:3] == ['scripts/issues.py', 'hold'])
    self.assertEqual(hold[hold.index('--reason') + 1], 'pin mismatch between blobless and full fetch')
    self.assertEqual(self.marker_creates(), [])

  def test_inputs_skip_remains_after_full_fetch_and_matching_pins(self):
    result = self.run_branch(PREVIOUS_INPUTS='inputs')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertEqual(sum('scripts/pins.py' in row for row in self.calls()), 2)
    self.assertTrue(any('fetch' in row and '--filter=blob:none' not in row for row in self.calls('git')))
    self.assertFalse(any('scripts/gates.py' in row for row in self.calls()))
    self.assertEqual(len(self.marker_pushes()), 1)
    self.assertEqual([row for row in self.calls('git') if 'push' in row], self.marker_pushes())
    create = self.marker_creates()[0]
    self.assertEqual(create[create.index('--fork') + 1], 'b' * 40)

  def test_successful_publish_records_new_fork_after_issue_closure(self):
    for force in ('false', 'true'):
      with self.subTest(force=force):
        self.log.write_text('')
        result = self.run_branch(FORCE=force)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        create, = self.marker_creates()
        for flag, value in (('--fork', 'c' * 40), ('--head', 'f' * 40), ('--mode', 'off'), ('--upstream', 'a' * 40)):
          self.assertEqual(create[create.index(flag) + 1], value)
        push, = self.marker_pushes()
        self.assertEqual(push[-3:], ['--force', 'origin', '9' * 40 + ':refs/wpa3-evaluated/nightly'])
        rows = self.calls()
        state, = self.workflow_state_reads()
        self.assertEqual(state[-2:], ['--jq', '.state'])
        lease = next(row for row in rows if any(arg.startswith('--force-with-lease=') for arg in row))
        pushes = [row for row in rows if row[0] == 'git' and 'push' in row]
        self.assertLess(rows.index(state), min(rows.index(row) for row in pushes))
        closes = [row for row in rows if 'scripts/issues.py' in row and '--close' in row and row[2] != 'smoke']
        self.assertLess(rows.index(lease), min(rows.index(row) for row in closes))
        self.assertLess(max(rows.index(row) for row in closes), rows.index(create))
        self.assertLess(rows.index(create), rows.index(push))

  def test_identical_deterministic_commit_records_marker_without_branch_push(self):
    result = self.run_branch(NEW_SHA='b' * 40)
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn('deterministic commit already published', result.stdout)
    self.assertEqual([row for row in self.calls('git') if 'push' in row], self.marker_pushes())
    create, = self.marker_creates()
    self.assertEqual(create[create.index('--fork') + 1], 'b' * 40)

  def test_missing_or_rolled_back_marker_requires_full_evaluation(self):
    for scenario in ({'MARKER_SHA': ''}, {'MARKER_MESSAGE': 'garbled'},
                     {'MARKER_UPSTREAM': 'a' * 40, 'MARKER_MESSAGE':
                      'wpa3-evaluated\n\nBranch: nightly\nHead: ' + 'f' * 40 +
                      '\nMode: off\nUpstream: ' + 'a' * 40 + '\nFork: ' + '1' * 40 + '\n'}):
      with self.subTest(scenario=scenario):
        self.log.write_text('')
        result = self.run_branch(**scenario)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('early-skip', result.stdout)
        self.assertTrue(any('scripts/gates.py' in row for row in self.calls()))
        self.assertEqual(len(self.marker_creates()), 1)

  def test_held_force_run_does_not_record_marker(self):
    result = self.run_branch(FORCE='true', FAIL_STAGE='gates')
    self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
    self.assertEqual(self.marker_creates(), [])
    self.assertEqual(self.marker_pushes(), [])
    self.assertTrue(any('scripts/issues.py' in row and row[2] == 'hold' and '--close' not in row for row in self.calls()))

  def test_disabled_workflow_skips_before_push_marker_or_issue_changes(self):
    for scenario in ({}, {'PREVIOUS_INPUTS': 'inputs'}, {'NEW_SHA': 'b' * 40},
                     {'MARKER_UPSTREAM': 'a' * 40}, {'UPSTREAM_SOURCE': 'published', 'FORCE': 'true'}):
      with self.subTest(scenario=scenario):
        self.log.write_text('')
        result = self.run_branch(WORKFLOW_STATE='disabled_manually', **scenario)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.work / 'nightly/result').read_text(), 'skipped (nightly disabled)\n')
        self.assertFalse(any('push' in row for row in self.calls('git')))
        self.assertEqual(self.marker_creates(), [])
        self.assertFalse(any('scripts/issues.py' in row for row in self.calls()))
        self.assertEqual(len(self.workflow_state_reads()), 1)

  def test_any_non_active_state_skips(self):
    for state in ('disabled_inactivity', 'deleted', '', 'unknown'):
      with self.subTest(state=state):
        self.log.write_text('')
        result = self.run_branch(WORKFLOW_STATE=state, PREVIOUS_INPUTS='inputs')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.work / 'nightly/result').read_text(), 'skipped (nightly disabled)\n')
        self.assertFalse(any('push' in row or 'scripts/issues.py' in row for row in self.calls()))
        self.assertEqual(self.marker_creates(), [])

  def test_workflow_state_api_failure_holds_without_publication(self):
    for scenario in ({}, {'PREVIOUS_INPUTS': 'inputs'}, {'NEW_SHA': 'b' * 40}, {'MARKER_UPSTREAM': 'a' * 40}):
      with self.subTest(scenario=scenario):
        self.log.write_text('')
        result = self.run_branch(FAIL_STAGE='workflow-state', **scenario)
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertFalse(any('push' in row for row in self.calls('git')))
        self.assertEqual(self.marker_creates(), [])
        issues = [row for row in self.calls('python3') if 'scripts/issues.py' in row]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0][2], 'hold')
        self.assertNotIn('--close', issues[0])
        self.assertEqual(issues[0][issues[0].index('--reason') + 1], 'nightly workflow state could not be read')
        self.assertIn('held/failed', (self.work / 'nightly/result').read_text())

  def test_dry_workflow_state_override_skips_or_prints_writes_without_api_read(self):
    for state in ('disabled_manually', 'active'):
      with self.subTest(state=state):
        self.log.write_text('')
        result = self.run_branch(DRY_RUN='1', DRY_WORKFLOW_STATE=state, FAIL_STAGE='workflow-state')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.workflow_state_reads(), [])
        self.assertFalse(any('push' in row or 'scripts/issues.py' in row for row in self.calls()))
        if state == 'active':
          self.assertIn('--force-with-lease=', result.stdout)
          self.assertIn(':refs/wpa3-evaluated/', result.stdout)
        else:
          self.assertEqual(self.marker_creates(), [])
          self.assertEqual((self.work / 'nightly/result').read_text(), 'skipped (nightly disabled)\n')

  def test_live_run_ignores_dry_workflow_state_override(self):
    result = self.run_branch(DRY_WORKFLOW_STATE='disabled_manually')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertEqual(len(self.workflow_state_reads()), 1)
    self.assertEqual(len(self.marker_pushes()), 1)

  def test_issue_closure_failure_never_opens_false_hold(self):
    for scenario in ({}, {'PREVIOUS_INPUTS': 'inputs'}, {'NEW_SHA': 'b' * 40}, {'MARKER_UPSTREAM': 'a' * 40}):
      with self.subTest(scenario=scenario):
        self.log.write_text('')
        result = self.run_branch(FAIL_STAGE='close-resolved', **scenario)
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertEqual((self.work / 'nightly/result').read_text(), 'failed (issue bookkeeping)\n')
        self.assertFalse(any('scripts/issues.py' in row and '--close' not in row for row in self.calls()))
        self.assertEqual(self.marker_creates(), [])
        self.assertEqual(self.marker_pushes(), [])

  def test_marker_creation_or_push_failure_never_opens_false_hold(self):
    for stage in ('marker-create', 'marker-push'):
      with self.subTest(stage=stage):
        self.log.write_text('')
        result = self.run_branch(FAIL_STAGE=stage)
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertEqual((self.work / 'nightly/result').read_text(), 'failed (issue bookkeeping)\n')
        self.assertFalse(any('scripts/issues.py' in row and '--close' not in row for row in self.calls()))

  def test_dry_run_defaults_output_file_for_pending(self):
    result = self.run_branch(DRY_RUN='1', GITHUB_OUTPUT=None, PENDING='1')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertEqual((self.work / 'nightly/github_output').read_text(), 'pending_nightly=true\n')

  def test_dry_head_and_message_override_skip_without_api_reads(self):
    message = 'wpa3-evaluated\n\nBranch: nightly\nHead: ' + '8' * 40 + '\nMode: off\nUpstream: ' + 'a' * 40 + '\nFork: ' + 'b' * 40 + '\n'
    result = self.run_branch(DRY_RUN='1', DRY_HEAD='8' * 40, DRY_MARKER_MESSAGE=message, DRY_WORKFLOW_STATE='active')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn('early-skip: unchanged', result.stdout)
    self.assertEqual(self.calls('gh'), [])
    self.assertFalse(any('push' in row for row in self.calls('git')))

  def test_head_fallback_and_live_run_ignores_dry_overrides(self):
    result = self.run_branch(WPA3_CI_HEAD=None, CHECKOUT_HEAD='7' * 40, DRY_HEAD='8' * 40,
                             DRY_MARKER_MESSAGE='garbled', MARKER_UPSTREAM='a' * 40, MARKER_HEAD='6' * 40)
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn(['git', 'rev-parse', 'HEAD'], self.calls('git'))
    create, = self.marker_creates()
    self.assertEqual(create[create.index('--head') + 1], '7' * 40)

  def test_lastgood_failure_cannot_publish_or_overwrite_backup(self):
    result = self.run_branch(FAIL_STAGE='lastgood')
    self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
    self.assertFalse(any('push' in row for row in self.calls('git')))

  def test_full_fetch_never_publishes_shallow_upstream(self):
    result = self.run_branch(SHALLOW_UPSTREAM='1')
    self.assertNotEqual(result.returncode, 0)
    self.assertIn('Upstream commit is recorded as shallow', result.stdout)
    self.assertFalse(any('push' in row for row in self.calls('git')))

  def test_pending_escalation_fails_without_output_or_full_fetch(self):
    result = self.run_branch(PENDING='1', FAIL_STAGE='pending-issue')
    self.assertNotEqual(result.returncode, 0)
    self.assertFalse((self.work / 'output').exists())
    self.assertFalse(any('fetch' in row and '--filter=blob:none' not in row for row in self.calls('git')))

  def test_withdrawal_never_reads_latest_and_uses_published_parent(self):
    result = self.run_branch(UPSTREAM_SOURCE='published', FORCE='true')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertFalse(any('commaai' in ' '.join(row) for row in self.calls('git')))
    fetches = [row for row in self.calls('git') if 'fetch' in row]
    self.assertEqual(len(fetches), 1)
    self.assertNotIn('--depth=1', fetches[0])
    self.assertFalse(any('scripts/nightly_skip.py' in row for row in self.calls()))
    gates = next(row for row in self.calls() if 'scripts/gates.py' in row)
    self.assertIn('--revoke', gates)
    pins = next(row for row in self.calls() if 'scripts/pins.py' in row)
    self.assertEqual(pins[pins.index('--follow-mode') + 1], 'off')
    self.assertEqual(self.marker_pushes(), [])

  def test_withdrawal_failure_reports_revoke_blocked(self):
    result = self.run_branch(UPSTREAM_SOURCE='published', FAIL_STAGE='gates')
    self.assertNotEqual(result.returncode, 0)
    self.assertTrue(any(row[1:3] == ['scripts/issues.py', 'revoke-blocked'] and '--close' not in row
                        for row in self.calls('python3')))

  def test_smoke_failure_is_warning_only_after_lease_push(self):
    result = self.run_branch(FAIL_STAGE='smoke')
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn('::warning::Installer smoke test failed', result.stdout)
    self.assertTrue(any('--force-with-lease=refs/heads/nightly:' + 'b' * 40 in row for row in self.calls('git')))
    self.assertTrue(any(row[1:3] == ['scripts/issues.py', 'smoke'] and '--close' not in row for row in self.calls('python3')))

  def test_dry_run_four_branches_shares_repo_and_never_writes_remotely(self):
    for branch in BRANCHES:
      result = self.run_branch(BRANCH=branch, DRY_RUN='1', FORCE='true', PREVIOUS_INPUTS='inputs')
      self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
      self.assertIn('DRY_RUN: git', result.stdout)
      self.assertIn('--force-with-lease=', result.stdout)
      self.assertIn('DRY_RUN: python3 scripts/issues.py hold', result.stdout)
      self.assertIn(':refs/wpa3-evaluated/', result.stdout)
      self.assertTrue((self.work / branch / 'pin.json').exists())
      self.assertTrue((self.work / branch / 'composed.txt').exists())
      self.assertTrue((self.work / branch / 'installer.elf').exists())
      self.assertTrue((self.work / branch / 'smoke.log').exists())
    self.assertFalse(any('push' in row for row in self.calls('git')))
    self.assertFalse(any('scripts/issues.py' in row for row in self.calls('python3')))
    full_fetches = [row for row in self.calls('git') if 'fetch' in row and '--filter=blob:none' not in row]
    self.assertTrue(all(row[2] == str(self.work / 'wpa3.git') for row in full_fetches))
    self.assertEqual(sum('scripts/pins.py' in row for row in self.calls()), 8)
    self.assertEqual(sum('scripts/gates.py' in row for row in self.calls()), 4)

  def test_marker_message_is_cached_without_history_or_issue_reads(self):
    for _ in range(2):
      result = self.run_branch(MARKER_UPSTREAM='a' * 40)
      self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    endpoints = [next(arg for arg in row if arg.startswith('repos/')) for row in self.calls('gh')]
    self.assertEqual(endpoints, ['repos/example/openpilot/git/commits/' + 'd' * 40,
                                 'repos/example/openpilot/actions/workflows/nightly.yml',
                                 'repos/example/openpilot/actions/workflows/nightly.yml'])

  def test_job_continues_after_failed_branch_and_still_fails(self):
    script = workflow_script('Publish branches sequentially')
    result = subprocess.run(['bash', '-eu', '-o', 'pipefail', '-c', script], cwd=ROOT,
      env={**self.env, 'BRANCHES': ' '.join(BRANCHES), 'FAIL_STAGE': 'gates', 'FAIL_BRANCH': BRANCHES[0]},
      capture_output=True, text=True)
    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
    summary = (self.work / 'summary').read_text()
    self.assertIn('held/failed', summary)
    self.assertEqual(summary.count('success'), 3)
    self.assertEqual(result.stdout.count('::group::'), 4)
    self.assertEqual(result.stdout.count('::endgroup::'), 4)

  def test_both_crons_reach_checkout_and_branch_checks_without_job_skip(self):
    self.assertIn("- cron: '7 11 * * *'", WORKFLOW)
    self.assertIn("- cron: '43 12 * * *'", WORKFLOW)
    self.assertNotIn('steps.schedule', WORKFLOW)
    self.assertNotIn('id: schedule', WORKFLOW)
    self.assertNotIn('Skip catch-up', WORKFLOW)
    self.assertNotIn('/actions/workflows/nightly.yml/runs', WORKFLOW)
    self.assertIn('    steps:\n      - uses: actions/checkout@', WORKFLOW)

  def test_catch_up_checks_markers_and_publishes_upstream_or_mode_changes(self):
    for scenario, unchanged in (({'MARKER_UPSTREAM': 'a' * 40}, True),
                                ({'MARKER_UPSTREAM': 'a' * 40, 'UPSTREAM_SHA': 'd' * 40}, False),
                                ({'MARKER_UPSTREAM': 'a' * 40, 'WPA3_FOLLOW_MODE': 'on', 'MARKER_MODE': 'off'}, False)):
      with self.subTest(scenario=scenario):
        self.log.write_text('')
        result = self.run_branch(EVENT_NAME='schedule', EVENT_SCHEDULE='43 12 * * *', **scenario)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual('early-skip: unchanged' in result.stdout, unchanged)
        if unchanged:
          self.assertFalse(any('fetch' in row for row in self.calls('git')))
          self.assertEqual(self.marker_pushes(), [])
        else:
          self.assertTrue(any('--force-with-lease=refs/heads/nightly:' + 'b' * 40 in row for row in self.calls('git')))
          self.assertEqual(len(self.marker_pushes()), 1)

  def test_workflow_passes_checkout_head_as_publisher_environment(self):
    setup = workflow_script('Initialise shared bare repository')
    self.assertIn('ci_head=$(git rev-parse HEAD)', setup)
    self.assertIn('WPA3_CI_HEAD: ${{ steps.setup.outputs.ci_head }}', WORKFLOW)


if __name__ == '__main__':
  unittest.main()
