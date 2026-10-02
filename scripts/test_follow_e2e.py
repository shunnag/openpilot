#!/usr/bin/env python3
"""Offline Part 4b simulation: real temporary git remote, fake GitHub, synthetic boots.

All commits and pushes in this test target disposable local repositories only.
No GitHub workflow, release, repository variable or real branch is modified.
"""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import compose
import follow_git
import follow_state as fs
import follow_publish as publish
import follow_admin
import gates
import nightly
import pins
import test_compose
import test_follow_publish
from kernel_common import git, git_text

ROOT = Path(__file__).resolve().parents[1]


class FollowEndToEnd(unittest.TestCase):
  def test_reserve_publish_all_four_and_revoke_against_published_upstream(self):
    # Reuse the signed synthetic boot/artifact fixtures, but replace MemoryGit
    # with the real state writer and a disposable bare clone of wpa3-ci.
    fixture_class = test_follow_publish.PublicationTests
    fixture_class.setUpClass()
    self.addCleanup(fixture_class.doClassCleanups)
    fixture = fixture_class('test_two_phase_publish_assets_then_pin_then_dispatch')
    fixture.setUp()
    self.addCleanup(fixture.doCleanups)
    for mock in fixture.mocks[:3]:  # Keep only fake HTTP, fixture gate version and byte downloads.
      mock.stop()
    with tempfile.TemporaryDirectory(prefix='follow-e2e-') as tmp:
      root = Path(tmp)
      remote, work = root / 'origin.git', root / 'publisher'
      env = {**os.environ, **compose.LFS_ENV, 'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_NOSYSTEM': '1'}
      def command(*args):
        return subprocess.run([str(a) for a in args], env=env, check=True, capture_output=True).stdout.decode().strip()
      command('git', 'clone', '--bare', '--no-hardlinks', '--single-branch', '--branch', 'wpa3-ci', ROOT, remote)
      command('git', 'clone', remote, work)
      # Include this uncommitted implementation in the isolated fixture checkout.
      for source in (ROOT / 'scripts').glob('*.py'):
        shutil.copyfile(source, work / 'scripts' / source.name)
      shutil.copytree(ROOT / 'follow/templates', work / 'follow/templates', dirs_exist_ok=True)
      shutil.copyfile(ROOT / 'README.md', work / 'README.md')
      state = deepcopy(fixture.remote.state)
      state['system_probe']['e' * 64] = deepcopy(next(iter(state['system_probe'].values())))
      for name, value in fs.state_files(state).items():
        (work / name).write_bytes(value)
      (work / 'agnos/pins.json').write_text(fs.dumps(state['manual']))
      (work / 'follow/policy.json').write_text(fs.dumps(state['policy']))
      command('git', '-C', work, 'add', '--', 'scripts', 'follow', 'agnos', 'README.md')
      command('git', '-C', work, '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
              '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'Local simulation inputs')
      command('git', '-C', work, 'push', 'origin', 'HEAD:refs/heads/wpa3-ci')
      before = git_text(remote, 'rev-parse', 'wpa3-ci')
      writer = follow_git.StateWriter(publish.Brakes(fixture.gh, fixture.gate, 'on'), 'on', fixture.writer.run_url, root=work)
      publisher = publish.Publisher(fixture.gh, writer, fixture.gate, writer.run_url)
      admin = follow_admin.Admin(publisher, 'shunnag', root / 'restore.json')
      publisher.kernel(fixture.verified, fixture.item, fixture.stock, fixture.key)
      after = git_text(remote, 'rev-parse', 'wpa3-ci')
      commits = git_text(remote, 'rev-list', '--reverse', f'{before}..{after}').splitlines()
      self.assertEqual(len(commits), 2, 'reservation must precede the pin state commit')
      reserved_status = json.loads(git(remote, 'show', f'{commits[0]}:agnos/auto/status.json'))
      self.assertEqual(reserved_status['allocated_tags'], [1, 2, 3, 4, 5])
      self.assertEqual(json.loads(git(remote, 'show', f'{commits[0]}:agnos/auto/pins.json')), {})
      state, _ = writer.read(operation="mark-tested")
      automatic = state['pins']['19.10']
      self.assertEqual(automatic['tag'], 'wpa3.sae=4')
      print('E2E: reservation commit -> immutable release -> pin state commit')
      dispatches = [e for e in fixture.gh.events if isinstance(e, tuple) and e[0] == 'dispatch']
      self.assertEqual(dispatches, [('dispatch', 'nightly.yml', None)])

      test_compose.TestCompose.setUpClass()
      self.addCleanup(test_compose.TestCompose.doClassCleanups)
      upstreams = test_compose.TestCompose()
      repo = upstreams.repo
      compose.git(repo, 'remote', 'add', 'simulation', str(remote))
      published, original, backups = {}, {}, {}
      for branch in fs.BRANCHES:
        manifest = json.loads(compose.blob(repo, upstreams.upstream, compose.MANIFEST))
        for entry in manifest:
          if entry['name'] == 'boot':
            entry.update(hash_raw=automatic['derived_from']['boot_hash_raw'], size=len(fixture.stock),
                         url=automatic['derived_from']['boot_url'])
          elif entry['name'] == 'system':
            entry['hash_raw'] = 'e' * 64
        launch = compose.blob(repo, upstreams.upstream, 'launch_env.sh').replace(b'19.8', b'19.10')
        changes = {'launch_env.sh': launch, compose.MANIFEST: compose.manifest_bytes(manifest),
                   'RELEASES.md': b'Version 0.11.2 (2026-08-12)\n============================\n* Upstream notes\n\nOlder notes\n'}
        if branch.startswith('release-'):
          changes['launch_chffrplus.sh'] = (test_compose.RELEASE_REF / 'launch_chffrplus.sh').read_bytes()
        with compose.temporary_index(repo, upstreams.upstream) as (index_env, _):
          for name, data in changes.items():
            compose.put_blob(repo, index_env, name, data, mode='100644' if name == 'RELEASES.md' else None)
          tree = compose.git(repo, 'write-tree', env=index_env).decode().strip()
          upstream = compose.git(repo, 'commit-tree', tree, data=b'Synthetic AGNOS 19.10 upstream\n',
                                 env=upstreams.identity).decode().strip()
        original[branch] = upstream
        # Keep a prior known branch build to exercise G6 and the backup guard.
        backup = upstreams.commit
        backups[branch] = backup
        compose.git(repo, 'push', 'simulation', f'{backup}:refs/heads/{branch}', f'{backup}:refs/heads/{branch}-lastgood')
        resolved = pins.resolve(lambda path: compose.blob(repo, upstream, path), state['manual'], fixture.fetch,
                                state=state, mode='on', branch=branch)
        self.assertEqual(resolved['mode'], 'pinned', branch)
        self.assertIn('auto', resolved['pin'])
        self.assertEqual(resolved['pin']['tag'], 'wpa3.sae=4')
        pin_file = root / 'pin.json'
        pin_file.write_text(fs.dumps(resolved))
        log = io.StringIO()
        with patch.object(gates, 'load', return_value=state), redirect_stdout(log):
          self.assertEqual(gates.run_gates(repo, upstream, pin_file, skip_download=True, published=backup, follow_mode='on'), 0)
        for gate in ('G1', 'G2', 'G3', 'G5', 'G6', 'G7', 'G8'):
          self.assertIn(f'{gate}: OK:', log.getvalue(), log.getvalue())
        self.assertIn('G4: SKIP: --skip-download', log.getvalue())
        result = upstreams.cli('compose.py', upstream, pin_file=pin_file)
        new = result.stdout.splitlines()[0]
        parsed = compose.launch_values(compose.blob(repo, new, 'launch_env.sh'))
        self.assertEqual(parsed[:3], ('19.10', automatic['tag'], automatic['boot']['hash_raw']))
        release_notes = compose.blob(repo, new, 'RELEASES.md').decode()
        self.assertTrue(release_notes.startswith(f"WPA3 kernel {automatic['release_tag']} was built automatically"))
        self.assertIn('Version 0.11.2', release_notes.split('\n\n')[0])
        compose.git(repo, 'push', f'--force-with-lease=refs/heads/{branch}:{backup}', 'simulation', f'{new}:refs/heads/{branch}')
        published[branch] = new
        print(f'E2E: {branch}: pinned automatic tag 4; G1-G8 pass (G4 skipped offline); composed and published locally')

      # Today's latest upstream cannot pass the launcher gate. Revoke must never use it.
      latest = upstreams.variant('launch_chffrplus.sh', b'upstream changed incompatibly\n')
      with self.assertRaisesRegex(ValueError, 'no launcher patch applies'):
        compose.select_launcher_patch(repo, latest)
      admin.revoke(automatic['release_tag'], 'synthetic Wi-Fi failure')
      state, _ = writer.read(operation='revoke')
      self.assertIsNotNone(state['status']['paused'])
      self.assertIn(('dispatch', 'nightly.yml', {'upstream': 'published'}), fixture.gh.events)
      revoke_repo = root / 'nightly-revoke.git'
      command('git', 'init', '--bare', revoke_repo)
      command('git', '-C', revoke_repo, 'remote', 'add', 'origin', remote)
      for branch, fork in published.items():
        command('git', '-C', revoke_repo, 'fetch', '--no-tags', '--no-recurse-submodules', 'origin', fork)
        upstream = nightly.published_upstream(revoke_repo, fork, state)
        self.assertEqual(upstream, original[branch])
        for mode in fs.MODES:
          resolved = pins.resolve(lambda path: compose.blob(revoke_repo, upstream, path), state['manual'], fixture.fetch,
                                  state=state, mode=mode, branch=branch)
          self.assertEqual(resolved['pin']['boot'], automatic['revert']['boot'])
          self.assertEqual(resolved['pin']['tag'], 'wpa3.sae=5')
        pin_file.write_text(fs.dumps(resolved))
        log = io.StringIO()
        with patch.object(gates, 'load', return_value=state), redirect_stdout(log):
          self.assertEqual(gates.run_gates(revoke_repo, upstream, pin_file, skip_download=True,
                                         published=fork, follow_mode='on', revoke=True), 0)
        self.assertIn('G8: WARN:', log.getvalue())
        new = command(os.sys.executable, ROOT / 'scripts/compose.py', '--repo', revoke_repo,
                      '--upstream', upstream, '--pin-file', pin_file).splitlines()[0]
        self.assertEqual(compose.launch_values(compose.blob(revoke_repo, new, 'launch_env.sh'))[:3],
                         ('19.10', 'wpa3.sae=5', automatic['revert']['boot']['hash_raw']))
        self.assertIn('was withdrawn;', compose.blob(revoke_repo, new, 'RELEASES.md').decode())
        self.assertTrue(nightly.withdrawn_release(revoke_repo, fork, state))
        # Execute the actual workflow push step with only the metadata helper mocked
        # to point at this simulation's state root (all git pushes remain local).
        from test_nightly import script
        fake_bin = root / 'bin'
        fake_bin.mkdir(exist_ok=True)
        fake = fake_bin / 'python3'
        fake.write_text('#!/bin/bash\n[[ "$1 $2" == "scripts/nightly.py keep-lastgood" ]] || exit 99\necho true\n')
        fake.chmod(0o755)
        command_env = {**env, 'PATH': str(fake_bin) + os.pathsep + env['PATH'], 'BARE_REPO': str(revoke_repo),
          'BRANCH': branch, 'NEW': new, 'FORK': fork, 'NIGHTLY_LOG': str(root / 'nightly.log'), 'GITHUB_OUTPUT': str(root / 'outputs')}
        subprocess.run(['bash', '-eo', 'pipefail', '-c', script('Back up previous nightly and publish with lease')],
                       env=command_env, capture_output=True, check=True)
        self.assertEqual(git_text(remote, 'rev-parse', branch + '-lastgood'), backups[branch])
        self.assertEqual(git_text(remote, 'rev-parse', branch), new)
        self.assertEqual(nightly.published_upstream(revoke_repo, new, state), '')
        print(f'E2E: {branch}: revoked to tag 5 against published upstream; lastgood retained')
      print('E2E: PASS; all changes stayed in temporary local repositories; GitHub was fake')


if __name__ == '__main__':
  unittest.main()
