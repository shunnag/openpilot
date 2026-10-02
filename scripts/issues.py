#!/usr/bin/env python3
"""Maintain nightly notices and follow reports, keyed by branch and stock hash."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from follow_state import load

KINDS = ('hold', 'smoke', 'pending', 'follow-hold', 'follow-dryrun', 'revoke-blocked', 'follow-paused')
FAILURE = re.compile(r'^(?:PIN: (?:FAIL|FOLLOW):|(?:G\d+|K\d+(?:\([a-z]\)|[a-z])?|[WPRT]\d+): FAIL:)')
FOLLOW = re.compile(r'^PIN: (?:FOLLOW|KEY): (kernel|probe|wpa) ([0-9a-f]{64}) (.*)$', re.M)


def gh(*args):
  return subprocess.check_output(['gh', *args, '--repo', os.environ['GH_REPO']], text=True).strip()


def escaped(text):
  return text.replace('@', '@\u200b').replace('```', '` ` `')


def utc(value):
  return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def labels_for(kind, branch='', key='', follow_kind='kernel'):
  labels = [f'nightly-{kind}' if kind in ('hold', 'smoke', 'pending') else kind]
  if branch:
    labels.append(f'branch:{branch}')
  if kind == 'follow-hold':
    labels.append(f'follow:{follow_kind}')
  if key:
    labels.append(f'stock:{key[:12]}')
  return labels


def listed(labels, key=''):
  flags = [arg for label in labels for arg in ('--label', label)]
  result = json.loads(gh('issue', 'list', '--state', 'open', *flags, '--limit', '1000', '--json', 'number,createdAt,body'))
  # The full key also prevents accidental consolidation of hash-prefix collisions.
  return [i for i in result if not key or f'<!-- wpa3-key:{key} -->' in i.get('body', '')]


def report(kind, branch, key, reason, body, *, existing=None, follow_kind='kernel'):
  labels = labels_for(kind, branch, key, follow_kind)
  existing = listed(labels, key) if existing is None else existing
  numbers = sorted(i['number'] for i in existing)
  prefix = f'nightly {kind}' if kind in ('hold', 'smoke', 'pending') else kind
  title = escaped(f'{prefix}' + (f' [{branch}]' if branch else '') + f': {reason}')[:200]
  color = 'FBCA04' if kind in ('pending', 'follow-dryrun') else 'B60205'
  for label in labels:
    gh('label', 'create', label, '--color', '1D76DB' if label.startswith('branch:') else color,
       '--description', f'WPA3 {label}', '--force')
  with tempfile.TemporaryDirectory(prefix='nightly-issue-') as directory:
    path = Path(directory) / 'body.md'
    path.write_text((f'<!-- wpa3-key:{key} -->\n\n' if key else '') + escaped(body))
    if numbers:
      gh('issue', 'edit', str(numbers[0]), '--title', title, '--body-file', str(path))
      close_issues([i for i in existing if i['number'] != numbers[0]], f'Consolidated into #{numbers[0]}.')
    else:
      flags = [arg for label in labels for arg in ('--label', label)]
      gh('issue', 'create', '--title', title, *flags, '--body-file', str(path))


def close_issues(issues, comment):
  for number in sorted(i['number'] for i in issues):
    gh('issue', 'close', str(number), '--comment', escaped(comment))


def pending_hold(issues, attempt, now):
  if attempt and attempt['result'] in ('held', 'risk_held'):
    return attempt['reason']
  if not issues:
    return ''
  start = min(utc(i['createdAt']) for i in issues)
  if attempt and attempt.get('deferred_until'):
    start = max(start, utc(attempt['deferred_until']))
  if now >= start + timedelta(hours=48):
    return 'follow pending for 48 hours without publication'
  return ''


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('kind', choices=KINDS)
  parser.add_argument('--branch', default='')
  parser.add_argument('--key', default='')
  parser.add_argument('--follow-kind', choices=('kernel', 'probe', 'wpa'), default='kernel')
  parser.add_argument('--close', action='store_true')
  parser.add_argument('--upstream', default='unknown')
  parser.add_argument('--reason', default='workflow failure')
  parser.add_argument('--log', type=Path)
  parser.add_argument('--now', help='UTC timestamp for deterministic tests')
  args = parser.parse_args(argv)
  if args.kind in ('hold', 'smoke', 'pending') and not args.branch:
    parser.error('--branch is required for nightly notices')
  if args.key and not re.fullmatch('[0-9a-f]{64}', args.key):
    parser.error('--key must be a full SHA-256')
  log = args.log.read_text(errors='replace') if args.log and args.log.exists() else 'No log was captured.'
  follow = FOLLOW.search(log)
  key = args.key or (follow[2] if follow and not args.close else '')
  follow_kind = follow[1] if follow else args.follow_kind
  # Dryrun and pause are single rolling reports/mirrors, independent of stock.
  if args.kind in ('follow-dryrun', 'follow-paused'):
    key = args.branch = ''
  issues = listed(labels_for(args.kind, args.branch, key, follow_kind), key)
  run_url = f"https://github.com/{os.environ['GH_REPO']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
  if args.close:
    message = f'Nightly [{args.branch}] succeeded for upstream {args.upstream}.' if args.branch else f'{args.kind} resolved.'
    close_issues(issues, f'{message}\n\n{run_url}')
    return 0
  reasons = [line for line in log.splitlines() if FAILURE.match(line)]
  reason = next((line for line in reasons if ': FAIL:' in line), next(iter(reasons), args.reason))
  status = {'hold': 'Publication held; no new nightly was published.',
            'smoke': 'Installer smoke test failed; published branch is retained.',
            'pending': 'Waiting for automatic follow; no new nightly was published.',
            'revoke-blocked': 'Withdrawal blocked; owner action is required.',
            'follow-paused': 'Automatic kernel publishing is paused. This issue is an authoritative brake.',
            'follow-hold': 'Automatic follow held; see gate evidence below.',
            'follow-dryrun': 'Dryrun report; nothing was published.'}[args.kind]
  detail = ''
  held = ''
  if args.kind == 'pending':
    if not key:
      parser.error('pending requires --key or a PIN: FOLLOW log line')
    state = load()
    attempts = state['status']['wpa_attempts'] if follow_kind == 'wpa' else state['status']['attempts']
    attempt = attempts.get(key)
    held = pending_hold(issues, attempt, utc(args.now) if args.now else datetime.now(timezone.utc))
    if not held and listed(labels_for('hold', args.branch, key), key):
      held = 'follow previously escalated; awaiting successful publication'
    if attempt and attempt.get('deferred_until'):
      detail = f"\nDeferred until: {attempt['deferred_until']}\n"
  body = f'{status}\n\nBranch: `{args.branch}`\nUpstream: `{args.upstream}`\nRun: {run_url}\n{detail}\n```text\n{log[-45000:]}\n```\n'
  if held:
    report('hold', args.branch, key, held, f'Publication held: {held}\n\n' + body)
    close_issues(issues, f'Escalated to nightly-hold: {held}\n\n{run_url}')
    print(f'PIN: FAIL: {held}')
    return 1
  report(args.kind, args.branch, key, reason, body, existing=issues, follow_kind=follow_kind)
  if args.kind == 'hold' and key:
    close_issues(listed(labels_for('pending', args.branch, key), key),
                 f'Escalated to nightly-hold: {reason}\n\n{run_url}')
  return 0


if __name__ == '__main__':
  sys.exit(main())
