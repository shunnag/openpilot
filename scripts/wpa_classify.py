#!/usr/bin/env python3
"""W1-W3: signed Ubuntu archive identity and conservative Debian source delta."""
import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request

from system_probe import require, sha_file

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = '2:2.10-21ubuntu0.4'
SNAPSHOT = '20260925T120000Z'
KEYRING = Path('/usr/share/keyrings/ubuntu-archive-keyring.gpg')


@dataclass(frozen=True)
class DebianFile:
  data: bytes
  mode: int

  def decode(self):
    return self.data.decode()


def paragraphs(text):
  result = []
  for stanza in text.strip().split('\n\n'):
    fields, key = {}, None
    for line in stanza.splitlines():
      if line.startswith((' ', '\t')) and key:
        fields[key] += '\n' + line[1:]
      elif ': ' in line or line.endswith(':'):
        key, value = line.split(':', 1)
        require(key not in fields, 'duplicate Debian field')
        fields[key] = value.strip()
    if fields:
      result.append(fields)
  return result


def fetch(url, path):
  require(url.startswith('https://'), 'HTTPS required')
  with urllib.request.urlopen(url, timeout=120) as stream, path.open('wb') as out:
    while data := stream.read(1024 * 1024):
      out.write(data)


def checksums(value):
  result = {}
  for line in value.splitlines():
    if not line.strip():
      continue
    digest, size, name = line.split()
    require(re.fullmatch('[0-9a-f]{64}', digest) and size.isdigit(), 'invalid signed checksum')
    require(name not in result and not PurePosixPath(name).is_absolute() and '..' not in name.split('/'),
            'invalid archive path')
    result[name] = (digest, int(size))
  return result


def verify_file(path, identity):
  require(path.stat().st_size == identity[1] and sha_file(path) == identity[0], f'hash/size mismatch: {path.name}')


