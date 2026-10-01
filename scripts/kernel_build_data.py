#!/usr/bin/env python3
"""Trusted host preparation and bounded reading of build data; never run make.

All git calls are confined to prepare(), before any container is started.
No post-build command uses git, sources shell output, or executes artifacts.
"""
import argparse
import hashlib
import lzma
import os
from pathlib import Path
import posixpath
import re
import shutil
import sys
import tarfile

import bootimg
import kernel_equiv as ke
from kernel_assemble import WIFI_DIRS, wifi_manifest
from kernel_common import (KERNEL_URL, ROOT, git, git_text, network_only_in_workflow,
                           oid, read_bytes, read_json, require, sha256, write_json)
from kernel_gates import config_bytes, normalize_diff, patch_paths, stock_facts


def safe_file(root, relative):
  root = Path(root).resolve()
  path = root / relative
  require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'unsafe artifact path')
  current = path
  while current != root:
    require(not current.is_symlink(), f'symlink in build output: {current}')
    current = current.parent
  return path


def extract_archive(archive, destination):
  destination.mkdir()
  with tarfile.open(archive) as tar:
    require(not any('.git' in Path(member.name).parts for member in tar.getmembers()), 'archive contains .git')
    tar.extractall(destination, filter='data')


def prepare(inputs, candidate_id, work, local_kernel=None):
  require(not work.exists(), 'build work directory must be new')
  work.mkdir(parents=True)
  plan = read_json(inputs / 'plan.json')
  rows = [row for row in plan['matrix']['include'] if row['id'] == candidate_id]
  require(len(rows) == 1, 'unknown candidate id')
  row = rows[0]
  item = read_json(inputs / 'items' / row['item'] / 'input.json')
  candidate = next(c for c in item['discovery']['candidates'] if c['commit'] == row['commit'])
  require(1 <= candidate['full_build_budget'] <= 2, 'invalid reserved full-build budget')
  policy = read_json(ROOT / 'follow/policy.json')
  pre = item['pre'][candidate['commit']]
  require(not pre['integrity_hold'] and not pre['brake'], 'pre-build integrity hold/brake')
  stock = read_bytes(inputs / 'items' / row['item'] / 'stock.img')
  require(sha256(stock) == item['stock_hash'], 'stock input changed')
  recipe_dir = inputs / 'items' / row['item'] / candidate['builder_commit']
  from kernel_gates import k2
  files = {name: read_bytes(recipe_dir / name.replace('/', '_')) for name in (
    *policy['recipe'], 'tools/aarch64-linux-gnu-gcc.tar.gz')}
  k2(files, policy)
  checkout = work / 'host-git'
  if local_kernel:
    git(work, 'clone', '--no-checkout', '--no-hardlinks', local_kernel, checkout)
  else:
    network_only_in_workflow()
    os.environ['KERNEL_FOLLOW_NETWORK'] = '1'
    git(work, 'init', checkout)
    git(checkout, 'remote', 'add', 'origin', KERNEL_URL)
    git(checkout, 'fetch', '--filter=blob:none', '--depth=1', 'origin', oid(candidate['commit']), oid(item['baseline_commit']))
  commit, baseline = oid(candidate['commit']), oid(item['baseline_commit'])
  source = read_bytes(ROOT / 'follow/kernel-patches/source.diff').decode()
  require(sha256(source.encode()) == policy['source_diff_sha256'], 'source.diff changed')
  paths = patch_paths(source)
  proof = {'candidate': commit, 'baseline': baseline, 'candidate_blobs': {}, 'baseline_blobs': {}}
  for label, ref in (('candidate_blobs', commit), ('baseline_blobs', baseline)):
    proof[label] = {path: git_text(checkout, 'rev-parse', f'{ref}:{path}') for path in paths}
  require(proof['candidate_blobs'] == proof['baseline_blobs'] == pre['patched_blobs'], 'patched source files differ from baseline')
  git(checkout, 'read-tree', commit)
  artifacts = work / 'artifacts'
  artifacts.mkdir()
  for name, digest in sorted(policy['patches'].items()):
    patch = read_bytes(ROOT / 'follow/kernel-patches' / name)
    require(sha256(patch) == digest, f'patch hash changed: {name}')
    git(checkout, 'apply', '--cached', '--check', '-', data=patch)
    git(checkout, 'apply', '--cached', '-', data=patch)
    (artifacts / name).write_bytes(patch)
  diff = git(checkout, 'diff', '--cached', '--no-ext-diff', '--no-textconv', '--no-renames', commit, '--').decode()
  require(normalize_diff(diff) == source, 'K6 normalized diff differs')
  proof['source_diff'] = normalize_diff(diff)
  patched_tree = git_text(checkout, 'write-tree')
  # All git ends here. The two export trees are the only source inputs the
  # container can see; host-git is never mounted and can now be removed.
  git(checkout, 'archive', '--format=tar', '--output=' + str(work / 'stock.tar'), commit)
  git(checkout, 'archive', '--format=tar', '--output=' + str(work / 'patched.tar'), patched_tree)
  shutil.rmtree(checkout)
  extract_archive(work / 'stock.tar', work / 'source')
  extract_archive(work / 'patched.tar', work / 'patched')
  with (work / 'stock.tar').open('rb') as source_file, lzma.open(artifacts / 'source.tar.xz', 'wb', preset=6) as dest:
    shutil.copyfileobj(source_file, dest)
  (work / 'stock.tar').unlink()
  (work / 'patched.tar').unlink()
  # Retain only the seven patched files; their directory is never writable by
  # the container. This also saves nearly a GB of runner disk.
  patched_files = work / 'patch-files'
  for path in paths:
    target = safe_file(patched_files, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(safe_file(work / 'patched', path).read_bytes())
  shutil.rmtree(work / 'patched')
  (artifacts / 'SOURCE.txt').write_text(f"Kernel: {commit}\nBranch at discovery: {candidate['branch']}\nBuilder: {candidate['builder_commit']}\nApply the two included patches to source.tar.xz.\n")
  write_json(artifacts / 'patch-proof.json', proof)
  (artifacts / 'source.diff').write_text(source)
  write_json(work / 'build.json', {'candidate': candidate, 'paths': paths, 'item': row['item'],
                                  'replay': item['replay'], 'policy': policy})
  (work / 'stock.img').write_bytes(stock)
  (work / 'key').write_bytes(files['vble-qti.key'])
  (work / 'image-context').mkdir()
  (work / 'image-context/Dockerfile.builder').write_bytes(files['Dockerfile.builder'])
  _, image, _ = ke.split(stock)
  user, host, number, timestamp = ke.banner_identity(image)
  wpa_identity = (user, host, number, timestamp)
  if item['replay'] == '19.9':
    manual = read_bytes(inputs / 'manual/19.9.img')
    wpa_identity = ke.banner_identity(ke.split(manual)[1])
  elif item['replay'] == '19.8':
    wpa_identity = ke.banner_identity(ke.split(read_bytes(inputs / 'manual/19.8.img'))[1])
  else:
    wpa_identity = ('wpa3ci', 'docker', number, timestamp)
  for name, identity in (('stock', (user, host, number, timestamp)), ('wpa3', wpa_identity)):
    write_json(work / f'{name}-identity.json', dict(zip(('user', 'host', 'number', 'timestamp'), identity)))
  write_json(work / 'stock-facts.json', stock_facts(stock))
  print(f'K6: OK: prepared two git archive exports; {len(paths)} pinned patched files')


def object_hashes(source):
  out = source / 'out'
  result = {}
  for path in sorted(out.rglob('*.o')):
    relative = path.relative_to(out).as_posix()
    path = safe_file(out, relative)
    if path.is_file():
      digest = hashlib.sha256()
      with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
          digest.update(chunk)
      result[relative] = digest.hexdigest()
  require(bool(result), 'no object files found')
  return result


def cheap(work):
  source = work / 'source'
  facts = read_json(work / 'stock-facts.json')
  config = read_bytes(safe_file(source, 'out/.config'))
  require(config == config_bytes(facts), 'cheap stock defconfig differs from ikconfig')
  dtbs = []
  for path in (source / 'out/arch/arm64/boot/dts').rglob('*.dtb'):
    path = safe_file(source, path.relative_to(source))
    dtbs.append(sha256(read_bytes(path)))
  require(sorted(dtbs) == facts['dtb_sha256'], 'cheap DTB multiset differs from stock')
  print('K5-cheap: OK: defconfig and DTB multiset')


def snapshot(work, kind):
  artifacts, source = work / 'artifacts', work / 'source'
  for name in ('Image', 'Image-dtb'):
    raw = read_bytes(safe_file(source, 'out/arch/arm64/boot/' + name))
    (artifacts / f'{kind}.{name}').write_bytes(raw)
  (artifacts / f'{kind}.config').write_bytes(read_bytes(safe_file(source, 'out/.config')))
  write_json(work / f'{kind}-objects.json', object_hashes(source))
  if kind == 'stock':
    stock = read_bytes(work / 'stock.img')
    fields = bootimg.parse(stock)
    rebuilt = bootimg.repack(fields['header'], read_bytes(artifacts / 'stock.Image-dtb'), fields['cmdline'], work / 'key')
    (artifacts / 'stock-rebuilt.img').write_bytes(rebuilt)
    ok, why = ke.rebuild_equivalent(stock, rebuilt)
    (artifacts / 'stock-rebuild-report.txt').write_text(f"K5: {'OK' if ok else 'FAIL'}: {'; '.join(why)}\n")
    if not ok:
      print('; '.join(why))
      return 2 if any('cert identity span ends differ' in reason for reason in why) else 1
  return 0


def patch_export(work):
  for path in read_json(work / 'build.json')['paths']:
    source = safe_file(work / 'patch-files', path)
    target = safe_file(work / 'source', path)
    target.write_bytes(read_bytes(source))


def dependencies(out):
  deps = set()
  for prefix in WIFI_DIRS:
    for path in (out / prefix).rglob('.*.o.cmd'):
      text = read_bytes(safe_file(out, path.relative_to(out))).decode()
      match = re.search(r'^deps_[^\n]*:=\s*(.*?)(?:\n\s*\n|\Z)', text, re.M | re.S)
      if match is None:
        # Kbuild also records aggregate relocatable links (wlan.o, cfg80211.o,
        # built-in.o). Their compiled children have their own dependency files.
        require(re.search(r'^cmd_[^\n]*:=.*(?:-ld(?:\.bfd)?\s.*\s-r\s|\bar\s)', text),
                f'unrecognized non-compile command: {path}')
        continue
      require(match is not None, f'unrecognized dependency file: {path}')
      source = re.search(r'^source_[^\n]*:=\s*(.+)$', text, re.M)
      require(source is not None, f'missing source in dependency file: {path}')
      for token in (source[1] + ' ' + match[1].replace('\\\n', ' ')).split():
        if token.startswith('../'):
          token = posixpath.normpath(token[3:])
          require('..' not in Path(token).parts and not token.startswith('/'), 'unsafe dependency')
          deps.add(token)
  require(bool(deps), 'no source dependencies found')
  return sorted(deps)


def manifests(work):
  old, new = read_json(work / 'stock-objects.json'), read_json(work / 'wpa3-objects.json')
  changed = sorted(path for path in old.keys() | new.keys() if old.get(path) != new.get(path))
  out = work / 'source/out'
  wifi = {}
  for path in new:
    if path.startswith(WIFI_DIRS) and Path(path).name != 'built-in.o':
      wifi[path] = sha256(read_bytes(safe_file(out, path + '.stripped')))
  require(bool(wifi), 'empty Wi-Fi object manifest')
  artifacts = work / 'artifacts'
  write_json(artifacts / 'manifests.json', {'rebuilt_objects': changed, 'wifi_objects': wifi,
                                          'computed_in': 'build job; publish cannot rederive from Image'})
  (artifacts / 'rebuilt-objects.txt').write_text('\n'.join(changed) + '\n')
  write_json(artifacts / 'wifi-objects.json', wifi)
  if read_json(work / 'build.json')['replay'] == '19.9':
    (artifacts / 'wifi-deps.txt').write_text('\n'.join(dependencies(out)) + '\n')
  write_json(artifacts / 'stock.json', read_json(work / 'stock-facts.json'))


def finalize(work, result, count):
  artifacts = work / 'artifacts'
  artifacts.mkdir(parents=True, exist_ok=True)
  write_json(artifacts / 'result.json', {'result': result, 'full_builds': count})
  sums = []
  for path in sorted(artifacts.iterdir()):
    if path.name == 'SHA256SUMS':
      continue
    path = safe_file(artifacts, path.name)
    require(path.is_file(), 'unexpected artifact directory')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
      while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
    sums.append(f'{digest.hexdigest()}  {path.name}\n')
  (artifacts / 'SHA256SUMS').write_text(''.join(sums))


def compare_wifi(first, second):
  """Q5: compare artifacts from two independent executions of the same source."""
  a, b = (read_json(path / 'patch-proof.json') for path in (first, second))
  require(a == b, 'Q5 requires the same source and patches in both runs')
  manifests = [wifi_manifest(read_json(path / 'wifi-objects.json')) for path in (first, second)]
  differences = sorted(p for p in manifests[0].keys() | manifests[1].keys()
                       if manifests[0].get(p) != manifests[1].get(p))
  print(f"K8: {'FAIL' if differences else 'OK'}: Q5 independent builds; {len(differences)} differing objects")
  for path in differences:
    print(path)
  return not differences


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('command', choices=('prepare', 'cheap', 'stock', 'wpa3', 'patch', 'manifests', 'finalize', 'compare-wifi'))
  parser.add_argument('--work', type=Path)
  parser.add_argument('--first', type=Path)
  parser.add_argument('--second', type=Path)
  parser.add_argument('--inputs', type=Path)
  parser.add_argument('--id')
  parser.add_argument('--local-kernel', type=Path)
  parser.add_argument('--result', default='failed')
  parser.add_argument('--count', type=int, default=0)
  args = parser.parse_args()
  try:
    if args.command == 'compare-wifi':
      require(args.first and args.second, 'compare-wifi requires --first and --second artifact directories')
      return 0 if compare_wifi(args.first, args.second) else 1
    require(args.work is not None, '--work is required')
    if args.command == 'prepare':
      prepare(args.inputs, args.id, args.work, args.local_kernel)
    elif args.command == 'cheap':
      cheap(args.work)
    elif args.command in ('stock', 'wpa3'):
      return snapshot(args.work, args.command)
    elif args.command == 'patch':
      patch_export(args.work)
    elif args.command == 'manifests':
      manifests(args.work)
    else:
      finalize(args.work, args.result, args.count)
    return 0
  except Exception as error:
    print(f'K*: FAIL: {error}', file=sys.stderr)
    return 1


if __name__ == '__main__':
  sys.exit(main())
