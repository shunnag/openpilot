#!/usr/bin/env python3
"""Publish verified data through drafts, immutable releases and FF state commits.

No build code or artifact is executed here. All remote writes pass a mode guard;
replays are dry even when the owner has enabled production publishing.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import bootimg
from boot_download import MAX_BOOT_SIZE, fetch_boot
from compose import utc_time, validate_pin
import follow_state as fs
from follow_git import StateWriter
import kernel_assemble as assembly
from kernel_common import network_only_in_workflow, read_bytes, read_json, require, run, sha256, write_json
from kernel_gates import k12

MARKER = re.compile(r'<!-- wpa3-follow key=([0-9a-f]{64}) stock=([0-9a-f]{64}) -->')
WRITE_MODES = ('state', 'on')


def now_text():
  return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def effective_mode(mode, replay=''):
  fs.mode_value(mode)
  return 'dryrun' if replay else mode


class GitHub:
  def __init__(self, repository, mode):
    fs.match(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository, 'repository')
    self.repository, self.mode = repository, fs.mode_value(mode)
    self.prefix = f'repos/{repository}/'

  def writable(self):
    require(self.mode in WRITE_MODES, 'remote writes require state/on; replay is dry')

  def api(self, path, method='GET', body=None):
    network_only_in_workflow()
    if method != 'GET':
      self.writable()
    args = ['gh', 'api', '-H', 'X-GitHub-Api-Version: 2026-03-10', '--method', method, self.prefix + path]
    if body is not None:
      args += ['--input', '-']
    data = run(*args, data=fs.dumps(body).encode() if body is not None else None)
    return json.loads(data) if data.strip() else None

  def pages(self, path):
    network_only_in_workflow()
    pages = json.loads(run('gh', 'api', '--paginate', '--slurp', self.prefix + path))
    require(isinstance(pages, list) and all(isinstance(p, list) for p in pages), 'invalid API pages')
    return [entry for page in pages for entry in page]

  def releases(self):
    return self.pages('releases?per_page=100')

  def release(self, identity):
    require(type(identity) is int and identity > 0, 'invalid release id')
    return self.api(f'releases/{identity}')

  def by_tag(self, tag):
    fs.match(fs.RELEASE, tag, 'release tag')
    matches = [r for r in self.releases() if r['tag_name'] == tag]
    require(len(matches) == 1, 'release missing/ambiguous')
    return matches[0]

  def immutable(self):
    require(self.api('immutable-releases').get('enabled') is True,
            'infra: repository immutable releases disabled')

  def paused(self):
    return [issue for issue in self.pages('issues?state=open&labels=follow-paused&per_page=100')
            if 'pull_request' not in issue]

  def workflow(self, name):
    require(name in ('follow.yml', 'nightly.yml'), 'invalid workflow')
    return self.api(f'actions/workflows/{name}')

  def edit(self, release, **fields):
    self.writable()
    if 'name' in fields or fields.get('draft') is False:
      current = self.release(release['id'])
      if (current.get('name') or '').startswith('WITHDRAWN'):
        require(fields.get('draft') is not False and fields.get('name', 'WITHDRAWN').startswith('WITHDRAWN'),
                'cannot clear a WITHDRAWN mirror or publish its release')
    return self.api(f"releases/{release['id']}", 'PATCH', fields)

  def download(self, release, directory, names=None):
    """API-backed gh download works for drafts too; reject hostile names first."""
    directory.mkdir(parents=True, exist_ok=True)
    assets = release['assets']
    seen = set()
    for asset in assets:
      name = asset['name']
      require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]*', name) and name not in seen,
              'invalid/duplicate release asset name')
      seen.add(name)
      require(type(asset['size']) is int and 0 < asset['size'] <= asset_limit(name), 'release asset size limit')
    wanted = set(names) if names is not None else seen
    require(wanted and wanted <= seen, 'missing release assets')
    # A fixed pattern per exact validated name, never --clobber or a shell glob.
    args = ['gh', 'release', 'download', release['tag_name'], '--repo', self.repository, '--dir', directory]
    for name in sorted(wanted):
      args += ['--pattern', name]
    network_only_in_workflow()
    run(*args)
    for name in wanted:
      path = directory / name
      require(path.is_file() and not path.is_symlink() and path.stat().st_size <= asset_limit(name), 'invalid downloaded asset')

  def upload(self, release, directory, *, names=None, replace=False):
    self.writable()
    for path in sorted(directory.iterdir()):
      if names is not None and path.name not in names:
        continue
      # Recheck before each upload; a published release is never an upload target.
      require(self.release(release['id'])['draft'] is True, 'assets may only be uploaded to drafts')
      run('gh', 'release', 'upload', release['tag_name'], path, '--repo', self.repository,
          *(['--clobber'] if replace else []))

  def dispatch(self, workflow='nightly.yml', inputs=None, *, details=False):
    self.writable()
    require(workflow in ('nightly.yml', 'follow.yml'), 'invalid dispatch workflow')
    if details:
      result = self.api(f'actions/workflows/{workflow}/dispatches', 'POST',
                        {'ref': 'wpa3-ci', 'inputs': inputs or {}})
      require(isinstance(result, dict) and type(result.get('workflow_run_id')) is int,
              'dispatch did not return its exact run id; cannot safely monitor revoke')
      return result['workflow_run_id']
    run('gh', 'workflow', 'run', workflow, '--repo', self.repository, '--ref', 'wpa3-ci',
        '--json', data=fs.dumps(inputs or {}).encode())

  def issue(self, label, title, body, *, key=''):
    self.writable()
    from issues import escaped, labels_for
    require(label in ('follow-paused', 'follow-hold', 'revoke-blocked'), 'invalid follow label')
    if key:
      fs.match(fs.SHA256, key, 'issue key')
    labels = labels_for(label, key=key)
    for name in labels:
      run('gh', 'label', 'create', name, '--repo', self.repository, '--color', 'B60205', '--force')
    candidates = self.pages(f'issues?state=open&labels={",".join(labels)}&per_page=100')
    marker = f'<!-- wpa3-key:{key} -->'
    existing = next((i for i in candidates if 'pull_request' not in i and
                     (marker in (i.get('body') or '') if key else
                      label == 'follow-paused' or i['title'] == escaped(title))), None)
    fields = {'title': escaped(title), 'body': (marker + '\n\n' if key else '') + escaped(body)}
    if existing:
      return self.api(f"issues/{existing['number']}", 'PATCH', fields)
    return self.api('issues', 'POST', {**fields, 'labels': labels})


def asset_limit(name):
  if re.fullmatch(r'agnos-kernel-sdm845-[0-9a-f]{12}\.tar\.xz', name) or name == 'source.tar.xz':
    return 1024 ** 3
  return 64 * 1024 ** 2


def hash_file(path):
  digest = hashlib.sha256()
  with path.open('rb') as stream:
    while chunk := stream.read(1024 * 1024):
      digest.update(chunk)
  return digest.hexdigest()


def checksums(directory, *, write=False):
  require(directory.is_dir() and not directory.is_symlink(), 'invalid asset directory')
  files = {}
  for path in sorted(directory.iterdir()):
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]*', path.name)
            and path.is_file() and not path.is_symlink(), 'assets must be flat regular files')
    require(0 < path.stat().st_size <= asset_limit(path.name), 'asset size limit')
    if path.name != 'SHA256SUMS':
      files[path.name] = hash_file(path)
  expected = ''.join(f'{digest}  {name}\n' for name, digest in files.items())
  if write:
    (directory / 'SHA256SUMS').write_text(expected)
  else:
    require(read_bytes(directory / 'SHA256SUMS', 1024 * 1024).decode() == expected,
            'SHA256SUMS mismatch or asset set differs')
  return files


def release_target(release):
  match = MARKER.search(release.get('body') or '')
  return {'key': match[1], 'stock': match[2], 'tag': release['tag_name']} if match else None


class Brakes:
  def __init__(self, github, gate_version, mode):
    self.github, self.gate_version, self.mode = github, gate_version, fs.mode_value(mode)

  def __call__(self, state, work, target=None, operation='kernel'):
    require(self.mode in WRITE_MODES, 'writes require state/on')
    require(state['policy']['repository'] == self.github.repository, 'policy repository changed')
    require(fs.gate_version(work) == self.gate_version, 'gate_version changed; rerun with current gates')
    # Read all brakes even on administrative operations. Revoke/mark/unpause/
    # retry must remain available while the automatic workflow is disabled.
    active = self.github.workflow('follow.yml')['state'] == 'active'
    paused = self.github.paused()
    releases = self.github.releases()
    withdrawn = False
    target = target or {}
    tags = {target.get('tag')}
    for pin in state['pins'].values():
      if pin['derived_from']['boot_hash_raw'] == target.get('stock') or pin['release_tag'] in tags:
        tags.add(pin['release_tag'])
        withdrawn |= pin['withdrawn'] is not None
    for release in releases:
      mirror = release_target(release)
      relevant = release['tag_name'] in tags or (mirror and mirror['stock'] == target.get('stock'))
      withdrawn |= bool(relevant and (release.get('name') or '').startswith('WITHDRAWN'))
    if operation == 'mark-tested':
      require(not withdrawn, 'target withdrawn in state or release title')
      return
    if operation in ('revoke', 'unpause', 'retry'):
      return
    require(active, 'follow.yml disabled; no publish/state push')
    require(state['status']['paused'] is None and not paused, 'paused in state or follow-paused mirror')
    require(not withdrawn, 'target withdrawn in state or release title')
    if operation == 'kernel':
      k12(state['status'], state['pins'], state['policy'], datetime.now(timezone.utc))


def idempotency_key(stock, candidate, patchset, recipe, gate):
  for value, pattern in ((stock, fs.SHA256), (candidate, r'[0-9a-f]{40}'),
                         (patchset, fs.SHA256), (recipe, fs.SHA256), (gate, fs.SHA256)):
    fs.match(pattern, value, 'idempotency input')
  return sha256((stock + candidate + patchset + recipe + gate).encode())


def recipe_identity(policy):
  patchset = sha256(fs.dumps(policy['patches']).encode())
  recipe = sha256(fs.dumps({'recipe': policy['recipe'], 'build_kernel_normalized': policy['build_kernel_normalized'],
                           'toolchain': policy['toolchain'], 'base_image': policy['builder_base_image']}).encode())
  return patchset, recipe


def artifact_image(path, digest, size):
  with lzma.LZMAFile(path) as stream:
    image = stream.read(MAX_BOOT_SIZE + 1)
  require(len(image) == size and size <= MAX_BOOT_SIZE and sha256(image) == digest, 'boot asset hash/size mismatch')
  return image


def pin_from_provenance(provenance, release, digest):
  """Fill the two values that cannot exist before an immutable publish.

  The asset stores the full pin template. A file cannot contain its own SHA256,
  nor GitHub's future publication timestamp. Only these two null slots are filled
  from the downloaded asset and the immutable release API response.
  """
  pin = deepcopy(provenance['pin'])
  require(pin['auto']['provenance_sha256'] is None and pin['auto']['published_at'] is None,
          'provenance must leave only its digest/publication-time slots unsealed')
  pin['auto'].update(provenance_sha256=digest, published_at=release['published_at'])
  require(pin['release_tag'] == release['tag_name'], 'provenance release tag mismatch')
  return pin


def gate_disposition(facts, *, publishing=False, approval=False):
  rows = facts['gates'] + facts['prebuild']['gates']
  require(all(r['result'] in ('OK', 'FAIL', 'SKIP') for r in rows), 'invalid gate result')
  failed = [r for r in rows if r['result'] == 'FAIL' and r['kind'] == 'integrity']
  require(not failed, 'integrity holds cannot be drafted or approved')
  required = {'K0', 'K2', 'K5', 'K7', 'K9', 'K9-selfcheck', 'K11', 'K7b-format', 'K8-format'}
  passed = {r['gate'] for r in rows if r['result'] == 'OK'}
  require(required <= passed, 'missing integrity gate evidence: ' + ', '.join(sorted(required - passed)))
  risks = [r['gate'] for r in rows if r['result'] == 'FAIL' and r['kind'] == 'risk']
  require('K6' in passed or 'K6' in risks, 'missing K6 patch identity evidence')
  risk_checks = {'K3', 'K4(a)', 'K4(b)', 'K4(c)', 'K4(f)'}
  require(risk_checks <= passed | set(risks), 'missing risk gate evidence')
  require(all(r in ('K3', 'K4(a)', 'K4(b)', 'K4(c)', 'K4(e)', 'K4(f)', 'K6', 'K8') for r in risks),
          'unknown risk hold')
  if publishing:
    # K8 remains advisory until separately qualified. Skips are never evidence.
    require('K7b' in passed, 'K7b reference unqualified; cannot publish')
    require('K4(e)' in passed or (approval and 'K4(e)' in risks), 'K4(e) reference unqualified; cannot publish')
    require(approval or not risks, 'risk-hold draft requires maintainer approve')
  return risks


def release_notes(provenance):
  from release_notes import render
  gate_disposition(provenance['facts'])
  return render(provenance)


def matching_releases(github, stock):
  """Do not use editable titles as proof of identity or recovery integrity."""
  matches = []
  for release in github.releases():
    if not re.fullmatch(fs.RELEASE, release['tag_name']):
      continue
    marker = release_target(release)
    if marker and marker['stock'] == stock:
      matches.append(release)
      continue
    # Recovery must survive edits to a release's mutable notes. The provenance
    # can identify a candidate, but a mutable release can NEVER supply a pin.
    if any(a['name'] == 'provenance.json' for a in release.get('assets', [])):
      with tempfile.TemporaryDirectory(prefix='follow-provenance-') as tmp:
        directory = Path(tmp)
        github.download(release, directory, ['provenance.json'])
        provenance = read_json(directory / 'provenance.json')
      if provenance.get('schema') == 'wpa3-follow-release-v1' and provenance.get('pin', {}).get('derived_from', {}).get('boot_hash_raw') == stock:
        matches.append(release)
  return matches


def attempt_facts(state, stock, result, reason, gate, refs, run_url, *, tag=None, at=None, deferred=None):
  attempts = deepcopy(state['status']['attempts'])
  attempts[stock] = {'result': result, 'reason': reason, 'gate_version': gate, 'refs_fingerprint': refs,
                     'release_tag': tag, 'run_url': run_url, 'at': at or now_text(), 'deferred_until': deferred}
  return {'status': {'attempts': attempts}}


def tested_entry(provenance, actor, device, note, at):
  require(device in ('mici', 'tizi'), 'device must be mici or tizi')
  fs.nonempty(actor, 'tester')
  fs.nonempty(note, 'test note')
  pin = provenance['pin']
  return {'at': at, 'by': actor, 'note': note, 'devices': [device],
          'kernel_commit': pin['auto']['kernel_commit'],
          'stock_boot_hash_raw': pin['derived_from']['boot_hash_raw'],
          'stock_boot_url': pin['derived_from']['boot_url']}


class Publisher:
  def __init__(self, github, writer, gate, run_url):
    self.gh, self.writer, self.gate, self.run_url = github, writer, gate, run_url

  def handoff(self, commit):
    if commit.changed and commit.dispatch:
      self.gh.dispatch()
    return commit

  def record(self, stock, result, reason, refs, *, tag=None, deferred=None):
    reason = reason.replace('\r', ' ').replace('\n', ' ')[:4000]
    def change(state):
      old = state['status']['attempts'].get(stock)
      if old and old['result'] == 'published':
        # A dispatch failure after a successful pin must not rewrite history.
        return {}, True
      detail, report = reason, result in ('held', 'risk_held')
      if result == 'error':
        previous = re.match(r'infra \[([0-9]+)/3\]:', old['reason']) if old and old['result'] == 'error' else None
        same = old and old['gate_version'] == self.gate and old['refs_fingerprint'] == refs
        count = int(previous[1]) + 1 if previous and same else 1
        detail, report = f'infra [{count}/3]: {reason}', count >= 3
      return attempt_facts(state, stock, result, detail, self.gate, refs, self.run_url,
                           tag=tag, deferred=deferred), report
    commit = self.writer.commit(change, stock, target={'stock': stock}, operation='record')
    if commit.changed and commit.value:
      body = f"Stock: `{stock}`\n\n{commit.state['status']['attempts'][stock]['reason']}\n\n{self.run_url}"
      if tag:
        body += f'\n\nDraft: https://github.com/{self.gh.repository}/releases/tag/{tag}'
      if result == 'risk_held':
        body += f'\n\nTo approve after review or device testing: follow-admin approve, target={stock}, device_tested=yes|no.'
      self.gh.issue('follow-hold', f'WPA3 follow held [{stock[:12]}]', body, key=stock)
    return commit

  def reserve(self, target, key):
    self.gh.immutable()
    def change(state):
      names = [r['tag_name'] for r in self.gh.releases()]
      names += [t['name'] for t in self.gh.pages('tags?per_page=100')]
      number = fs.allocate_tag(state, names)
      reserved = fs.reserve_tags(state, 2, names)
      return {'status': {'allocated_tags': reserved['status']['allocated_tags']}}, number
    return self.writer.commit(change, key, target=target, operation='kernel')

  def seal(self, verified, item, stock, key_path, number, state, dest):
    """Retag already verified images only AFTER the reservation's FF push."""
    facts = read_json(verified / 'provenance.json')
    require(facts['gate_version'] == self.gate, 'verified artifacts have stale gates')
    gate_disposition(facts)
    require(facts['stock_hash_raw'] == item['stock_hash'] == sha256(stock), 'stock identity differs')
    policy = state['policy']
    patchset, recipe = recipe_identity(policy)
    candidate = facts['candidate']
    key = idempotency_key(sha256(stock), candidate['commit'], patchset, recipe, self.gate)
    tag = f"agnos-{item['version']}-wpa3.{number}"
    public = bootimg._openssl('rsa', '-in', key_path, '-pubout')
    pin = {'release_tag': tag, 'tag': f'wpa3.sae={number}', 'withdrawn': None,
           'derived_from': {'boot_hash_raw': sha256(stock), 'boot_url': next(x['url'] for x in item['manifest'] if x['name'] == 'boot'),
                            'system_hash_raw': next(x['hash_raw'] for x in item['manifest'] if x['name'] == 'system'),
                            'agnos_py_blob': item['agnos_py_blob']},
           'auto': {'kernel_commit': candidate['commit'], 'builder_commit': candidate['builder_commit'],
                    'recipe_sha256': recipe, 'patchset_sha256': patchset, 'baseline_release': item['baseline_release'],
                    'baseline_kernel_commit': item['baseline_commit'], 'gate_version': self.gate,
                    'provenance_sha256': None, 'run_url': self.run_url, 'published_at': None}}
    dest.mkdir(parents=True)
    for label, offset in (('boot', 0), ('revert', 1)):
      meta = facts[label]
      raw = artifact_image(verified / meta['file'], meta['hash_raw'], meta['size'])
      raw = bootimg.with_tag(raw, f'wpa3.sae={number + offset}', key_path)
      data = assembly.image_checks(stock, raw, public, policy, revert=bool(offset))
      digest = data['hash_raw']
      (dest / f'boot-{digest}.img.xz').write_bytes(assembly.compress_checked(raw))
      facts[label] = {**data, 'file': f'boot-{digest}.img.xz'}
      boot = {'name': 'boot', 'url': f'https://github.com/{self.gh.repository}/releases/download/{tag}/boot-{digest}.img.xz',
              'hash': digest, 'hash_raw': digest, 'size': len(raw), 'sparse': False, 'full_check': True,
              'has_ab': True, 'ondevice_hash': data['ondevice_hash']}
      if offset:
        pin['revert'] = {'tag': f'wpa3.sae={number + offset}', 'boot': boot}
      else:
        pin['boot'] = boot
    # The stock and public key make K9/K11 recovery independent of expiring CDN URLs.
    (dest / f'stock-{sha256(stock)}.img.xz').write_bytes(assembly.compress_checked(stock))
    (dest / 'signing-public.pem').write_bytes(public)
    required = (*policy['patches'], 'source.tar.xz', 'SOURCE.txt', 'stock-rebuild-report.txt', 'build.log', 'source.diff')
    for name in required:
      source = verified / name
      require(source.is_file() and not source.is_symlink(), f'missing verified release asset {name}')
      filename = f"agnos-kernel-sdm845-{candidate['commit'][:12]}.tar.xz" if name == 'source.tar.xz' else name
      shutil.copyfile(source, dest / filename)
    facts.update(mode=self.gh.mode, proposed_tag=number, proposed_revert_tag=number + 1,
                 K10=f'reserved {number} and {number + 1} in a prior fast-forward state commit',
                 notice='Auto-built; NOT device-tested. No WPA3 kernel has ever booted on a comma 3X.')
    provenance = {'schema': 'wpa3-follow-release-v1', 'key': key, 'version': item['version'], 'pin': pin,
                  'facts': facts, 'approval': None,
                  'assets': sorted(p.name for p in dest.iterdir()) + ['provenance.json', 'SHA256SUMS'],
                  'baseline_tested': state['status']['device_tested'].get(item['baseline_release']),
                  'wpa_status': 'stock system not yet probed'}
    facts['toolchain'] = policy['toolchain']
    probe = state['system_probe'].get(pin['derived_from']['system_hash_raw'])
    if probe:
      entry = state['supplicants'].get(probe['stock_wpa_sha256'])
      provenance['wpa_status'] = ('matched stock SHA-256 ' + probe['stock_wpa_sha256'] +
                                  ('; override ' + entry['build_version'] if entry else '; no matching override'))
    write_json(dest / 'provenance.json', provenance)
    checksums(dest, write=True)
    return provenance

  def verify_release(self, release, directory, state, *, publishing=False):
    require(release['draft'] is True or release.get('immutable') is True,
            'infra: mutable published release is never trusted')
    self.gh.download(release, directory)
    checksums(directory)
    provenance = read_json(directory / 'provenance.json')
    require(provenance['schema'] == 'wpa3-follow-release-v1', 'unknown release provenance')
    pin = pin_from_provenance(provenance, {**release, 'published_at': release.get('published_at') or now_text()},
                              sha256(read_bytes(directory / 'provenance.json')))
    validate_pin(provenance['version'], pin, self.gh.repository)
    require(pin['auto']['gate_version'] == self.gate, 'release gate_version differs; integrity review required')
    require(provenance['key'] == idempotency_key(pin['derived_from']['boot_hash_raw'], pin['auto']['kernel_commit'],
            pin['auto']['patchset_sha256'], pin['auto']['recipe_sha256'], self.gate), 'release idempotency key differs')
    approval = provenance['approval']
    if approval is not None:
      fs.keys(approval, ('by', 'device_tested', 'device', 'note', 'at'), 'approval')
      fs.nonempty(approval['by'], 'approver')
      fs.nonempty(approval['note'], 'approval note')
      require(type(approval['device_tested']) is bool, 'invalid device_tested')
      require(approval['device'] in ('mici', 'tizi', ''), 'invalid approval device')
      require(not approval['device_tested'] or bool(approval['device']), 'tested approval requires device')
      utc_time(approval['at'])
    gate_disposition(provenance['facts'], publishing=publishing, approval=approval is not None)
    policy = state['policy']
    require((pin['auto']['patchset_sha256'], pin['auto']['recipe_sha256']) == recipe_identity(policy),
            'release recipe/patchset identity differs from policy')
    facts = provenance['facts']
    require(set(provenance['assets']) == {p.name for p in directory.iterdir()}, 'provenance asset inventory differs')
    require(facts['toolchain'] == policy['toolchain'], 'provenance toolchain differs from policy')
    require(facts['candidate']['commit'] == pin['auto']['kernel_commit']
            and facts['candidate']['builder_commit'] == pin['auto']['builder_commit']
            and facts['stock_hash_raw'] == pin['derived_from']['boot_hash_raw'], 'provenance inputs differ from pin')
    for name, digest in policy['patches'].items():
      require(sha256(read_bytes(directory / name)) == digest, 'release patch identity mismatch')
    require(sha256(read_bytes(directory / 'source.diff')) == policy['source_diff_sha256'], 'release source diff mismatch')
    required = {'SOURCE.txt', 'stock-rebuild-report.txt', 'build.log',
                f"agnos-kernel-sdm845-{pin['auto']['kernel_commit'][:12]}.tar.xz"}
    require(required <= {p.name for p in directory.iterdir()}, 'missing required source/report assets')
    stock_hash = pin['derived_from']['boot_hash_raw']
    with lzma.LZMAFile(directory / f'stock-{stock_hash}.img.xz') as stream:
      stock = stream.read(MAX_BOOT_SIZE + 1)
    require(len(stock) <= MAX_BOOT_SIZE and sha256(stock) == stock_hash, 'release stock bytes differ')
    public = read_bytes(directory / 'signing-public.pem', 16384)
    for entry, revert in ((pin, False), (pin['revert'], True)):
      boot = entry['boot']
      image = artifact_image(directory / f"boot-{boot['hash_raw']}.img.xz", boot['hash_raw'], boot['size'])
      data = assembly.image_checks(stock, image, public, policy, revert=revert)
      require(data['ondevice_hash'] == boot['ondevice_hash'], 'ondevice_hash mismatch')
      require(bootimg.parse(image)['cmdline'].endswith(' ' + entry['tag']), 'image tag differs from pin')
      if not revert:
        import kernel_equiv as ke
        assembly.k7(ke.split(stock)[1], ke.split(image)[1])
    assembly.ondevice_selfcheck(state['manual'], {v: fetch_boot(p['boot']['url'], p['boot']['hash_raw'], p['boot']['size'])
                                                 for v, p in state['manual'].items()})
    return provenance, pin

  def pin_commit(self, provenance, pin):
    require(self.gh.mode == 'on', 'kernel pins require on')
    stock, tag = pin['derived_from']['boot_hash_raw'], pin['release_tag']
    def change(state):
      existing = state['pins'].get(provenance['version'])
      if existing is not None:
        require(existing == pin, 'existing pin differs from immutable release')
        return {}, None
      facts = attempt_facts(state, stock, 'published', 'K13: immutable release verified', self.gate,
        provenance['facts']['refs_fingerprint'], self.run_url, tag=tag, at=pin['auto']['published_at'])
      facts['pins'] = {provenance['version']: pin}
      facts['status']['last_auto_publish_at'] = pin['auto']['published_at']
      approval = provenance.get('approval')
      if approval and approval['device_tested']:
        tested = deepcopy(state['status']['device_tested'])
        tested[tag] = tested_entry(provenance, approval['by'], approval['device'], approval['note'], approval['at'])
        facts['status']['device_tested'] = tested
      return facts, None
    return self.handoff(self.writer.commit(change, provenance['key'], target={'stock': stock, 'tag': tag},
                                           operation='kernel', readme=True))

  def public_boots(self, pin):
    for entry in (pin, pin['revert']):
      boot = entry['boot']
      raw = fetch_boot(boot['url'], boot['hash_raw'], boot['size'])
      require(sha256(raw) == boot['hash_raw'] and len(raw) == boot['size']
              and bootimg.ondevice_hash(raw) == boot['ondevice_hash'], 'public boot verification failed')

  def publish_draft(self, release, *, expected=None):
    require(self.gh.mode == 'on', 'kernel releases require on')
    state, _ = self.writer.read(release_target(release), 'kernel')
    self.gh.immutable()
    release = self.gh.release(release['id'])
    require(release['draft'] is True, 'publish requires an existing draft')
    with tempfile.TemporaryDirectory(prefix='follow-api-verify-') as tmp:
      provenance, _ = self.verify_release(release, Path(tmp), state, publishing=True)
      if expected is not None:
        require(checksums(expected) == checksums(Path(tmp)) and
                read_bytes(expected / 'SHA256SUMS') == read_bytes(Path(tmp) / 'SHA256SUMS'), 'API assets differ from local verified assets')
      target = {'stock': provenance['pin']['derived_from']['boot_hash_raw'], 'tag': release['tag_name']}
      # Last remote reads before the irreversible draft -> published PATCH.
      self.gh.immutable()
      self.writer.read(target, 'kernel')
      published = self.gh.edit(release, draft=False, prerelease=True, make_latest='false')
      require(published.get('immutable') is True and published['draft'] is False,
              'infra: published release is not immutable; refusing pin')
      pin = pin_from_provenance(provenance, published, sha256(read_bytes(Path(tmp) / 'provenance.json')))
    self.public_boots(pin)
    return self.pin_commit(provenance, pin)

  def recover(self, release):
    require(self.gh.mode == 'on', 'kernel recovery requires on')
    require(release['draft'] is False and release.get('immutable') is True,
            'infra: recovery requires an immutable published release')
    self.gh.immutable()
    state, _ = self.writer.read({'tag': release['tag_name']}, 'record')
    if any(p['release_tag'] == release['tag_name'] for p in state['pins'].values()):
      print('K13: SKIP: recovered pin already exists')
      return
    self.writer.read({'tag': release['tag_name']}, 'kernel')
    with tempfile.TemporaryDirectory(prefix='follow-recover-') as tmp:
      provenance, pin = self.verify_release(release, Path(tmp), state, publishing=True)
    target = {'stock': pin['derived_from']['boot_hash_raw'], 'tag': pin['release_tag']}
    self.writer.read(target, 'kernel')
    self.public_boots(pin)
    numbers = {int(p['tag'].split('=')[1]) for p in (pin, pin['revert'])}
    def reserve_lost(state):
      allocated = sorted(set(state['status']['allocated_tags']) | numbers)
      # Check collisions BEFORE persisting lost reservations.
      fs.validate_union(state['manual'], {**state['pins'], provenance['version']: pin}, self.gh.repository)
      return {'status': {'allocated_tags': allocated}}, None
    self.writer.commit(reserve_lost, provenance['key'], target=target, operation='kernel')
    return self.pin_commit(provenance, pin)

  def reuse(self, item):
    """Crash before publish: reverify retained build data, abandon the draft."""
    import kernel_follow
    fs.match(fs.SHA256, item['stock'], 'reuse stock')
    fs.match(r'[0-9]+', item['run_id'], 'original run id')
    release = self.gh.release(item['release_id'])
    require(release['draft'] is True, 'reuse requires a draft; use immutable recovery for published releases')
    target = {'stock': item['stock'], 'tag': release['tag_name']}
    self.writer.read(target, 'kernel')
    with tempfile.TemporaryDirectory(prefix='follow-reuse-') as tmp:
      root = Path(tmp)
      inputs, builds, out = root / 'detect', root / 'builds', root / 'verified'
      try:
        run('gh', 'run', 'download', item['run_id'], '--repo', self.gh.repository,
            '--name', 'kernel-detect', '--dir', inputs)
        plan = read_json(inputs / 'plan.json')
        require(not plan.get('replay') and plan['gate_version'] == self.gate, 'reused artifacts have stale/replay gates')
        identity = item['stock'][:12]
        require(identity in plan['items'], 'original run has no matching stock item')
        directory = inputs / 'items' / identity
        original = read_json(directory / 'input.json')
        for commit in original['scheduled']:
          fs.match(r'[0-9a-f]{40}', commit, 'reused candidate commit')
          name = f'kernel-{identity}-{commit[:12]}'
          run('gh', 'run', 'download', item['run_id'], '--repo', self.gh.repository,
              '--name', name, '--dir', builds / name)
      except subprocess.CalledProcessError:
        self.writer.read(target, 'kernel')
        self.gh.edit(release, name='ABANDONED: ' + (release.get('name') or release['tag_name']))
        # Next detect rebuilds instead of repeatedly requesting expired artifacts.
        self.record(item['stock'], 'error', 'rebuild: artifacts unavailable for original run ' + item['run_id'], '0' * 64)
        return
      plan['items'] = [identity]
      write_json(inputs / 'plan.json', plan)
      kernel_follow.publish(inputs, builds, out)
      stock = read_bytes(directory / 'stock.img')
      require(sha256(stock) == item['stock'], 'reused stock hash mismatch')
      facts = read_json(out / identity / 'provenance.json')
      return self.kernel(out / identity, original, stock, directory / facts['candidate']['builder_commit'] / 'vble-qti.key')

  def kernel(self, verified, item, stock, key_path):
    from kernel_follow import verify_sums
    verify_sums(verified)
    facts = read_json(verified / 'provenance.json')
    risks = gate_disposition(facts)
    target = {'stock': sha256(stock)}
    state, _ = self.writer.read(target, 'record')
    if any(p['derived_from']['boot_hash_raw'] == target['stock'] for p in state['pins'].values()):
      print('K13: SKIP: stock already pinned')
      return
    matches = matching_releases(self.gh, target['stock'])
    require(not any((r.get('name') or '').startswith('WITHDRAWN') for r in matches), 'target withdrawn in release title')
    published = [r for r in matches if not r['draft']]
    require(len(published) <= 1, 'multiple published releases for one stock hash')
    if published:
      return self.recover(published[0])
    # A prior crash never leads to deletion or reuse of a draft's numbers.
    for draft in matches:
      if not (draft.get('name') or '').startswith(('ABANDONED:', 'WITHDRAWN')):
        self.writer.read({**target, 'tag': draft['tag_name']}, 'kernel')
        self.gh.edit(draft, name='ABANDONED: ' + (draft.get('name') or draft['tag_name']))
    patchset, recipe = recipe_identity(state['policy'])
    key = idempotency_key(target['stock'], facts['candidate']['commit'], patchset, recipe, self.gate)
    reservation = self.reserve(target, key)
    with tempfile.TemporaryDirectory(prefix='follow-draft-') as tmp:
      directory = Path(tmp) / 'assets'
      provenance = self.seal(verified, item, stock, key_path, reservation.value, reservation.state, directory)
      title, body = release_notes(provenance)
      self.writer.read(target, 'kernel')
      draft = self.gh.api('releases', 'POST', {'tag_name': provenance['pin']['release_tag'],
        'target_commitish': reservation.head, 'name': title, 'body': body, 'draft': True,
        'prerelease': True, 'make_latest': 'false'})
      self.gh.upload(draft, directory)
      # Even a held draft must have every asset downloaded and checked.
      draft = self.gh.release(draft['id'])
      with tempfile.TemporaryDirectory(prefix='follow-draft-check-') as check:
        checked, _ = self.verify_release(draft, Path(check), reservation.state)
        require(checked == provenance and checksums(Path(check)) == checksums(directory), 'draft differs from verified assets')
      if self.gh.mode == 'state' or risks:
        return self.record(target['stock'], 'risk_held' if risks else 'held',
          'risk checks failed: ' + ', '.join(risks) if risks else 'state mode: draft awaiting on mode',
          facts['refs_fingerprint'], tag=draft['tag_name'])
      return self.publish_draft(draft, expected=directory)

  def wpa_draft(self, source):
    """Stage a T3 request, never publish a rebuilt supplicant in this part.

    Anonymous pollers cannot read drafts. Public distribution of a candidate is
    deliberately disabled while policy.wpa.auto_publish is false (§16.1).
    """
    import wpa_request as protocol
    request = read_json(source / 'test-request.json')
    protocol.validate(request, request['suite_commit'])
    protocol.verify_assets(request, source)
    target = {'stock': request['assets']['stock']['sha256']}
    state, head = self.writer.read(target, 'probe')
    require(state['policy']['wpa']['auto_publish'] is False, 'Part 4a does not enable rebuilt supplicant publication')
    self.gh.immutable()
    releases = self.gh.releases()
    tag = 'wpa-test-' + request['id']
    existing = [r for r in releases if r['tag_name'] == tag]
    if existing:
      # A retry gets a fresh request tag; abandoned drafts remain forever.
      for release in existing:
        require(release['draft'] is True, 'unexpected published WPA request; refuses mutable recovery')
        self.gh.edit(release, name='ABANDONED: ' + (release.get('name') or tag))
      suffix = 1
      base = request['id'].split('-')[1]
      while tag in {r['tag_name'] for r in releases}:
        request['id'] = f"wpa3-{base}0{suffix}-{request['assets']['candidate']['sha256'][:12]}"
        tag = 'wpa-test-' + request['id']
        suffix += 1
      for name, asset in request['assets'].items():
        asset['url'] = f'https://github.com/{self.gh.repository}/releases/download/{tag}/{name}'
      protocol.validate(request, request['suite_commit'])
    with tempfile.TemporaryDirectory(prefix='wpa-draft-') as tmp:
      directory = Path(tmp) / 'assets'
      directory.mkdir()
      for name in protocol.ASSETS | {'build-report.json', 'test-report.json'}:
        require((source / name).is_file() and not (source / name).is_symlink(), 'missing WPA evidence')
        shutil.copyfile(source / name, directory / name)
      write_json(directory / 'test-request.json', request)
      build = read_json(directory / 'build-report.json')
      tests = read_json(directory / 'test-report.json')
      provenance = {'schema': 'wpa3-wpa-release-v1', 'request': request,
        'publication_status': 'DRAFT; auto_publish=false',
        'wpa_status': 'test-request only; no public binary or supplicant pin',
        'publication_requirements': 'Publication requires policy.wpa.auto_publish AND a matching public Mac mini T3 result.',
        'assets': sorted(p.name for p in directory.iterdir()) + ['provenance.json', 'SHA256SUMS'],
        'facts': {'build': build, 'toolchain': {'base_image': state['policy']['wpa']['base_image'],
          'snapshot': state['policy']['wpa']['snapshot']}, 'gates': [
          {'gate': gate, 'result': result, 'detail': 'recorded in build/test report', 'line': f'{gate}: {result}'}
          for gate, result in {**build, **tests}.items() if re.fullmatch('[RT][0-9]+', gate)]}}
      write_json(directory / 'provenance.json', provenance)
      from release_notes import render
      title, body = render(provenance, 'wpa')
      checksums(directory, write=True)
      self.writer.read(target, 'probe')
      draft = self.gh.api('releases', 'POST', {'tag_name': tag, 'target_commitish': head,
        'name': title, 'body': body,
        'draft': True, 'prerelease': True, 'make_latest': 'false'})
      self.gh.upload(draft, directory)
      with tempfile.TemporaryDirectory(prefix='wpa-draft-check-') as check:
        self.gh.download(self.gh.release(draft['id']), Path(check))
        require(checksums(directory) == checksums(Path(check)), 'WPA draft checksum mismatch')
    print(f"T3: DRAFT: {request['id']}; auto_publish=false, no public binary or supplicant pin")


