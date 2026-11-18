#!/usr/bin/env python3
"""Maintain nightly notices and follow reports, keyed by branch and stock hash."""
import argparse
from datetime import datetime, timedelta, timezone
import getpass
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile

from follow_state import load

KINDS = ('hold', 'smoke', 'pending', 'follow-hold', 'follow-dryrun', 'revoke-blocked', 'follow-paused', 'local-runner')
# The local runner keeps one rolling issue per subject: a good run closes only
# the failure issue; the token issue closes once expiry is far enough away.
SUBJECTS = ('failure', 'token-expiry')
TOKEN_WARNING = timedelta(days=14)
STAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z')
TOKEN_SHAPE = re.compile(r'github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}')
ADDRESS = r'(?:\d{1,3}(?:\.\d{1,3}){3}|\[[0-9A-Fa-f:.%]+\])'
# Only addresses in network-error shapes; dotted version numbers stay as they are.
NETWORK = ((re.compile(rf'\b((?:tcp|udp)[46]?) {ADDRESS}:(\d+)'), r'\1 <ip>:\2'),
           (re.compile(rf'->{ADDRESS}:(\d+)'), r'-><ip>:\1'),
           (re.compile(rf'\bfrom (?:{ADDRESS}|[0-9A-Fa-f]*:[0-9A-Fa-f:.%]+) port (\d+)'), r'from <ip> port \1'),
           (re.compile(rf'\({ADDRESS}\) port (\d+)'), r'(<ip>) port \1'),
           (re.compile(rf'\bTrying {ADDRESS}:(\d+)'), r'Trying <ip>:\1'))
FAILURE = re.compile(r'^(?:PIN: (?:FAIL|FOLLOW):|(?:G\d+|K\d+(?:\([a-z]\)|[a-z])?|[WPRT]\d+): FAIL:)')
FOLLOW = re.compile(r'^PIN: (?:FOLLOW|KEY): (kernel|probe|wpa) ([0-9a-f]{64}) (.*)$', re.M)


def gh(*args):
  return subprocess.check_output(['gh', *args, '--repo', os.environ['GH_REPO']], text=True).strip()


def local_run():
  return os.environ.get('WPA3_LOCAL_RUN') == '1'


def run_reference():
  """Actions run URL, or a neutral reference for the off-Actions runner."""
  if local_run():
    stamp = os.environ.get('WPA3_LOCAL_RUN_ID', '')
    if not STAMP.fullmatch(stamp):
      stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return f'local run {stamp}'
  return f"https://github.com/{os.environ['GH_REPO']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"


def redacted(text):
  """Keep host paths, user and host names of a local run out of public text."""
  if not local_run():
    return text
  token = os.environ.get('GH_TOKEN', '')
  if len(token) >= 8:
    text = text.replace(token, '<token>')
  text = TOKEN_SHAPE.sub('<token>', text)
  for pattern, replacement in NETWORK:
    text = pattern.sub(replacement, text)
  places = []
  for variable, placeholder in (('RUNNER_TEMP', '<run>'), ('WPA3_WORK_ROOT', '<work>'), ('WPA3_EXPORT_DIR', '<export>'),
                                ('TMPDIR', '<tmp>'), ('HOME', '<home>')):
    value = os.environ.get(variable, '').rstrip('/')
    if len(value) > 1:
      places += [(value, placeholder), (os.path.realpath(value), placeholder)]
  for value, placeholder in sorted(set(places), key=lambda item: -len(item[0])):
    text = text.replace(value, placeholder)
  text = re.sub(r'/(Users|home)/[^/\s]+', r'/\1/<user>', text)
  owner = os.environ.get('GH_REPO', '').split('/')[0].lower()
  host = socket.gethostname()
  names = {host: '<host>', host.split('.')[0]: '<host>'}
  try:
    names[getpass.getuser()] = '<user>'
  except Exception:
    pass
  # The GitHub owner is public already; very short names would match ordinary words.
  for name in sorted((n for n in names if len(n) >= 3 and n.lower() != owner), key=len, reverse=True):
    text = re.sub(r'(?<![\w.-])' + re.escape(name) + r'(?![\w-])', names[name], text, flags=re.I)
  return text


def escaped(text):
  return redacted(text).replace('@', '@\u200b').replace('```', '` ` `')


def utc(value):
  return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def labels_for(kind, branch='', key='', follow_kind='kernel', subject='failure'):
  labels = [f'nightly-{kind}' if kind in ('hold', 'smoke', 'pending') else kind]
  if branch:
    labels.append(f'branch:{branch}')
  if kind == 'follow-hold':
    labels.append(f'follow:{follow_kind}')
  if kind == 'local-runner':
    labels.append(f'local:{subject}')
  if key:
    labels.append(f'stock:{key[:12]}')
  return labels


