"""Local shell-flow tests: no root, loop mounts, Linux, or real supplicant needed."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

# One executable stub is symlinked under each command name. The real shell and
# wpa_abi.py execute; synthetic ELF headers/readelf output substitute for T0.
# File-based control state avoids sockets, which local sandboxes may prohibit.
# The fake daemon persists sae_pwe in the config and uses real process signals.
STUB = r'''
import json, os, pathlib, signal, sys
base = pathlib.Path(os.environ['T2_FIXTURE'])
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (base / 'commands.jsonl').open('a') as out:
  out.write(json.dumps([name, *args]) + '\n')
mode = os.environ.get('T2_FAILURE', '')
if name == 'sudo':
  os.execvp(args[0], args)
elif name == 'mktemp':
  (base / 'work').mkdir()
  print(base / 'work')
elif name == 'readelf':
  print('(NEEDED) [libc.so.6]\n(FLAGS) BIND_NOW' if args[0] == '-dW' else 'Name: GLIBC_2.17')
elif name == 'ip':
  pass
elif name == 'mount':
  target = pathlib.Path(args[-1])
  if 'loop,ro,noload' in args:
    for directory in ('usr/sbin', 'tmp', 'dev', 'run'):
      (target / directory).mkdir(parents=True, exist_ok=True)
    if mode != 'missing-cli':
      cli = target / 'usr/sbin/wpa_cli'
      cli.touch()
      cli.chmod(0o755)
  if '--bind' in args and target.name == 'run':
    target.rmdir()
    target.symlink_to(args[-2], target_is_directory=True)
  if mode == 'dev-remount' and 'remount,bind,ro' in args and target.name == 'dev':
    sys.exit(1)
elif name == 'umount':
  if mode == 'cleanup' and args[0].endswith('/dev'):
    sys.exit(1)
elif name == 'wpa_cli':
  raise SystemExit('HOST wpa_cli MUST NOT RUN')
elif name == 'chroot':
  root, executable, *options = args
  root = pathlib.Path(root)
  runtime = root.parent / 'run'
  endpoint = runtime / 'ctrl/wpa3test'
  if executable == '/usr/sbin/wpa_supplicant':
    if '-v' in options:
      print('wpa_supplicant v2.10')
      sys.exit(0)
    print('FAKE daemon diagnostic', flush=True)
    if mode == 'startup':
      sys.exit(1)
    # Fail if the harness did not provide the mounts needed by the real client.
    commands = [json.loads(line) for line in (base / 'commands.jsonl').read_text().splitlines()]
    assert ['mount', '-t', 'tmpfs', '-o', 'mode=1777,nosuid,nodev', 'tmpfs', str(root / 'tmp')] in commands
    assert ['mount', '-o', 'remount,bind,ro', str(root / 'dev')] in commands
    value = '0' if 'sae_pwe=0' in (runtime / 'wpa.conf').read_text() else '2'
    endpoint.parent.mkdir(exist_ok=True)
    (runtime / 'value').write_text(value)
    (runtime / 'pid').write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    endpoint.touch()
    try:
      while True: signal.pause()
    finally:
      endpoint.unlink(missing_ok=True)
  else:
    assert executable == '/usr/sbin/wpa_cli' and options[:4] == ['-p', '/run/ctrl', '-i', 'wpa3test']
    if not endpoint.exists(): sys.exit(1)
    local = root / 'tmp' / ('cli-' + str(os.getpid()))
    local.touch()
    try:
      command = ' '.join(options[4:])
      response = 'OK'
      if command == 'ping': response = 'PONG'
      elif command == 'get sae_pwe': response = '9' if mode == 'get' else (runtime / 'value').read_text()
      elif command == 'set sae_pwe 0': (runtime / 'value').write_text('0')
      elif command == 'save_config':
        if mode == 'save': response = 'FAIL'
        else:
          with (runtime / 'wpa.conf').open('a') as out:
            out.write('sae_pwe=' + (runtime / 'value').read_text() + '\n')
      elif command == 'terminate': os.kill(int((runtime / 'pid').read_text()), signal.SIGTERM)
      else: raise AssertionError('unexpected control command: ' + command)
      print(response)
    finally:
      local.unlink(missing_ok=True)
'''


class ChrootShellTests(unittest.TestCase):
  def exercise(self, failure=''):
    with tempfile.TemporaryDirectory(prefix='t2-', dir='/tmp') as tmp:
      base = Path(tmp)
      binaries = base / 'bin'
      binaries.mkdir()
      stub = binaries / 'stub'
      stub.write_text('#!' + sys.executable + '\n' + STUB)
      stub.chmod(0o755)
      for name in ('sudo', 'mount', 'umount', 'chroot', 'wpa_cli', 'ip', 'mktemp', 'readelf'):
        (binaries / name).symlink_to(stub)
      (binaries / 'python3').symlink_to(sys.executable)
      elf = bytearray(64)
      elf[:7], elf[16:20] = b'\x7fELF\x02\x01\x01', b'\x03\x00\xb7\x00'
      for name in ('candidate', 'stock', 'system.raw'):
        (base / name).write_bytes(elf)
      result = subprocess.run(['bash', str(ROOT / 'scripts/wpa_test.sh'),
                               *(str(base / n) for n in ('candidate', 'stock', 'system.raw'))],
                              env={**os.environ, 'PATH': str(binaries) + ':' + os.environ['PATH'],
                                   'T2_FIXTURE': str(base), 'T2_FAILURE': failure},
                              capture_output=True, text=True, timeout=20)
      commands = [json.loads(line) for line in (base / 'commands.jsonl').read_text().splitlines()]
      mounted = [c[-1] for c in commands if c[0] == 'mount' and 'remount,bind,ro' not in c]
      self.assertEqual([c[1] for c in commands if c[0] == 'umount'], list(reversed(mounted)))
      self.assertFalse(any(c[0] == 'wpa_cli' for c in commands), 'host wpa_cli was used')
      self.assertEqual((base / 'work').exists(), failure == 'cleanup')
      if any(c[:4] == ['ip', 'link', 'add', 'wpa3test'] for c in commands):
        delete = commands.index(['ip', 'link', 'delete', 'wpa3test'])
        unmount = next(i for i, c in enumerate(commands) if c[0] == 'umount')
        self.assertLess(delete, unmount)
      return result

  def test_success_with_shared_tmp_and_image_client(self):
    result = self.exercise()
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn('T2: PASS: default 2; saved override 0 survives restart', result.stdout)

  def test_missing_image_client_has_clear_error(self):
    result = self.exercise('missing-cli')
    self.assertNotEqual(result.returncode, 0)
    self.assertIn('missing executable /usr/sbin/wpa_cli', result.stderr)

  def test_readonly_dev_remount_failure_unwinds_partial_setup(self):
    self.assertNotEqual(self.exercise('dev-remount').returncode, 0)

  def test_runtime_failures_dump_log_and_unwind(self):
    for failure in ('startup', 'get', 'save', 'cleanup'):
      with self.subTest(failure=failure):
        result = self.exercise(failure)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FAKE daemon diagnostic', result.stderr)


if __name__ == '__main__':
  unittest.main()
