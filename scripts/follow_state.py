#!/usr/bin/env python3
"""Offline follow state, validation and pure transitions (no git or network writes)."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re

from compose import ROOT, utc_time, validate_pin, validate_supplicant

MODES = ("off", "dryrun", "state", "on")
BRANCHES = ("nightly", "nightly-chestnut", "release-mici-staging", "release-tizi-staging")
STATE_FILES = ("pins", "status", "system_probe", "supplicants")
SHA256 = r"[0-9a-f]{64}"
RELEASE = r"agnos-[0-9]+(?:\.[0-9]+)*-wpa3\.([1-9][0-9]*)"
TAG = r"wpa3\.sae=([1-9][0-9]*)"


def require(condition, detail):
  if not condition:
    raise ValueError(detail)


def match(pattern, value, label):
  require(isinstance(value, str) and re.fullmatch(pattern, value) is not None, f"invalid {label}")


def keys(value, required, label, optional=()):
  require(isinstance(value, dict), f"{label} must be an object")
  require(set(required) <= set(value) <= set(required) | set(optional), f"invalid {label} keys")


def nonempty(value, label):
  require(isinstance(value, str) and bool(value.strip()) and not any(c in value for c in '\r\n\0'), f"invalid {label}")


def mode_value(mode):
  require(mode in MODES, f"unknown follow mode {mode!r}")
  return mode


def dumps(value):
  return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def load_json(path):
  def pairs(items):
    result = {}
    for key, value in items:
      require(key not in result, f"duplicate JSON key {key!r} in {path}")
      result[key] = value
    return result
  def constant(value):
    raise ValueError(f"invalid JSON constant {value} in {path}")
  return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=constant)


def load(root=ROOT):
  root = Path(root)
  state = {name: load_json(root / 'agnos/auto' / f'{name}.json') for name in STATE_FILES}
  state['manual'] = load_json(root / 'agnos/pins.json')
  state['policy'] = load_json(root / 'follow/policy.json')
  validate(state)
  for name, digest in state['policy']['patches'].items():
    require(hashlib.sha256((root / 'follow/kernel-patches' / name).read_bytes()).hexdigest() == digest,
            f"kernel patch digest mismatch: {name}")
  require(hashlib.sha256((root / 'follow/kernel-patches/source.diff').read_bytes()).hexdigest() == state['policy']['source_diff_sha256'],
          "source.diff digest mismatch")
  return state


def validate_policy(policy):
  keys(policy, ("schema", "repository", "allowed_branches", "recipe", "build_kernel_normalized", "toolchain",
                "vble_public_key_sha256", "patches", "source_diff_sha256", "risk_paths", "wifi_config_regex",
                "max_changed_lines", "max_commits", "max_full_builds", "max_untested_chain", "min_publish_interval_days",
                "min_free_gb", "builder_base_image", "manifest_shape", "manifest_keys", "on_unknown_stock_wpa", "wpa"), 'policy')
  require(type(policy['schema']) is int and policy['schema'] == 1, 'unsupported policy schema')
  match(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', policy['repository'], 'policy.repository')
  branches = policy['allowed_branches']
  require(isinstance(branches, list) and bool(branches) and all(b in BRANCHES for b in branches)
          and len(set(branches)) == len(branches), 'invalid allowed_branches')
  keys(policy['recipe'], ('build_kernel.sh', 'Dockerfile.builder', 'tools/mkbootimg', 'vble-qti.key'), 'recipe')
  for name, digest in policy['recipe'].items():
    match(r'[0-9a-f]{40}', digest, f'recipe.{name}')
  body = policy['build_kernel_normalized']
  require(isinstance(body, str) and body.startswith('build_kernel() {\n') and body.endswith('}\n')
          and body.count('--cmdline "<CMDLINE>"') == 1, 'invalid normalized build_kernel()')
  keys(policy['toolchain'], ('url', 'sha256', 'gcc_lfs_oid', 'gcc_lfs_size'), 'toolchain')
  match(r'https://[^\s]+', policy['toolchain']['url'], 'toolchain URL')
  for key in ('sha256', 'gcc_lfs_oid'):
    match(SHA256, policy['toolchain'][key], f'toolchain.{key}')
  require(type(policy['toolchain']['gcc_lfs_size']) is int and policy['toolchain']['gcc_lfs_size'] > 0, 'invalid gcc LFS size')
  for key in ('vble_public_key_sha256', 'source_diff_sha256'):
    match(SHA256, policy[key], key)
  require(isinstance(policy['patches'], dict) and len(policy['patches']) == 2, 'expected two kernel patches')
  for name, digest in policy['patches'].items():
    match(r'000[12]-[A-Za-z0-9_.-]+\.patch', name, 'kernel patch name')
    match(SHA256, digest, 'kernel patch hash')
  for key in ('risk_paths', 'manifest_keys'):
    require(isinstance(policy[key], list) and bool(policy[key]), f'invalid {key}')
    for value in policy[key]:
      nonempty(value, key)
  nonempty(policy['wifi_config_regex'], 'wifi_config_regex')
  re.compile(policy['wifi_config_regex'])
  for key in ('max_changed_lines', 'max_commits', 'max_full_builds', 'max_untested_chain', 'min_publish_interval_days', 'min_free_gb'):
    require(type(policy[key]) is int and policy[key] > 0, f'invalid {key}')
  if policy['builder_base_image'] is not None:
    match(r'ubuntu:20\.04@sha256:' + SHA256, policy['builder_base_image'], 'builder_base_image')
  require(isinstance(policy['manifest_shape'], list) and bool(policy['manifest_shape']), 'invalid manifest_shape')
  names = []
  for entry in policy['manifest_shape']:
    keys(entry, ('name', 'sparse', 'full_check'), 'manifest entry', ('has_ab',))
    nonempty(entry['name'], 'partition name')
    require(all(type(v) is bool for k, v in entry.items() if k != 'name'), 'invalid manifest flags')
    names.append(entry['name'])
  require(len(names) == len(set(names)) and {'boot', 'system'} <= set(names), 'invalid manifest partitions')
  require(policy['on_unknown_stock_wpa'] in ('hold', 'stock'), 'invalid on_unknown_stock_wpa')
  wpa = policy['wpa']
  keys(wpa, ('auto_publish', 'version_regex', 'orig_tarball_sha256', 'base_image', 'reference_sha256', 'reference_stock_sha256', 'snapshot', 'reference_debian_sha256'), 'policy.wpa')
  require(type(wpa['auto_publish']) is bool, 'wpa.auto_publish must be boolean')
  nonempty(wpa['version_regex'], 'wpa version regex')
  re.compile(wpa['version_regex'])
  match(r'[0-9]{8}T[0-9]{6}Z', wpa['snapshot'], 'wpa snapshot')
  for key in ('orig_tarball_sha256', 'reference_sha256', 'reference_stock_sha256', 'reference_debian_sha256'):
    match(SHA256, wpa[key], f'wpa.{key}')
  match(r'ubuntu:24\.04@sha256:' + SHA256, wpa['base_image'], 'wpa base image')


def validate_union(manual, auto, repository=None):
  tags, hashes = {}, {}
  for collection in (manual, auto):
    require(isinstance(collection, dict), 'pins must be an object')
    for version, pin in collection.items():
      match(r'[0-9]+(?:\.[0-9]+)*', version, 'AGNOS version')
      validate_pin(version, pin, repository)
      for item in (pin, *([pin['revert']] if 'revert' in pin else [])):
        tag, digest = item['tag'], item['boot']['hash_raw']
        if tag in tags and tags[tag][0] != digest:
          raise ValueError(f"pins {tags[tag][1]} and {version}: tag {tag!r} identifies different boot hashes")
        if digest in hashes and hashes[digest][0] != tag:
          raise ValueError(f"pins {hashes[digest][1]} and {version}: boot hash {digest} has different tags")
        tags[tag], hashes[digest] = (digest, version), (tag, version)
  for version in set(manual) & set(auto):
    require(auto[version].get('withdrawn') is not None, f'duplicate pin {version}')
    require(manual[version]['tag'] not in (auto[version]['tag'], auto[version]['revert']['tag']),
            f'manual fix for {version} must use a new tag')


def validate_status(status):
  keys(status, ('schema', 'device_tested', 'allocated_tags', 'attempts', 'wpa_attempts', 'paused', 'last_auto_publish_at'), 'status')
  require(type(status['schema']) is int and status['schema'] == 1, 'unsupported status schema')
  allocated = status['allocated_tags']
  require(isinstance(allocated, list) and all(type(n) is int and n > 0 for n in allocated)
          and len(allocated) == len(set(allocated)) and {1, 2, 3} <= set(allocated), 'invalid allocated_tags')
  require(isinstance(status['device_tested'], dict), 'device_tested must be an object')
  for release, entry in status['device_tested'].items():
    match(RELEASE, release, 'tested release')
    keys(entry, ('at', 'by', 'note', 'devices', 'kernel_commit', 'stock_boot_hash_raw', 'stock_boot_url'), 'device_tested')
    date.fromisoformat(entry['at']) if re.fullmatch(r'\d{4}-\d\d-\d\d', str(entry['at'])) else utc_time(entry['at'])
    for key in ('by', 'note'):
      nonempty(entry[key], f'device_tested.{key}')
    require(isinstance(entry['devices'], list) and bool(entry['devices']) and all(d in ('mici', 'tizi') for d in entry['devices'])
            and len(entry['devices']) == len(set(entry['devices'])), 'invalid tested devices')
    match(r'[0-9a-f]{40}', entry['kernel_commit'], 'tested kernel commit')
    match(SHA256, entry['stock_boot_hash_raw'], 'tested stock hash')
    require(entry['stock_boot_url'] == f'https://commadist.azureedge.net/agnosupdate/boot-{entry["stock_boot_hash_raw"]}.img.xz', 'invalid tested stock URL')
  for kind in ('attempts', 'wpa_attempts'):
    require(isinstance(status[kind], dict), f'{kind} must be an object')
    for digest, attempt in status[kind].items():
      match(SHA256, digest, 'attempt key')
      keys(attempt, ('result', 'reason', 'gate_version', 'refs_fingerprint', 'release_tag', 'run_url', 'at', 'deferred_until'), kind)
      require(attempt['result'] in ('published', 'held', 'risk_held', 'deferred', 'error'), 'invalid attempt result')
      nonempty(attempt['reason'], 'attempt reason')
      for key in ('gate_version', 'refs_fingerprint'):
        match(SHA256, attempt[key], key)
      if attempt['release_tag'] is not None:
        nonempty(attempt['release_tag'], 'attempt release')
      match(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/[0-9]+', attempt['run_url'], 'attempt run URL')
      utc_time(attempt['at'])
      if attempt['deferred_until'] is not None:
        utc_time(attempt['deferred_until'])
      require(attempt['result'] != 'deferred' or attempt['deferred_until'] is not None, 'deferral requires deferred_until')
  if status['paused'] is not None:
    keys(status['paused'], ('at', 'by', 'reason'), 'paused')
    utc_time(status['paused']['at'])
    nonempty(status['paused']['by'], 'paused.by')
    nonempty(status['paused']['reason'], 'paused.reason')
  if status['last_auto_publish_at'] is not None:
    utc_time(status['last_auto_publish_at'])


def validate(state):
  keys(state, (*STATE_FILES, 'manual', 'policy'), 'state')
  validate_policy(state['policy'])
  validate_status(state['status'])
  validate_union(state['manual'], state['pins'], state['policy']['repository'])
  for pin in state['manual'].values():
    require('auto' not in pin, 'manual pin cannot have auto metadata')
  for pin in state['pins'].values():
    require('auto' in pin and 'wpa_supplicant' not in pin, 'auto state requires auto metadata and no wpa_supplicant')
    for tag in (pin['tag'], pin['revert']['tag']):
      number = int(re.fullmatch(TAG, tag)[1])
      require(number in state['status']['allocated_tags'], f'unreserved tag {number}')
    require(pin['tag'] != pin['revert']['tag'], 'stored auto pin must retain its original boot and tag')
  require(isinstance(state['system_probe'], dict), 'system_probe must be an object')
  for digest, probe in state['system_probe'].items():
    match(SHA256, digest, 'system hash')
    keys(probe, ('stock_wpa_sha256', 'dpkg_version', 'changelog_head', 'probed_by', 'kernel_modules_present'), 'probe')
    match(SHA256, probe['stock_wpa_sha256'], 'stock wpa hash')
    for key in ('dpkg_version', 'changelog_head', 'probed_by'):
      nonempty(probe[key], f'probe.{key}')
    require(type(probe['kernel_modules_present']) is bool, 'invalid kernel_modules_present')
  require(isinstance(state['supplicants'], dict), 'supplicants must be an object')
  for digest, entry in state['supplicants'].items():
    match(SHA256, digest, 'stock supplicant hash')
    keys(entry, ('build_version', 'ubuntu_version', 'sha256', 'path', 'copyright', 'patchset_sha256', 'toolchain',
                 'ci_reproduced_reference', 'built_by'), 'supplicant')
    validate_supplicant(supplicant_entry(digest, entry))
    match(r'(?:[0-9]+:)?[A-Za-z0-9_.+-]+', entry['build_version'], 'build_version')
    for key in ('ubuntu_version', 'built_by'):
      nonempty(entry[key], key)
    match(SHA256, entry['patchset_sha256'], 'supplicant patchset')
    require(isinstance(entry['toolchain'], dict) and bool(entry['toolchain']), 'invalid supplicant toolchain')
    require(type(entry['ci_reproduced_reference']) is bool, 'invalid ci_reproduced_reference')
  wpa = state['policy']['wpa']
  if wpa['auto_publish']:
    reference = state['supplicants'].get(wpa['reference_stock_sha256'], {})
    require(reference.get('sha256') == wpa['reference_sha256'] and reference.get('ci_reproduced_reference') is True,
            'wpa.auto_publish requires ci_reproduced_reference for the reference binary')
  return state


def merged_pins(manual, auto, mode, branch, allowed_branches=BRANCHES, now=None, *, repository=None):
  mode_value(mode)
  if now is not None:
    utc_time(now)
  validate_union(manual, auto, repository)
  merged = deepcopy(manual)
  for version, pin in auto.items():
    if pin['withdrawn'] is not None:
      if version not in manual:
        merged[version] = {**deepcopy(pin), **deepcopy(pin['revert'])}
    elif mode == 'on' and branch in allowed_branches:
      merged[version] = deepcopy(pin)
  return merged


def allocate_tag(state, release_names=()):
  """Next number; release_names must include drafts and abandoned drafts."""
  validate(state)
  numbers = list(state['status']['allocated_tags'])
  for collection in (state['manual'], state['pins']):
    for pin in collection.values():
      for item in (pin, *([pin['revert']] if 'revert' in pin else [])):
        match(TAG, item['tag'], 'tag for allocation')
        numbers.append(int(re.fullmatch(TAG, item['tag'])[1]))
  for name in release_names:
    nonempty(name, 'release name')
    found = re.fullmatch(RELEASE, name)
    if found:
      numbers.append(int(found[1]))
  return max(numbers, default=0) + 1


def reserve_tags(state, n, release_names=()):
  """Return a reservation-only state. Persist it before creating any draft."""
  require(type(n) is int and n > 0, 'reservation count must be positive')
  first = allocate_tag(state, release_names)
  result = deepcopy(state)
  result['status']['allocated_tags'] = sorted(set(result['status']['allocated_tags']) | set(range(first, first + n)))
  return validate(result)


def apply(state, facts, *, brakes=None):
  """Return validated state; map facts merge entries, never erase allocations.

  Status facts replace individual status fields. Withdrawal is a separate fact
  {withdraw: {version: {at, by, reason}}}; it also pauses automatic builds.
  Call state_files() for deterministic bytes. This function never writes files.
  """
  validate(state)
  if brakes is not None:
    require(brakes is True, 'fresh publication brakes refused the state transition')
  keys(facts, (), 'facts', (*STATE_FILES, 'withdraw'))
  result = deepcopy(state)
  if 'status' in facts:
    keys(facts['status'], (), 'status facts', state['status'])
    result['status'].update(deepcopy(facts['status']))
    require(set(state['status']['allocated_tags']) <= set(result['status']['allocated_tags']), 'cannot forget allocated tags')
  for kind in ('pins', 'system_probe', 'supplicants'):
    updates = facts.get(kind, {})
    require(isinstance(updates, dict), f'{kind} facts must be an object')
    for key, value in updates.items():
      old = state[kind].get(key)
      if old == value:
        continue
      if kind == 'pins':
        require(state['status']['paused'] is None and result['status']['paused'] is None, 'automatic pins are paused')
        require(old is None or old['withdrawn'] is None, 'cannot change a withdrawn pin')
        require(old is None, 'automatic pins are immutable; use withdrawal and a manual fix')
        require(value.get('withdrawn') is None, 'use a withdrawal fact')
        for tag in (value['tag'], value['revert']['tag']):
          match(TAG, tag, 'new pin tag')
          require(int(re.fullmatch(TAG, tag)[1]) in state['status']['allocated_tags'], 'reserve tags in a prior state commit')
      elif old is not None:
        # R0 qualification can annotate the exact same binary, never replace it.
        require(kind == 'supplicants' and {**old, 'ci_reproduced_reference': True} == value,
                f'cannot replace immutable {kind} entry {key}')
      result[kind][key] = deepcopy(value)
  withdrawals = facts.get('withdraw', {})
  require(isinstance(withdrawals, dict), 'withdraw facts must be an object')
  for version, notice in withdrawals.items():
    require(version in result['pins'], f'unknown withdrawal {version}')
    old = result['pins'][version]['withdrawn']
    require(old is None or old == notice, 'cannot change an existing withdrawal')
    require(notice is not None, 'cannot clear a withdrawal')
    result['pins'][version]['withdrawn'] = deepcopy(notice)
    result['status']['paused'] = deepcopy(notice)
  return validate(result)


def state_files(state):
  validate(state)
  return {f'agnos/auto/{name}.json': dumps(state[name]).encode() for name in STATE_FILES}


def attempt_wait(attempt, gate, refs, now, *, force=False):
  """Seven-day holds, K1 ref changes and rate deferrals; force only skips holds."""
  if not attempt:
    return None
  if attempt['result'] == 'deferred' and now < utc_time(attempt['deferred_until']):
    return 'deferred until ' + attempt['deferred_until']
  if force or attempt['gate_version'] != gate or attempt['result'] not in ('held', 'risk_held'):
    return None
  if attempt['reason'].startswith('K1') and refs != attempt['refs_fingerprint']:
    return None
  if now < utc_time(attempt['at']) + timedelta(days=7):
    return 'same held attempt younger than seven days'
  return None


def check_allowlist(diff_name_status, readme_old, readme_new, *, modes=None):
  """Check --name-status (no renames) plus {path: (old_mode, new_mode)}.

  Name/status alone cannot distinguish chmod or symlinks. Callers must supply
  modes from git diff --raw; missing mode evidence fails closed.
  """
  require(isinstance(modes, dict), 'missing mode evidence for state allowlist')
  if '\0' in diff_name_status:
    tokens = diff_name_status.rstrip('\0').split('\0')
    require(len(tokens) % 2 == 0, 'invalid NUL name-status')
    rows = list(zip(tokens[::2], tokens[1::2]))
  else:
    rows = [line.split('\t') for line in diff_name_status.splitlines()]
  seen = set()
  for row in rows:
    require(len(row) == 2, 'invalid name-status (renames are forbidden)')
    status, path = row
    require(path not in seen, f'duplicate diff path {path}')
    seen.add(path)
    require(status in ('A', 'M'), f'forbidden status {status}: {path}')
    old, new = modes.get(path, (None, None))
    require(new in ('100644', '100755') and ((status == 'A' and old == '000000') or (status == 'M' and old == new)),
            f'mode change, symlink or missing mode evidence: {path}')
    if path in {f'agnos/auto/{name}.json' for name in STATE_FILES}:
      require(new == '100644', 'state JSON must be a regular non-executable file')
    elif re.fullmatch(r'userspace/wpa/[A-Za-z0-9_.+-]+/(?:wpa_supplicant|wpa_supplicant\.copyright)', path):
      require(status == 'A' and Path(path).parts[2] not in ('.', '..'), 'wpa binaries are create only')
    elif path == 'README.md' and status == 'M':
      begin, end = '<!-- wpa3-status:begin -->', '<!-- wpa3-status:end -->'
      outside = []
      for text in (readme_old, readme_new):
        require(isinstance(text, str) and text.count(begin) == text.count(end) == 1, 'README markers must occur exactly once')
        start, stop = text.index(begin) + len(begin), text.index(end)
        require(start <= stop, 'README markers out of order')
        outside.append((text[:start], text[stop:]))
      require(outside[0] == outside[1], 'README edit outside status markers')
    else:
      raise ValueError(f'path not on state allowlist: {path}')
  require(set(modes) == seen, 'mode evidence differs from name-status')


def gate_version(root=ROOT):
  """Hash paths and bytes, including future follow scripts and reference data."""
  root = Path(root)
  paths = sorted(p for folder in ('scripts', 'follow') for p in (root / folder).rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts and (folder == 'follow' or p.suffix in ('.py', '.sh')))
  digest = hashlib.sha256()
  for path in paths:
    data = path.read_bytes()
    digest.update(str(path.relative_to(root)).encode() + b'\0' + str(len(data)).encode() + b'\0' + data)
  return digest.hexdigest()


class FollowNeeded(ValueError):
  def __init__(self, kind, key, detail):
    self.kind, self.key, self.detail = kind, key, detail
    super().__init__(detail)


def follow_exit(needed, mode, policy, status):
  mode_value(mode)
  # Only recorded holds escalate here. Time-based escalation belongs to issues.py.
  attempts = status['wpa_attempts'] if needed.kind == 'wpa' else status['attempts']
  attempt = attempts.get(needed.key)
  if attempt and attempt['result'] in ('held', 'risk_held'):
    raise ValueError(attempt['reason'])
  if needed.kind == 'kernel':
    return 3 if mode == 'on' else 1
  if needed.kind == 'probe':
    return 3 if mode in ('state', 'on') else 0
  if needed.kind == 'wpa':
    if mode in ('off', 'dryrun'):
      return 0
    if mode == 'on' and policy['wpa']['auto_publish']:
      return 3
    return 0 if policy['on_unknown_stock_wpa'] == 'stock' else 1
  raise ValueError(f'unknown follow kind {needed.kind}')


def supplicant_entry(digest, entry):
  return {**{key: entry[key] for key in ('path', 'sha256', 'copyright')}, 'stock_sha256': digest}


def resolve_supplicant(resolved, system_hash, state, mode):
  """Return resolved data for enforced G8; callers keep original data in WARN mode."""
  probe = state['system_probe'].get(system_hash)
  if probe is None:
    raise FollowNeeded('probe', system_hash, 'system image has not been probed')
  if resolved['mode'] == 'native' and '+agnos' in probe['dpkg_version']:
    raise ValueError('native +agnos wpa_supplicant requires runtime qualification')
  digest = probe['stock_wpa_sha256']
  entry = state['supplicants'].get(digest)
  result = deepcopy(resolved)
  pin = result if result['mode'] == 'native' else result['pin']
  if entry is None:
    needed = FollowNeeded('wpa', digest, 'stock wpa_supplicant has no patched binary')
    try:
      rc = follow_exit(needed, mode, state['policy'], state['status'])
    except ValueError as error:
      raise FollowNeeded('wpa', digest, str(error)) from error
    if rc != 0 or mode in ('off', 'dryrun'):
      raise needed
    pin.pop('wpa_supplicant', None)
    return result
  require(entry['ubuntu_version'] == probe['dpkg_version'], 'G8 probe and supplicant Ubuntu versions differ')
  expected = supplicant_entry(digest, entry)
  if 'wpa_supplicant' in pin:
    require(pin['wpa_supplicant'] == expected, 'G8 explicit wpa_supplicant differs from probed entry')
  pin['wpa_supplicant'] = expected
  return result
