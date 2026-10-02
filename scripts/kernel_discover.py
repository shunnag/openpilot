#!/usr/bin/env python3
"""Propose kernel sources from builder gitlinks; only a rebuild can verify one.

Offline: --builder BARE --kernel REPO --prs JSON [--heads JSON] --offline.
Online access is restricted to GitHub Actions. PR refs never establish trust.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import kernel_equiv as ke
from kernel_common import (BUILDER_URL, KERNEL_URL, Gates, api, git, git_text,
                           network_only_in_workflow, oid, read_bytes, read_json,
                           require, sha256, write_json)

GITLINK = 'agnos-kernel-sdm845'
VERSION_PATHS = ('VERSION', 'userspace/root/VERSION')


def build_time(stock):
  _, image, _ = ke.split(stock)
  user, host, number, timestamp = ke.banner_identity(image)
  when = datetime.strptime(timestamp, '%a %b %d %H:%M:%S UTC %Y').replace(tzinfo=timezone.utc)
  return when, {'user': user, 'host': host, 'number': number, 'timestamp': timestamp}


def local_heads(repo):
  rows = git_text(repo, 'for-each-ref', '--format=%(objectname) %(refname)',
                  'refs/heads/', 'refs/remotes/origin/').splitlines()
  heads = {}
  for row in rows:
    sha, ref = row.split()
    if ref.endswith('/HEAD'):
      continue
    ref = ref.replace('refs/remotes/origin/', 'refs/heads/')
    heads[ref] = oid(sha)
  return heads


def trusted_heads(heads):
  require(isinstance(heads, dict), 'invalid heads snapshot')
  return {ref: oid(sha) for ref, sha in heads.items() if ref.startswith('refs/heads/')}


def same_repo_prs(prs):
  return [pr for pr in prs if (pr.get('head', {}).get('repo') or {}).get('full_name') == 'commaai/agnos-builder']


def oracle(builder, version, when, prs):
  refs = [(ref, sha) for ref, sha in local_heads(builder).items()]
  refs += [(f"PR#{pr['number']}", oid(pr['head']['sha'])) for pr in same_repo_prs(prs)]
  proposals = []
  # Cache shared history blobs: dozens of branch histories overlap almost entirely.
  cache = {}
  for ref, tip in sorted(refs):
    rows = git_text(builder, 'log', '--format=%H %cI', tip, '--', *VERSION_PATHS, GITLINK).splitlines()
    hits = []
    for row in rows:
      commit, date = row.split()
      if commit not in cache:
        versions = []
        for path in VERSION_PATHS:
          if git_text(builder, 'ls-tree', commit, path):
            versions.append(git_text(builder, 'show', f'{commit}:{path}'))
        link = git_text(builder, 'ls-tree', commit, GITLINK).split()
        cache[commit] = (versions, link[2] if len(link) >= 3 and link[0] == '160000' else None)
      versions, link = cache[commit]
      if version in versions and link:
        hits.append((datetime.fromisoformat(date), commit, link))
    hits.sort()
    if not hits:
      continue
    earlier = [hit for hit in hits if hit[0] <= when + timedelta(minutes=10)]
    for label, hit in (('at_build', earlier[-1] if earlier else None), ('last', hits[-1])):
      if hit:
        proposals.append({'commit': hit[2], 'builder_commit': hit[1], 'builder_ref': ref,
                          'oracle': True, 'reason': label, 'date': hit[0].isoformat()})
  return sorted(proposals, key=lambda p: (p['reason'] != 'at_build', p['date'], p['builder_ref']))


def window(kernel, heads, when):
  tips = sorted(set(trusted_heads(heads).values()))
  if not tips:
    return []
  rows = git_text(kernel, 'log', '--format=%H %T %ct',
                  f'--since-as-filter={(when - timedelta(days=14)).isoformat()}',
                  f'--until={(when + timedelta(minutes=60)).isoformat()}', *tips, '--').splitlines()
  seen, result = set(), []
  for commit, tree, date in sorted((r.split() for r in rows), key=lambda r: int(r[2]), reverse=True):
    if tree not in seen:
      seen.add(tree)
      result.append({'commit': commit, 'tree': tree, 'oracle': False, 'reason': 'window'})
  return result[:5]


def branch_contains(candidate, heads, compare=None, fallback=None):
  heads = trusted_heads(heads)
  for ref, tip in heads.items():
    if tip == candidate:
      return ref, 'tip'
  if compare:
    try:
      for ref, tip in heads.items():
        result = compare(candidate, tip)
        require(type(result.get('behind_by')) is int and result['behind_by'] >= 0, 'invalid compare response')
        if result['behind_by'] == 0:
          return ref, 'compare API'
    except Exception:
      if fallback is None:
        raise
    else:
      raise ValueError('kernel commit not on any branch')
  require(fallback is not None, 'branch membership unavailable')
  return fallback(candidate, heads), 'blobless heads fallback'


def local_membership(kernel, candidate, heads):
  for ref, tip in heads.items():
    try:
      git(kernel, 'merge-base', '--is-ancestor', candidate, tip)
      return ref
    except subprocess.CalledProcessError as error:
      if error.returncode != 1:
        raise
  raise ValueError('kernel commit not on any branch')


class DiscoveryHold(ValueError):
  def __init__(self, detail, fingerprint):
    self.refs_fingerprint = fingerprint
    super().__init__(detail)


def refs_fingerprint(proposals, candidates, heads, compare=None, fallback=None):
  """Only VERSION-matching builder proposals and containing kernel heads count."""
  referenced = sorted({(p['builder_ref'], p['builder_commit'], p['commit']) for p in proposals if p['oracle']})
  containing = set()
  for ref, tip in trusted_heads(heads).items():
    for candidate in candidates:
      commit = candidate['commit']
      if tip == commit:
        containing.add((ref, tip))
      elif compare or fallback:
        try:
          branch_contains(commit, {ref: tip}, compare, fallback)
          containing.add((ref, tip))
        except ValueError as error:
          if str(error) != 'kernel commit not on any branch':
            raise
  return sha256(json.dumps([referenced, sorted(containing)]).encode())


def discover(builder, kernel, version, stock, prs, heads, policy, *, compare=None, fallback=None, forced=None):
  when, identity = build_time(stock)
  proposals = oracle(builder, version, when, prs)
  if not proposals:
    raise DiscoveryHold(f'no builder gitlink for VERSION={version}', refs_fingerprint([], [], heads))
  recipe = proposals[0]
  if forced:
    proposals = [{**recipe, 'commit': oid(forced), 'oracle': False, 'reason': 'negative replay'}]
  else:
    proposals += [{**recipe, **p} for p in window(kernel, heads, when)]
  candidates, rejected, seen = [], [], set()
  fallback_measurements = []
  def measured_fallback(commit, snapshot):
    started = time.monotonic()
    try:
      return fallback(commit, snapshot)
    finally:
      fallback_measurements.append({'candidate': commit, 'seconds': time.monotonic() - started})
  for proposal in proposals:
    commit = oid(proposal['commit'])
    try:
      branch, method = branch_contains(commit, heads, compare, measured_fallback if fallback else None)
      # The tree id is in the commit itself; dereferencing ^{tree} would force
      # a needless lazy tree download in an offline treeless history cache.
      tree = oid(git_text(kernel, 'cat-file', 'commit', commit).splitlines()[0].removeprefix('tree '))
      if tree in seen:
        continue
      seen.add(tree)
      candidates.append({**proposal, 'tree': tree, 'branch': branch, 'membership': method})
    except Exception as error:
      rejected.append({**proposal, 'error': str(error)})
  fingerprint = refs_fingerprint(proposals, candidates, heads, compare, measured_fallback if fallback else None)
  if not candidates:
    raise DiscoveryHold(f'K1: no trusted candidates: {rejected}', fingerprint)
  cap = policy['max_full_builds']
  require(type(cap) is int and 1 <= cap <= 3, 'max_full_builds must be 1..3')
  omitted = candidates[cap:]
  candidates = candidates[:cap]
  # Reserve retry slots centrally. Matrix legs cannot each spend the global cap.
  spare = cap - len(candidates)
  for index, candidate in enumerate(candidates):
    candidate['full_build_budget'] = 1 + int(index < spare)
  return {'schema': 1, 'version': version, 'identity': identity, 'stock_sha256': sha256(stock),
          'refs_fingerprint': fingerprint, 'candidates': candidates, 'rejected': rejected,
          'omitted_by_budget': omitted, 'max_full_builds': cap, 'verified': False,
          'fallback_measurements': fallback_measurements}


def fetch_inputs(builder, kernel, builder_url=BUILDER_URL):
  network_only_in_workflow()
  os.environ['KERNEL_FOLLOW_NETWORK'] = '1'
  started = time.monotonic()
  git(builder.parent, 'clone', '--bare', '--filter=blob:none', builder_url, builder)
  pages = json.loads(__import__('kernel_common').run('gh', 'api', '--paginate', '--slurp',
                     'repos/commaai/agnos-builder/pulls?state=all&per_page=100'))
  prs = [pr for page in pages for pr in page]
  for pr in same_repo_prs(prs):
    git(builder, 'fetch', '--filter=blob:none', 'origin', oid(pr['head']['sha']))
  # History without blobs/trees supports the date window. Fetching full trees is
  # restricted to the shortlisted candidates; the fallback cost is measured.
  git(kernel.parent, 'init', '--bare', kernel)
  git(kernel, 'remote', 'add', 'origin', KERNEL_URL)
  raw = git_text(kernel, 'ls-remote', '--heads', 'origin')
  heads = {ref: sha for sha, ref in (line.split() for line in raw.splitlines())}
  heads_started = time.monotonic()
  git(kernel, 'fetch', '--filter=tree:0', 'origin', '+refs/heads/*:refs/heads/*')
  write_json(kernel.parent / 'fetch-metrics.json', {
    'trusted_heads_history_fetch_seconds': time.monotonic() - heads_started,
    'total_fetch_seconds': time.monotonic() - started,
    'note': 'treeless history fetch; fallback ancestry timing is recorded separately when used'})
  heads = dict(sorted(heads.items(), key=lambda row: int(git_text(kernel, 'log', '-1', '--format=%ct', row[1])), reverse=True))
  return prs, heads


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--version', required=True)
  parser.add_argument('--stock', type=Path, required=True)
  parser.add_argument('--builder', type=Path)
  parser.add_argument('--kernel', type=Path)
  parser.add_argument('--builder-url', default=BUILDER_URL)
  parser.add_argument('--prs', type=Path)
  parser.add_argument('--heads', type=Path)
  parser.add_argument('--policy', type=Path, default=Path('follow/policy.json'))
  parser.add_argument('--offline', action='store_true')
  parser.add_argument('--out', type=Path, required=True)
  args = parser.parse_args()
  gates = Gates()
  try:
    with tempfile.TemporaryDirectory(prefix='kernel-discover-') as temporary:
      builder = args.builder or Path(temporary) / 'builder.git'
      kernel = args.kernel or Path(temporary) / 'kernel.git'
      if args.offline:
        require(args.builder and args.kernel and args.prs, 'offline requires builder, kernel and PR JSON')
        prs, heads = read_json(args.prs), read_json(args.heads) if args.heads else local_heads(kernel)
      else:
        prs, heads = fetch_inputs(builder, kernel, args.builder_url)
      started = time.monotonic()
      result = discover(builder, kernel, args.version, read_bytes(args.stock), prs, heads, read_json(args.policy),
                        compare=None if args.offline else lambda a, b: api(f'repos/commaai/agnos-kernel-sdm845/compare/{a}...{b}'),
                        fallback=lambda c, h: local_membership(kernel, c, h))
      result['discovery_seconds'] = time.monotonic() - started
      write_json(args.out, result)
      gates.add('K1', True, f"{len(result['candidates'])} proposals; K5 rebuild verification required")
      return 0
  except Exception as error:
    gates.add('K1', False, error)
    return 1


if __name__ == '__main__':
  sys.exit(main())