def listed(labels, key=''):
  flags = [arg for label in labels for arg in ('--label', label)]
  result = json.loads(gh('issue', 'list', '--state', 'open', *flags, '--limit', '1000', '--json', 'number,createdAt,body'))
  # The full key also prevents accidental consolidation of hash-prefix collisions.
  return [i for i in result if not key or f'<!-- wpa3-key:{key} -->' in i.get('body', '')]


def report(kind, branch, key, reason, body, *, existing=None, follow_kind='kernel', subject='failure'):
  labels = labels_for(kind, branch, key, follow_kind, subject)
  existing = listed(labels, key) if existing is None else existing
  numbers = sorted(i['number'] for i in existing)
  prefix = f'nightly {kind}' if kind in ('hold', 'smoke', 'pending') else kind
  scope = branch or (subject if kind == 'local-runner' else '')
  title = escaped(f'{prefix}' + (f' [{scope}]' if scope else '') + f': {reason}')[:200]
  color = 'FBCA04' if kind in ('pending', 'follow-dryrun') or subject == 'token-expiry' else 'B60205'
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


def parse_expiry(value):
  """GitHub sends '2026-12-01 00:00:00 UTC' or a numeric offset such as '-0700'."""
  value = value.strip()
  if value.endswith(' UTC'):
    return datetime.strptime(value[:-4], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
  return datetime.strptime(value, '%Y-%m-%d %H:%M:%S %z').astimezone(timezone.utc)


def token_expiry():
  """Read the expiry header of the token in GH_TOKEN; None when the token has no expiry."""
  # gh sends the token from the environment; it never appears in argv or output.
  output = subprocess.run(['gh', 'api', '--include', 'rate_limit'], capture_output=True, text=True, check=True).stdout
  for line in output.splitlines()[1:]:
    if not line.strip():
      break
    name, _, value = line.partition(':')
    if name.strip().lower() == 'github-authentication-token-expiration':
      return parse_expiry(value)
  return None


def local_runner(args, log, now):
  """Rolling issues of the off-Actions runner: run failures and token expiry."""
  if not local_run():
    raise SystemExit('local-runner issues are only for runs with WPA3_LOCAL_RUN=1')
  run = run_reference()
  subject = 'token-expiry' if args.token_check else args.subject
  issues = listed(labels_for('local-runner', subject=subject))
  if args.token_check:
    expiry = token_expiry()
    if expiry is None or expiry - now > TOKEN_WARNING:
      print('token expiry: ' + (expiry.strftime('%Y-%m-%d %H:%M UTC') if expiry else 'none'))
      close_issues(issues, f'The runner token no longer expires within 14 days.\n\n{run}')
      return 0
    when = expiry.strftime('%Y-%m-%d %H:%M UTC')
    print(f'token expiry: {when}; warning issue opened or updated')
    body = (f'The token used by the local nightly runner expires on {when}. Create a new token with the same '
            'permissions and replace the token file on the runner host before then. With an expired token the '
            f'runner can neither publish nor report.\n\nChecked: {run}\n')
    report('local-runner', '', '', f'runner token expires {when}', body, existing=issues, subject=subject)
    return 0
  if args.close:
    close_issues(issues, f'The local nightly runner completed a run without failures.\n\n{run}')
    return 0
  body = (f'The local nightly runner failed outside the per-branch hold handling. Check the runner host and its '
          f'log; per-branch holds are reported separately.\n\nReason: {args.reason}\nRun: {run}\n\n'
          f'```text\n{log[-45000:]}\n```\n')
  report('local-runner', '', '', args.reason, body, existing=issues, subject=subject)
  return 0


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
  parser.add_argument('--subject', choices=SUBJECTS, default='failure', help='local-runner issue subject')
  parser.add_argument('--token-check', action='store_true',
                      help='local-runner: warn when the GH_TOKEN token expires within 14 days')
  args = parser.parse_args(argv)
  if args.kind in ('hold', 'smoke', 'pending') and not args.branch:
    parser.error('--branch is required for nightly notices')
  if args.key and not re.fullmatch('[0-9a-f]{64}', args.key):
    parser.error('--key must be a full SHA-256')
  if args.kind != 'local-runner' and (args.token_check or args.subject != 'failure'):
    parser.error('--subject and --token-check are only for local-runner')
  log = args.log.read_text(errors='replace') if args.log and args.log.exists() else 'No log was captured.'
  # Redact the whole log before any slice, so a cut never splits a path or token.
  log = redacted(log)
  if args.kind == 'local-runner':
    return local_runner(args, log, utc(args.now) if args.now else datetime.now(timezone.utc))
  follow = FOLLOW.search(log)
  key = args.key or (follow[2] if follow and not args.close else '')
  follow_kind = follow[1] if follow else args.follow_kind
  # Dryrun and pause are single rolling reports/mirrors, independent of stock.
  if args.kind in ('follow-dryrun', 'follow-paused'):
    key = args.branch = ''
  issues = listed(labels_for(args.kind, args.branch, key, follow_kind), key)
  run_url = run_reference()
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
