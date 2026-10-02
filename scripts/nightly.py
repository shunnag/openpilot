#!/usr/bin/env python3
"""Read published fork metadata without executing any upstream code."""
import argparse
from pathlib import Path
import re

from compose import blob, git, launch_values
from follow_state import load


def trailer(repo, commit, name):
  return git(repo, 'show', '-s', f'--format=%(trailers:key={name},valueonly)', commit).decode().strip()


def withdrawn_release(repo, commit, state):
  tag = trailer(repo, commit, 'WPA3-AGNOS')
  return next((p for p in state['pins'].values() if p['release_tag'] == tag and p['withdrawn']), None)


def published_upstream(repo, commit, state):
  """Only branches still serving withdrawn bytes participate in a revoke."""
  _, _, digest, _ = launch_values(blob(repo, commit, 'launch_env.sh'))
  if not any(p['withdrawn'] and p['boot']['hash_raw'] == digest for p in state['pins'].values()):
    return ''
  upstream = trailer(repo, commit, 'Upstream-Commit')
  if not re.fullmatch(r'[0-9a-f]{40}', upstream):
    raise ValueError('published fork has no unique Upstream-Commit trailer')
  parents = git(repo, 'show', '-s', '--format=%P', commit).decode().split()
  if parents != [upstream]:
    raise ValueError('published parent differs from Upstream-Commit')
  if git(repo, 'show', '-s', '--format=%P', upstream).strip():
    raise ValueError('published upstream is not an orphan commit')
  return upstream


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('action', choices=('published-upstream', 'keep-lastgood'))
  parser.add_argument('--repo', type=Path, required=True)
  parser.add_argument('--published', required=True)
  args = parser.parse_args()
  state = load()
  if args.action == 'published-upstream':
    print(published_upstream(args.repo, args.published, state))
  else:
    print('true' if withdrawn_release(args.repo, args.published, state) else 'false')


if __name__ == '__main__':
  main()
