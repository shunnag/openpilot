"""Fast-forward-only state transactions. The worktree is never a build tree."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import tempfile

import follow_state as fs
from kernel_common import ROOT, git, git_text, run


@dataclass
class Commit:
  changed: bool
  state: dict
  head: str
  value: object = None
  dispatch: bool = False


def final_allowlist(work, base):
  """Inspect the committed diff, including modes, not just staged filenames."""
  names = git(work, 'diff', '--no-renames', '--name-status', '-z', base, 'HEAD').decode()
  raw = git(work, 'diff', '--no-renames', '--raw', '-z', base, 'HEAD').decode()
  tokens = raw.rstrip('\0').split('\0') if raw else []
  fs.require(len(tokens) % 2 == 0, 'invalid raw state diff')
  modes = {}
  for header, path in zip(tokens[::2], tokens[1::2]):
    fields = header.split()
    fs.require(len(fields) == 5 and fields[0].startswith(':'), 'invalid raw diff modes')
    fs.require(path not in modes, 'duplicate raw diff path')
    modes[path] = (fields[0][1:], fields[1])
  old = new = ''
  if 'README.md' in modes:
    old = git(work, 'show', f'{base}:README.md').decode()
    new = git(work, 'show', 'HEAD:README.md').decode()
  fs.check_allowlist(names, old, new, modes=modes)
  # A new filename in an existing version directory is not a new build.
  for path in modes:
    if path.startswith('userspace/wpa/'):
      directory = str(Path(path).parent)
      fs.require(not git(work, 'ls-tree', base, '--', directory), 'wpa build directory already exists')


def status_readme(text, state):
  begin, end = '<!-- wpa3-status:begin -->', '<!-- wpa3-status:end -->'
  fs.require(text.count(begin) == text.count(end) == 1, 'README status markers missing/duplicate')
  left, right = text.index(begin) + len(begin), text.index(end)
  fs.require(left <= right, 'README status markers reversed')
  rows = ['\n\n| Automatic release | Status | Tested devices |', '|---|---|---|']
  for version, pin in sorted(state['pins'].items()):
    devices = state['status']['device_tested'].get(pin['release_tag'], {}).get('devices', [])
    status = 'WITHDRAWN; stock revert' if pin['withdrawn'] else 'device-tested' if devices else 'NOT device-tested'
    rows.append(f"| {pin['release_tag']} | {status} | {', '.join(devices) or 'none'} |")
  if not state['pins']:
    rows.append('| none | No automatic kernel pins | none |')
  if state['status']['paused']:
    rows.append('\nAutomatic kernel publishing is paused.')
  return text[:left] + '\n'.join(rows) + '\n\n' + text[right:]


class StateWriter:
  def __init__(self, brakes, mode, run_url, root=ROOT):
    self.root, self.brakes, self.mode, self.run_url = Path(root), brakes, fs.mode_value(mode), run_url
    fs.nonempty(run_url, 'run URL')

  @contextmanager
  def fresh(self):
    git(self.root, 'fetch', '--depth=50', '--no-tags', '--no-recurse-submodules', 'origin', 'wpa3-ci')
    head = git_text(self.root, 'rev-parse', 'FETCH_HEAD')
    with tempfile.TemporaryDirectory(prefix='follow-state-') as tmp:
      work = Path(tmp) / 'state'
      git(self.root, 'worktree', 'add', '--detach', work, head)
      try:
        yield work, head, fs.load(work)
      finally:
        git(self.root, 'worktree', 'remove', '--force', work)

  def read(self, target=None, operation='kernel'):
    with self.fresh() as (work, head, state):
      self.brakes(state, work, target, operation)
      return state, head

  def commit(self, change, key, *, target=None, operation='kernel', readme=False):
    """Re-run change(old_state) -> (facts, result) on each newly fetched head.

    Only this method pushes wpa3-ci. Three attempts include both a changed head
    noticed before push and a non-fast-forward rejection at push time.
    """
    fs.require(self.mode in ('state', 'on'), 'state writes require state/on')
    fs.nonempty(key, 'idempotency key')
    for attempt in range(3):
      with self.fresh() as (work, base, old):
        self.brakes(old, work, target, operation)
        facts, value = change(old)
        if facts.get('pins'):
          fs.require(self.mode == 'on', 'kernel pins require on')
        fs.require(not facts.get('supplicants'), 'supplicant writes need a separately qualified T3 publication path')
        # apply stays pure: read brakes now and pass its fail-closed result.
        self.brakes(old, work, target, operation)
        state = fs.apply(old, facts, brakes=True)
        files = fs.state_files(state)
        if readme:
          files['README.md'] = status_readme((work / 'README.md').read_text(), state).encode()
        changed = []
        for name, data in files.items():
          path = work / name
          if not path.exists() or path.read_bytes() != data:
            fs.require(not path.is_symlink(), 'symlink at state path')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            changed.append(name)
        if not changed:
          return Commit(False, old, base, value)
        # Execute the trusted checkout's validator against data in the worktree.
        run(sys.executable, self.root / 'scripts/pins.py', '--validate-state', '--state-root', work)
        git(work, 'add', '--', *changed)
        message = (f'WPA3 follow: {operation}\n\nWPA3-Follow-Run: {self.run_url}\n'
                   f'WPA3-Follow-Key: {key}\nWPA3-Follow-Mode: {self.mode}\n')
        git(work, '-c', 'user.name=openpilot-wpa3-bot', '-c', 'user.email=shunnag@users.noreply.github.com',
            '-c', 'commit.gpgsign=false', 'commit', '-F', '-', data=message.encode())
        # Re-fetch/re-read immediately before EVERY push, including retries.
        with self.fresh() as (latest_work, latest_head, latest):
          self.brakes(latest, latest_work, target, operation)
          if latest_head != base:
            continue
        final_allowlist(work, base)
        head = git_text(work, 'rev-parse', 'HEAD')
        try:
          git(work, 'push', 'origin', 'HEAD:refs/heads/wpa3-ci')
        except subprocess.CalledProcessError as error:
          detail = (error.stderr or b'').decode(errors='replace')
          if not any(s in detail for s in ('non-fast-forward', 'fetch first', 'stale info')):
            raise
          continue
        dispatch = any(state[name] != old[name] for name in ('pins', 'system_probe', 'supplicants'))
        return Commit(True, state, head, value, dispatch)
    raise ValueError('follow-hold: state push conflict after 3 tries')
