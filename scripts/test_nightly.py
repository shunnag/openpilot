"""Nightly control-path tests; fake gh/git/python, no network or upstream execution."""
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import follow_state as fs
import issues
import nightly
from test_follow_state import automatic_pin, withdrawal

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github/workflows/nightly.yml').read_text()


def step(name):
  return next(s for s in WORKFLOW.split('      - ') if s.startswith(f'name: {name}\n'))


def script(name):
  section = step(name).split('        run: |\n', 1)[1]
  return textwrap.dedent(section.rstrip()) + '\n'


class NightlyTests(unittest.TestCase):
  def test_pending_rc3_succeeds_and_preserves_four_distinct_outputs(self):
    with tempfile.TemporaryDirectory() as tmp:
      work = Path(tmp)
      fake = work / 'python3'
      fake.write_text('#!/bin/bash\nif [[ "$1" == scripts/pins.py ]]; then\n'
                      'echo "PIN: FOLLOW: kernel fixture waiting for follow"\nexit "$FAKE_RC"\nfi\n'
                      'if [[ "$1" == scripts/issues.py ]]; then echo "$*" >> "$ISSUE_CALLS"; exit 0; fi\nexit 99\n')
      fake.chmod(0o755)
      all_outputs = {}
      for branch, rc in zip(fs.BRANCHES, (1, 3, 1, 3)):
        output, calls = work / 'outputs', work / 'calls'
        output.write_text('')
        calls.write_text('')
        env = {**os.environ, 'PATH': str(work) + os.pathsep + os.environ['PATH'],
          'FAKE_RC': str(rc), 'ISSUE_CALLS': str(calls), 'WPA3_FOLLOW_MODE': 'on', 'BRANCH': branch,
          'UPSTREAM_SOURCE': 'latest', 'UPSTREAM': 'a' * 40, 'BARE_REPO': str(work),
          'RUNNER_TEMP': str(work), 'GITHUB_OUTPUT': str(output), 'NIGHTLY_LOG': str(work / 'log')}
        result = subprocess.run(['bash', '-eo', 'pipefail', '-c', script('Resolve AGNOS pin')],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if rc == 3 else 1, result.stderr)
        if rc == 3:
          self.assertEqual(output.read_text(), f'pending=true\npending_{branch.replace("-", "_")}=true\n')
          self.assertIn('issues.py pending', calls.read_text())
          self.assertNotIn('--close', calls.read_text())
          all_outputs[f'pending_{branch.replace("-", "_")}'] = 'true'
        else:
          self.assertEqual(output.read_text(), '')
      for branch in fs.BRANCHES:
        key = 'pending_' + branch.replace('-', '_')
        self.assertIn(f'{key}: ${{{{ steps.pin.outputs.{key} }}}}', WORKFLOW)
      self.assertEqual(len(all_outputs), 2)

  def test_one_pending_among_held_or_unchanged_dispatches_once(self):
    request = step('Request follow once for all pending branches')
    condition = request.split('        if: ', 1)[1].splitlines()[0]
    command = request.split('        run: ', 1)[1].strip()
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      fake = root / 'gh'
      fake.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$CALLS"\n')
      fake.chmod(0o755)
      for pending in ((), (0,), (1,), (2,), (3,), (0, 1, 2, 3)):
        flags = {f'pending_{b.replace("-", "_")}': 'true' if i in pending else '' for i, b in enumerate(fs.BRANCHES)}
        terms = re.findall(r"needs.publish.outputs.(\w+) == 'true'", condition)
        log = root / 'calls'
        log.write_text('')
        if any(flags[name] == 'true' for name in terms):
          subprocess.run(['bash', '-eo', 'pipefail', '-c', command], check=True,
            env={**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'], 'CALLS': str(log), 'GH_REPO': 'fake/local'})
        self.assertEqual(len(log.read_text().splitlines()), int(bool(pending)))
    self.assertIn('    needs: publish\n    if: always()\n', WORKFLOW)
    self.assertIn('      actions: write\n', WORKFLOW)

  def test_pending_never_closes_or_composes_and_writes_never_execute_upstream(self):
    for name in ('Skip identical published inputs', 'Gate upstream and download-verify pinned boot',
                 'Compose and validate deterministic commit', 'Back up previous nightly and publish with lease',
                 'Close resolved hold issues'):
      self.assertIn("steps.pin.outputs.pending != 'true'", step(name))
    close = step('Close resolved hold issues')
    self.assertIn("steps.push.outcome == 'success' || steps.inputs.outputs.unchanged == 'true'", close)
    self.assertIn('issues.py pending', close)
    self.assertIn('--close', close)
    self.assertNotRegex(WORKFLOW, r'(?m)^\s+(?:source|\.) .*launch_env|eval |bash .*launch_')
    self.assertNotIn('--checkout', WORKFLOW)
    self.assertNotRegex(WORKFLOW, r'uses: [^\n]*@(?![0-9a-f]{40}\b)')

  def test_backup_guard_failure_cannot_overwrite_lastgood(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      for name, content in (('python3', 'exit 17'), ('git', 'echo unexpected > "$PUSH_LOG"')):
        path = root / name
        path.write_text('#!/bin/bash\n' + content + '\n')
        path.chmod(0o755)
      log = root / 'pushes'
      env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'], 'PUSH_LOG': str(log),
             'NEW': 'a' * 40, 'FORK': 'b' * 40, 'BARE_REPO': str(root), 'BRANCH': 'nightly',
             'NIGHTLY_LOG': str(root / 'nightly.log'), 'GITHUB_OUTPUT': str(root / 'outputs')}
      result = subprocess.run(['bash', '-eo', 'pipefail', '-c', script('Back up previous nightly and publish with lease')],
                              env=env, capture_output=True)
      self.assertEqual(result.returncode, 17)
      self.assertFalse(log.exists())

  def test_revoke_uses_only_published_parent_and_never_latest(self):
    state = fs.reserve_tags(fs.load(), 2)
    pin = automatic_pin(state)
    pin['withdrawn'] = withdrawal()
    state['pins'] = {'19.10': pin}
    fork, upstream = 'e' * 40, 'd' * 40
    launch = f'if [ -z "$AGNOS_VERSION" ]; then\n  export AGNOS_VERSION="19.10"\nfi\nexport WPA3_BOOT_HASH="{pin["boot"]["hash_raw"]}"\n'
    def git(repo, *args):
      if args[2] == '--format=%P':
        return (upstream if args[3] == fork else '').encode()
      return upstream.encode()
    with patch.object(nightly, 'blob', return_value=launch.encode()), patch.object(nightly, 'git', side_effect=git) as calls:
      self.assertEqual(nightly.published_upstream('/mock', fork, state), upstream)
      self.assertFalse(any('fetch' in c.args or 'ls-remote' in c.args for c in calls.call_args_list))
    with patch.object(nightly, 'blob', return_value=launch.replace(pin['boot']['hash_raw'], pin['revert']['boot']['hash_raw']).encode()):
      self.assertEqual(nightly.published_upstream('/mock', fork, state), '')
    fetch = script('Resolve and fetch upstream and current fork (no checkout)')
    revoke = fetch.split('if [ "$UPSTREAM_SOURCE" = published ]; then')[1].split('\n  else\n')[0]
    self.assertNotIn('--depth', revoke)
    self.assertNotIn('commaai/openpilot', revoke)

  def test_revoke_rejects_forged_parent_and_shell_syntax(self):
    state = fs.reserve_tags(fs.load(), 2)
    pin = automatic_pin(state)
    pin['withdrawn'] = withdrawal()
    state['pins'] = {'19.10': pin}
    launch = f'if [ -z "$AGNOS_VERSION" ]; then\n  export AGNOS_VERSION="19.10"\nfi\nexport WPA3_BOOT_HASH="{pin["boot"]["hash_raw"]}"\n'
    with patch.object(nightly, 'blob', return_value=launch.encode()), patch.object(nightly, 'trailer', return_value='a' * 40), \
         patch.object(nightly, 'git', return_value=b'b' * 40):
      with self.assertRaisesRegex(ValueError, 'parent differs'):
        nightly.published_upstream('/mock', 'e' * 40, state)
    with patch.object(nightly, 'blob', return_value=(launch + 'source attacker.sh\n').encode()):
      with self.assertRaises(ValueError):
        nightly.published_upstream('/mock', 'e' * 40, state)

  def test_lastgood_guard_uses_withdrawn_release_trailer(self):
    state = fs.reserve_tags(fs.load(), 2)
    pin = automatic_pin(state)
    state['pins'] = {'19.10': pin}
    with patch.object(nightly, 'trailer', return_value=pin['release_tag']):
      self.assertIsNone(nightly.withdrawn_release('/mock', 'f' * 40, state))
      pin['withdrawn'] = withdrawal()
      self.assertEqual(nightly.withdrawn_release('/mock', 'f' * 40, state), pin)
    push = script('Back up previous nightly and publish with lease')
    self.assertLess(push.index('keep-lastgood'), push.index('push --force origin'))


class PendingIssuesTests(unittest.TestCase):
  def test_escalation_uses_created_at_and_deferral_deadline(self):
    created = issues.utc('2026-10-01T00:00:00Z')
    rows = [{'number': 1, 'createdAt': '2026-10-01T00:00:00Z'}]
    self.assertEqual(issues.pending_hold(rows, None, created + timedelta(hours=47)), '')
    self.assertIn('48 hours', issues.pending_hold(rows, None, created + timedelta(hours=48)))
    for result in ('held', 'risk_held'):
      self.assertEqual(issues.pending_hold([], {'result': result, 'reason': 'K4: held'}, created), 'K4: held')
    deferred = {'result': 'deferred', 'deferred_until': '2026-10-08T00:00:00Z'}
    self.assertEqual(issues.pending_hold(rows, deferred, created + timedelta(days=8)), '')
    self.assertIn('48 hours', issues.pending_hold(rows, deferred, created + timedelta(days=9)))

  def test_full_key_isolation(self):
    key = 'a' * 64
    rows = [{'number': 1, 'body': f'<!-- wpa3-key:{key} -->'},
            {'number': 2, 'body': f'<!-- wpa3-key:{key[:-1]}b -->'}]
    with patch.object(issues, 'gh', return_value=json.dumps(rows)):
      self.assertEqual(issues.listed(['nightly-pending'], key), rows[:1])

  def test_failure_prefixes_and_mentions(self):
    for prefix in ('PIN: FOLLOW:', 'PIN: FAIL:', 'G8: FAIL:', 'K4(e): FAIL:', 'K7b: FAIL:',
                   'W1: FAIL:', 'P1: FAIL:', 'R1: FAIL:', 'T3: FAIL:'):
      self.assertTrue(issues.FAILURE.match(prefix + ' @someone bad'))
    self.assertNotIn('@someone', issues.escaped('``` @someone'))

  def test_cli_pending_escalates_to_red_issue_and_closes_yellow_only(self):
    key = 'a' * 64
    calls, bodies = [], []
    def gh(*args):
      calls.append(args)
      if '--body-file' in args:
        bodies.append(Path(args[args.index('--body-file') + 1]).read_text())
      if args[:2] == ('issue', 'list'):
        if 'nightly-pending' in args:
          return json.dumps([{'number': 7, 'createdAt': '2026-10-01T00:00:00Z', 'body': f'<!-- wpa3-key:{key} -->'}])
        return '[]'
      return ''
    with tempfile.TemporaryDirectory() as tmp, patch.object(issues, 'gh', side_effect=gh), \
         patch.dict(os.environ, GH_REPO='fake/local', GITHUB_RUN_ID='1'):
      log = Path(tmp) / 'log'
      log.write_text(f'PIN: FOLLOW: kernel {key} waiting @owner\n')
      rc = issues.main(['pending', '--branch', 'nightly', '--log', str(log), '--now', '2026-10-03T00:00:00Z'])
    self.assertEqual(rc, 1)
    created = next(c for c in calls if c[:2] == ('issue', 'create'))
    self.assertIn('nightly-hold', created)
    self.assertIn(('issue', 'close', '7'), [c[:3] for c in calls])
    self.assertTrue(all('@owner' not in body for body in bodies))

  def test_recorded_hold_closes_only_matching_pending_key(self):
    key = 'a' * 64
    calls = []
    def gh(*args):
      calls.append(args)
      if args[:2] == ('issue', 'list'):
        if 'nightly-pending' in args:
          return json.dumps([{'number': 7, 'body': f'<!-- wpa3-key:{key} -->'},
                             {'number': 8, 'body': '<!-- wpa3-key:' + 'b' * 64 + ' -->'}])
        return '[]'
      return ''
    with tempfile.TemporaryDirectory() as tmp, patch.object(issues, 'gh', side_effect=gh), \
         patch.dict(os.environ, GH_REPO='fake/local', GITHUB_RUN_ID='1'):
      log = Path(tmp) / 'log'
      log.write_text(f'PIN: FAIL: K4: held\nPIN: KEY: kernel {key} kernel changed\n')
      self.assertEqual(issues.main(['hold', '--branch', 'nightly', '--log', str(log)]), 0)
    self.assertEqual([c[2] for c in calls if c[:2] == ('issue', 'close')], ['7'])

  def test_prior_escalation_cannot_reset_the_48_hour_clock(self):
    key = 'a' * 64
    calls = []
    def gh(*args):
      calls.append(args)
      if args[:2] == ('issue', 'list'):
        if 'nightly-hold' in args:
          return json.dumps([{'number': 9, 'body': f'<!-- wpa3-key:{key} -->'}])
        return '[]'  # The original yellow issue was closed on escalation.
      return ''
    with patch.object(issues, 'gh', side_effect=gh), patch.dict(os.environ, GH_REPO='fake/local', GITHUB_RUN_ID='1'):
      self.assertEqual(issues.main(['pending', '--branch', 'nightly', '--key', key]), 1)
    self.assertIn(('issue', 'edit', '9'), [c[:3] for c in calls])
    self.assertFalse(any(c[:2] == ('issue', 'create') for c in calls))

  def test_wpa_recorded_hold_uses_wpa_attempts(self):
    state = fs.load()
    key = 'a' * 64
    needed = fs.FollowNeeded('wpa', key, 'stock missing')
    state['status']['wpa_attempts'][key] = {'result': 'held', 'reason': 'W1: signature mismatch'}
    with self.assertRaisesRegex(ValueError, 'W1: signature mismatch'):
      fs.follow_exit(needed, 'on', state['policy'], state['status'])

  def test_new_global_kinds_labels_and_rolling_reports(self):
    for kind in ('follow-hold', 'follow-dryrun', 'follow-paused', 'revoke-blocked'):
      calls = []
      def gh(*args):
        calls.append(args)
        return '[]' if args[:2] == ('issue', 'list') else ''
      with patch.object(issues, 'gh', side_effect=gh), patch.dict(os.environ, GH_REPO='fake/local', GITHUB_RUN_ID='1'):
        self.assertEqual(issues.main([kind, '--key', 'a' * 64]), 0)
      created = next(c for c in calls if c[:2] == ('issue', 'create'))
      self.assertIn(kind, created)
      if kind in ('follow-dryrun', 'follow-paused'):
        self.assertNotIn('stock:' + 'a' * 12, created)
      elif kind == 'follow-hold':
        self.assertIn('follow:kernel', created)


if __name__ == '__main__':
  unittest.main()
