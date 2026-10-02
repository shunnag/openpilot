#!/usr/bin/env python3
"""Owner-only follow controls. Dispatch inputs are read from env, never shell code."""
from copy import deepcopy
import os
from pathlib import Path
import re
import sys
import tempfile
import time

import follow_state as fs
from follow_git import StateWriter
from follow_publish import (Brakes, GitHub, Publisher, WRITE_MODES, checksums, gate_disposition,
                            now_text, pin_from_provenance, release_notes, tested_entry)
from kernel_common import network_only_in_workflow, read_bytes, read_json, require, sha256, write_json
from compose import validate_pin


def pin_for_tag(state, tag):
  matches = [(version, pin) for version, pin in state['pins'].items() if pin['release_tag'] == tag]
  require(len(matches) == 1, 'target is not a unique automatic pin')
  return matches[0]


class Admin:
  def __init__(self, publisher, actor, marker):
    self.publisher, self.gh, self.writer = publisher, publisher.gh, publisher.writer
    self.actor, self.marker = actor, Path(marker)

  def approve(self, stock, tested, device, note):
    require(self.gh.mode == 'on', 'approve publishes a kernel; requires on')
    fs.match(fs.SHA256, stock, 'stock hash')
    require(tested in ('yes', 'no'), 'device_tested must be yes or no')
    require(tested != 'yes' or device in ('mici', 'tizi'), 'device-tested approval requires device type')
    fs.nonempty(note, 'approval note')
    state, _ = self.writer.read({'stock': stock}, 'kernel')
    attempt = state['status']['attempts'].get(stock)
    require(attempt and attempt['result'] == 'risk_held', 'approve requires a risk-hold attempt; integrity holds cannot be approved')
    draft = self.gh.by_tag(attempt['release_tag'])
    require(draft['draft'] is True and not (draft.get('name') or '').startswith(('ABANDONED:', 'WITHDRAWN')),
            'approve requires an existing, non-abandoned risk-hold draft')
    with tempfile.TemporaryDirectory(prefix='follow-approve-') as tmp:
      directory = Path(tmp)
      provenance, pin = self.publisher.verify_release(draft, directory, state)
      require(pin['derived_from']['boot_hash_raw'] == stock, 'draft stock differs from approval target')
      risks = gate_disposition(provenance['facts'], publishing=True, approval=True)
      require(risks, 'approve requires a risk failure, not a mode/integrity hold')
      provenance['approval'] = {'by': self.actor, 'device_tested': tested == 'yes', 'device': device,
                                'note': note, 'at': now_text()}
      write_json(directory / 'provenance.json', provenance)
      checksums(directory, write=True)
      target = {'stock': stock, 'tag': draft['tag_name']}
      self.writer.read(target, 'kernel')
      # Replacing these two assets is permitted ONLY while the release is draft.
      self.gh.upload(draft, directory, names={'provenance.json', 'SHA256SUMS'}, replace=True)
      self.writer.read(target, 'kernel')
      _, body = release_notes(provenance)
      title = (f"AGNOS {provenance['version']} WPA3 boot image ({pin['tag']}): risk check "
               f"{', '.join(risks)} FAILED, published by the maintainer " +
               (f'after a device test ({device})' if tested == 'yes' else 'without a device test'))
      draft = self.gh.edit(draft, name=title, body=body + f'\nApproved by `{self.actor}`; device_tested={tested}; device={device or "none"}.\n')
      return self.publisher.publish_draft(draft, expected=directory)

  def mark_tested(self, tag, device, note):
    fs.match(fs.RELEASE, tag, 'release tag')
    require(device in ('mici', 'tizi'), 'device must be mici or tizi')
    fs.nonempty(note, 'test note')
    release = self.gh.by_tag(tag)
    require(release['draft'] is False and release.get('immutable') is True,
            'mark-tested requires immutable release provenance')
    with tempfile.TemporaryDirectory(prefix='follow-tested-') as tmp:
      directory = Path(tmp)
      self.gh.download(release, directory)
      checksums(directory)
      provenance = read_json(directory / 'provenance.json')
      require(provenance['schema'] == 'wpa3-follow-release-v1', 'missing automatic provenance')
      pin = pin_from_provenance(provenance, release, sha256(read_bytes(directory / 'provenance.json')))
    validate_pin(provenance['version'], pin, self.gh.repository)
    at = now_text()
    def change(state):
      _, current = pin_for_tag(state, tag)
      require(current['withdrawn'] is None and current == pin, 'tested pin withdrawn or differs from immutable provenance')
      tested = deepcopy(state['status']['device_tested'])
      entry = tested_entry(provenance, self.actor, device, note, at)
      entry['devices'] = sorted(set(tested.get(tag, {}).get('devices', [])) | {device})
      tested[tag] = entry
      return {'status': {'device_tested': tested}}, None
    result = self.writer.commit(change, tag, target={'tag': tag}, operation='mark-tested', readme=True)
    # Never dispatch nightly: device_tested is a sidecar, not compose input.
    self.writer.read({'tag': tag}, 'mark-tested')
    release = self.gh.release(release['id'])
    require(not (release.get('name') or '').startswith('WITHDRAWN'), 'cannot clear withdrawal while marking tested')
    devices = result.state['status']['device_tested'][tag]['devices']
    provenance['device_tested'] = result.state['status']['device_tested'][tag]
    _, body = release_notes(provenance)
    self.gh.edit(release, name=f"AGNOS {provenance['version']} WPA3 boot image ({pin['tag']}): device-tested ({', '.join(devices)})",
                 body=body + f'\nDevice-tested on {device} by `{self.actor}` at {at}.\n',
                 prerelease=False, make_latest='false')
    return result

  def revoke(self, tag, note):
    fs.match(fs.RELEASE, tag, 'release tag')
    fs.nonempty(note, 'withdrawal reason')
    state, _ = self.writer.read({'tag': tag}, 'revoke')
    _, pin = pin_for_tag(state, tag)
    notice = pin['withdrawn'] or {'at': now_text(), 'by': self.actor, 'reason': note}
    # Install the out-of-git brake first. A crash before the state commit still
    # stops automatic publication, and repeating revoke completes the transition.
    self.gh.issue('follow-paused', 'WPA3 follow paused after withdrawal',
                  f"WITHDRAWN: {tag}\n\n{note}\n\n{self.publisher.run_url}")
    def change(current):
      version, existing = pin_for_tag(current, tag)
      return {'withdraw': {version: existing['withdrawn'] or notice}}, None
    result = self.writer.commit(change, tag, target={'tag': tag}, operation='revoke', readme=True)
    try:
      release = self.gh.by_tag(tag)
      title = release.get('name') or tag
      if not title.startswith('WITHDRAWN'):
        self.gh.edit(release, name='WITHDRAWN: ' + title,
          body=f'WITHDRAWN: {note}\n\nUse the prebuilt stock revert {pin["revert"]["tag"]}.\n\n' + (release.get('body') or ''))
      self.dispatch_revoke()
    except Exception as error:
      self.gh.issue('revoke-blocked', f'WPA3 revoke blocked: {tag}',
                    f'Withdrawal and pause are recorded. Revert dispatch/restore failed: {error}\n\n{self.publisher.run_url}')
      raise
    return result

  def restore_nightly(self):
    if self.marker.exists():
      marker = read_json(self.marker)
      require(marker == {'repository': self.gh.repository, 'restore_disabled': True}, 'invalid restore marker')
      self.gh.api('actions/workflows/nightly.yml/disable', 'PUT')
      require(self.gh.workflow('nightly.yml')['state'] != 'active', 'nightly remained active after restore')
      self.marker.unlink()

  def dispatch_revoke(self):
    disabled = self.gh.workflow('nightly.yml')['state'] != 'active'
    if disabled:
      # Written before enabling, also consumed by an always() workflow step.
      self.marker.parent.mkdir(parents=True, exist_ok=True)
      write_json(self.marker, {'repository': self.gh.repository, 'restore_disabled': True})
    try:
      if disabled:
        self.gh.api('actions/workflows/nightly.yml/enable', 'PUT')
      identity = self.gh.dispatch(inputs={'upstream': 'published'}, details=True)
      # Monitor the exact returned run, never guess from a concurrently created
      # scheduled/owner run. API 2026-03-10 returns this ID on dispatch.
      deadline = time.monotonic() + 35 * 60
      while time.monotonic() < deadline:
        result = self.gh.api(f'actions/runs/{identity}')
        require(result['event'] == 'workflow_dispatch' and result['head_branch'] == 'wpa3-ci', 'unexpected revoke run')
        if result['status'] == 'completed':
          require(result['conclusion'] == 'success', 'revoke nightly failed: ' + str(result['conclusion']))
          return
        time.sleep(15)
      raise ValueError('revoke nightly timed out; inspect the dispatched run')
    finally:
      if disabled:
        self.restore_nightly()

  def unpause(self):
    mirrors = self.gh.paused()
    result = self.writer.commit(lambda state: ({'status': {'paused': None}}, None),
                                'unpause', operation='unpause', readme=True)
    for issue in mirrors:
      self.gh.api(f"issues/{issue['number']}", 'PATCH', {'state': 'closed'})
    return result

  def retry(self, stock):
    fs.match(fs.SHA256, stock, 'stock hash')
    def change(state):
      status = {}
      for kind in ('attempts', 'wpa_attempts'):
        status[kind] = {key: value for key, value in state['status'][kind].items() if key != stock}
      return {'status': status}, None
    result = self.writer.commit(change, stock, target={'stock': stock}, operation='retry')
    self.gh.dispatch('follow.yml', {'reason': f'owner retry {stock}', 'force': True})
    return result


