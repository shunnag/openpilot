"""Part 4a failure injection. gh/git are mocked; no test accesses the network."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import bootimg
import follow_admin as admin
import follow_git as transaction
import follow_publish as publish
import follow_state as fs
from kernel_common import ROOT, read_json, sha256, write_json
import kernel_equiv as ke
import kernel_follow
from test_follow_state import automatic_pin, attempt, withdrawal
import test_kernel_follow as kernel_tests
import wpa_request


class MemoryGit:
  """Mock remote heads/worktrees while exercising the real commit protocol."""
  def __init__(self, state, root):
    self.state, self.root = deepcopy(state), root
    self.head, self.counter = '1' * 40, 1
    self.events, self.snapshots = [], {}
    self.rejects = 0
    self.on_reject = lambda state: None
    self.on_fetch = lambda state: None
    self.disallowed = None

  @contextmanager
  def fresh(self):
    self.on_fetch(self.state)
    self.events.append('fetch')
    with tempfile.TemporaryDirectory(dir=self.root) as tmp:
      work = Path(tmp)
      old = deepcopy(self.state)
      for name, data in fs.state_files(old).items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
      (work / 'README.md').write_text('owner text\n<!-- wpa3-status:begin -->\nold\n<!-- wpa3-status:end -->\nend\n')
      self.snapshots[work] = {str(p.relative_to(work)): p.read_bytes() for p in work.rglob('*') if p.is_file()}
      yield work, self.head, old

  def diff(self, work):
    old = self.snapshots[work]
    changed = [(name, 'M') for name, data in old.items() if (work / name).read_bytes() != data]
    if self.disallowed:
      changed.append((self.disallowed, 'M'))
    return changed

  def git(self, work, *args, data=None):
    self.events.append(args)
    if args[0] == 'diff':
      rows = self.diff(work)
      if '--name-status' in args:
        return ''.join(f'{status}\0{name}\0' for name, status in rows).encode()
      return ''.join(f':100644 100644 {"a" * 40} {"b" * 40} {status}\0{name}\0' for name, status in rows).encode()
    if args[0] == 'show':
      return (work / 'README.md').read_bytes() if args[1] == 'HEAD:README.md' else self.snapshots[work]['README.md']
    if args[0] == 'push':
      if self.rejects:
        self.rejects -= 1
        self.counter += 1
        self.head = f'{self.counter:040x}'
        self.on_reject(self.state)
        raise subprocess.CalledProcessError(1, ['git', *args], stderr=b'[rejected] non-fast-forward')
      for kind in fs.STATE_FILES:
        self.state[kind] = read_json(work / 'agnos/auto' / f'{kind}.json')
      self.counter += 1
      self.head = f'{self.counter:040x}'
    return b''


class MemoryGitHub:
  def __init__(self, mode='on'):
    self.mode, self.repository = mode, 'shunnag/openpilot'
    self.items, self.assets, self.issues, self.events = {}, {}, [], []
    self.enabled, self.immutable_after = True, True
    self.active, self.nightly_active = True, True
    self.after_upload = lambda: None
    self.after_publish = lambda: None

  def releases(self):
    return deepcopy(list(self.items.values()))

  def release(self, identity):
    return deepcopy(self.items[identity])

  def by_tag(self, tag):
    return next(r for r in self.releases() if r['tag_name'] == tag)

  def pages(self, path):
    return []

  def immutable(self):
    self.events.append('immutable')
    publish.require(self.enabled, 'infra: repository immutable releases disabled')

  def paused(self):
    return deepcopy(self.issues)

  def workflow(self, name):
    active = self.active if name == 'follow.yml' else self.nightly_active
    return {'state': 'active' if active else 'disabled_manually'}

  def api(self, path, method='GET', body=None):
    self.events.append((path, method, body))
    if path == 'releases' and method == 'POST':
      identity = len(self.items) + 1
      result = {**deepcopy(body), 'id': identity, 'assets': [], 'immutable': False, 'published_at': None}
      self.items[identity], self.assets[identity] = result, {}
      return deepcopy(result)
    if path.endswith('/enable'):
      self.nightly_active = True
      return None
    if path.endswith('/disable'):
      self.nightly_active = False
      return None
    if path.startswith('actions/runs/'):
      return {'event': 'workflow_dispatch', 'head_branch': 'wpa3-ci', 'status': 'completed', 'conclusion': 'success'}
    raise AssertionError(f'unexpected mock API {method} {path}')

  def edit(self, release, **fields):
    self.events.append(('edit', release['id'], deepcopy(fields)))
    current = self.items[release['id']]
    current.update(fields)
    if fields.get('draft') is False:
      current.update(immutable=self.immutable_after, published_at=publish.now_text())
      self.after_publish()
    return deepcopy(current)

  def upload(self, release, directory, *, names=None, replace=False):
    publish.require(self.items[release['id']]['draft'] is True, 'upload after publication')
    self.events.append(('upload', release['id'], replace))
    for path in directory.iterdir():
      if names is None or path.name in names:
        self.assets[release['id']][path.name] = path.read_bytes()
    self.items[release['id']]['assets'] = [{'name': k, 'size': len(v)} for k, v in self.assets[release['id']].items()]
    self.after_upload()

  def download(self, release, directory, names=None):
    self.events.append(('download', release['id']))
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in self.assets[release['id']].items():
      if names is None or name in names:
        (directory / name).write_bytes(data)

  def issue(self, label, title, body, *, key=''):
    self.events.append(('issue', label, title))
    if label == 'follow-paused':
      self.issues.append({'number': 10, 'title': title, 'body': body})

  def dispatch(self, workflow='nightly.yml', inputs=None, *, details=False):
    self.events.append(('dispatch', workflow, inputs))
    return 42 if details else None


class TransactionTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.remote = MemoryGit(fs.load(), Path(self.tmp.name))
    self.brakes = Mock()
    self.writer = transaction.StateWriter(self.brakes, 'on', 'https://github.com/shunnag/openpilot/actions/runs/123')
    self.writer.fresh = self.remote.fresh
    for name, value in [('git', self.remote.git), ('git_text', lambda *a: 'e' * 40), ('run', Mock(return_value=b''))]:
      mock = patch.object(transaction, name, value)
      mock.start()
      self.addCleanup(mock.stop)

  def allocate(self, state):
    n = fs.allocate_tag(state)
    return {'status': {'allocated_tags': fs.reserve_tags(state, 2)['status']['allocated_tags']}}, n

  def test_reservation_reapplies_on_push_conflict_and_serializes_allocators(self):
    self.remote.rejects = 1
    self.remote.on_reject = lambda state: state['status']['allocated_tags'].extend([4, 5])
    result = self.writer.commit(self.allocate, 'reserve')
    self.assertEqual(result.value, 6)
    self.assertFalse(result.dispatch)
    second = self.writer.commit(self.allocate, 'reserve')
    self.assertEqual(second.value, 8)
    self.assertEqual(self.remote.state['status']['allocated_tags'], list(range(1, 10)))
    pushes = [e for e in self.remote.events if isinstance(e, tuple) and e[0] == 'push']
    self.assertEqual(pushes, [('push', 'origin', 'HEAD:refs/heads/wpa3-ci')] * 3)
    checks = [e for e in self.remote.events if isinstance(e, tuple) and e[:2] == ('diff', '--no-renames')]
    self.assertEqual(len(checks), 6)
    self.assertTrue(all(e[-1] == 'HEAD' for e in checks))

  def test_three_push_conflicts_abort(self):
    self.remote.rejects = 3
    with self.assertRaisesRegex(ValueError, 'after 3 tries'):
      self.writer.commit(self.allocate, 'reserve')
    self.assertEqual(sum(isinstance(e, tuple) and e[0] == 'push' for e in self.remote.events), 3)

  def test_changed_head_before_push_is_reapplied(self):
    count = 0
    def fetch(state):
      nonlocal count
      count += 1
      if count == 2:
        state['status']['allocated_tags'].extend([4, 5])
        self.remote.head = '2' * 40
    self.remote.on_fetch = fetch
    result = self.writer.commit(self.allocate, 'reserve')
    self.assertEqual(result.value, 6)
    self.assertEqual(sum(isinstance(e, tuple) and e[0] == 'push' for e in self.remote.events), 1)

  def test_pause_on_retry_prevents_push(self):
    self.remote.rejects = 1
    self.remote.on_reject = lambda state: state['status'].update(paused=withdrawal())
    self.brakes.side_effect = lambda state, *a: fs.require(state['status']['paused'] is None, 'paused')
    with self.assertRaisesRegex(ValueError, 'paused'):
      self.writer.commit(self.allocate, 'reserve')
    self.assertEqual(sum(isinstance(e, tuple) and e[0] == 'push' for e in self.remote.events), 1)

  def test_allowlist_checks_final_commit_before_every_push(self):
    for path in ('.github/workflows/follow.yml', 'follow/policy.json', 'follow/reference/test.txt', 'scripts/pins.py',
                 'agnos/pins.json', 'patches/launcher-wpa3.patch', 'userspace/wpa_supplicant', 'other.txt'):
      with self.subTest(path=path):
        self.remote.events.clear()
        self.remote.disallowed = path
        with self.assertRaisesRegex(ValueError, 'allowlist'):
          self.writer.commit(self.allocate, 'reserve')
        self.assertFalse(any(isinstance(e, tuple) and e[0] == 'push' for e in self.remote.events))

  def test_noop_does_not_commit_or_dispatch(self):
    result = self.writer.commit(lambda old: ({}, None), 'noop')
    self.assertFalse(result.changed or result.dispatch)
    self.assertFalse(any(isinstance(e, tuple) for e in self.remote.events))

  def test_readme_changes_only_inside_markers(self):
    self.writer.commit(self.allocate, 'reserve', readme=True)
    self.assertTrue(any(isinstance(e, tuple) and e[0] == 'show' for e in self.remote.events))
    text = 'before\n<!-- wpa3-status:begin -->old<!-- wpa3-status:end -->after'
    result = transaction.status_readme(text, self.remote.state)
    self.assertTrue(result.startswith('before\n<!-- wpa3-status:begin -->'))
    self.assertTrue(result.endswith('<!-- wpa3-status:end -->after'))

  def test_mode_guard_is_independent_of_caller(self):
    for mode in ('off', 'dryrun'):
      self.writer.mode = mode
      with self.assertRaisesRegex(ValueError, 'state/on'):
        self.writer.commit(self.allocate, 'reserve')
    self.assertEqual(self.remote.events, [])

  def test_final_diff_rejects_deletion_mode_symlink_rename_and_old_build(self):
    cases = [('D', 'agnos/auto/pins.json', '100644', '000000'),
             ('M', 'agnos/auto/status.json', '100644', '100755'),
             ('A', 'agnos/auto/pins.json', '000000', '120000'),
             ('R100', 'agnos/auto/pins.json', '100644', '100644'),
             ('M', 'userspace/wpa/2.10-21ubuntu0.5/wpa_supplicant', '100755', '100755'),
             ('A', 'userspace/wpa/2.10-21ubuntu0.5/wpa_supplicant.copyright', '000000', '100644')]
    for status, path, old, new in cases:
      with self.subTest(status=status, path=path):
        def git(work, *args):
          if '--name-status' in args:
            return f'{status}\0{path}\0'.encode()
          if '--raw' in args:
            return f':{old} {new} {"a" * 40} {"b" * 40} {status}\0{path}\0'.encode()
          if args[0] == 'ls-tree':
            return b'existing directory'
          raise AssertionError(args)
        with patch.object(transaction, 'git', side_effect=git), self.assertRaises(ValueError):
          transaction.final_allowlist(Path('/mock'), 'a' * 40)


class PublicationTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    # Reuse the existing synthetic boot generator, not a real image or network.
    cls.crypto = tempfile.TemporaryDirectory()
    cls.addClassCleanup(cls.crypto.cleanup)
    cls.key = Path(cls.crypto.name) / 'key'
    subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(cls.key)],
                   check=True, capture_output=True)
    cls.stock = kernel_tests.TestAssembly.signed.__func__(cls, False)
    cls.wpa = kernel_tests.TestAssembly.signed.__func__(cls, True)

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.root = Path(self.tmp.name)
    state = fs.load()
    state['policy']['vble_public_key_sha256'] = bootimg.pubkey_sha256(bootimg._openssl('rsa', '-in', self.key, '-pubout'))
    self.raw = {sha256(self.stock): self.stock}
    for pin in state['manual'].values():
      image = bootimg.with_tag(self.wpa, pin['tag'], self.key)
      self.raw[sha256(image)] = image
      pin['boot'].update(hash=sha256(image), hash_raw=sha256(image), size=len(image), ondevice_hash=bootimg.ondevice_hash(image))
    self.remote = MemoryGit(state, self.root)
    self.gh = MemoryGitHub()
    self.gate = 'f' * 64
    self.writer = transaction.StateWriter(publish.Brakes(self.gh, self.gate, 'on'), 'on', 'https://github.com/shunnag/openpilot/actions/runs/123')
    self.writer.fresh = self.remote.fresh
    self.pub = publish.Publisher(self.gh, self.writer, self.gate, self.writer.run_url)
    self.admin = admin.Admin(self.pub, 'shunnag', self.root / 'restore.json')
    self.mocks = [patch.object(transaction, 'git', self.remote.git),
                  patch.object(transaction, 'git_text', return_value='e' * 40), patch.object(transaction, 'run', return_value=b''),
                  patch.object(fs, 'gate_version', return_value=self.gate),
                  patch.object(publish, 'fetch_boot', side_effect=self.fetch),
                  patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden'))]
    for mock in self.mocks:
      mock.start()
      self.addCleanup(mock.stop)
    self.verified = self.root / 'verified'
    self.verified.mkdir()
    required = ('K0', 'K2', 'K3', 'K4(a)', 'K4(b)', 'K4(c)', 'K4(e)', 'K4(f)', 'K5', 'K6', 'K7', 'K7b',
                'K7b-format', 'K8-format', 'K9', 'K9-selfcheck', 'K11', 'K12')
    rows = [{'gate': gate, 'result': 'OK', 'kind': 'integrity', 'detail': 'fixture'} for gate in required]
    self.facts = {'gates': rows, 'prebuild': {'gates': []}, 'gate_version': self.gate, 'stock_hash_raw': sha256(self.stock),
                  'candidate': {'commit': 'a' * 40, 'builder_commit': 'b' * 40}, 'refs_fingerprint': 'c' * 64}
    for name in (*state['policy']['patches'], 'source.diff'):
      shutil.copyfile(ROOT / 'follow/kernel-patches' / name, self.verified / name)
    for name in ('source.tar.xz', 'SOURCE.txt', 'stock-rebuild-report.txt', 'build.log'):
      (self.verified / name).write_bytes(b'fixture data\n')
    wpa = bootimg.with_tag(self.wpa, 'wpa3.sae=4', self.key)
    revert = bootimg.with_tag(self.stock, 'wpa3.sae=5', self.key)
    for name, image in (('boot', wpa), ('revert', revert)):
      self.facts[name] = {'hash_raw': sha256(image), 'size': len(image)}
    publish.assembly.write_artifacts(self.verified, wpa, revert, self.facts)
    self.item = {'version': '19.10', 'stock_hash': sha256(self.stock), 'baseline_release': 'agnos-19.9-wpa3.3',
      'baseline_commit': 'd' * 40, 'agnos_py_blob': state['manual']['19.9']['derived_from']['agnos_py_blob'],
      'manifest': [{'name': 'boot', 'url': f'https://commadist.azureedge.net/agnosupdate/boot-{sha256(self.stock)}.img.xz'},
                   {'name': 'system', 'hash_raw': 'e' * 64}]}

  def fetch(self, url, digest, size):
    if digest not in self.raw:
      for assets in self.gh.assets.values():
        name = f'boot-{digest}.img.xz'
        if name in assets:
          import lzma
          self.raw[digest] = lzma.decompress(assets[name])
    data = self.raw[digest]
    self.assertEqual(len(data), size)
    return data

  def kernel(self):
    return self.pub.kernel(self.verified, self.item, self.stock, self.key)

  def published(self):
    return [e for e in self.gh.events if isinstance(e, tuple) and e[0] == 'edit' and e[2].get('draft') is False]

  def risk(self):
    self.facts['prebuild']['gates'] = [{'gate': 'K4(a)', 'result': 'FAIL', 'kind': 'risk', 'detail': 'Wi-Fi path'}]
    write_json(self.verified / 'provenance.json', self.facts)
    publish.checksums(self.verified, write=True)

  def test_wpa_draft_notes_are_rendered_from_its_provenance(self):
    source = self.root / 'wpa'
    shutil.copytree(ROOT / 'scripts/fixtures/wpa_request/assets', source)
    shutil.copyfile(ROOT / 'scripts/fixtures/wpa_request/valid.json', source / 'test-request.json')
    write_json(source / 'build-report.json', {'R1': 'PASS', 'device_tested': False})
    write_json(source / 'test-report.json', {'T0': 'PASS', 'T1': 'PASS', 'T2': 'PASS', 'T3': 'PENDING (dryrun)'})
    self.pub.wpa_draft(source)
    release = self.gh.release(1)
    self.assertTrue(release['draft'])
    provenance = json.loads(self.gh.assets[1]['provenance.json'])
    from release_notes import render
    title, body = render(provenance, 'wpa')
    self.assertEqual((release['name'], release['body']), (title, body))
    self.assertIn('WITHOUT any device test', body)
    self.assertIn('T3: PENDING (dryrun)', body)
    self.assertIn('policy.wpa.auto_publish AND a matching public Mac mini T3 result', body)
    self.assertEqual(set(provenance['assets']), set(self.gh.assets[1]))

  def test_two_phase_publish_assets_then_pin_then_dispatch(self):
    self.kernel()
    state = self.remote.state
    pin = state['pins']['19.10']
    self.assertEqual(state['status']['allocated_tags'], [1, 2, 3, 4, 5])
    self.assertEqual(pin['tag'], 'wpa3.sae=4')
    self.assertEqual(pin['revert']['tag'], 'wpa3.sae=5')
    self.assertEqual(len(self.published()), 1)
    self.assertTrue(self.gh.items[1]['immutable'])
    self.assertTrue(self.gh.items[1]['prerelease'])
    self.assertEqual(self.gh.items[1]['make_latest'], 'false')
    self.assertEqual(self.gh.events[-1], ('dispatch', 'nightly.yml', None))
    self.assertTrue(any(e == ('download', 1) for e in self.gh.events))
    template = json.loads(self.gh.assets[1]['provenance.json'])
    rebuilt = publish.pin_from_provenance(template, self.gh.items[1], sha256(self.gh.assets[1]['provenance.json']))
    self.assertEqual(pin, rebuilt)

  def test_already_pinned_does_nothing(self):
    self.kernel()
    before = deepcopy(self.gh.events)
    self.kernel()
    self.assertEqual(self.gh.events, before)

  def test_crash_after_publish_recovers_without_build_and_dispatches_once(self):
    with patch.object(self.pub, 'pin_commit', side_effect=RuntimeError('crash after release')):
      with self.assertRaisesRegex(RuntimeError, 'crash'):
        self.kernel()
    self.assertEqual(self.remote.state['pins'], {})
    release = self.gh.release(1)
    self.pub.recover(release)
    self.assertIn('19.10', self.remote.state['pins'])
    self.assertEqual(len(self.published()), 1)
    self.assertEqual(sum(isinstance(e, tuple) and e[0] == 'dispatch' for e in self.gh.events), 1)
    before = deepcopy(self.gh.events)
    self.pub.recover(release)
    self.assertEqual([e for e in self.gh.events[len(before):] if isinstance(e, tuple)], [])

  def test_mutable_release_never_recovers_or_pins(self):
    self.gh.immutable_after = False
    with self.assertRaisesRegex(ValueError, 'not immutable'):
      self.kernel()
    with self.assertRaisesRegex(ValueError, 'immutable'):
      self.pub.recover(self.gh.release(1))
    self.assertEqual(self.remote.state['pins'], {})

  def test_crash_draft_abandoned_fresh_tags_never_deleted(self):
    with patch.object(self.pub, 'publish_draft', side_effect=RuntimeError('crash')):
      with self.assertRaises(RuntimeError):
        self.kernel()
    self.kernel()
    self.assertTrue(self.gh.items[1]['name'].startswith('ABANDONED:'))
    self.assertTrue(self.gh.items[1]['draft'])
    self.assertEqual(self.remote.state['pins']['19.10']['tag'], 'wpa3.sae=6')
    self.assertEqual(self.remote.state['status']['allocated_tags'], list(range(1, 8)))
    self.assertEqual(len(self.gh.items), 2)

  def test_crash_reservation_leaks_numbers_safely(self):
    with patch.object(self.pub, 'seal', side_effect=RuntimeError('crash')):
      with self.assertRaises(RuntimeError):
        self.kernel()
    self.assertEqual(self.gh.items, {})
    self.kernel()
    self.assertEqual(self.remote.state['pins']['19.10']['tag'], 'wpa3.sae=6')

  def test_draft_reuses_retained_data_and_reverifies_without_building(self):
    with patch.object(self.pub, 'publish_draft', side_effect=RuntimeError('crash')):
      with self.assertRaises(RuntimeError):
        self.kernel()
    identity = sha256(self.stock)[:12]
    downloads = []
    def download(*args, **kwargs):
      downloads.append(args)
      dest = Path(args[args.index('--dir') + 1])
      dest.mkdir(parents=True)
      if args[args.index('--name') + 1] == 'kernel-detect':
        write_json(dest / 'plan.json', {'replay': '', 'gate_version': self.gate, 'items': [identity]})
        directory = dest / 'items' / identity
        (directory / ('b' * 40)).mkdir(parents=True)
        write_json(directory / 'input.json', {**self.item, 'scheduled': ['a' * 40]})
        (directory / 'stock.img').write_bytes(self.stock)
        shutil.copyfile(self.key, directory / ('b' * 40) / 'vble-qti.key')
    def reverify(inputs, builds, out):
      self.assertTrue((builds / f'kernel-{identity}-aaaaaaaaaaaa').is_dir())
      shutil.copytree(self.verified, out / identity)
    with patch.object(publish, 'run', side_effect=download), patch.object(kernel_follow, 'publish', side_effect=reverify) as verify:
      self.pub.reuse({'stock': sha256(self.stock), 'release_id': 1, 'run_id': '123'})
    verify.assert_called_once()
    self.assertEqual(len(downloads), 2)
    self.assertTrue(self.gh.items[1]['name'].startswith('ABANDONED:'))
    self.assertEqual(self.remote.state['pins']['19.10']['tag'], 'wpa3.sae=6')

  def test_expired_artifacts_abandon_draft_and_request_rebuild_next_detect(self):
    with patch.object(self.pub, 'publish_draft', side_effect=RuntimeError('crash')):
      with self.assertRaises(RuntimeError):
        self.kernel()
    with patch.object(publish, 'run', side_effect=subprocess.CalledProcessError(1, ['gh'], stderr=b'no artifacts')):
      self.pub.reuse({'stock': sha256(self.stock), 'release_id': 1, 'run_id': '123'})
    self.assertTrue(self.gh.items[1]['name'].startswith('ABANDONED:'))
    self.assertEqual(len(self.gh.items), 1)
    self.assertIn('rebuild: artifacts unavailable', self.remote.state['status']['attempts'][sha256(self.stock)]['reason'])

  def test_infra_escalates_after_three_errors_not_before(self):
    for count in range(1, 4):
      result = self.pub.record(sha256(self.stock), 'error', 'runner failed', 'a' * 64)
      self.assertEqual(result.value, count == 3)
      self.assertIn(f'infra [{count}/3]', result.state['status']['attempts'][sha256(self.stock)]['reason'])
    issues = [e for e in self.gh.events if isinstance(e, tuple) and e[:2] == ('issue', 'follow-hold')]
    self.assertEqual(len(issues), 1)
    self.assertFalse(self.pub.record(sha256(self.stock), 'error', 'different inputs', 'b' * 64).value)

  def test_k12_cannot_be_bypassed_before_publish(self):
    self.remote.state['status']['last_auto_publish_at'] = publish.now_text()
    with self.assertRaisesRegex(ValueError, 'deferred until'):
      self.kernel()
    self.assertEqual(self.gh.items, {})

  def test_allocator_includes_all_release_pages_drafts_and_abandoned(self):
    self.gh.items = {1: {'id': 1, 'tag_name': 'agnos-19.12-wpa3.19', 'name': 'ABANDONED: fixture',
                         'draft': True, 'body': '', 'assets': []}}
    self.kernel()
    self.assertEqual(self.remote.state['pins']['19.10']['tag'], 'wpa3.sae=20')

  def test_disabled_immutable_setting_refuses_even_a_draft(self):
    self.gh.enabled = False
    with self.assertRaisesRegex(ValueError, 'disabled'):
      self.kernel()
    self.assertEqual(self.gh.items, {})
    self.assertEqual(self.remote.state['status']['allocated_tags'], [1, 2, 3])

  def test_pause_between_build_and_publish(self):
    self.gh.after_upload = lambda: self.remote.state['status'].update(paused=withdrawal())
    with self.assertRaisesRegex(ValueError, 'paused'):
      self.kernel()
    self.assertEqual(self.published(), [])
    self.assertEqual(self.remote.state['pins'], {})

  def test_withdrawn_title_between_build_and_publish(self):
    self.gh.after_upload = lambda: self.gh.items[1].update(name='WITHDRAWN: external brake')
    with self.assertRaisesRegex(ValueError, 'withdrawn'):
      self.kernel()
    self.assertEqual(self.published(), [])

  def test_disable_follow_between_verification_and_publish(self):
    self.gh.after_upload = lambda: setattr(self.gh, 'active', False)
    with self.assertRaisesRegex(ValueError, 'follow.yml disabled'):
      self.kernel()
    self.assertEqual(self.published(), [])

  def test_each_brake_after_publication_stops_pin_commit(self):
    for kind in ('paused', 'withdrawn', 'disabled', 'gate'):
      with self.subTest(kind=kind):
        # Reset all per-run mocks and state, keeping the synthetic signed boots.
        if kind != 'paused':
          self.doCleanups()
          self.setUp()
        def brake():
          if kind == 'paused':
            self.remote.state['status']['paused'] = withdrawal()
          elif kind == 'withdrawn':
            self.gh.items[1]['name'] = 'WITHDRAWN: concurrent revoke'
          elif kind == 'disabled':
            self.gh.active = False
          else:
            fs.gate_version.return_value = '0' * 64
        self.gh.after_publish = brake
        with self.assertRaises(ValueError):
          self.kernel()
        self.assertEqual(len(self.published()), 1)
        self.assertEqual(self.remote.state['pins'], {})

  def test_external_pause_mirror_wins_when_git_unpaused(self):
    self.gh.issues = [{'number': 1}]
    with self.assertRaisesRegex(ValueError, 'mirror'):
      self.kernel()
    self.assertEqual(self.gh.items, {})

  def test_corrupt_asset_cannot_publish(self):
    self.gh.after_upload = lambda: self.gh.assets[1].update({'build.log': b'tampered'})
    with self.assertRaisesRegex(ValueError, 'SHA256SUMS'):
      self.kernel()
    self.assertEqual(self.published(), [])

  def test_recovery_reruns_k9_even_when_checksums_match(self):
    with patch.object(self.pub, 'pin_commit', side_effect=RuntimeError('crash')):
      with self.assertRaises(RuntimeError):
        self.kernel()
    # A forged checksum manifest is not a substitute for a correct boot hash.
    files = self.gh.assets[1]
    name = next(n for n in files if n.startswith('boot-'))
    files[name] = publish.assembly.compress_checked(self.stock)
    files['SHA256SUMS'] = ''.join(f'{sha256(v)}  {k}\n' for k, v in sorted(files.items()) if k != 'SHA256SUMS').encode()
    with self.assertRaisesRegex(ValueError, 'boot asset hash/size'):
      self.pub.recover(self.gh.release(1))
    self.assertEqual(self.remote.state['pins'], {})

  def test_recovery_finds_provenance_when_mutable_notes_changed(self):
    with patch.object(self.pub, 'pin_commit', side_effect=RuntimeError('crash')):
      with self.assertRaises(RuntimeError):
        self.kernel()
    self.gh.items[1]['body'] = 'owner edited the notes'
    matches = publish.matching_releases(self.gh, sha256(self.stock))
    self.assertEqual([r['id'] for r in matches], [1])
    self.pub.recover(matches[0])
    self.assertIn('19.10', self.remote.state['pins'])

  def test_state_mode_drafts_but_never_pins_or_publishes(self):
    self.gh.mode = self.writer.mode = self.writer.brakes.mode = 'state'
    self.kernel()
    self.assertTrue(self.gh.items[1]['draft'])
    self.assertEqual(self.remote.state['pins'], {})
    self.assertFalse(any(isinstance(e, tuple) and e[0] == 'dispatch' for e in self.gh.events))

  def test_risk_draft_approve_no_device_test_records_risk(self):
    self.risk()
    self.kernel()
    self.assertEqual(self.remote.state['status']['attempts'][sha256(self.stock)]['result'], 'risk_held')
    self.admin.approve(sha256(self.stock), 'no', '', 'reviewed content diff')
    self.assertIn('without a device test', self.gh.items[1]['name'])
    self.assertNotIn('agnos-19.10-wpa3.4', self.remote.state['status']['device_tested'])
    self.assertEqual(len(self.published()), 1)

  def test_approve_with_device_test_and_mark_another_device(self):
    self.risk()
    self.kernel()
    self.admin.approve(sha256(self.stock), 'yes', 'mici', 'flashed and checked SAE')
    tested = self.remote.state['status']['device_tested']['agnos-19.10-wpa3.4']
    self.assertEqual(tested['devices'], ['mici'])
    self.assertEqual(tested['kernel_commit'], 'a' * 40)
    dispatches = [e for e in self.gh.events if isinstance(e, tuple) and e[0] == 'dispatch']
    self.admin.mark_tested('agnos-19.10-wpa3.4', 'tizi', 'tested on tizi')
    self.assertEqual(self.remote.state['status']['device_tested']['agnos-19.10-wpa3.4']['devices'], ['mici', 'tizi'])
    self.assertEqual(dispatches, [e for e in self.gh.events if isinstance(e, tuple) and e[0] == 'dispatch'])

  def test_integrity_hold_cannot_be_approved_even_with_risk_attempt(self):
    self.risk()
    self.kernel()
    data = json.loads(self.gh.assets[1]['provenance.json'])
    data['facts']['gates'][0]['result'] = 'FAIL'
    self.gh.assets[1]['provenance.json'] = fs.dumps(data).encode()
    files = self.gh.assets[1]
    files['SHA256SUMS'] = ''.join(f'{sha256(v)}  {k}\n' for k, v in sorted(files.items()) if k != 'SHA256SUMS').encode()
    with self.assertRaisesRegex(ValueError, 'integrity'):
      self.admin.approve(sha256(self.stock), 'yes', 'mici', 'cannot bypass integrity')
    self.assertEqual(self.published(), [])

  def test_approve_cannot_erase_a_late_withdrawn_mirror(self):
    self.risk()
    self.kernel()
    self.gh.after_upload = lambda: self.gh.items[1].update(name='WITHDRAWN: owner brake')
    with self.assertRaisesRegex(ValueError, 'withdrawn'):
      self.admin.approve(sha256(self.stock), 'no', '', 'reviewed')
    self.assertEqual(self.gh.items[1]['name'], 'WITHDRAWN: owner brake')
    self.assertEqual(self.published(), [])

  def test_mark_tested_cannot_clear_withdrawal_mirror(self):
    self.kernel()
    self.gh.items[1]['name'] = 'WITHDRAWN: owner brake'
    with self.assertRaisesRegex(ValueError, 'withdrawn'):
      self.admin.mark_tested('agnos-19.10-wpa3.4', 'mici', 'test note')
    self.assertEqual(self.gh.items[1]['name'], 'WITHDRAWN: owner brake')
    self.assertNotIn('agnos-19.10-wpa3.4', self.remote.state['status']['device_tested'])

  def test_missing_qualified_references_hold_on_publication(self):
    self.facts['gates'] = [row for row in self.facts['gates'] if row['gate'] != 'K7b']
    write_json(self.verified / 'provenance.json', self.facts)
    publish.checksums(self.verified, write=True)
    with self.assertRaisesRegex(ValueError, 'K7b'):
      self.kernel()
    self.assertEqual(self.published(), [])

  def test_revoke_pauses_and_resolves_revert_in_every_mode(self):
    self.kernel()
    self.gh.active = False  # rollback's brake must not prevent a revoke.
    self.gh.nightly_active = False
    self.admin.revoke('agnos-19.10-wpa3.4', 'device failed')
    pin = self.remote.state['pins']['19.10']
    self.assertIsNotNone(pin['withdrawn'])
    self.assertEqual(self.remote.state['status']['paused'], pin['withdrawn'])
    self.assertTrue(self.gh.items[1]['name'].startswith('WITHDRAWN:'))
    self.assertTrue(self.gh.issues)
    for mode in fs.MODES:
      for branch in fs.BRANCHES:
        merged = fs.merged_pins(self.remote.state['manual'], self.remote.state['pins'], mode, branch)
        self.assertEqual(merged['19.10']['tag'], 'wpa3.sae=5')
        self.assertEqual(merged['19.10']['boot'], pin['revert']['boot'])
        import pins
        launch = b'if [ -z "$AGNOS_VERSION" ]; then\n  export AGNOS_VERSION="19.10"\nfi\n'
        resolved = pins.resolve(lambda path: launch, self.remote.state['manual'], self.fetch,
                                state=self.remote.state, mode=mode, branch=branch)
        self.assertEqual(resolved['pin']['tag'], 'wpa3.sae=5')
        self.assertEqual(resolved['pin']['boot'], pin['revert']['boot'])
    self.assertIn(('dispatch', 'nightly.yml', {'upstream': 'published'}), self.gh.events)
    self.assertFalse(self.gh.nightly_active)
    self.assertFalse(self.admin.marker.exists())

  def test_revoke_dispatch_failure_restores_disabled_nightly_and_reports(self):
    self.kernel()
    self.gh.nightly_active = False
    with patch.object(self.gh, 'dispatch', side_effect=ValueError('unsupported upstream input')):
      with self.assertRaisesRegex(ValueError, 'unsupported'):
        self.admin.revoke('agnos-19.10-wpa3.4', 'bad kernel')
    self.assertFalse(self.gh.nightly_active)
    self.assertIsNotNone(self.remote.state['status']['paused'])
    self.assertTrue(any(e[:2] == ('issue', 'revoke-blocked') for e in self.gh.events if isinstance(e, tuple)))

  def test_failed_revoke_run_restores_disabled_nightly(self):
    self.gh.nightly_active = False
    original = self.gh.api
    def api(path, *args):
      if path.startswith('actions/runs/'):
        return {'event': 'workflow_dispatch', 'head_branch': 'wpa3-ci', 'status': 'completed', 'conclusion': 'failure'}
      return original(path, *args)
    with patch.object(self.gh, 'api', side_effect=api), self.assertRaisesRegex(ValueError, 'nightly failed'):
      self.admin.dispatch_revoke()
    self.assertFalse(self.gh.nightly_active)

  def test_unpause_closes_mirrors_and_retry_only_dispatches_follow(self):
    self.remote.state['status']['paused'] = withdrawal()
    self.gh.issues = [{'number': 7}]
    original = self.gh.api
    def api(path, method='GET', body=None):
      if path == 'issues/7':
        self.assertEqual(body, {'state': 'closed'})
        self.gh.issues = []
      else:
        return original(path, method, body)
    with patch.object(self.gh, 'api', side_effect=api):
      self.admin.unpause()
    self.assertIsNone(self.remote.state['status']['paused'])
    self.assertEqual(self.gh.issues, [])
    self.remote.state['status']['attempts'][sha256(self.stock)] = attempt()
    self.admin.retry(sha256(self.stock))
    self.assertNotIn(sha256(self.stock), self.remote.state['status']['attempts'])
    self.assertEqual(self.gh.events[-1], ('dispatch', 'follow.yml', {'reason': f'owner retry {sha256(self.stock)}', 'force': True}))


class DetectionTests(unittest.TestCase):
  def test_existing_pin_release_held_and_deferred_never_build(self):
    for found in ('pin', 'immutable', 'mutable', 'held', 'deferred'):
      with self.subTest(found=found), tempfile.TemporaryDirectory() as tmp:
        state = fs.load()
        gate = 'a' * 64
        stock = 'b' * 64
        item = {'manifest': [{'name': 'boot', 'hash_raw': stock}]}
        release = {'id': 1, 'name': 'automatic', 'draft': False, 'immutable': found == 'immutable'}
        if found == 'pin':
          state = fs.reserve_tags(state, 2)
          pin = automatic_pin(state)
          pin['derived_from']['boot_hash_raw'] = stock
          pin['derived_from']['boot_url'] = f'https://commadist.azureedge.net/agnosupdate/boot-{stock}.img.xz'
          state = fs.apply(state, {'pins': {'19.10': pin}})
        elif found in ('held', 'deferred'):
          old = attempt(found)
          old['gate_version'] = gate
          old['at'] = publish.now_text()
          old['deferred_until'] = (publish.utc_time(old['at']) + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ') if found == 'deferred' else None
          state['status']['attempts'][stock] = old
        gh = Mock()
        gh.paused.return_value = []
        matches = [release] if found in ('immutable', 'mutable') else []
        with patch.object(kernel_follow, 'network_only_in_workflow'), patch.object(fs, 'load', return_value=state), \
             patch.object(fs, 'gate_version', return_value=gate), patch.object(kernel_follow, 'upstream_items', return_value=[item]), \
             patch.object(publish, 'GitHub', return_value=gh), patch.object(publish, 'matching_releases', return_value=matches), \
             patch.object(kernel_follow, 'fetch_inputs', side_effect=AssertionError('must not rebuild')) as build:
          if found == 'mutable':
            with self.assertRaisesRegex(ValueError, 'immutable'):
              kernel_follow.detect(Path(tmp), '', 'on', 'all')
          else:
            plan = kernel_follow.detect(Path(tmp), '', 'on', 'all')
            self.assertEqual(plan['matrix'], {'include': []})
            if found == 'immutable':
              self.assertEqual(plan['recover'], [{'stock': stock, 'release_id': 1}])
          build.assert_not_called()

  def test_replay_forces_the_entire_publish_orchestrator_dry(self):
    plan = {'gate_version': 'a' * 64, 'replay': '19.9'}
    with patch.object(publish, 'read_json', return_value=plan), patch.object(fs, 'gate_version', return_value='a' * 64), \
         patch.object(kernel_follow, 'publish'), patch('wpa_follow.publish'), patch.object(publish, 'GitHub') as gh, \
         patch.object(publish, 'network_only_in_workflow', side_effect=AssertionError('no remote writes')):
      publish.run_follow(*[Path('/mock')] * 5, mode='on')
      gh.assert_not_called()


class ProtocolTests(unittest.TestCase):
  def test_crash_matrix_attempt_windows(self):
    old = attempt()
    now = publish.utc_time(old['at']) + timedelta(days=6)
    args = old, old['gate_version'], 'd' * 64, now
    self.assertIsNotNone(fs.attempt_wait(*args))  # unrelated refs cannot trigger rebuilds
    self.assertIsNone(fs.attempt_wait(*args, force=True))
    self.assertIsNone(fs.attempt_wait(old, 'f' * 64, 'd' * 64, now))
    self.assertIsNone(fs.attempt_wait(old, old['gate_version'], old['refs_fingerprint'], now + timedelta(days=1)))
    old['reason'] = 'K1: candidate not on branch'
    self.assertIsNone(fs.attempt_wait(*args))
    old = attempt('deferred')
    self.assertIsNotNone(fs.attempt_wait(old, old['gate_version'], 'd' * 64, now, force=True))
    self.assertIsNone(fs.attempt_wait(old, old['gate_version'], 'd' * 64, now + timedelta(days=2)))
    self.assertIsNone(fs.attempt_wait(None, 'a' * 64, 'b' * 64, now))
    self.assertIsNone(fs.attempt_wait(attempt('error'), 'a' * 64, 'b' * 64, now))

  def test_replay_and_modes_block_all_remote_write_apis(self):
    for mode in fs.MODES:
      for replay in ('19.9', '19.8', 'latest', 'neg-caff1d8d'):
        effective = publish.effective_mode(mode, replay)
        self.assertEqual(effective, 'dryrun')
        gh = publish.GitHub('shunnag/openpilot', effective)
        with patch.object(publish, 'network_only_in_workflow'), patch.object(publish, 'run') as run:
          with self.assertRaisesRegex(ValueError, 'state/on'):
            gh.api('releases', 'POST', {})
          run.assert_not_called()

  def test_assets_uploaded_only_to_drafts_even_mid_upload(self):
    gh = publish.GitHub('shunnag/openpilot', 'state')
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      (root / 'a').write_text('one')
      (root / 'b').write_text('two')
      with patch.object(gh, 'release', side_effect=[{'draft': True}, {'draft': False}]), patch.object(publish, 'run') as run:
        with self.assertRaisesRegex(ValueError, 'only be uploaded to drafts'):
          gh.upload({'id': 1, 'tag_name': 'agnos-19.10-wpa3.4'}, root)
        self.assertEqual(run.call_count, 1)

  def test_immutable_endpoint_is_required_at_runtime(self):
    gh = publish.GitHub('shunnag/openpilot', 'on')
    with patch.object(gh, 'api', return_value={'enabled': False}) as api:
      with self.assertRaisesRegex(ValueError, 'disabled'):
        gh.immutable()
      api.assert_called_once_with('immutable-releases')

  def test_release_edits_preserve_withdrawal_mirror(self):
    gh = publish.GitHub('shunnag/openpilot', 'on')
    release = {'id': 1, 'name': 'WITHDRAWN: owner brake'}
    with patch.object(gh, 'release', return_value=release), patch.object(gh, 'api') as api:
      for fields in ({'name': 'ABANDONED: test'}, {'name': 'device-tested'}, {'draft': False}):
        with self.assertRaisesRegex(ValueError, 'WITHDRAWN'):
          gh.edit(release, **fields)
      api.assert_not_called()

  def test_follow_hold_uses_full_key_and_escapes_log_mentions(self):
    gh = publish.GitHub('shunnag/openpilot', 'on')
    key = 'a' * 64
    old = {'number': 7, 'title': 'older reason', 'body': f'<!-- wpa3-key:{key} -->'}
    with patch.object(gh, 'pages', return_value=[old]), patch.object(gh, 'api') as api, patch.object(publish, 'run') as run:
      gh.issue('follow-hold', 'held @owner', 'K4: @owner', key=key)
    self.assertEqual(api.call_args.args[:2], ('issues/7', 'PATCH'))
    self.assertNotIn('@owner', api.call_args.args[2]['body'])
    self.assertEqual({c.args[3] for c in run.call_args_list}, {'follow-hold', 'follow:kernel', 'stock:' + key[:12]})

  def test_t3_requires_policy_and_anonymous_matching_result(self):
    fixture = ROOT / 'scripts/fixtures/wpa_request'
    request = read_json(fixture / 'valid.json')
    log = b'redacted result\n'
    result = {'schema': 1, 'request_id': request['id'], 'suite_commit': request['suite_commit'],
      'assets': {name: meta['sha256'] for name, meta in request['assets'].items()}, 'tested_at': request['created_at'],
      'colima_version': 'fixture', 'kernel_version': 'fixture', 'passed': True, 'log_sha256': sha256(log),
      'tests': [{'name': name, 'passed': True} for name in sorted(wpa_request.TESTS)]}
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      with patch.object(wpa_request, 'download') as download:
        with self.assertRaisesRegex(ValueError, 'auto_publish is false'):
          publish.wpa_publication_gate(fs.load()['policy'], request, request['id'], root)
        download.assert_not_called()
      urls = []
      def download(url, path, limit):
        urls.append(url)
        path.write_bytes(log if url.endswith('.log') else fs.dumps(result).encode())
      policy = deepcopy(fs.load()['policy'])
      policy['wpa']['auto_publish'] = True
      with patch.object(wpa_request, 'download', side_effect=download):
        publish.wpa_publication_gate(policy, request, request['id'], root)
        self.assertEqual(urls[0], 'https://raw.githubusercontent.com/shunnag/wpa3-test-results/main/results/' + request['id'] + '.json')
        result['assets']['candidate'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hashes differ'):
          publish.wpa_publication_gate(policy, request, request['id'], root)

  def test_owner_only_and_four_modes_at_admin_entry(self):
    env = {'GITHUB_ACTIONS': 'true', 'FOLLOW_MODE': 'on', 'GITHUB_REPOSITORY': 'shunnag/openpilot',
           'GITHUB_ACTOR': 'someone-else', 'GITHUB_REF': 'refs/heads/wpa3-ci'}
    with patch.dict(os.environ, env), patch.object(admin, 'GitHub') as gh:
      self.assertEqual(admin.main(), 1)
      gh.assert_not_called()
    for mode in ('off', 'dryrun', 'canary'):
      with patch.dict(os.environ, {**env, 'FOLLOW_MODE': mode}), patch.object(admin, 'GitHub') as gh:
        self.assertEqual(admin.main(), 1)
        gh.assert_not_called()

  def test_admin_inputs_cannot_be_commands(self):
    publisher = Mock()
    publisher.gh.mode = 'on'
    controller = admin.Admin(publisher, 'owner', '/not-used')
    for target in ('--repo evil/repo', '$(id)', 'agnos-19.10-wpa3.4\nmalicious'):
      with self.assertRaises(ValueError):
        controller.revoke(target, 'note')
      with self.assertRaises(ValueError):
        controller.approve(target, 'no', '', 'note')
    publisher.writer.commit.assert_not_called()


if __name__ == '__main__':
  unittest.main()
