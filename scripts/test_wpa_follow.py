"""Offline acceptance and adversarial tests for Part 3 and the Mac mini boundary."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import lzma
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zlib

import system_probe as probe
import wpa_abi
import wpa_classify as classify
import wpa_follow as follow
import wpa_patch
import wpa_request as request

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'scripts/fixtures/wpa_request'
NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


def sparse(chunks, blocks, checksum=0):
  header = struct.pack('<I4H4I', 0xed26ff3a, 1, 0, 28, 12, 4, blocks, len(chunks), checksum)
  return header + b''.join(struct.pack('<2H2I', kind, 0, count, 12 + len(data)) + data for kind, count, data in chunks)


class SparseTests(unittest.TestCase):
  def test_all_four_chunks_and_holes(self):
    raw = b'raw!' + b'fill' * 2 + b'\0' * 8
    crc = zlib.crc32(raw)
    data = sparse([(0xcac1, 1, b'raw!'), (0xcac2, 2, b'fill'), (0xcac3, 2, b''),
                   (0xcac4, 0, struct.pack('<I', crc))], 5, crc)
    with tempfile.TemporaryFile() as output:
      a, b = probe.expand(io.BytesIO(data), output)
      output.seek(0)
      self.assertEqual(output.read(), raw)
    self.assertEqual(a, hashlib.sha256(data).hexdigest())
    self.assertEqual(b, hashlib.sha256(raw).hexdigest())

  def test_bad_crc_and_header_crc(self):
    for data in (sparse([(0xcac1, 1, b'abcd'), (0xcac4, 0, b'\0' * 4)], 1),
                 sparse([(0xcac3, 1, b'')], 1, 1)):
      with self.assertRaisesRegex(ValueError, 'CRC'):
        probe.expand(io.BytesIO(data), io.BytesIO())

  def test_lengths_and_types_rejected(self):
    for data in (sparse([(0xcac1, 2, b'abcd')], 2), sparse([(0xcac3, 2, b'')], 1),
                 sparse([(0xcac3, 1, b'')], 2), sparse([(0xcac4, 1, b'\0' * 4)], 1),
                 sparse([(0xffff, 1, b'')], 1), sparse([(0xcac2, 1, b'abc')], 1),
                 sparse([(0xcac1, 1, b'abcd')], 1) + b'x', b'bad'):
      with self.subTest(data=data), self.assertRaises(ValueError):
        probe.expand(io.BytesIO(data), io.BytesIO())

  def test_hash_mismatch_discards_before_debugfs(self):
    data = sparse([(0xcac1, 1, b'abcd')], 1)
    for sparse_hash, raw_hash in [('0' * 64, hashlib.sha256(b'abcd').hexdigest()),
                                  (hashlib.sha256(data).hexdigest(), '0' * 64)]:
      with tempfile.TemporaryDirectory() as tmp, patch.object(probe, 'inspect') as inspect:
        keep = Path(tmp) / 'verified'
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
          probe.probe(io.BytesIO(data), sparse_hash, raw_hash, keep=keep)
        self.assertFalse(keep.exists())
        self.assertEqual(list(Path(tmp).iterdir()), [])
        inspect.assert_not_called()

  def test_extended_headers_and_truncation(self):
    data = sparse([(0xcac1, 1, b'abcd')], 1)
    for size in range(len(data)):
      with self.assertRaises(ValueError):
        probe.expand(io.BytesIO(data[:size]), io.BytesIO())
    data = struct.pack('<I4H4I', 0xed26ff3a, 1, 0, 32, 16, 4, 1, 1, 0) + b'1234'
    data += struct.pack('<2H2I', 0xcac1, 0, 1, 20) + b'1234abcd'
    self.assertEqual(probe.expand(io.BytesIO(data), io.BytesIO())[1], hashlib.sha256(b'abcd').hexdigest())

  def test_xz_streaming(self):
    data = sparse([(0xcac1, 1, b'abcd')], 1)
    with lzma.LZMAFile(io.BytesIO(lzma.compress(data))) as stream:
      self.assertEqual(probe.expand(stream, io.BytesIO())[0], hashlib.sha256(data).hexdigest())


class ClassificationTests(unittest.TestCase):
  def setUp(self):
    self.policy = json.loads((ROOT / 'follow/policy.json').read_text())['wpa']
    self.files = {'debian/rules': b'build', 'debian/control': b'control', 'debian/config/a': b'config',
                  'debian/changelog': b'old', 'debian/patches/series': b'a.patch\nb.patch\n',
                  'debian/patches/a.patch': b'a', 'debian/patches/b.patch': b'b'}

  def test_w2_versions(self):
    for version in ('2:2.10-21ubuntu0.1', '2:2.10-21ubuntu0.4', '2:2.10-21ubuntu0.999'):
      classify.w2(version, self.policy['orig_tarball_sha256'], self.policy)
    for version in ('2:2.11-21ubuntu0.4', '2:2.10-22ubuntu0.4', '2.10-21ubuntu0.4',
                    '2:2.10-21ubuntu0.4+agnos1', '2:2.10-21ubuntu0.4\n'):
      with self.assertRaisesRegex(ValueError, 'W2'):
        classify.w2(version, self.policy['orig_tarball_sha256'], self.policy)
    with self.assertRaisesRegex(ValueError, 'tarball'):
      classify.w2('2:2.10-21ubuntu0.4', '0' * 64, self.policy)

  def test_w3_allows_only_patch_and_changelog_updates(self):
    candidate = {**self.files, 'debian/changelog': b'new', 'debian/patches/c.patch': b'c',
                 'debian/patches/series': b'a.patch\nb.patch\nc.patch\n'}
    self.assertIn('debian/changelog', classify.w3(self.files, candidate))
    self.assertEqual(classify.w3(self.files, self.files), [])

  def test_w3_rules_control_and_config_hold(self):
    for name in ('debian/rules', 'debian/control', 'debian/config/a'):
      with self.assertRaisesRegex(ValueError, 'W3: changed'):
        classify.w3(self.files, {**self.files, name: b'changed'})

  def test_w3_mode_only_rules_change_holds(self):
    reference = {name: classify.DebianFile(data, 0o644) for name, data in self.files.items()}
    candidate = {**reference, 'debian/rules': classify.DebianFile(self.files['debian/rules'], 0o755)}
    with self.assertRaisesRegex(ValueError, 'W3: changed debian/rules'):
      classify.w3(reference, candidate)

  def test_w3_patch_removal_and_reorder_hold(self):
    removed = deepcopy(self.files)
    del removed['debian/patches/a.patch']
    for candidate in (removed, {**self.files, 'debian/patches/series': b'b.patch\n'},
                      {**self.files, 'debian/patches/series': b'b.patch\na.patch\n'}):
      with self.assertRaisesRegex(ValueError, 'W3'):
        classify.w3(self.files, candidate)

  def test_gpgv_failure_cannot_be_bypassed(self):
    with patch.object(classify.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'gpgv')):
      with self.assertRaisesRegex(ValueError, 'W1: gpgv failed'):
        classify.signed_release(Path('InRelease'), Path('keyring'))

  def test_signed_release_uses_only_gpgv_output(self):
    def verify(command, **kwargs):
      path = Path(command[command.index('--output') + 1])
      path.write_text('Origin: Ubuntu\nCodename: noble\nSuite: noble-updates\nSHA256:\n ' + 'a' * 64 + ' 12 main/source/Sources.xz\n')
      self.assertIn('--keyring', command)
      return subprocess.CompletedProcess(command, 0)
    with patch.object(classify.subprocess, 'run', side_effect=verify):
      self.assertEqual(classify.signed_release(Path('unread-untrusted-input'), Path('keyring')),
                       {'main/source/Sources.xz': ('a' * 64, 12)})

  def test_signed_index_file_mutation_rejected(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / 'Packages.xz'
      path.write_bytes(b'original')
      identity = (probe.sha_file(path), path.stat().st_size)
      classify.verify_file(path, identity)
      path.write_bytes(b'mutation')
      with self.assertRaisesRegex(ValueError, 'mismatch'):
        classify.verify_file(path, identity)

  def test_descriptor_paths_reject_traversal_and_duplicates(self):
    for sums in ('a' * 64 + ' 1 ../escape', 'a' * 64 + ' 1 /escape', ('a' * 64 + ' 1 file\n') * 2):
      with self.assertRaises(ValueError):
        classify.checksums(sums)

  def test_deb_member_without_installing(self):
    content = b'INERT ELF fixture'
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w:gz') as tar:
      info = tarfile.TarInfo('./usr/sbin/wpa_supplicant')
      info.size = len(content)
      tar.addfile(info, io.BytesIO(content))
    data = payload.getvalue()
    header = f'{"data.tar.gz/":<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(data):<10}`\n'.encode()
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / 'fixture.deb'
      path.write_bytes(b'!<arch>\n' + header + data)
      self.assertEqual(classify.deb_member(path, 'usr/sbin/wpa_supplicant'), content)
      with self.assertRaises(ValueError):
        classify.deb_member(path, 'etc/passwd')

  def test_complete_offline_classification_with_clearsigned_descriptor(self):
    with tempfile.TemporaryDirectory() as tmp:
      directory = Path(tmp)
      delta = directory / 'wpa_2.10-21ubuntu0.4.debian.tar.xz'
      files = {**self.files, 'debian/changelog': b'wpa (2:2.10-21ubuntu0.4) noble; urgency=medium\n\n'
               b' -- Test <test@example.invalid>  Fri, 25 Sep 2026 00:00:00 +0000\n'}
      with tarfile.open(delta, 'w:xz') as tar:
        for name, data in files.items():
          member = tarfile.TarInfo(name)
          member.size = len(data)
          tar.addfile(member, io.BytesIO(data))
      source_sums = f" {self.policy['orig_tarball_sha256']} 1234 wpa_2.10.orig.tar.xz\n"
      source_sums += f' {probe.sha_file(delta)} {delta.stat().st_size} {delta.name}\n'
      dsc = directory / 'wpa_2.10-21ubuntu0.4.dsc'
      dsc.write_text('-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512\n\nSource: wpa\nVersion: 2:2.10-21ubuntu0.4\n'
                     'Checksums-Sha256:\n' + source_sums + '\n-----BEGIN PGP SIGNATURE-----\nfixture\n-----END PGP SIGNATURE-----\n')
      sources = directory / 'Sources-noble-updates-main.xz'
      sources.write_bytes(lzma.compress(('Package: wpa\nVersion: 2:2.10-21ubuntu0.4\nDirectory: pool/main/w/wpa\n'
                                         'Checksums-Sha256:\n' + source_sums +
                                         f' {probe.sha_file(dsc)} {dsc.stat().st_size} {dsc.name}\n').encode()))
      binary = b'INERT fixture binary'
      payload = io.BytesIO()
      with tarfile.open(fileobj=payload, mode='w:gz') as tar:
        member = tarfile.TarInfo('usr/sbin/wpa_supplicant')
        member.size = len(binary)
        tar.addfile(member, io.BytesIO(binary))
      body = payload.getvalue()
      header = f'{"data.tar.gz/":<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(body):<10}`\n'.encode()
      deb = directory / 'stock.deb'
      deb.write_bytes(b'!<arch>\n' + header + body)
      packages = directory / 'pkgs-arm64.xz'
      packages.write_bytes(lzma.compress(('Package: wpasupplicant\nVersion: 2:2.10-21ubuntu0.4\nArchitecture: arm64\n'
                                          f'SHA256: {probe.sha_file(deb)}\nSize: {deb.stat().st_size}\n').encode()))
      signed = {'main/source/Sources.xz': (probe.sha_file(sources), sources.stat().st_size),
                'main/binary-arm64/Packages.xz': (probe.sha_file(packages), packages.stat().st_size)}
      policy = {**self.policy, 'reference_debian_sha256': probe.sha_file(delta)}
      with patch.object(classify, 'signed_release', return_value=signed):
        result = classify.classify(directory, hashlib.sha256(binary).hexdigest(), classify.REFERENCE, Path('keyring'), policy)
        self.assertEqual([result[k] for k in ('W1', 'W2', 'W3')], ['PASS'] * 3)
        self.assertEqual(result['dsc_sha256'], probe.sha_file(dsc))
        with self.assertRaisesRegex(ValueError, 'stock binary differs'):
          classify.classify(directory, '0' * 64, classify.REFERENCE, Path('keyring'), policy)


class PatchTests(unittest.TestCase):
  def test_actual_reverse_patch_holds_before_quilt(self):
    with tempfile.TemporaryDirectory() as tmp:
      tree = Path(tmp)
      (tree / 'test.c').write_text('int result = 2;\n')
      patch_file = tree / 'change.patch'
      patch_file.write_text('--- a/test.c\n+++ b/test.c\n@@ -1 +1 @@\n-int result = 1;\n+int result = 2;\n')
      with self.assertRaisesRegex(ValueError, 'backported by Ubuntu; drop it'):
        wpa_patch.apply_patch(tree, patch_file)

  def test_reverse_is_reported_separately(self):
    for text in ('Reversed (or previously applied) patch detected!', 'Unreversed patch detected!'):
      with self.assertRaisesRegex(ValueError, 'backported by Ubuntu; drop it'):
        wpa_patch.patch_status(text, 1)

  def test_fuzz_rejected_offsets_recorded(self):
    for text, rc in [('Hunk #1 succeeded with fuzz 1', 0), ('Hunk FAILED', 1)]:
      with self.assertRaises(ValueError):
        wpa_patch.patch_status(text, rc)
    self.assertEqual(wpa_patch.patch_status('Hunk #1 succeeded at 44 (offset -3 lines).', 0), [-3])

  def test_function_identity_ignores_unrelated_function(self):
    before = 'static int sae(void)\n{\n  return 1;\n}\n\nint other(void)\n{\n  return 3;\n}\n'
    patched = before.replace('return 1', 'return 2')
    candidate = before.replace('return 3', 'return 4')
    self.assertEqual(wpa_patch.compare_functions(before, patched, candidate), ['sae'])
    with self.assertRaisesRegex(ValueError, 'changed function sae'):
      wpa_patch.compare_functions(before, patched, before.replace('return 1', 'return 5'))

  def test_changed_global_c_text_holds(self):
    with self.assertRaisesRegex(ValueError, 'unambiguous function'):
      wpa_patch.compare_functions('int setting = 1;\n', 'int setting = 2;\n', 'int setting = 1;\n')


class RequestTests(unittest.TestCase):
  def setUp(self):
    self.data = request.read_json(FIXTURES / 'valid.json')
    self.commit = self.data['suite_commit']

  def test_valid_fixture_every_hash_verified(self):
    request.validate(self.data, self.commit, NOW)
    request.verify_assets(self.data, FIXTURES / 'assets')

  def test_hash_mismatch_rejected(self):
    with tempfile.TemporaryDirectory() as tmp:
      directory = Path(tmp) / 'assets'
      shutil.copytree(FIXTURES / 'assets', directory)
      for name in request.ASSETS:
        path = directory / name
        original = path.read_bytes()
        path.write_bytes(original.replace(b'INERT', b'EVIL!'))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
          request.verify_assets(self.data, directory)
        path.write_bytes(original)

  def test_request_asking_to_run_shipped_code_rejected(self):
    with self.assertRaisesRegex(ValueError, 'shipped code/commands'):
      request.validate(request.read_json(FIXTURES / 'shipped-code.json'), self.commit, NOW)
    for name in ('command', 'entrypoint', 'script', 'test_command', 'suite_url'):
      with self.assertRaises(ValueError):
        request.validate({**self.data, name: 'run-my-code'}, self.commit, NOW)

  def test_shipped_asset_code_and_metadata_rejected(self):
    altered = deepcopy(self.data)
    altered['assets']['run.sh'] = altered['assets']['candidate']
    with self.assertRaises(ValueError):
      request.validate(altered, self.commit, NOW)
    altered = deepcopy(self.data)
    altered['assets']['candidate']['command'] = '/bin/bash'
    with self.assertRaises(ValueError):
      request.validate(altered, self.commit, NOW)

  def test_wrong_pin_url_path_deadline_hold(self):
    for field, value in [('suite_commit', '2' * 40), ('id', '../../escape'), ('deadline', '2026-10-01T01:00:00Z'),
                         ('created_at', '2026-10-03T00:00:00Z'), ('deadline', '2027-01-01T00:00:00Z')]:
      with self.subTest(field=field), self.assertRaises(ValueError):
        request.validate({**self.data, field: value}, self.commit, NOW)
    for url in ('file:///tmp/evil', 'https://example.com/evil', self.data['assets']['candidate']['url'] + '?token=bad'):
      altered = deepcopy(self.data)
      altered['assets']['candidate']['url'] = url
      with self.assertRaises(ValueError):
        request.validate(altered, self.commit, NOW)

  def result(self):
    log = b'redacted synthetic fixture\n'
    result = {'schema': 1, 'request_id': self.data['id'], 'suite_commit': self.commit,
              'assets': {n: a['sha256'] for n, a in self.data['assets'].items()},
              'tested_at': '2026-10-02T00:00:00Z', 'colima_version': '0.10.3', 'kernel_version': '6.8.0-117',
              'tests': [{'name': n, 'passed': True} for n in sorted(request.TESTS)], 'passed': True,
              'log_sha256': hashlib.sha256(log).hexdigest()}
    return result, log

  def test_result_all_tests_hashes_and_commit_must_match(self):
    result, log = self.result()
    self.assertTrue(request.verify_result(self.data, result, log))
    for name, value in [('request_id', 'other'), ('suite_commit', '2' * 40), ('assets', {}), ('tests', []),
                        ('passed', 'true'), ('tested_at', '2026-10-05T00:00:00Z'), ('log_sha256', '0' * 64)]:
      with self.subTest(name=name), self.assertRaises(ValueError):
        request.verify_result(self.data, {**result, name: value}, log)
    result['tests'][0]['passed'] = False
    with self.assertRaisesRegex(ValueError, 'T3 failed'):
      request.verify_result(self.data, result, log)


class OrchestrationTests(unittest.TestCase):
  def test_bundle_does_not_depend_on_checkout_time(self):
    with tempfile.TemporaryDirectory() as tmp:
      root = Path(tmp)
      source = root / 'suite'
      source.mkdir()
      code = source / 'suite.py'
      code.write_text('print("fixed")\n')
      follow.bundle(root / 'one.tar.gz', source, 'hwsim')
      os.utime(code, (1, 1))
      os.utime(source, (2, 2))
      follow.bundle(root / 'two.tar.gz', source, 'hwsim')
      self.assertEqual((root / 'one.tar.gz').read_bytes(), (root / 'two.tar.gz').read_bytes())

  def test_prior_result_requires_identical_rebuilt_assets(self):
    previous = request.read_json(FIXTURES / 'valid.json')
    current = deepcopy(previous)
    current['id'] = 'wpa3-456-aaaaaaaaaaaa'
    for asset in current['assets'].values():
      asset['url'] = asset['url'].replace(previous['id'], current['id'])
    request.validate(current, current['suite_commit'], NOW)
    with tempfile.TemporaryDirectory() as tmp:
      directory = Path(tmp)
      def download(_url, path, _limit):
        path.write_text(json.dumps(previous))
      with patch.object(request, 'download', side_effect=download):
        self.assertEqual(follow.result_request([current], previous['id'], directory), previous)
        altered = deepcopy(current)
        altered['assets']['candidate']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'does not match rebuilt'):
          follow.result_request([altered], previous['id'], directory)

  def test_deduplicate_systems_and_reject_conflicts(self):
    system = {'name': 'system', 'hash': 'a' * 64, 'hash_raw': 'b' * 64, 'sparse': True}
    self.assertEqual(len(follow.unique_systems([[system]] * 4)), 1)
    with self.assertRaises(ValueError):
      follow.unique_systems([[system], [{**system, 'hash': 'c' * 64}]])

  def test_off_does_not_fetch(self):
    with tempfile.TemporaryDirectory() as tmp, patch.object(follow, 'get_json', side_effect=AssertionError('network')):
      follow.probe_plan(Path(tmp), 'latest', 'off')
      self.assertEqual(request.read_json(Path(tmp) / 'plan.json')['items'], [])

  def test_seeded_replay_does_not_download(self):
    with tempfile.TemporaryDirectory() as tmp, patch.object(follow.urllib.request, 'urlopen', side_effect=AssertionError('network')):
      follow.probe_plan(Path(tmp), '19.9', 'dryrun')
      plan = request.read_json(Path(tmp) / 'plan.json')
      self.assertEqual(plan['items'], [])
      self.assertEqual(len(plan['probes']), 1)
      with patch.object(request, 'download', side_effect=AssertionError('network')):
        follow.publish(Path(tmp), Path(tmp))

  def test_t0_subset_and_bind_now(self):
    with patch.object(wpa_abi, 'abi', side_effect=[({'libc'}, {'GLIBC_2.17'}), ({'libc', 'libm'}, {'GLIBC_2.17'})]):
      wpa_abi.check(Path('candidate'), Path('stock'))
    with patch.object(wpa_abi, 'abi', side_effect=[({'libnew'}, {'GLIBC_2.40'}), ({'libc'}, {'GLIBC_2.17'})]):
      with self.assertRaisesRegex(ValueError, 'new library'):
        wpa_abi.check(Path('candidate'), Path('stock'))

  def test_t0_rejects_wrong_arch_and_missing_now(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = Path(tmp) / 'candidate'
      path.write_bytes(b'not ELF')
      with self.assertRaisesRegex(ValueError, 'not ELF64'):
        wpa_abi.abi(path)
      header = bytearray(64)
      header[:7], header[16:20] = b'\x7fELF\x02\x01\x01', b'\x03\x00\xb7\x00'
      path.write_bytes(header)
      with patch.object(wpa_abi.subprocess, 'check_output', side_effect=['(NEEDED) [libc.so.6]', 'Name: GLIBC_2.17']):
        with self.assertRaisesRegex(ValueError, 'BIND_NOW'):
          wpa_abi.abi(path)

  def test_pinned_suite_never_reads_request_bundle(self):
    spec = importlib.util.spec_from_file_location('macmini_runner', ROOT / 'follow/macmini/runner.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    commit = '1' * 40
    with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'output', return_value=commit), \
        patch.object(runner.subprocess, 'check_output', return_value=b'PINNED CODE') as git:
      directory = Path(tmp)
      (directory / 'test-suite.tar.gz').write_bytes(b'UNTRUSTED SHIPPED CODE')
      runner.pinned_suite(ROOT, commit, directory)
      self.assertEqual((directory / 'suite.py').read_bytes(), b'PINNED CODE')
      self.assertEqual(len(git.call_args_list), 2)
      self.assertTrue(all(c.args[0][-1].startswith(commit + ':') for c in git.call_args_list))

  def test_vm_stops_even_when_start_fails(self):
    spec = importlib.util.spec_from_file_location('macmini_runner_cleanup', ROOT / 'follow/macmini/runner.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    calls = []
    def command(*args, **kwargs):
      calls.append(args)
      if args[:2] == ('colima', 'start'):
        raise subprocess.CalledProcessError(1, args)
    with patch.object(runner, 'run', side_effect=command):
      with self.assertRaises(subprocess.CalledProcessError):
        runner.vm(Path('unused'))
    self.assertEqual(calls[-1], ('colima', 'stop', 'wpa3hwsim'))


if __name__ == '__main__':
  unittest.main()