def main():
  try:
    network_only_in_workflow()
    mode = fs.mode_value(os.environ.get('FOLLOW_MODE', 'off'))
    require(mode in WRITE_MODES, 'follow-admin writes require state/on')
    repository, actor = os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_ACTOR']
    owner = repository.split('/')[0]
    require(actor == owner and os.environ.get('GITHUB_TRIGGERING_ACTOR', actor) == owner, 'follow-admin is owner-only')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/wpa3-ci', 'admin must run on wpa3-ci')
    state, gate = fs.load(), fs.gate_version()
    require(state['policy']['repository'] == repository, 'workflow/policy repository mismatch')
    run_url = f"https://github.com/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    gh = GitHub(repository, mode)
    writer = StateWriter(Brakes(gh, gate, mode), mode, run_url)
    admin = Admin(Publisher(gh, writer, gate, run_url), actor, Path(os.environ['RUNNER_TEMP']) / 'follow-restore-nightly.json')
    action = os.environ.get('ADMIN_ACTION', '')
    target, note = os.environ.get('TARGET', ''), os.environ.get('NOTE', '')
    device, tested = os.environ.get('DEVICE', ''), os.environ.get('DEVICE_TESTED', 'no')
    device = '' if device == 'none' else device
    if action == 'mark-tested':
      admin.mark_tested(target, device, note)
    elif action == 'revoke':
      admin.revoke(target, note)
    elif action == 'approve':
      admin.approve(target, tested, device, note)
    elif action == 'unpause':
      admin.unpause()
    elif action == 'retry':
      admin.retry(target)
    elif action == 'restore-nightly':
      admin.restore_nightly()
    else:
      raise ValueError('unknown admin action')
    return 0
  except Exception as error:
    print(f'FOLLOW ADMIN: FAIL: {error}', file=sys.stderr)
    return 1


if __name__ == '__main__':
  sys.exit(main())
