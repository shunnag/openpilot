#!/usr/bin/env python3
"""Create and compare deterministic per-branch nightly evaluation markers."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


MARKER = re.compile(
  r'wpa3-evaluated\n\nBranch: (?P<branch>[A-Za-z0-9][A-Za-z0-9._-]*)\n'
  r'Head: (?P<head>[0-9a-f]{40})\nMode: (?P<mode>off|dryrun|state|on)\n'
  r'Upstream: (?P<upstream>[0-9a-f]{40})\nFork: (?P<fork>[0-9a-f]{40})')


def parse_marker(message):
  # gh --jq adds a transport newline; command substitution can remove it.
  match = MARKER.fullmatch(message.rstrip('\n'))
  return match.groupdict() if match else None


def marker_message(*, branch, head, mode, upstream, fork):
  message = (f'wpa3-evaluated\n\nBranch: {branch}\nHead: {head}\nMode: {mode}\n'
             f'Upstream: {upstream}\nFork: {fork}\n')
  if parse_marker(message) != dict(branch=branch, head=head, mode=mode, upstream=upstream, fork=fork):
    raise ValueError('invalid evaluation marker fields')
  return message


def can_skip(*, upstream, message, head, mode, fork, branch,
             force=False, source='latest', ref=''):
  if source != 'latest' or force or ref != 'refs/heads/wpa3-ci':
    return False
  marker = parse_marker(message)
  return marker is not None and marker == dict(
    branch=branch, head=head, mode=mode, upstream=upstream, fork=fork)


def git(repo, *args, data=None, env=None):
  return subprocess.check_output(['git', '-C', str(repo), *args], input=data, env=env)


def create_marker(repo, *, branch, head, mode, upstream, fork):
  message = marker_message(branch=branch, head=head, mode=mode, upstream=upstream, fork=fork)
  date = git(repo, 'show', '-s', '--format=%cI', upstream).decode().strip()
  tree = git(repo, 'hash-object', '-t', 'tree', '-w', '--stdin', data=b'').decode().strip()
  identity = {f'GIT_{role}_{key}': value for role in ('AUTHOR', 'COMMITTER')
              for key, value in (('NAME', 'wpa3-ci'), ('EMAIL', 'wpa3-ci@users.noreply.github.com'), ('DATE', date))}
  return git(repo, '-c', 'i18n.commitEncoding=UTF-8', 'commit-tree', '--no-gpg-sign', tree,
             data=message.encode(), env={**os.environ, **identity}).decode().strip()


def read_marker(marker, env):
  if env.get('DRY_RUN') == '1' and 'DRY_MARKER_MESSAGE' in env:
    return env['DRY_MARKER_MESSAGE']
  if not re.fullmatch('[0-9a-f]{40}', marker):
    return ''
  cache = Path(env['RUNNER_TEMP']) / 'nightly-skip' / env.get('GITHUB_RUN_ID', 'local')
  cache.mkdir(parents=True, exist_ok=True)
  path = cache / f'marker-{marker}.json'
  if not path.exists():
    message = subprocess.check_output([
      'gh', 'api', '--method', 'GET', f"repos/{env['GH_REPO']}/git/commits/{marker}",
      '--jq', '.message'], text=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(message))
    temporary.replace(path)
  return json.loads(path.read_text())


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  commands = parser.add_subparsers(dest='action', required=True)
  check = commands.add_parser('check')
  check.add_argument('--upstream', required=True)
  check.add_argument('--published', required=True)
  check.add_argument('--marker', default='')
  create = commands.add_parser('create')
  create.add_argument('--repo', type=Path, required=True)
  for name in ('branch', 'head', 'mode', 'upstream', 'fork'):
    create.add_argument(f'--{name}', required=True)
  args = parser.parse_args()
  if args.action == 'create':
    print(create_marker(args.repo, branch=args.branch, head=args.head, mode=args.mode,
                        upstream=args.upstream, fork=args.fork))
    return
  env = os.environ
  eligible = (env.get('UPSTREAM_SOURCE', 'latest') == 'latest' and env.get('FORCE') != 'true'
              and env.get('GITHUB_REF') == 'refs/heads/wpa3-ci')
  message = read_marker(args.marker, env) if eligible else ''
  skip = can_skip(upstream=args.upstream, message=message, head=env['WPA3_CI_HEAD'],
                  mode=env['WPA3_FOLLOW_MODE'], fork=args.published, branch=env['BRANCH'],
                  force=env.get('FORCE') == 'true', source=env.get('UPSTREAM_SOURCE', 'latest'),
                  ref=env.get('GITHUB_REF', ''))
  print('true' if skip else 'false')


if __name__ == '__main__':
  main()
