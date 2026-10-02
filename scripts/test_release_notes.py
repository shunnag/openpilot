"""Release templates and README status must be factual projections of provenance."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

import follow_git
import follow_state as fs
import release_notes
from test_follow_state import automatic_pin

ROOT = Path(__file__).resolve().parents[1]


def provenance():
  state = fs.reserve_tags(fs.load(), 2)
  pin = automatic_pin(state)
  return {'schema': 'wpa3-follow-release-v1', 'version': '19.10', 'key': 'a' * 64, 'pin': pin,
    'facts': {'gates': [{'gate': 'K7b', 'result': 'OK', 'detail': 'only expected objects changed'}],
              'toolchain': {'url': 'https://example.invalid/compiler.tar.xz', 'sha256': 'b' * 64}},
    'assets': ['provenance.json', 'boot-fixture.img.xz', 'build.log', 'SHA256SUMS'],
    'wpa_status': 'known stock; override matched', 'baseline_tested': {'devices': ['mici']}, 'approval': None}


class ReleaseNotesTests(unittest.TestCase):
  def test_kernel_renders_exact_facts_and_assets(self):
    data = provenance()
    title, body = release_notes.render(data)
    self.assertIn('NOT device-tested', title)
    self.assertIn('WITHOUT any device test', body)
    self.assertIn('K7b: OK: only expected objects changed', body)
    self.assertIn(data['facts']['toolchain']['url'], body)
    self.assertIn(data['facts']['toolchain']['sha256'], body)
    self.assertIn('mici', body)
    self.assertIn(data['wpa_status'], body)
    for name in data['assets']:
      self.assertIn(name, body)
    self.assertNotIn('K9:', body)
    self.assertNotIn('gates.txt', body)

  def test_template_rejects_unsupplied_gate_asset_or_toolchain(self):
    data = provenance()
    for kind in ('kernel', 'wpa'):
      template = (ROOT / f'follow/templates/{kind}-release.md').read_text()
      for unsupported in ('K99: OK', 'K7: signature verified', 'gates.txt', 'linux-19.10.tar.xz', 'gcc-unrecorded-8.3'):
        with self.subTest(kind=kind, unsupported=unsupported), self.assertRaisesRegex(ValueError, 'absent from provenance'):
          release_notes.validate_template(template + '\n' + unsupported, data)
      release_notes.validate_template(template + '\nK7b: build.log', data)

  def test_unknown_placeholder_and_missing_assets_fail_closed(self):
    data = provenance()
    with self.assertRaises(KeyError):
      release_notes.render(data, template='$invented_fact')
    del data['assets']
    with self.assertRaises(KeyError):
      release_notes.render(data)

  def test_device_tested_and_risk_come_only_from_provenance(self):
    data = provenance()
    data['approval'] = {'device_tested': True, 'device': 'mici'}
    data['facts']['gates'].append({'gate': 'K4(e)', 'result': 'FAIL', 'detail': 'changed Wi-Fi source'})
    title, body = release_notes.render(data)
    self.assertIn('mici', title)
    self.assertIn('Device-tested: mici', body)
    self.assertIn('K4(e): FAIL: changed Wi-Fi source', body)
    self.assertIn('Maintainer approved', body)
    data['device_tested'] = {'devices': ['tizi']}
    self.assertIn('Device-tested: mici, tizi', release_notes.render(data)[1])

  def test_wpa_template_uses_only_its_provenance(self):
    data = {'request': {'id': 'wpa3-fixture', 'assets': {'stock': {'sha256': 'a' * 64}}},
      'publication_status': 'DRAFT; auto_publish=false', 'wpa_status': 'no public binary or pin',
      'assets': ['candidate', 'test-report.json', 'provenance.json'],
      'facts': {'gates': [{'gate': 'T3', 'result': 'PENDING', 'detail': 'waiting for result',
                           'line': 'T3: PENDING (dryrun)'}]}}
    title, body = release_notes.render(data, 'wpa')
    self.assertIn('DRAFT; auto_publish=false', title)
    self.assertIn('WITHOUT any device test', body)
    self.assertIn('T3: PENDING (dryrun)', body)
    self.assertIn('not recorded', body)
    self.assertNotIn('K7', body)
    self.assertNotIn('compiler.tar.xz', body)

  def test_readme_status_from_provenance_with_mutable_test_and_withdrawal(self):
    state = fs.reserve_tags(fs.load(), 2)
    data = provenance()
    pin = data['pin']
    state['pins'] = {'19.10': pin}
    state['status']['device_tested'][pin['release_tag']] = {'devices': ['mici']}
    text = 'owner prose\n<!-- wpa3-status:begin -->old<!-- wpa3-status:end -->\nowner tail'
    result = follow_git.status_readme(text, state, 'on', {pin['release_tag']: data})
    self.assertTrue(result.startswith('owner prose\n<!-- wpa3-status:begin -->'))
    self.assertTrue(result.endswith('<!-- wpa3-status:end -->\nowner tail'))
    self.assertIn('currently `on`', result)
    self.assertNotIn('currently `off`', result)
    self.assertIn('K7b: OK: only expected objects changed', result)
    self.assertIn(data['facts']['toolchain']['url'], result)
    pin['withdrawn'] = {'reason': 'bad Wi-Fi'}
    result = follow_git.status_readme(text, state, 'on', {pin['release_tag']: data})
    self.assertIn('WITHDRAWN; stock revert', result)
    with self.assertRaises(KeyError):
      follow_git.status_readme(text, state, 'on')

  def test_readme_notices_and_exactly_one_current_mode_block(self):
    readme = (ROOT / 'README.md').read_text()
    for marker in ('wpa3-status:begin', 'wpa3-status:end'):
      self.assertEqual(readme.count(marker), 1)
    before, status = readme.split('<!-- wpa3-status:begin -->')
    status, after = status.split('<!-- wpa3-status:end -->')
    self.assertIn('is currently `off`', status)
    self.assertNotIn('is currently `off`', before + after)
    self.assertNotIn('canary', readme)
    self.assertNotIn('soak', readme)
    for text in ('WITHOUT any device test', '実機テストなし', '19.8 → 19.9', '`wpa3.sae=2`', '`wpa3.sae=3`',
                 'No WPA3 kernel has ever booted on a comma 3X', 'Do not report problems to comma', 'flash.comma.ai'):
      self.assertIn(text, before)
    self.assertIn('**`release-mici-staging` and `release-tizi-staging` have NOT been tested on any device.', before)


if __name__ == '__main__':
  unittest.main()
