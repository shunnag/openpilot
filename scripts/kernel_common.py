"""Small, fail-closed helpers shared by kernel follow's read-only stages."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from boot_download import MAX_BOOT_SIZE
from follow_state import dumps, load_json, require

ROOT = Path(__file__).resolve().parents[1]
BUILDER_URL = 'https://github.com/commaai/agnos-builder.git'
KERNEL_URL = 'https://github.com/commaai/agnos-kernel-sdm845.git'


def sha256(data):
  return hashlib.sha256(data).hexdigest()


def read_bytes(path, limit=MAX_BOOT_SIZE):
  path = Path(path)
  require(path.is_file() and not path.is_symlink(), f'not a regular input: {path}')
  with path.open('rb') as stream:
    data = stream.read(limit + 1)
  require(len(data) <= limit, f'input exceeds {limit} bytes: {path}')
  return data


def read_json(path):
  read_bytes(path, 8 * 1024 * 1024)
  return load_json(path)


def write_json(path, value):
  Path(path).write_text(dumps(value))


def run(*args, cwd=None, data=None, env=None):
  return subprocess.run(list(map(str, args)), cwd=cwd, input=data, check=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        env={**os.environ, **(env or {})}).stdout


def git(repo, *args, data=None):
  # Never call on a directory mounted writable by the build container.
  return run('git', '-c', 'core.fsmonitor=', '-c', 'core.hooksPath=/dev/null',
             '-C', repo, *args, data=data,
             env={'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0',
                  'GIT_LFS_SKIP_SMUDGE': '1', 'GIT_LFS_SKIP_PUSH': '1',
                  'GIT_NO_LAZY_FETCH': '0' if os.environ.get('KERNEL_FOLLOW_NETWORK') == '1'
                  and os.environ.get('GITHUB_ACTIONS') == 'true' else '1'})


def git_text(repo, *args):
  return git(repo, *args).decode().strip()


def oid(value):
  require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{40}', value), 'expected full git object id')
  return value


def blob_id(data):
  return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def network_only_in_workflow():
  require(os.environ.get('GITHUB_ACTIONS') == 'true',
          'network is allowed only inside the workflow; use --offline with cached repositories')


def api(path):
  network_only_in_workflow()
  return json.loads(run('gh', 'api', path))


class Gates:
  def __init__(self):
    self.rows = []

  def add(self, gate, ok, detail, kind='integrity'):
    row = {'gate': gate, 'result': 'OK' if ok else 'FAIL', 'detail': str(detail), 'kind': kind}
    self.rows.append(row)
    print(f"{gate}: {row['result']}: {detail}")
    return ok

  def skip(self, gate, detail):
    self.rows.append({'gate': gate, 'result': 'SKIP', 'detail': detail, 'kind': 'advisory'})
    print(f'{gate}: SKIP: {detail}')

  def check(self, gate, function, kind='integrity'):
    try:
      detail = function()
      return self.add(gate, True, detail or 'verified', kind)
    except Exception as error:
      return self.add(gate, False, str(error), kind)

  def failed(self, kind=None):
    return any(row['result'] == 'FAIL' and (kind is None or row['kind'] == kind) for row in self.rows)
