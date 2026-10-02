"""Offline adversarial coverage of the kernel-follow boundary and workflow."""
from copy import deepcopy
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import bootimg
from boot_fixture import BANNER, boot_image
import follow_state
import kernel_assemble as assembly
import kernel_build_data as build
from kernel_common import ROOT, Gates, blob_id, git, git_text, read_json, sha256, write_json
import kernel_discover as discovery
import kernel_equiv as ke
import kernel_follow as follow
import kernel_gates as gates


class FakeRepos(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory(prefix='kernel-follow-test-')
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.env = patch.dict(os.environ, {'GIT_CONFIG_NOSYSTEM': '1', 'GIT_NO_LAZY_FETCH': '1', 'KERNEL_FOLLOW_NETWORK': '0'})
    self.env.start()
    self.addCleanup(self.env.stop)

  def repo(self, name):
    path = self.root / name
    path.mkdir()
    git(path, 'init', '-b', 'main')
    git(path, 'config', 'user.email', 'test@example.invalid')
    git(path, 'config', 'user.name', 'Offline test')
    return path

  def commit(self, repo, files, date='2026-09-01T12:00:00Z'):
    for name, value in files.items():
      path = repo / name
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_bytes(value.encode() if isinstance(value, str) else value)
    git(repo, 'add', '--', *files)
    with patch.dict(os.environ, {'GIT_AUTHOR_DATE': date, 'GIT_COMMITTER_DATE': date}):
      git(repo, 'commit', '-m', 'offline fixture')
    return git_text(repo, 'rev-parse', 'HEAD')

  def link(self, builder, kernel, version, date):
    git(builder, 'update-index', '--add', '--cacheinfo', f'160000,{kernel},agnos-kernel-sdm845')
    return self.commit(builder, {'VERSION': version}, date)


class TestKernelDiscovery(FakeRepos):
  def test_oracle_at_build_last_and_same_repo_pr(self):
    builder, kernel = self.repo('builder'), self.repo('kernel')
    first = self.commit(kernel, {'file': 'first'})
    second = self.commit(kernel, {'file': 'second'})
    third = self.commit(kernel, {'file': 'third'})
    early = self.link(builder, first, '19.9', '2026-09-01T12:00:00Z')
    late = self.link(builder, second, '19.9', '2026-09-03T12:00:00Z')
    pr = self.link(builder, third, '19.9', '2026-09-04T12:00:00Z')
    git(builder, 'reset', '--hard', late)
    when = datetime(2026, 9, 2, tzinfo=timezone.utc)
    refs = [{'number': 631, 'head': {'sha': pr, 'repo': {'full_name': 'attacker/fork'}}}]
    result = discovery.oracle(builder, '19.9', when, refs)
    self.assertEqual(result[0]['builder_commit'], early)
    self.assertEqual(result[0]['reason'], 'at_build')
    self.assertIn(second, [p['commit'] for p in result])
    self.assertNotIn(third, [p['commit'] for p in result])
    refs[0]['head']['repo']['full_name'] = 'commaai/agnos-builder'
    self.assertIn(third, [p['commit'] for p in discovery.oracle(builder, '19.9', when, refs)])
    self.assertEqual(discovery.same_repo_prs([{'head': {'repo': None}}]), [])

  def test_moved_version_path(self):
    builder, kernel = self.repo('builder'), self.repo('kernel')
    source = self.commit(kernel, {'file': 'code'})
    git(builder, 'update-index', '--add', '--cacheinfo', f'160000,{source},agnos-kernel-sdm845')
    self.commit(builder, {'userspace/root/VERSION': '19.9'})
    self.assertEqual(discovery.oracle(builder, '19.9', datetime.now(timezone.utc), [])[0]['commit'], source)

  def test_pull_refs_never_propose_or_prove_membership(self):
    kernel = self.repo('kernel')
    base = self.commit(kernel, {'file': 'base'})
    pr = self.commit(kernel, {'file': 'PR only'})
    git(kernel, 'update-ref', 'refs/pull/147/head', pr)
    git(kernel, 'reset', '--hard', base)
    heads = {'refs/heads/main': base, 'refs/pull/147/head': pr}
    with self.assertRaisesRegex(ValueError, 'not on any branch'):
      discovery.branch_contains(pr, heads, fallback=lambda c, h: discovery.local_membership(kernel, c, h))
    candidates = discovery.window(kernel, heads, datetime(2026, 9, 2, tzinfo=timezone.utc))
    self.assertNotIn(pr, [p['commit'] for p in candidates])
    self.assertNotIn('refs/pull/147/head', discovery.local_heads(kernel))

  def test_tip_api_and_outage_fallback(self):
    candidate, head = 'a' * 40, 'b' * 40
    compare = unittest.mock.Mock(side_effect=AssertionError('tip must not call API'))
    self.assertEqual(discovery.branch_contains(candidate, {'refs/heads/a': candidate}, compare)[1], 'tip')
    fixture = read_json(ROOT / 'follow/replay/compare-eccd1465-8b0e4d28.json')
    self.assertEqual(discovery.branch_contains(candidate, {'refs/heads/b': head}, lambda a, b: fixture)[1], 'compare API')
    with self.assertRaisesRegex(ValueError, 'not on any branch'):
      discovery.branch_contains(candidate, {'refs/heads/b': head}, lambda a, b: {'behind_by': 3})
    def unavailable(a, b):
      raise OSError('API unavailable')
    self.assertEqual(discovery.branch_contains(candidate, {'refs/heads/b': head}, unavailable,
                     lambda c, h: 'refs/heads/b')[1], 'blobless heads fallback')
    with self.assertRaises(ValueError):
      discovery.branch_contains(candidate, {'refs/heads/b': head}, lambda a, b: {})

  def test_budget_dedup_and_oracle_order(self):
    proposals = [{'commit': str(i) * 40, 'builder_commit': 'a' * 40, 'builder_ref': 'refs/heads/release',
                  'oracle': True, 'reason': 'at_build', 'date': '2026-01-01'} for i in range(1, 5)]
    with patch.object(discovery, 'build_time', return_value=(datetime.now(timezone.utc), {})), \
         patch.object(discovery, 'oracle', return_value=proposals), patch.object(discovery, 'window', return_value=[]), \
         patch.object(discovery, 'git_text', side_effect=lambda repo, *args: 'tree ' + args[-1]):
      for cap in (1, 2, 3):
        result = discovery.discover('', '', '19.9', b'boot', [],
          {f'refs/heads/{i}': str(i) * 40 for i in range(1, 5)}, {'max_full_builds': cap})
        self.assertEqual(len(result['candidates']), cap)
        self.assertLessEqual(sum(c['full_build_budget'] for c in result['candidates']), cap)
        self.assertFalse(result['verified'])
      proposals[:] = proposals[:1]
      result = discovery.discover('', '', '19.9', b'boot', [], {'refs/heads/a': '1' * 40}, {'max_full_builds': 3})
      self.assertEqual(result['candidates'][0]['full_build_budget'], 2)


class TestContentGates(FakeRepos):
  def setUp(self):
    super().setUp()
    self.policy = read_json(ROOT / 'follow/policy.json')

  def test_divergence_sees_reverse_tested_change(self):
    repo = self.repo('kernel')
    base = self.commit(repo, {'drivers/usb/host/xhci.h': 'old\n', 'drivers/net/can/m_can/m_can.c': 'old\n'})
    tested = self.commit(repo, {'drivers/usb/host/xhci.h': 'tested\n'})
    git(repo, 'reset', '--hard', base)
    candidate = self.commit(repo, {'drivers/net/can/m_can/m_can.c': 'new\n'})
    diff = gates.content_diff(repo, tested, candidate)
    self.assertFalse(diff['ancestor'])
    self.assertEqual(diff['paths'], ['drivers/net/can/m_can/m_can.c', 'drivers/usb/host/xhci.h'])
    gates.k3(diff, self.policy)

  def test_line_commit_binary_and_rename_gates(self):
    repo = self.repo('kernel')
    base = self.commit(repo, {'drivers/staging/qcacld-3.0/risk.c': 'x\n'})
    git(repo, 'mv', 'drivers/staging/qcacld-3.0/risk.c', 'safe.c')
    renamed = self.commit(repo, {'new.c': 'other\n'})
    diff = gates.content_diff(repo, base, renamed)
    self.assertIn('drivers/staging/qcacld-3.0/risk.c', diff['paths'])
    self.assertIn('safe.c', diff['paths'])
    huge = self.commit(repo, {'large': 'x\n' * 1001})
    with self.assertRaisesRegex(ValueError, 'changed lines'):
      gates.k3(gates.content_diff(repo, base, huge), self.policy)
    binary = self.commit(repo, {'binary': b'\x00\xff'})
    with self.assertRaisesRegex(ValueError, 'binary'):
      gates.k3(gates.content_diff(repo, huge, binary), self.policy)
    diff['commits'] = 21
    with self.assertRaisesRegex(ValueError, 'commit cap'):
      gates.k3(diff, self.policy)
    diff['ancestor'] = False
    gates.k3(diff, self.policy)

  def test_recipe_only_cmdline_normalized(self):
    body = self.policy['build_kernel_normalized'].replace('<CMDLINE>', 'firmware_class.path=/old')
    files = {'build_kernel.sh': body.encode(), 'Dockerfile.builder': b'FROM ubuntu:20.04\n',
             'tools/mkbootimg': b'mkbootimg', 'vble-qti.key': b'key'}
    pointer = self.policy['toolchain']
    files['tools/aarch64-linux-gnu-gcc.tar.gz'] = f"version https://git-lfs.github.com/spec/v1\noid sha256:{pointer['gcc_lfs_oid']}\nsize {pointer['gcc_lfs_size']}\n".encode()
    policy = deepcopy(self.policy)
    policy['recipe'] = {name: blob_id(data) for name, data in files.items() if name in policy['recipe']}
    gates.k2(files, policy)
    quoted = body.replace('firmware_class.path=/old', 'firmware_class.path=/old dyndbg=\\"\\"')
    self.assertEqual(gates.normalize_recipe(quoted), policy['build_kernel_normalized'])
    self.assertEqual(gates.recipe_cmdline(quoted), 'firmware_class.path=/old dyndbg=""')
    files['build_kernel.sh'] = body.replace('/old', '/firmware/image').encode()
    gates.k2(files, policy)
    self.assertNotEqual(gates.recipe_cmdline(body), gates.recipe_cmdline(files['build_kernel.sh'].decode()))
    files['build_kernel.sh'] = body.replace('KCFLAGS="-w"', 'KCFLAGS="-O3"').encode()
    with self.assertRaisesRegex(ValueError, 'recipe changed'):
      gates.k2(files, policy)
    files['build_kernel.sh'] = body.encode()
    files['Dockerfile.builder'] += b'# changed\n'
    with self.assertRaisesRegex(ValueError, 'recipe blob'):
      gates.k2(files, policy)

  def risk(self, *, old=None, new=None, paths=(), deps=None, cmdline=None, status=None):
    old = old or boot_image()
    new = new or old
    report = Gates()
    with redirect_stdout(io.StringIO()):
      gates.risk_gates(report, new, gates.stock_facts(old), {'paths': list(paths)}, self.policy,
        status or {'paused': None, 'device_tested': {}}, {}, deps, cmdline)
    return {row['gate']: row['result'] for row in report.rows}

  def test_risk_paths_dependency_closure_and_all_config(self):
    for path in ('firmware/touch.img', 'drivers/soc/qcom/wcnss.c', 'x/sdm845.dtsi',
                 'drivers/staging/qcacld-3.0/file.c', 'net/mac80211/file.c'):
      self.assertEqual(self.risk(paths=[path])['K4(a)'], 'FAIL')
    self.assertEqual(self.risk(paths=['include/linux/skbuff.h'], deps=['include/linux/skbuff.h'])['K4(e)'], 'FAIL')
    self.assertEqual(self.risk()['K4(e)'], 'SKIP')
    self.assertEqual(self.risk(deps=[])['K4(e)'], 'FAIL')
    for config in (b'CONFIG_MODULE_SIG_FORCE=y\n', b'CONFIG_WLAN=y\n', b'CONFIG_UNRELATED=y\n'):
      self.assertEqual(self.risk(new=boot_image(config=config))['K4(b)'], 'FAIL')
    self.assertEqual(self.risk(cmdline='changed')['K4(f)'], 'FAIL')
    self.assertEqual(self.risk(status={'paused': 'revoked', 'device_tested': {}})['K4(d)'], 'FAIL')

  def test_dtb_multiset_and_chain_limit(self):
    raw = bytearray(boot_image())
    raw[4096 + 128 * 1024 + 56] ^= 1
    self.assertEqual(self.risk(new=bytes(raw))['K4(c)'], 'FAIL')
    status = {'paused': None, 'device_tested': {}, 'last_auto_publish_at': None}
    auto = {str(i): {'tag': f'wpa3.sae={i}'} for i in (4, 5, 6)}
    with self.assertRaisesRegex(ValueError, 'chain'):
      gates.brakes(status, auto, self.policy)
    status['last_auto_publish_at'] = '2026-10-01T00:00:00Z'
    with self.assertRaisesRegex(ValueError, 'deferred until'):
      gates.k12(status, {}, self.policy, datetime(2026, 10, 2, tzinfo=timezone.utc))


class TestAssembly(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.tmp = tempfile.TemporaryDirectory()
    cls.addClassCleanup(cls.tmp.cleanup)
    cls.key = Path(cls.tmp.name) / 'key'
    subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048', '-out', str(cls.key)], check=True, capture_output=True)
    cls.public = bootimg._openssl('rsa', '-in', cls.key, '-pubout')
    cls.policy = read_json(ROOT / 'follow/policy.json')
    cls.policy['vble_public_key_sha256'] = bootimg.pubkey_sha256(cls.public)
    cls.stock = cls.signed(False)
    cls.wpa = cls.signed(True)

  @classmethod
  def signed(cls, sae):
    config = b'# CONFIG_MODULE_SIG_FORCE is not set\n' + (b'CONFIG_WLAN_FEATURE_SAE=y\n' if sae else b'# CONFIG_WLAN_FEATURE_SAE is not set\n')
    raw = boot_image(config=config, sae=4 if sae else 0, rsnxe=sae)
    image, chain = ke.split_kernel(bootimg.parse(raw)['kernel'])
    image = bytearray(image)
    image[:2] = b'MZ'
    struct.pack_into('<3Q', image, 8, 0x80000, len(image), 0xa)
    image[56:60] = b'ARM\x64'
    banner = b'Linux version 4.9.103 (user@host) (gcc 8.2) #1 SMP PREEMPT Sep 2 12:34:56 UTC 2026'
    image[BANNER:BANNER + 256] = banner.ljust(256, b'\0')
    wrapped = b'UNCOMPRESSED_IMG' + struct.pack('<I', len(image)) + image
    return bootimg.repack(raw, wrapped + chain, 'console=tty0', cls.key)

  def test_publish_uses_wrapped_image_dtb_with_raw_image_present(self):
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      inputs, builds, out = root / 'detect', root / 'builds', root / 'verified'
      item_id, commit, builder = sha256(self.stock)[:12], 'b' * 40, 'c' * 40
      directory = inputs / 'items' / item_id
      recipe = directory / builder
      artifact = builds / f'kernel-{item_id}-{commit[:12]}'
      recipe.mkdir(parents=True)
      artifact.mkdir(parents=True)
      (inputs / 'manual').mkdir()
      shutil.copyfile(self.key, recipe / 'vble-qti.key')
      for name in (*self.policy['recipe'], 'tools/aarch64-linux-gnu-gcc.tar.gz'):
        if name != 'vble-qti.key':
          (recipe / name.replace('/', '_')).write_bytes(b'fixture recipe')
      (directory / 'stock.img').write_bytes(self.stock)
      # Both files exist, just as in CI. Reading the raw MZ Image breaks K9/Q1.
      for name, boot in (('stock', self.stock), ('wpa3', self.wpa)):
        (artifact / f'{name}.Image').write_bytes(ke.split(boot)[1][20:])
        (artifact / f'{name}.Image-dtb').write_bytes(bootimg.parse(boot)['kernel'])
      self.assertEqual((artifact / 'wpa3.Image').read_bytes()[:2], b'MZ')
      source = (ROOT / 'follow/kernel-patches/source.diff').read_text()
      blobs = dict.fromkeys(gates.patch_paths(source), 'a' * 40)
      proof = {'source_diff': source, 'candidate': commit, 'baseline': 'd' * 40,
               'candidate_blobs': blobs, 'baseline_blobs': blobs}
      pre = {'patched_blobs': blobs, 'diff': {'paths': [], 'candidate': commit, 'baseline': 'd' * 40}, 'risk_hold': False}
      write_json(artifact / 'patch-proof.json', proof)
      write_json(artifact / 'result.json', {'result': 'complete', 'full_builds': 1})
      write_json(artifact / 'manifests.json', {'rebuilt_objects': ['kernel/configs.o'],
                 'wifi_objects': {'net/wireless/test.o': '0' * 64}})
      for name in ('source.diff', *self.policy['patches']):
        shutil.copyfile(ROOT / 'follow/kernel-patches' / name, artifact / name)
      (artifact / 'SHA256SUMS').write_text(''.join(
        f'{sha256(path.read_bytes())}  {path.name}\n' for path in sorted(artifact.iterdir())))
      state = follow_state.load()
      state['policy'] = self.policy
      manual = bootimg.with_tag(self.wpa, 'wpa3.sae=3', self.key)
      for version, pin in state['manual'].items():
        (inputs / 'manual' / f'{version}.img').write_bytes(manual)
        pin['boot'].update(hash_raw=sha256(manual), size=len(manual), ondevice_hash=bootimg.ondevice_hash(manual))
      candidate = {'commit': commit, 'builder_commit': builder, 'tree': 'e' * 40, 'oracle': True, 'full_build_budget': 1}
      write_json(inputs / 'plan.json', {'mode': 'dryrun', 'items': [item_id],
                 'gate_version': follow_state.gate_version(), 'release_names': [], 'tag_names': []})
      write_json(directory / 'input.json', {'stock_hash': sha256(self.stock), 'scheduled': [commit],
        'replay': '19.9', 'baseline_release': 'fixture', 'manifest': [], 'agnos_py_blob': 'fixture',
        'pre': {commit: pre}, 'discovery': {'candidates': [candidate], 'fetch_metrics': {},
                                          'fallback_measurements': {}, 'refs_fingerprint': 'fixture'}})
      # Source discovery/recipe gates have separate coverage. All artifact
      # checks, stock selection, assembly, signing and replay comparison run.
      with patch.object(follow_state, 'load', return_value=state), \
           patch.object(gates, 'k0'), patch.object(gates, 'k2'), redirect_stdout(io.StringIO()):
        follow.publish(inputs, builds, out)
      facts = read_json(out / item_id / 'provenance.json')
      results = {row['gate']: row['result'] for row in facts['gates']}
      for gate in ('K5', 'K6', 'K7', 'K9', 'K11', 'K12', 'Q1-WPA3'):
        self.assertEqual(results[gate], 'OK', gate)
      self.assertEqual(facts['boot']['layout']['header_offset'], 20)
      self.assertEqual(read_json(out / 'run.json')['failures'], [])

  def test_replay_allows_identity_dtb_order_and_expected_tag_only(self):
    reference = bootimg.with_tag(self.wpa, 'wpa3.sae=3', self.key)
    image, chain = ke.split(self.wpa)[1:]
    changed = image.replace(b'user@host', b'user@ci01')
    reordered = b''.join(reversed(ke.dtb_blobs(chain)))
    assembled = bootimg.repack(self.wpa, changed + reordered, 'console=tty0 wpa3.sae=4', self.key)
    self.assertFalse(ke.rebuild_equivalent(reference, assembled)[0])
    self.assertIn('rebuild-equivalent', assembly.replay_check(reference, assembled, 4, self.key))
    for cmdline in ('console=tty1 wpa3.sae=4', 'console=tty0  wpa3.sae=4',
                    'console=tty0 wpa3.sae=5', 'console=tty0 wpa3.sae=4 extra=1',
                    'console=tty0 wpa3.sae=3 wpa3.sae=4'):
      with self.subTest(cmdline=cmdline), self.assertRaisesRegex(ValueError, 'cmdline'):
        wrong = bootimg.repack(self.wpa, changed + reordered, cmdline, self.key)
        assembly.replay_check(reference, wrong, 4, self.key)
    for kernel in (image[:9000] + bytes([image[9000] ^ 1]) + image[9001:] + chain,
                   image + ke.dtb_blobs(chain)[0], image + chain + ke.dtb_blobs(chain)[0],
                   image[20:] + chain, bootimg.parse(self.stock)['kernel']):
      with self.subTest(kernel_size=len(kernel)), self.assertRaises(ValueError):
        wrong = bootimg.repack(self.wpa, kernel, 'console=tty0 wpa3.sae=4', self.key)
        assembly.replay_check(reference, wrong, 4, self.key)
    for cmdline in ('console=tty0', 'console=tty0 wpa3.sae=0',
                    'console=tty0 wpa3.sae=3 wpa3.sae=3', 'console=tty0 wpa3.sae=3 '):
      with self.subTest(reference_cmdline=cmdline), self.assertRaisesRegex(ValueError, 'manual replay'):
        wrong = bootimg.repack(self.wpa, image + chain, cmdline, self.key)
        assembly.replay_check(wrong, assembled, 4, self.key)

  def test_k0_shape_agnos_signature_and_repack(self):
    manifest = []
    for shape in self.policy['manifest_shape']:
      entry = {key: 'unused' for key in self.policy['manifest_keys'] if key != 'alt'}
      entry.update(shape)
      if entry['sparse']:
        entry['alt'] = {'url': 'unused', 'hash': 'unused', 'size': 1}
      if entry['name'] == 'boot':
        entry.update(hash_raw=sha256(self.stock), hash=sha256(self.stock), size=len(self.stock))
      manifest.append(entry)
    gates.k0(self.stock, manifest, 'a', 'a', self.key, self.policy)
    with self.assertRaisesRegex(ValueError, 'agnos.py'):
      gates.k0(self.stock, manifest, 'b', 'a', self.key, self.policy)
    changed = deepcopy(manifest)
    changed[0]['new_key'] = True
    with self.assertRaisesRegex(ValueError, 'key set'):
      gates.k0(self.stock, changed, 'a', 'a', self.key, self.policy)
    changed = deepcopy(self.policy)
    changed['vble_public_key_sha256'] = '0' * 64
    with self.assertRaisesRegex(ValueError, 'key'):
      gates.k0(self.stock, manifest, 'a', 'a', self.key, changed)

  def test_k5_code_change_is_not_identity(self):
    kernel = bootimg.parse(self.stock)['kernel']
    assembly.stock_rebuild(self.stock, kernel, self.key)
    altered = bytearray(kernel)
    altered[9000] ^= 1
    with self.assertRaises(ValueError):
      assembly.stock_rebuild(self.stock, bytes(altered), self.key)

  def test_config_markers_layout_signature_size_and_revert(self):
    assembly.k7(ke.split(self.stock)[1], ke.split(self.wpa)[1])
    absent = ke.split(boot_image(config=b'# CONFIG_MODULE_SIG_FORCE is not set\n'))[1]
    assembly.k7(absent, ke.split(self.wpa)[1])
    with self.assertRaisesRegex(ValueError, 'SAE only'):
      assembly.k7(ke.split(self.stock)[1], ke.split(self.stock)[1])
    tagged = bootimg.with_tag(self.wpa, 'wpa3.sae=4', self.key)
    assembly.image_checks(self.stock, tagged, self.public, self.policy)
    revert = bootimg.with_tag(self.stock, 'wpa3.sae=5', self.key)
    assembly.image_checks(self.stock, revert, self.public, self.policy, revert=True)
    with self.assertRaisesRegex(ValueError, 'capacity'):
      with patch.object(assembly, 'MAX_BOOT_SIZE', 1):
        assembly.image_checks(self.stock, tagged, self.public, self.policy)
    with self.assertRaises(ValueError):
      assembly.image_checks(self.stock, tagged, b'bad key', self.policy)
    fields = bootimg.parse(tagged)
    raw = bytearray(fields['kernel'])
    raw[76] ^= 1
    wrong = bootimg.repack(tagged, bytes(raw), fields['cmdline'], self.key)
    with self.assertRaisesRegex(ValueError, 'Image header'):
      assembly.image_checks(self.stock, wrong, self.public, self.policy)

  def test_rebuilt_and_wifi_manifests(self):
    allowed = ['kernel/configs.o', 'drivers/staging/qcacld-3.0/test.o']
    assembly.k7b(allowed, allowed)
    with self.assertRaisesRegex(ValueError, 'unexpected rebuilt'):
      assembly.k7b(['net/core/skbuff.o'], allowed)
    with self.assertRaisesRegex(ValueError, 'empty'):
      assembly.k7b([], allowed)
    manifest = {prefix + 'test.o': '0' * 64 for prefix in assembly.WIFI_DIRS}
    assembly.wifi_manifest(manifest)
    for path in ('../bad.o', 'drivers/staging/qcacld-3.0/built-in.o', 'net/core/skbuff.o'):
      with self.assertRaises(ValueError):
        assembly.wifi_manifest({path: '0' * 64})

  def test_uniqueness_requires_all_jobs_and_prefers_oracle(self):
    rows = [{'commit': 'a', 'tree': '1', 'oracle': False}, {'commit': 'b', 'tree': '2', 'oracle': False}]
    results = {'a': {'reproduced': True}, 'b': {'reproduced': True}}
    with self.assertRaisesRegex(ValueError, 'multiple'):
      assembly.select_candidate(rows, results)
    rows[1]['oracle'] = True
    self.assertEqual(assembly.select_candidate(rows, results)['commit'], 'b')
    with self.assertRaisesRegex(ValueError, 'missing'):
      assembly.select_candidate(rows, {'a': results['a']})

  def test_both_tags_avoid_all_collisions(self):
    state = follow_state.load()
    before = deepcopy(state)
    number, _ = assembly.dry_tags(state, release_names=['agnos-20.0-wpa3.10', 'agnos-20.0-wpa3.11'])
    self.assertEqual(number, 12)
    self.assertEqual(state, before)
    self.assertEqual(assembly.dry_tags(state, '19.9')[0], 3)

  def test_source_diff_and_blob_proof(self):
    policy = read_json(ROOT / 'follow/policy.json')
    source = (ROOT / 'follow/kernel-patches/source.diff').read_text()
    paths = gates.patch_paths(source)
    blobs = dict.fromkeys(paths, 'a' * 40)
    proof = {'source_diff': source, 'candidate': 'b' * 40, 'baseline': 'c' * 40,
             'candidate_blobs': blobs, 'baseline_blobs': blobs}
    pre = {'patched_blobs': blobs, 'diff': {'paths': ['drivers/usb/host/xhci.h'], 'candidate': 'b' * 40, 'baseline': 'c' * 40}}
    assembly.k6(proof, pre, ROOT / 'follow/kernel-patches', policy)
    pre['diff']['paths'] = paths[:1]
    with self.assertRaisesRegex(ValueError, 'patched paths'):
      assembly.k6(proof, pre, ROOT / 'follow/kernel-patches', policy)
    pre['diff']['paths'] = []
    proof['source_diff'] += 'changed\n'
    with self.assertRaisesRegex(ValueError, 'diff differs'):
      assembly.k6(proof, pre, ROOT / 'follow/kernel-patches', policy)


class TestBuildBoundary(unittest.TestCase):
  def test_q5_comparison_and_artifact_tampering(self):
    with tempfile.TemporaryDirectory() as temporary:
      first, second = Path(temporary) / 'a', Path(temporary) / 'b'
      manifest = {'net/wireless/test.o': '0' * 64}
      for directory in (first, second):
        directory.mkdir()
        write_json(directory / 'patch-proof.json', {'candidate': 'a' * 40, 'source_diff': 'same'})
        write_json(directory / 'wifi-objects.json', manifest)
      with redirect_stdout(io.StringIO()):
        self.assertTrue(build.compare_wifi(first, second))
        write_json(second / 'wifi-objects.json', {'net/wireless/test.o': '1' * 64})
        self.assertFalse(build.compare_wifi(first, second))
      sums = ''.join(f'{sha256(path.read_bytes())}  {path.name}\n' for path in first.iterdir())
      (first / 'SHA256SUMS').write_text(sums)
      follow.verify_sums(first)
      (first / 'wifi-objects.json').write_text('{}')
      with self.assertRaisesRegex(ValueError, 'checksum'):
        follow.verify_sums(first)

  def test_dependency_closure_and_symlink_refusal(self):
    with tempfile.TemporaryDirectory() as temporary:
      out = Path(temporary)
      source = out / 'drivers/staging/qcacld-3.0/.test.o.cmd'
      source.parent.mkdir(parents=True)
      source.write_text('source_test.o := ../drivers/staging/qcacld-3.0/test.c\n\n'
                        'deps_test.o := \\\n  ../include/linux/skbuff.h \\\n  include/generated/autoconf.h\n\n')
      self.assertEqual(build.dependencies(out), ['drivers/staging/qcacld-3.0/test.c', 'include/linux/skbuff.h'])
      (out / 'escape').symlink_to('/tmp')
      with self.assertRaisesRegex(ValueError, 'symlink'):
        build.safe_file(out, 'escape/output')

  def test_archive_rejects_git_and_escape(self):
    import io
    import tarfile
    with tempfile.TemporaryDirectory() as temporary:
      root = Path(temporary)
      for index, name in enumerate(('.git/config', '../escape')):
        archive = root / f'{index}.tar'
        with tarfile.open(archive, 'w') as tar:
          info = tarfile.TarInfo(name)
          info.size = 1
          tar.addfile(info, io.BytesIO(b'x'))
        with self.assertRaises((ValueError, tarfile.FilterError)):
          build.extract_archive(archive, root / f'out{index}')

  def test_modes_and_network_guard(self):
    for mode in ('off', 'dryrun', 'state', 'on'):
      self.assertEqual(follow.effective_mode(mode, '19.9'), 'dryrun')
      self.assertEqual(follow.effective_mode(mode, ''), 'off' if mode == 'off' else 'dryrun')
    for mode in ('canary', 'soak', 'invalid'):
      with self.assertRaises(ValueError):
        follow.effective_mode(mode, '19.9')
    with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
      with self.assertRaisesRegex(ValueError, 'network'):
        discovery.fetch_inputs(Path('/not-used'), Path('/not-used'))

  def test_workflow_yaml_structure_enforces_readonly(self):
    # JSON is a strict subset of YAML 1.2. Keeping this workflow in that subset
    # lets stdlib tests parse the *structure*, including every job permission.
    workflow = json.loads((ROOT / '.github/workflows/follow.yml').read_text())
    self.assertEqual(set(workflow['on']), {'workflow_dispatch'})
    self.assertEqual(workflow['permissions'], {})
    jobs = workflow['jobs']
    self.assertEqual(set(jobs), {'detect', 'kernel-build', 'publish', 'probe', 'wpa-classify', 'wpa-build', 'wpa-test'})
    self.assertEqual(jobs['kernel-build']['permissions'], {'contents': 'read'})
    self.assertEqual(jobs['kernel-build']['strategy']['max-parallel'], 3)
    self.assertEqual(jobs['kernel-build']['timeout-minutes'], 150)
    banned = re.compile(r'\b(?:git\s+(?:push|commit|tag)|gh\s+(?:release\s+(?:create|upload|edit)|workflow|issue)|curl\s+.*(?:-X|--request)\s*(?:POST|PUT|PATCH))\b')
    for name, job in jobs.items():
      self.assertEqual(job['permissions'], {'contents': 'read'})
      for step in job['steps']:
        self.assertNotIn('secrets.', json.dumps(step))
        if 'uses' in step:
          self.assertRegex(step['uses'], r'^[\w/-]+@[0-9a-f]{40}$')
          if step['uses'].startswith('actions/checkout@'):
            self.assertIs(step['with']['persist-credentials'], False)
          if name == 'publish':
            self.assertNotIn('cache', step['uses'])
        if 'run' in step:
          self.assertNotRegex(step['run'], banned)
          self.assertNotIn('${{', step['run'])
          if name == 'kernel-build':
            self.assertNotRegex(step['run'], r'\bgh\b')
        if name == 'kernel-build':
          self.assertNotIn('GH_TOKEN', step.get('env', {}))
    self.assertEqual(workflow['on']['workflow_dispatch']['inputs']['mode']['options'], ['off', 'dryrun', 'state', 'on'])


if __name__ == '__main__':
  unittest.main()
