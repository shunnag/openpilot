"""Marker format, skip decisions and real local deterministic Git objects."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import nightly_skip as skip

ROOT = Path(__file__).resolve().parents[1]
FIELDS = dict(branch='nightly', head='b' * 40, mode='off', upstream='a' * 40, fork='c' * 40)


class EvaluationMarkerTests(unittest.TestCase):
  def test_exact_format_round_trip(self):
    message = skip.marker_message(**FIELDS)
    self.assertEqual(message, 'wpa3-evaluated\n\nBranch: nightly\nHead: ' + 'b' * 40 +
                     '\nMode: off\nUpstream: ' + 'a' * 40 + '\nFork: ' + 'c' * 40 + '\n')
    self.assertEqual(skip.parse_marker(message), FIELDS)
    self.assertEqual(skip.marker_message(**skip.parse_marker(message)), message)
    self.assertEqual(skip.parse_marker(message.rstrip('\n')), FIELDS)

  def test_missing_garbled_or_duplicate_fields_are_rejected(self):
    message = skip.marker_message(**FIELDS)
    for bad in ('', 'wpa3-evaluated', message.replace('wpa3-evaluated', 'unknown'),
                message.replace('Branch: nightly\n', ''), message + 'Fork: ' + 'c' * 40,
                message.replace('Mode: off', 'Mode: unknown'),
                message.replace('Head: ' + 'b' * 40, 'Head: bad'), message + 'extra text'):
      with self.subTest(message=bad):
        self.assertIsNone(skip.parse_marker(bad))
    with self.assertRaises(ValueError):
      skip.marker_message(**{**FIELDS, 'branch': 'nightly\nHead: injected'})

  def test_marker_sha_is_deterministic_empty_tree_and_parentless(self):
    (ROOT / '.tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / '.tmp', prefix='test-marker-') as directory:
      repo = Path(directory) / 'marker.git'
      subprocess.run(['git', 'init', '--bare', str(repo)], capture_output=True, check=True)
      tree = skip.git(repo, 'hash-object', '-t', 'tree', '-w', '--stdin', data=b'').decode().strip()
      identity = {**os.environ, **{f'GIT_{role}_{key}': value for role in ('AUTHOR', 'COMMITTER')
        for key, value in (('NAME', 'fixture'), ('EMAIL', 'fixture@example.invalid'),
                           ('DATE', '2026-10-01T00:00:00+00:00'))}}
      upstream = skip.git(repo, 'commit-tree', '--no-gpg-sign', tree, data=b'upstream\n', env=identity).decode().strip()
      fields = {**FIELDS, 'upstream': upstream}
      subprocess.run(['git', '-C', str(repo), 'config', 'commit.gpgsign', 'true'], check=True)
      first = skip.create_marker(repo, **fields)
      with patch.dict(os.environ, GIT_AUTHOR_NAME='different', GIT_COMMITTER_NAME='different',
                      GIT_AUTHOR_DATE='2000-01-01T00:00:00Z', GIT_COMMITTER_DATE='2001-01-01T00:00:00Z'):
        second = skip.create_marker(repo, **fields)
      self.assertEqual(first, second)
      self.assertNotEqual(first, skip.create_marker(repo, **{**fields, 'fork': 'd' * 40}))
      self.assertEqual(skip.git(repo, 'show', '-s', '--format=%T', first).decode().strip(), tree)
      self.assertEqual(skip.git(repo, 'show', '-s', '--format=%P', first).strip(), b'')
      raw = skip.git(repo, 'cat-file', 'commit', first).decode()
      self.assertEqual(raw.split('\n\n', 1)[1], skip.marker_message(**fields))
      self.assertIn('author wpa3-ci <wpa3-ci@users.noreply.github.com> 1790812800 +0000\n', raw)
      self.assertIn('committer wpa3-ci <wpa3-ci@users.noreply.github.com> 1790812800 +0000\n', raw)

  def test_marker_reads_are_gets_and_cached_per_sha_without_run_or_issue_lookups(self):
    (ROOT / '.tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as directory:
      env = {'GH_REPO': 'fake/local', 'RUNNER_TEMP': directory, 'GITHUB_RUN_ID': '1'}
      message = skip.marker_message(**FIELDS)
      with patch.object(skip.subprocess, 'check_output', return_value=message) as api:
        self.assertEqual(skip.read_marker('d' * 40, env), message)
        self.assertEqual(skip.read_marker('d' * 40, env), message)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(api.call_args.args[0], [
          'gh', 'api', '--method', 'GET', 'repos/fake/local/git/commits/' + 'd' * 40, '--jq', '.message'])
        skip.read_marker('e' * 40, env)
        self.assertEqual(api.call_count, 2)

  def test_missing_marker_has_no_api_reads(self):
    with patch.object(skip.subprocess, 'check_output') as api:
      for marker in ('', 'garbled'):
        self.assertEqual(skip.read_marker(marker, {}), '')
      api.assert_not_called()

  def test_dry_message_override_is_ignored_without_dry_run(self):
    message = skip.marker_message(**FIELDS)
    with patch.object(skip.subprocess, 'check_output') as api:
      self.assertEqual(skip.read_marker('', {'DRY_RUN': '1', 'DRY_MARKER_MESSAGE': message}), message)
      self.assertEqual(skip.read_marker('', {'DRY_RUN': '0', 'DRY_MARKER_MESSAGE': message}), '')
      api.assert_not_called()


class EarlySkipTests(unittest.TestCase):
  def setUp(self):
    self.inputs = {**FIELDS, 'message': skip.marker_message(**FIELDS), 'ref': 'refs/heads/wpa3-ci'}

  def test_all_marker_fields_match(self):
    self.assertTrue(skip.can_skip(**self.inputs))

  def test_each_field_mismatch_requires_evaluation(self):
    for field, different in dict(branch='other', head='d' * 40, mode='on', upstream='d' * 40, fork='d' * 40).items():
      with self.subTest(field=field):
        self.assertFalse(skip.can_skip(**{**self.inputs, field: different}))

  def test_missing_garbled_or_unversioned_marker_never_skips(self):
    for message in ('', 'garbled', 'Build\n\nUpstream-Commit: ' + 'a' * 40):
      self.assertFalse(skip.can_skip(**{**self.inputs, 'message': message}))

  def test_force_never_skips(self):
    self.assertFalse(skip.can_skip(**self.inputs, force=True))

  def test_withdrawal_never_skips(self):
    self.assertFalse(skip.can_skip(**self.inputs, source='published'))

  def test_other_or_missing_ref_never_skips(self):
    for ref in ('refs/heads/other', 'refs/tags/wpa3-ci', ''):
      self.assertFalse(skip.can_skip(**{**self.inputs, 'ref': ref}))


if __name__ == '__main__':
  unittest.main()
