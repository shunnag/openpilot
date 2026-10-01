#!/usr/bin/env python3
"""State transitions and safety checks; all inputs are local or synthetic."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import compose
import follow_state as fs


def automatic_pin(state, version='19.10', number=4):
  pin = deepcopy(state['manual']['19.9'])
  pin.pop('wpa_supplicant')
  pin['release_tag'] = f'agnos-{version}-wpa3.{number}'
  pin['tag'] = f'wpa3.sae={number}'
  for key in ('hash', 'hash_raw'):
    pin['boot'][key] = hashlib.sha256(f'boot {number}'.encode()).hexdigest()
  pin['boot']['url'] = f'https://github.com/{state["policy"]["repository"]}/releases/download/{pin["release_tag"]}/boot-{pin["boot"]["hash_raw"]}.img.xz'
  pin['auto'] = {
    'kernel_commit': 'a' * 40, 'builder_commit': 'b' * 40, 'recipe_sha256': 'c' * 64,
    'patchset_sha256': 'd' * 64, 'baseline_release': 'agnos-19.9-wpa3.3',
    'baseline_kernel_commit': '8b0e4d289b246a5cc1b0484b25a3f9f8d4772544', 'gate_version': 'e' * 64,
    'provenance_sha256': 'f' * 64, 'run_url': f'https://github.com/{state["policy"]["repository"]}/actions/runs/123',
    'published_at': '2026-10-02T12:00:00Z',
  }
  pin['revert'] = {'tag': f'wpa3.sae={number + 1}', 'boot': deepcopy(pin['boot'])}
  boot = pin['revert']['boot']
  boot['hash'] = boot['hash_raw'] = hashlib.sha256(f'revert {number + 1}'.encode()).hexdigest()
  boot['url'] = f'https://github.com/{state["policy"]["repository"]}/releases/download/{pin["release_tag"]}/boot-{boot["hash_raw"]}.img.xz'
  pin['withdrawn'] = None
  return pin


def withdrawal():
  return {'at': '2026-10-02T13:00:00Z', 'by': 'owner', 'reason': 'device failed to boot'}


def attempt(result='held'):
  return {'result': result, 'reason': 'K4: risky driver change', 'gate_version': 'a' * 64,
          'refs_fingerprint': 'b' * 64, 'release_tag': None,
          'run_url': 'https://github.com/shunnag/openpilot/actions/runs/123',
          'at': '2026-10-02T12:00:00Z', 'deferred_until': '2026-10-09T12:00:00Z' if result == 'deferred' else None}


class TestFollowState(unittest.TestCase):
  def setUp(self):
    self.state = fs.load()
    self.auto = automatic_pin(self.state)

  def with_auto(self):
    state = fs.reserve_tags(self.state, 2)
    return fs.apply(state, {'pins': {'19.10': self.auto}})

  def test_seeds_and_reference_qualification(self):
    self.assertEqual(self.state['pins'], {})
    self.assertEqual(self.state['status']['allocated_tags'], [1, 2, 3])
    self.assertEqual(set(self.state['policy']['allowed_branches']), set(fs.BRANCHES))
    self.assertNotIn('canary', fs.dumps(self.state['policy']))
    self.assertNotIn('soak', fs.dumps(self.state['policy']))
    self.assertEqual(set(self.state['system_probe']), {pin['derived_from']['system_hash_raw'] for pin in self.state['manual'].values()})
    self.state['policy']['wpa']['auto_publish'] = True
    with self.assertRaisesRegex(ValueError, 'ci_reproduced_reference'):
      fs.validate(self.state)
    reference = self.state['policy']['wpa']['reference_stock_sha256']
    self.state['supplicants'][reference]['ci_reproduced_reference'] = True
    fs.validate(self.state)
    self.state['supplicants'][reference]['sha256'] = '0' * 64
    with self.assertRaisesRegex(ValueError, 'reference binary'):
      fs.validate(self.state)

  def test_modes_and_all_allowed_branches_adopt_immediately(self):
    for mode in fs.MODES:
      for branch in (*fs.BRANCHES, 'unlisted', None):
        with self.subTest(mode=mode, branch=branch):
          merged = fs.merged_pins(self.state['manual'], {'19.10': self.auto}, mode, branch,
                                  now=self.auto['auto']['published_at'])
          self.assertEqual('19.10' in merged, mode == 'on' and branch in fs.BRANCHES)
    with self.assertRaisesRegex(ValueError, 'unknown follow mode'):
      fs.merged_pins({}, {}, 'canary', 'nightly')
    # No deadline or age filter, even when --now precedes the recorded publication.
    self.assertIn('19.10', fs.merged_pins({}, {'19.10': self.auto}, 'on', 'nightly', now='2020-01-01T00:00:00Z'))

  def test_withdrawal_precedes_mode_branch_and_pause(self):
    state = self.with_auto()
    state = fs.apply(state, {'withdraw': {'19.10': withdrawal()}})
    self.assertEqual(state['status']['paused'], withdrawal())
    for mode in fs.MODES:
      for branch in (*fs.BRANCHES, 'unlisted', None):
        with self.subTest(mode=mode, branch=branch):
          merged = fs.merged_pins(state['manual'], state['pins'], mode, branch, [])
          self.assertEqual(merged['19.10']['boot'], self.auto['revert']['boot'])
          self.assertEqual(merged['19.10']['tag'], self.auto['revert']['tag'])
          self.assertEqual(merged['19.10']['auto'], self.auto['auto'])
    self.assertEqual(state['pins']['19.10']['boot'], self.auto['boot'])

  def test_duplicate_live_pin_holds_even_when_ignored(self):
    for mode in fs.MODES:
      for version in ('19.8', '19.9'):
        pin = automatic_pin(self.state, version)
        with self.subTest(mode=mode, version=version), self.assertRaisesRegex(ValueError, 'duplicate pin'):
          fs.merged_pins(self.state['manual'], {version: pin}, mode, 'nightly')

  def test_manual_fix_overrides_withdrawn_directly_and_as_base(self):
    auto = automatic_pin(self.state, '19.9')
    auto['withdrawn'] = withdrawal()
    for mode in fs.MODES:
      merged = fs.merged_pins(self.state['manual'], {'19.9': auto}, mode, 'nightly')
      self.assertEqual(merged['19.9'], self.state['manual']['19.9'])
    manual = deepcopy(self.state['manual'])
    manual['19.9']['tag'] = auto['tag']
    manual['19.9']['boot'] = deepcopy(auto['boot'])
    with self.assertRaisesRegex(ValueError, 'new tag'):
      fs.merged_pins(manual, {'19.9': auto}, 'off', 'nightly')

  def test_union_includes_ignored_auto_and_revert_identities(self):
    for side in ('boot', 'revert'):
      other = deepcopy(self.state['manual'])
      target = self.auto if side == 'boot' else self.auto['revert']
      other['19.8']['tag'] = target['tag']
      with self.subTest(side=side), self.assertRaisesRegex(ValueError, 'different boot hashes'):
        fs.merged_pins(other, {'19.10': self.auto}, 'off', 'nightly')
      other['19.8']['tag'] = 'wpa3.sae=9'
      other['19.8']['boot'] = deepcopy(target['boot'])
      with self.assertRaisesRegex(ValueError, 'different tags'):
        fs.merged_pins(other, {'19.10': self.auto}, 'off', 'nightly')

  def test_reservation_never_reuses_releases_reverts_or_abandoned_drafts(self):
    original = deepcopy(self.state)
    self.assertEqual(fs.allocate_tag(self.state), 4)
    names = ['agnos-19.10-wpa3.8', 'agnos-19.11-wpa3.13', 'unrelated-v90']
    first = fs.reserve_tags(self.state, 2, names)
    self.assertEqual(first['status']['allocated_tags'], [1, 2, 3, 14, 15])
    self.assertEqual(first['pins'], {})
    self.assertEqual(fs.allocate_tag(first), 16)
    second = fs.reserve_tags(first, 2)
    self.assertEqual(fs.allocate_tag(second), 18)  # Even after abandoning both reservations.
    state = self.with_auto()
    self.assertEqual(fs.allocate_tag(state), 6)  # Includes the reserved revert.
    state['status']['allocated_tags'] += [24]
    self.assertEqual(fs.allocate_tag(state), 25)
    self.assertEqual(self.state, original)

  def test_reserve_before_pin_is_a_separate_transition(self):
    with self.assertRaisesRegex(ValueError, 'prior state commit'):
      fs.apply(self.state, {'status': {'allocated_tags': [1, 2, 3, 4, 5]}, 'pins': {'19.10': self.auto}})
    state = fs.reserve_tags(self.state, 2)
    new = fs.apply(state, {'pins': {'19.10': self.auto}})
    self.assertEqual(state['pins'], {})
    self.assertEqual(new['pins']['19.10'], self.auto)
    self.assertEqual(fs.apply(new, {'pins': {'19.10': self.auto}}), new)

  def test_apply_brakes_and_immutability(self):
    paused = fs.reserve_tags(self.state, 2)
    paused['status']['paused'] = withdrawal()
    with self.assertRaisesRegex(ValueError, 'paused'):
      fs.apply(paused, {'pins': {'19.10': self.auto}})
    with self.assertRaisesRegex(ValueError, 'paused'):
      fs.apply(paused, {'status': {'paused': None}, 'pins': {'19.10': self.auto}})
    state = self.with_auto()
    changed = deepcopy(self.auto)
    changed['auto']['provenance_sha256'] = '0' * 64
    with self.assertRaisesRegex(ValueError, 'immutable'):
      fs.apply(state, {'pins': {'19.10': changed}})
    withdrawn = fs.apply(state, {'withdraw': {'19.10': withdrawal()}})
    withdrawn = fs.apply(withdrawn, {'status': {'paused': None}})
    with self.assertRaisesRegex(ValueError, 'withdrawn'):
      fs.apply(withdrawn, {'pins': {'19.10': self.auto}})
    with self.assertRaisesRegex(ValueError, 'forget allocated'):
      fs.apply(state, {'status': {'allocated_tags': [1, 2, 3]}})
    for key in ('manual', 'policy', 'README.md'):
      with self.assertRaises(ValueError):
        fs.apply(state, {key: {}})

  def test_canonical_bytes_and_status_not_in_pin(self):
    state = self.with_auto()
    before = fs.merged_pins(state['manual'], state['pins'], 'on', 'nightly')
    state['status']['last_auto_publish_at'] = '2026-10-02T12:00:00Z'
    after = fs.merged_pins(state['manual'], state['pins'], 'on', 'nightly')
    self.assertEqual(before, after)
    for data in fs.state_files(state).values():
      self.assertEqual(data.decode(), json.dumps(json.loads(data), sort_keys=True, indent=2) + '\n')

  def test_malformed_state_fails_closed(self):
    bad = [
      ('pins', []), ('status', {}), ('system_probe', []), ('supplicants', []), ('policy', {}),
    ]
    for field, value in bad:
      state = deepcopy(self.state)
      state[field] = value
      with self.subTest(field=field), self.assertRaises(ValueError):
        fs.validate(state)
    for field in self.state['status']:
      state = deepcopy(self.state)
      del state['status'][field]
      with self.subTest(field=field), self.assertRaises(ValueError):
        fs.validate(state)
    for allocated in ([1, 2], [1, 2, 3, True], [1, 2, 3, 3], [1, 2, 3, -1]):
      state = deepcopy(self.state)
      state['status']['allocated_tags'] = allocated
      with self.assertRaises(ValueError):
        fs.validate(state)
    state = self.with_auto()
    state['status']['allocated_tags'] = [1, 2, 3]
    with self.assertRaisesRegex(ValueError, 'unreserved'):
      fs.validate(state)

  def test_load_missing_malformed_duplicate_keys_and_patch_tampering(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      shutil.copytree(compose.ROOT / 'agnos', root / 'agnos')
      shutil.copytree(compose.ROOT / 'follow', root / 'follow')
      path = root / 'agnos/auto/pins.json'
      for data in ('[]', '{', '{"19.10": {}, "19.10": {}}', '{"19.10": NaN}'):
        path.write_text(data)
        with self.subTest(data=data), self.assertRaises(ValueError):
          fs.load(root)
      path.unlink()
      with self.assertRaises(OSError):
        fs.load(root)
      path.write_text('{}')
      patch_file = next((root / 'follow/kernel-patches').glob('0001*'))
      patch_file.write_bytes(patch_file.read_bytes() + b'\n')
      with self.assertRaisesRegex(ValueError, 'digest mismatch'):
        fs.load(root)

  def test_gate_version_covers_scripts_policy_and_reference_but_not_status(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      for folder in ('scripts', 'follow', 'agnos/auto'):
        (root / folder).mkdir(parents=True)
      script = root / 'scripts/follow.py'
      script.write_text('gate one')
      policy = root / 'follow/policy.json'
      policy.write_text('{}')
      digest = fs.gate_version(root)
      (root / 'agnos/auto/status.json').write_text('{"paused": true}')
      self.assertEqual(digest, fs.gate_version(root))
      for path in (script, policy, root / 'follow/reference.json'):
        path.write_text('changed')
        changed = fs.gate_version(root)
        self.assertNotEqual(changed, digest)
        digest = changed


class TestAllowlist(unittest.TestCase):
  def setUp(self):
    self.old = 'before\n<!-- wpa3-status:begin -->\nold\n<!-- wpa3-status:end -->\nafter\n'
    self.new = self.old.replace('\nold\n', '\nnew\n')

  def check(self, status, path, old_mode=None, new_mode='100644', before=None, after=None):
    fs.check_allowlist(f'{status}\t{path}\n', self.old if before is None else before, self.new if after is None else after,
                       modes={path: (old_mode or ('000000' if status == 'A' else '100644'), new_mode)})

  def test_allowed_paths(self):
    for name in fs.STATE_FILES:
      for status in ('A', 'M'):
        self.check(status, f'agnos/auto/{name}.json')
    self.check('A', 'userspace/wpa/2.10-21ubuntu0.5-agnos1/wpa_supplicant', new_mode='100755')
    self.check('A', 'userspace/wpa/2.10-21ubuntu0.5-agnos1/wpa_supplicant.copyright')
    self.check('M', 'README.md')
    fs.check_allowlist('M\0agnos/auto/status.json\0', '', '', modes={'agnos/auto/status.json': ('100644', '100644')})

  def test_reject_deletions_renames_modes_symlinks_and_unknown_paths(self):
    for status, path in [('D', 'agnos/auto/pins.json'), ('R100', 'agnos/auto/status.json'),
        ('M', '.github/workflows/nightly.yml'), ('M', 'follow/policy.json'), ('M', 'scripts/pins.py'),
        ('A', 'agnos/auto/../pins.json'), ('A', 'userspace/wpa/../wpa_supplicant'),
        ('M', 'userspace/wpa/2.10-21ubuntu0.5-agnos1/wpa_supplicant')]:
      with self.subTest(status=status, path=path), self.assertRaises(ValueError):
        self.check(status, path)
    for old, new in [('100644', '100755'), ('120000', '120000'), ('100644', '120000')]:
      with self.assertRaises(ValueError):
        self.check('M', 'agnos/auto/pins.json', old, new)
    with self.assertRaises(ValueError):
      fs.check_allowlist('M\tagnos/auto/pins.json', '', '', modes={})

  def test_readme_outside_markers_or_missing_duplicate_reversed_markers(self):
    for text in (self.new.replace('before', 'changed'), self.new.replace('after', 'changed'), 'no markers',
                 self.new + '<!-- wpa3-status:end -->', '<!-- wpa3-status:end --><!-- wpa3-status:begin -->'):
      with self.subTest(text=text), self.assertRaises(ValueError):
        self.check('M', 'README.md', after=text)


class TestAutoValidation(unittest.TestCase):
  def setUp(self):
    self.state = fs.load()
    self.pin = automatic_pin(self.state)

  def test_metadata_revert_and_withdrawal_schema(self):
    compose.validate_pin('19.10', self.pin)
    for key in self.pin['auto']:
      pin = deepcopy(self.pin)
      del pin['auto'][key]
      with self.subTest(key=key), self.assertRaises(ValueError):
        compose.validate_pin('19.10', pin)
    for value in ('yesterday', '2026-10-02T12:00:00', '2026-10-02T12:00:00+01:00', None):
      pin = deepcopy(self.pin)
      pin['auto']['published_at'] = value
      with self.assertRaises(ValueError):
        compose.validate_pin('19.10', pin)
    for value in (True, {}, '', {'at': 'yesterday', 'by': 'owner', 'reason': 'bad'}):
      pin = deepcopy(self.pin)
      pin['withdrawn'] = value
      with self.assertRaises(ValueError):
        compose.validate_pin('19.10', pin)
    pin = deepcopy(self.pin)
    pin['revert']['boot']['extra'] = True
    with self.assertRaisesRegex(ValueError, 'unexpected boot keys'):
      compose.validate_pin('19.10', pin)
    pin = deepcopy(self.pin)
    pin['revert']['tag'] = pin['tag']
    with self.assertRaises(ValueError):
      compose.validate_pin('19.10', pin)

  def test_auto_urls_are_exact(self):
    for target in ('boot', 'revert', 'derived_from'):
      for change in ('host', 'http', 'query', 'fragment', 'credentials', 'hash', 'tag'):
        pin = deepcopy(self.pin)
        entry = pin['revert']['boot'] if target == 'revert' else pin[target]
        key = 'boot_url' if target == 'derived_from' else 'url'
        url = entry[key]
        variants = {'host': url.replace('github.com', 'github.com.evil').replace('commadist.azureedge.net', 'evil.invalid'),
                    'http': url.replace('https:', 'http:'), 'query': url + '?download=1', 'fragment': url + '#x',
                    'credentials': url.replace('https://', 'https://token@'), 'hash': url.replace('boot-', 'boot-0'),
                    'tag': url.replace('/agnosupdate/', '/different/').replace('/releases/download/', '/releases/different/')}
        entry[key] = variants[change]
        with self.subTest(target=target, change=change), self.assertRaises(ValueError):
          compose.validate_pin('19.10', pin)
    sandbox = deepcopy(self.state)
    sandbox['policy']['repository'] = 'shunnag/wpa3-follow-sandbox'
    pin = automatic_pin(sandbox)
    compose.validate_pin('19.10', pin, sandbox['policy']['repository'])
    with self.assertRaises(ValueError):
      compose.validate_pin('19.10', pin)


if __name__ == '__main__':
  unittest.main()
