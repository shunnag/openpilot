#!/usr/bin/env python3
"""Strict data-only T3 request/result protocol shared by CI and the Mac mini."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from system_probe import require, sha_file

REPOSITORY = 'shunnag/openpilot'
RESULTS = 'https://raw.githubusercontent.com/shunnag/wpa3-test-results/main/'
ASSETS = {'candidate', 'candidate.deb', 'candidate.copyright', 'stock', 'stock.copyright', 'test-suite.tar.gz'}
TESTS = {kind + '/' + name for kind in ('candidate', 'stock') for name in (
  'sae_hnp', 'sae_h2e_default', 'sae_h2e_optin', 'sae_h2e_disabled', 'wpa2_psk',
  'transition_psk', 'pmf_required', 'pmf_disabled_rejected')}


def utc(text):
  require(isinstance(text, str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', text), 'invalid UTC timestamp')
  return datetime.strptime(text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)


def read_json(path):
  def unique(pairs):
    result = {}
    for key, value in pairs:
      require(key not in result, 'duplicate JSON key')
      result[key] = value
    return result
  return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def validate(request, suite_commit, now=None):
  require(isinstance(request, dict) and set(request) == {'schema', 'id', 'created_at', 'deadline', 'suite_commit', 'assets'},
          'request may contain only data; shipped code/commands are forbidden')
  require(type(request['schema']) is int and request['schema'] == 1, 'unsupported request schema')
  require(isinstance(request['id'], str) and re.fullmatch(r'wpa3-[0-9]+-[0-9a-f]{12}', request['id']), 'invalid request id')
  require(isinstance(suite_commit, str) and re.fullmatch('[0-9a-f]{40}', suite_commit), 'pin a full suite commit locally')
  require(request['suite_commit'] == suite_commit, 'request suite differs from locally pinned commit')
  created, deadline = utc(request['created_at']), utc(request['deadline'])
  now = now or datetime.now(timezone.utc)
  require(created <= now < deadline and 0 < (deadline - created).total_seconds() <= 7 * 86400, 'request expired/not yet valid/overlong')
  require(isinstance(request['assets'], dict) and set(request['assets']) == ASSETS, 'unexpected request assets (shipped code forbidden)')
  prefix = f"https://github.com/{REPOSITORY}/releases/download/wpa-test-{request['id']}/"
  for name, asset in request['assets'].items():
    require(isinstance(asset, dict) and set(asset) == {'sha256', 'size', 'url'}, 'asset commands/code forbidden')
    require(isinstance(asset['sha256'], str) and re.fullmatch('[0-9a-f]{64}', asset['sha256']), 'invalid asset sha256')
    require(type(asset['size']) is int and 0 < asset['size'] <= 64 * 1024**2, 'invalid asset size')
    require(asset['url'] == prefix + name, 'assets must belong to the same public fork release')
  return request


def verify_assets(request, directory):
  for name, asset in request['assets'].items():
    path = directory / name
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == asset['size']
            and sha_file(path) == asset['sha256'], 'request hash mismatch: ' + name)


def download(url, path, limit=64 * 1024**2):
  require(url.startswith('https://'), 'HTTPS required')
  # No ambient GH_TOKEN, credentials or Authorization header are used.
  request = urllib.request.Request(url, headers={'User-Agent': 'wpa3-hwsim-public-poller'})
  with urllib.request.urlopen(request, timeout=120) as response, path.open('wb') as out:
    total = 0
    while data := response.read(1024 * 1024):
      total += len(data)
      require(total <= limit, 'download too large')
      out.write(data)


def verify_result(request, result, log):
  require(set(result) == {'schema', 'request_id', 'suite_commit', 'assets', 'tested_at', 'colima_version',
                          'kernel_version', 'tests', 'passed', 'log_sha256'}, 'invalid result schema')
  require(type(result['schema']) is int and result['schema'] == 1
          and result['request_id'] == request['id'] and result['suite_commit'] == request['suite_commit'],
          'result request/suite mismatch')
  require(result['assets'] == {name: item['sha256'] for name, item in request['assets'].items()}, 'result candidate hashes differ')
  require(utc(request['created_at']) <= utc(result['tested_at']) <= utc(request['deadline']), 'result outside request window')
  require(hashlib.sha256(log).hexdigest() == result['log_sha256'], 'result log hash mismatch')
  tests = result['tests']
  require(isinstance(tests, list) and len(tests) == len(TESTS) and {t.get('name') for t in tests} == TESTS, 'incomplete T3 suite')
  require(result['passed'] is True and all(test.get('passed') is True for test in tests), 'T3 failed')
  require(all(isinstance(result[k], str) and result[k].strip() for k in ('colima_version', 'kernel_version')), 'missing runner versions')
  return True