def wpa_publication_gate(policy, request, result_id, directory):
  """The two independent requirements, for any future supplicant write path."""
  import wpa_request as protocol
  require(policy['wpa']['auto_publish'] is True, 'wpa.auto_publish is false')
  require(result_id == request['id'], 'T3 result id does not match request')
  protocol.validate(request, request['suite_commit'], protocol.utc(request['created_at']))
  result, log = directory / 'result.json', directory / 'result.log'
  # This downloader uses no GitHub credentials or Authorization header.
  protocol.download(protocol.RESULTS + 'results/' + result_id + '.json', result, 65536)
  protocol.download(protocol.RESULTS + 'results/' + result_id + '.log', log, 1024 * 1024)
  protocol.verify_result(request, read_json(result), log.read_bytes())


def run_follow(inputs, builds, probes, wpa_builds, out, *, mode, replay='', result_id='', reference=False):
  import kernel_follow
  import wpa_follow
  plan, probe_plan = read_json(inputs / 'plan.json'), read_json(probes / 'plan.json')
  mode = effective_mode(mode, replay or plan.get('replay') or probe_plan.get('replay') or reference)
  gate = fs.gate_version()
  require(plan['gate_version'] == probe_plan['gate_version'] == gate, 'gate_version changed between jobs')
  if mode == 'off':
    print('FOLLOW: off; no writes')
    return
  # Missing/failing WPA build jobs cannot silently qualify a binary. Probes are
  # independent facts and can still be recorded when a rebuild is held.
  errors = []
  wpa_error = None
  try:
    wpa_follow.publish(probes, wpa_builds, result_id or None)
    wpa_verified = True
  except Exception as error:
    wpa_error = f'WPA: {error}'
    errors.append(wpa_error)
    wpa_verified = False
  try:
    kernel_follow.publish(inputs, builds, out)
  except Exception as error:
    errors.append(f'kernel verification: {error}')
  if mode not in WRITE_MODES:
    require(not errors, '; '.join(errors))
    print('FOLLOW: dryrun; no releases, state commits or dispatches')
    return
  network_only_in_workflow()
  state = fs.load()
  repository = state['policy']['repository']
  require(repository == os.environ['GITHUB_REPOSITORY'], 'workflow/policy repository mismatch')
  require(os.environ.get('GITHUB_REF') == 'refs/heads/wpa3-ci', 'write jobs must run on wpa3-ci')
  run_url = f"https://github.com/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
  gh = GitHub(repository, mode)
  writer = StateWriter(Brakes(gh, gate, mode), mode, run_url)
  publisher = Publisher(gh, writer, gate, run_url)
  gh.immutable()
  # Kernel verification outcomes are recorded per stock below. A transient
  # infrastructure error is retried next run, escalating only on its third hit.
  errors = [wpa_error] if wpa_error else []
  # Probe facts may never replace a previously recorded hash/version.
  publisher.handoff(writer.commit(lambda old: ({'system_probe': probe_plan['probes']}, None),
                                 'system-probes', operation='probe'))
  for recovery in plan.get('recover', []):
    if mode == 'on':
      try:
        publisher.recover(gh.release(recovery['release_id']))
      except Exception as error:
        errors.append(f"recovery {recovery['stock']}: {error}")
  for reuse in plan.get('reuse', []):
    try:
      publisher.reuse(reuse)
    except Exception as error:
      errors.append(f"draft reuse {reuse['stock']}: {error}")
  for outcome in plan.get('outcomes', []):
    commit = publisher.record(outcome['stock'], outcome['result'], outcome['reason'], outcome['refs_fingerprint'],
                              deferred=outcome.get('deferred_until'))
    if commit.value:
      errors.append(outcome['reason'])
  outcomes = read_json(out / 'run.json').get('outcomes', {}) if (out / 'run.json').exists() else {}
  for identity in plan['items']:
    item_dir = inputs / 'items' / identity
    item = read_json(item_dir / 'input.json')
    stock = read_bytes(item_dir / 'stock.img')
    verified = out / identity
    if not verified.is_dir():
      outcome = outcomes.get(identity, {'result': 'held', 'reason': 'integrity hold: no verified candidate artifacts'})
      commit = publisher.record(sha256(stock), outcome['result'], outcome['reason'], item['discovery']['refs_fingerprint'])
      if commit.value:
        errors.append(outcome['reason'])
      continue
    try:
      require(not probe_plan['kernel_holds'], 'integrity hold: system contains 4.9 modules')
      facts = read_json(verified / 'provenance.json')
      key_path = item_dir / facts['candidate']['builder_commit'] / 'vble-qti.key'
      publisher.kernel(verified, item, stock, key_path)
    except Exception as error:
      reason = str(error)
      # Record a rate deferral separately; force never bypasses it.
      deferred = re.search(r'deferred until ([0-9T:+-]+)', reason)
      if deferred:
        until = datetime.fromisoformat(deferred[1]).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        publisher.record(sha256(stock), 'deferred', reason, item['discovery']['refs_fingerprint'], deferred=until)
      else:
        result = 'error' if 'infra:' in reason or isinstance(error, (OSError, subprocess.CalledProcessError)) else 'held'
        commit = publisher.record(sha256(stock), result, reason, item['discovery']['refs_fingerprint'])
        if commit.value:
          errors.append(f"{identity}: {reason}")
  if wpa_verified:
    for request in sorted(wpa_builds.glob('*/test-request.json')):
      publisher.wpa_draft(request.parent)
  if errors:
    gh.issue('follow-hold', 'WPA3 follow: publication held', '\n'.join(errors) + '\n\n' + run_url)
    raise ValueError('; '.join(errors))


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--inputs', type=Path, required=True)
  parser.add_argument('--builds', type=Path, required=True)
  parser.add_argument('--probes', type=Path, required=True)
  parser.add_argument('--wpa-builds', type=Path, required=True)
  parser.add_argument('--out', type=Path, required=True)
  args = parser.parse_args()
  try:
    run_follow(args.inputs, args.builds, args.probes, args.wpa_builds, args.out,
      mode=os.environ.get('FOLLOW_MODE', 'off'), replay=os.environ.get('REPLAY', ''),
      result_id=os.environ.get('RESULT_ID', ''), reference=os.environ.get('WPA_REFERENCE') == 'true')
    return 0
  except Exception as error:
    print(f'FOLLOW: FAIL: {error}', file=sys.stderr)
    return 1


if __name__ == '__main__':
  sys.exit(main())
