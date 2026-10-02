#!/usr/bin/env python3
"""T3: synthetic SAE/H2E/PMF associations in an isolated mac80211_hwsim namespace.

Reimplements the association cases from the 2026-09-25 cli_tests.sh work using
only the standard library. No NetworkManager, external netlink module, real
SSID, IP traffic, credentials, or code supplied by a test request.
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time

CASES = (
  ('sae_hnp', 'SAE', 2, 0, 'SAE', 2, None, True, True),
  ('sae_h2e_default', 'SAE', 2, 1, 'SAE', 2, None, True, False),
  ('sae_h2e_optin', 'SAE', 2, 1, 'SAE', 2, 2, True, True),
  ('sae_h2e_disabled', 'SAE', 2, 1, 'SAE', 2, 0, False, False),
  ('wpa2_psk', 'WPA-PSK', 0, 0, 'WPA-PSK', 0, None, True, True),
  ('transition_psk', 'WPA-PSK SAE', 1, 2, 'WPA-PSK', 0, None, True, True),
  ('pmf_required', 'WPA-PSK-SHA256', 2, 0, 'WPA-PSK-SHA256', 2, None, True, True),
  ('pmf_disabled_rejected', 'WPA-PSK', 2, 0, 'WPA-PSK', 0, None, False, False),
)


def control(path, command, work):
  local = work / 'client'
  local.unlink(missing_ok=True)
  with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
    sock.settimeout(2)
    sock.bind(str(local))
    try:
      sock.connect(str(path))
      sock.send(command.encode())
      return sock.recv(65536).decode()
    finally:
      local.unlink(missing_ok=True)


def wait_ready(process, path, work):
  for _ in range(50):
    if process.poll() is not None:
      raise RuntimeError('daemon exited before control interface was ready')
    if path.exists():
      if control(path, 'PING', work).strip() == 'PONG':
        return
    time.sleep(0.1)
  raise RuntimeError('control interface timeout')


def case(binary, kind, spec, ap_iface, sta_iface):
  name, ap_akm, ap_pmf, ap_pwe, sta_akm, sta_pmf, override, expected_candidate, expected_stock = spec
  expected = expected_candidate if kind == 'candidate' else expected_stock
  with tempfile.TemporaryDirectory(prefix='t3-', dir='/tmp') as temporary:
    work = Path(temporary)
    ap_conf, sta_conf = work / 'ap.conf', work / 'sta.conf'
    ap_conf.write_text(f'interface={ap_iface}\ndriver=nl80211\nctrl_interface={work}/ap\n'
                       f'ssid=wpa3-ci-synthetic\nhw_mode=g\nchannel=1\nwpa=2\n'
                       f'wpa_key_mgmt={ap_akm}\nrsn_pairwise=CCMP\nieee80211w={ap_pmf}\n'
                       f'sae_pwe={ap_pwe}\nwpa_passphrase=wpa3-ci-test-only\n')
    global_config = '' if override is None else f'sae_pwe={override}\n'
    sta_conf.write_text(f'ctrl_interface={work}/sta\n' + global_config +
                        'network={\n  ssid="wpa3-ci-synthetic"\n  psk="wpa3-ci-test-only"\n'
                        f'  key_mgmt={sta_akm}\n  ieee80211w={sta_pmf}\n  scan_freq=2412\n}}\n')
    processes = []
    try:
      # Raw logs stay inside the disposable VM and are never published.
      with (work / 'ap.log').open('w') as ap_log, (work / 'sta.log').open('w') as sta_log:
        ap = subprocess.Popen(['hostapd', str(ap_conf)], stdout=ap_log, stderr=subprocess.STDOUT)
        processes.append(ap)
        ap_socket = work / 'ap' / ap_iface
        wait_ready(ap, ap_socket, work)
        for _ in range(50):
          if 'state=ENABLED' in control(ap_socket, 'STATUS', work):
            break
          time.sleep(0.1)
        else:
          raise RuntimeError('AP did not enable')
        sta = subprocess.Popen([str(binary), '-Dnl80211', '-i', sta_iface, '-c', str(sta_conf)],
                               stdout=sta_log, stderr=subprocess.STDOUT)
        processes.append(sta)
        sta_socket = work / 'sta' / sta_iface
        wait_ready(sta, sta_socket, work)
        connected, pmf, akm = False, False, ''
        for _ in range(100):
          if any(p.poll() is not None for p in processes):
            raise RuntimeError('daemon exited during association')
          status = dict(line.split('=', 1) for line in control(sta_socket, 'STATUS', work).splitlines() if '=' in line)
          if status.get('wpa_state') == 'COMPLETED':
            connected = True
            akm = status.get('key_mgmt', '')
            address = status.get('address', '')
            pmf = '[MFP]' in control(ap_socket, 'STA ' + address, work)
            break
          time.sleep(0.2)
        akm_ok = not connected or (('SAE' in akm) if sta_akm == 'SAE' else ('PSK' in akm))
        passed = connected == expected and akm_ok and (not connected or ap_pmf != 2 or pmf)
        return {'name': kind + '/' + name, 'passed': passed, 'connected': connected,
                'expected_connected': expected, 'pmf': pmf}
    finally:
      for process in reversed(processes):
        process.terminate()
        try:
          process.wait(timeout=5)
        except subprocess.TimeoutExpired:
          process.kill()
          process.wait()


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--candidate', type=Path, required=True)
  parser.add_argument('--stock', type=Path, required=True)
  parser.add_argument('--out', type=Path, required=True)
  parser.add_argument('--ap', default='ap0')
  parser.add_argument('--sta', default='sta0')
  args = parser.parse_args()
  results = []
  for kind, binary in (('candidate', args.candidate), ('stock', args.stock)):
    for spec in CASES:
      try:
        result = case(binary, kind, spec, args.ap, args.sta)
      except Exception as error:
        result = {'name': kind + '/' + spec[0], 'passed': False, 'error': type(error).__name__}
      results.append(result)
      print(json.dumps(result), flush=True)
  args.out.write_text(json.dumps({'tests': results, 'passed': all(r['passed'] for r in results)}, indent=2) + '\n')
  return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
  raise SystemExit(main())