def signed_release(inrelease, keyring, gpgv='gpgv'):
  # Verified output only, never a hand-stripped or artifact-supplied Release.
  with tempfile.TemporaryDirectory(prefix='wpa-gpgv-') as tmp:
    clear = Path(tmp) / 'Release'
    try:
      subprocess.run([gpgv, '--homedir', tmp, '--keyring', str(keyring.resolve()), '--output', str(clear),
                      str(inrelease.resolve())], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      if not clear.exists():
        # Some gpgv builds (including Homebrew 2.5.24) verify successfully but
        # ignore --output. Require gpgv success AND a second valid signature
        # from gpg, using only the same keyring and an isolated home/config.
        verified = subprocess.run(['gpg', '--no-options', '--batch', '--homedir', tmp,
                                   '--no-default-keyring', '--keyring', str(keyring.resolve()),
                                   '--no-auto-key-retrieve', '--status-fd', '1', '--output', str(clear),
                                   '--decrypt', str(inrelease.resolve())], check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        require(any(line.startswith(b'[GNUPG:] VALIDSIG ') for line in verified.stdout.splitlines()),
                'W1: gpg output has no valid signature')
    except subprocess.CalledProcessError as error:
      detail = (error.stderr or b'gpgv failed').decode(errors='replace').strip()
      raise ValueError('W1: ' + detail) from error
    fields = paragraphs(clear.read_text())[0]
  require(fields.get('Origin') == 'Ubuntu' and fields.get('Codename') == 'noble', 'not Ubuntu noble')
  require(fields.get('Suite') in ('noble-updates', 'noble-security'), 'unexpected Ubuntu pocket')
  return checksums(fields['SHA256'])


def deb_member(deb, name):
  """Read a .deb without extracting paths or running maintainer scripts (also on macOS)."""
  data = deb.read_bytes()
  require(data.startswith(b'!<arch>\n'), 'invalid deb archive')
  position = 8
  while position < len(data):
    header = data[position:position + 60]
    require(len(header) == 60 and header[58:] == b'`\n', 'invalid ar header')
    size = int(header[48:58])
    member = header[:16].decode().strip().rstrip('/')
    body = data[position + 60:position + 60 + size]
    require(len(body) == size, 'truncated deb')
    if member.startswith('data.tar'):
      if member.endswith('.zst'):
        body = subprocess.run(['zstd', '-dc'], input=body, check=True, capture_output=True).stdout
      with tarfile.open(fileobj=io.BytesIO(body), mode='r:*') as tar:
        matches = [m for m in tar if m.name.removeprefix('./') == name]
        require(len(matches) == 1 and matches[0].isfile(), 'missing/nonregular deb member: ' + name)
        return tar.extractfile(matches[0]).read()
    position += 60 + size + size % 2
  raise ValueError('missing deb data archive')


def debian_files(tar_path):
  with tarfile.open(tar_path, 'r:*') as tar:
    files = {}
    for member in tar:
      name = member.name.removeprefix('./')
      require(name.startswith('debian/') or name == 'debian', 'non-Debian source delta')
      require('..' not in name.split('/') and not member.issym() and not member.islnk(), 'unsafe Debian tar member')
      if member.isfile():
        require(name not in files, 'duplicate Debian tar member')
        files[name] = DebianFile(tar.extractfile(member).read(), member.mode)
    return files


def w2(version, orig_sha, policy):
  require(re.fullmatch(policy['version_regex'], version), 'W2: unsupported Ubuntu version (native +agnos holds)')
  require(orig_sha == policy['orig_tarball_sha256'], 'W2: orig tarball changed')


def w3(reference, candidate):
  changed = sorted(k for k in set(reference) | set(candidate) if reference.get(k) != candidate.get(k))
  for name in changed:
    require(name == 'debian/changelog' or name.startswith('debian/patches/'), 'W3: changed ' + name)
    require(not (name.startswith('debian/patches/') and name not in candidate), 'W3: removed Ubuntu patch ' + name)
  def series(files):
    return [line.split()[0] for line in files['debian/patches/series'].decode().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]
  old, new = series(reference), series(candidate)
  require(set(old) <= set(new), 'W3: removed patch from series')
  require([name for name in new if name in old] == old, 'W3: reordered Ubuntu patches')
  return changed


def one(rows, package, version, arch=None):
  found = [row for row in rows if row.get('Package') == package and row.get('Version') == version
           and (arch is None or row.get('Architecture') == arch)]
  require(len(found) == 1, f'archive version unavailable/ambiguous: {package} {version}')
  return found[0]


def classify(directory, stock_sha, version, keyring, policy, reference_dir=None):
  signed = signed_release(directory / 'InRelease', keyring)
  sources_path = directory / 'Sources-noble-updates-main.xz'
  packages_path = directory / 'pkgs-arm64.xz'
  verify_file(sources_path, signed['main/source/Sources.xz'])
  verify_file(packages_path, signed['main/binary-arm64/Packages.xz'])
  source = one(paragraphs(lzma.decompress(sources_path.read_bytes()).decode()), 'wpa', version)
  package = one(paragraphs(lzma.decompress(packages_path.read_bytes()).decode()), 'wpasupplicant', version, 'arm64')
  sums = checksums(source['Checksums-Sha256'])
  w2(version, sums['wpa_2.10.orig.tar.xz'][0], policy)
  debs = [path for path in directory.glob('*.deb') if sha_file(path) == package['SHA256']]
  require(len(debs) >= 1, 'W1: no stock deb with signed hash')
  verify_file(debs[0], (package['SHA256'], int(package['Size'])))
  binary = deb_member(debs[0], 'usr/sbin/wpa_supplicant')
  require(hashlib.sha256(binary).hexdigest() == stock_sha, 'W1: stock binary differs from Ubuntu')
  suffix = version.split(':')[-1]
  dsc_name, delta_name = f'wpa_{suffix}.dsc', f'wpa_{suffix}.debian.tar.xz'
  for name in (dsc_name, delta_name):
    verify_file(directory / name, sums[name])
  # Compare the descriptor's hashes to signed Sources, rather than trusting its text.
  descriptors = [row for row in paragraphs((directory / dsc_name).read_text()) if row.get('Source') == 'wpa']
  require(len(descriptors) == 1, 'W1: missing/ambiguous source descriptor')
  dsc = descriptors[0]
  require(dsc.get('Version') == version, 'W1: descriptor version differs')
  dsc_sums = checksums(dsc['Checksums-Sha256'])
  require(all(sums.get(n) == identity for n, identity in dsc_sums.items()), 'W1: descriptor checksum differs')
  reference_dir = reference_dir or directory
  reference_delta = reference_dir / 'wpa_2.10-21ubuntu0.4.debian.tar.xz'
  # Reference tarball is independently pinned, including in offline mode.
  require(sha_file(reference_delta) == policy['reference_debian_sha256'], 'W3: reference Debian tar changed')
  candidate, reference = debian_files(directory / delta_name), debian_files(reference_delta)
  changed = w3(reference, candidate)
  changelog = candidate['debian/changelog'].decode()
  require(changelog.startswith(f'wpa ({version}) '), 'W1: source changelog version differs')
  date = re.search(r'^ -- .+?  (.+)$', changelog, re.M)
  require(date is not None, 'missing changelog date')
  return {'schema': 1, 'W1': 'PASS', 'W2': 'PASS', 'W3': 'PASS', 'version': version,
          'stock_wpa_sha256': stock_sha, 'dsc_sha256': sums[dsc_name][0], 'changelog_date': date[1],
          'source_directory': source['Directory'], 'source_files': sums, 'debian_changed': changed,
          'snapshot': policy['snapshot'], 'base_image': policy['base_image']}


def download_archive(directory, base, pocket, version, keyring):
  directory.mkdir(parents=True, exist_ok=True)
  fetch(f'{base}/dists/{pocket}/InRelease', directory / 'InRelease')
  sums = signed_release(directory / 'InRelease', keyring)
  for local, remote in (('Sources-noble-updates-main.xz', 'main/source/Sources.xz'),
                        ('pkgs-arm64.xz', 'main/binary-arm64/Packages.xz')):
    fetch(f'{base}/dists/{pocket}/{remote}', directory / local)
    verify_file(directory / local, sums[remote])
  source = one(paragraphs(lzma.decompress((directory / 'Sources-noble-updates-main.xz').read_bytes()).decode()), 'wpa', version)
  package = one(paragraphs(lzma.decompress((directory / 'pkgs-arm64.xz').read_bytes()).decode()), 'wpasupplicant', version, 'arm64')
  fetch(f"{base}/{package['Filename']}", directory / 'stock.deb')
  verify_file(directory / 'stock.deb', (package['SHA256'], int(package['Size'])))
  for name, identity in checksums(source['Checksums-Sha256']).items():
    fetch(f"{base}/{source['Directory']}/{name}", directory / name)
    verify_file(directory / name, identity)


def online(directory, version, keyring):
  errors = []
  # The live signed archive first; an old release branch may need Launchpad's date.
  choices = [('https://ports.ubuntu.com/ubuntu-ports', p) for p in ('noble-updates', 'noble-security')]
  for base, pocket in choices:
    try:
      download_archive(directory, base, pocket, version, keyring)
      return
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
      errors.append(str(error))
  query = urllib.parse.urlencode({'ws.op': 'getPublishedSources', 'source_name': 'wpa', 'exact_match': 'true',
                                 'version': version, 'distro_series': 'https://api.launchpad.net/1.0/ubuntu/noble'})
  with urllib.request.urlopen('https://api.launchpad.net/1.0/ubuntu/+archive/primary?' + query, timeout=60) as response:
    rows = json.load(response)['entries']
  for row in rows:
    if row.get('source_package_version') != version or row.get('pocket') not in ('Updates', 'Security'):
      continue
    published = datetime.fromisoformat(row['date_published']).astimezone(timezone.utc) + timedelta(days=1)
    stamp = published.strftime('%Y%m%dT%H%M%SZ')
    try:
      download_archive(directory, f'https://snapshot.ubuntu.com/ubuntu/{stamp}', 'noble-' + row['pocket'].lower(), version, keyring)
      return
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
      errors.append(str(error))
  raise ValueError('W1: no verified Ubuntu archive: ' + '; '.join(errors))


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--stock-sha', required=True)
  parser.add_argument('--dpkg-version', required=True)
  parser.add_argument('--offline', type=Path)
  parser.add_argument('--work', type=Path)
  parser.add_argument('--keyring', type=Path)
  parser.add_argument('--out', type=Path)
  args = parser.parse_args()
  try:
    policy = json.loads((ROOT / 'follow/policy.json').read_text())['wpa']
    require(re.fullmatch(policy['version_regex'], args.dpkg_version), 'W2: unsupported version; hold')
    directory = args.offline or args.work
    require(directory is not None, '--work or --offline required')
    keyring = args.keyring or (directory / 'ubuntu-archive-keyring.gpg' if args.offline else KEYRING)
    if not args.offline:
      online(directory, args.dpkg_version, keyring)
      reference = directory / 'reference'
      download_archive(reference, f"https://snapshot.ubuntu.com/ubuntu/{policy['snapshot']}", 'noble-updates', REFERENCE, keyring)
    else:
      reference = directory
    result = classify(directory, args.stock_sha, args.dpkg_version, keyring, policy, reference)
    if args.out:
      args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0
  except Exception as error:
    print(f'WPA: HOLD: {error}', file=sys.stderr)
    return 1


if __name__ == '__main__':
  sys.exit(main())
