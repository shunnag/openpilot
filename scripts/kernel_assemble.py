#!/usr/bin/env python3
"""Publish-side verification and signing. Artifacts are data, never executed.

This part has no publication implementation. Images and provenance stay local.
"""
import argparse
from datetime import datetime, timezone
import lzma
from pathlib import Path
import re
import sys

import bootimg
import kernel_equiv as ke
from boot_download import MAX_BOOT_SIZE
from kernel_common import ROOT, Gates, read_bytes, read_json, require, sha256, write_json
from kernel_gates import k12, patch_paths, stock_facts

WIFI_DIRS = ('drivers/staging/qcacld-3.0/', 'drivers/staging/qca-wifi-host-cmn/',
             'drivers/staging/fw-api/', 'net/wireless/', 'net/mac80211/')


def stock_rebuild(stock, image_dtb, key):
  fields = bootimg.parse(stock)
  rebuilt = bootimg.repack(fields['header'], image_dtb, fields['cmdline'], key)
  ok, reasons = ke.rebuild_equivalent(stock, rebuilt)
  require(ok, '; '.join(reasons))
  return rebuilt


def k6(proof, pre, patch_dir, policy):
  for name, digest in policy['patches'].items():
    require(sha256(read_bytes(patch_dir / name)) == digest, f'patch bytes changed: {name}')
  source = read_bytes(patch_dir / 'source.diff')
  require(sha256(source) == policy['source_diff_sha256'], 'policy source.diff mismatch')
  require(proof['source_diff'] == source.decode(), 'normalized source diff differs')
  paths = patch_paths(source.decode())
  require(set(proof['candidate_blobs']) == set(paths) == set(proof['baseline_blobs']), 'patched blob path set differs')
  require(proof['candidate_blobs'] == proof['baseline_blobs'] == pre['patched_blobs'], 'patched file blob ids changed')
  require(not set(paths) & set(pre['diff']['paths']), 'K3 diff contains patched paths')
  require(proof['candidate'] == pre['diff']['candidate'] and proof['baseline'] == pre['diff']['baseline'], 'proof source mismatch')
  require(all(re.fullmatch(r'[0-9a-f]{40}', blob) for blob in proof['candidate_blobs'].values()), 'invalid blob ids')
  return 'patch bytes, normalized diff and seven baseline/candidate blobs agree'


def k7(stock_image, wpa_image):
  # 0001 adds the Kconfig symbol itself. In the actual 19.8/19.9 stocks it is
  # absent, rather than spelled '# ... is not set' (DESIGN's shorthand).
  delta = ke.ikconfig_delta(stock_image, wpa_image)
  require(delta in ({'CONFIG_WLAN_FEATURE_SAE': ('n', 'y')},
                    {'CONFIG_WLAN_FEATURE_SAE': (None, 'y')}), 'config delta must be SAE only')
  require(b'# CONFIG_MODULE_SIG_FORCE is not set\n' in ke.ikconfig(wpa_image), 'MODULE_SIG_FORCE must be unset')
  return 'only WLAN_FEATURE_SAE changed; MODULE_SIG_FORCE unset'


def object_paths(values):
  require(isinstance(values, list) and len(values) == len(set(values)), 'invalid/duplicate object list')
  for value in values:
    require(isinstance(value, str) and not value.startswith('/') and '..' not in Path(value).parts
            and value.endswith('.o'), f'invalid object path: {value}')
  return set(values)


def k7b(changed, allowed):
  changed, allowed = object_paths(changed), object_paths(allowed)
  require(changed and allowed, 'empty rebuilt-object set/reference')
  unexpected = sorted(changed - allowed)
  require(not unexpected, f'unexpected rebuilt objects: {unexpected}')
  return f'{len(changed)} rebuilt objects within reviewed reference (computed in the build job)'


def wifi_manifest(manifest):
  require(isinstance(manifest, dict) and bool(manifest), 'empty Wi-Fi object manifest')
  object_paths(list(manifest))
  for path, digest in manifest.items():
    require(path.startswith(WIFI_DIRS) and Path(path).name != 'built-in.o', 'unexpected Wi-Fi object path')
    require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest), 'invalid object hash')
  return manifest


def ondevice_selfcheck(manual, images):
  require(len(images) == len(manual) and bool(images), 'all manual pin images are required')
  for version, pin in manual.items():
    image = images[version]
    require(sha256(image) == pin['boot']['hash_raw'] and len(image) == pin['boot']['size'], 'manual image hash/size mismatch')
    require(bootimg.ondevice_hash(image) == pin['boot']['ondevice_hash'], 'ondevice_hash self-check failed')
  return 'ondevice_hash self-check passed for both manual pins'


def image_checks(stock, image, public, policy, *, revert=False):
  original, fields = bootimg.parse(stock), bootimg.parse(image)
  require(len(image) <= MAX_BOOT_SIZE, 'image exceeds boot partition capacity')
  for name in (*bootimg.FIELDS, 'name'):
    if name != 'kernel_size':
      require(original[name] == fields[name], f'boot header field changed: {name}')
  require(re.fullmatch(re.escape(original['cmdline']) + r' wpa3\.sae=[1-9][0-9]*', fields['cmdline']), 'invalid tagged cmdline')
  require(bootimg.pubkey_sha256(public) == policy['vble_public_key_sha256'], 'wrong signing key')
  require(bootimg.verify(image, public), 'signature failed')
  _, stock_image, stock_chain = ke.split(stock)
  _, wpa_image, chain = ke.split(image)
  require(chain == stock_chain, 'DTB chain must preserve exact stock bytes and order')
  layout, stock_layout = ke.image_layout(wpa_image), ke.image_layout(stock_image)
  for field in ('header_offset', 'text_offset', 'flags'):
    require(layout[field] == stock_layout[field], f'Image layout changed: {field}')
  if revert:
    require(fields['kernel'] == original['kernel'], 'revert kernel bytes changed')
  else:
    require(ke.native_sae(stock)[0] == 'none', 'stock has SAE markers')
    require(ke.native_sae(image)[0] == 'all' and ke.has_rsnxe(image), 'missing SAE/RSNXE markers')
  return {'hash_raw': sha256(image), 'ondevice_hash': bootimg.ondevice_hash(image),
          'size': len(image), 'layout': layout}


def compress_checked(image):
  # Python liblzma's preset 9 is the single-threaded xz -9 -T1 encoder.
  compressed = lzma.compress(image, format=lzma.FORMAT_XZ, preset=9)
  decoder = lzma.LZMADecompressor()
  raw = decoder.decompress(compressed, max_length=MAX_BOOT_SIZE + 1)
  require(raw == image and decoder.eof and not decoder.unused_data, 'xz round-trip failed')
  return compressed


def dry_tags(state, replay=None, release_names=()):
  from follow_state import allocate_tag
  if replay in ('19.9', '19.8'):
    # Deliberately reuse the historical number ONLY in an artifact-only replay.
    return (3 if replay == '19.9' else 2), 'historical replay tag; never reserved or published'
  number = allocate_tag(state, release_names)
  return number, 'dryrun allocation proposal; no reservation or state mutation'


def select_candidate(candidates, results):
  require(set(results) == {candidate['commit'] for candidate in candidates}, 'missing candidate result; uniqueness unresolved')
  reproduced = [c for c in candidates if results[c['commit']]['reproduced']]
  require(reproduced, 'no candidate reproduced stock')
  if len({c['tree'] for c in reproduced}) == 1:
    return reproduced[0]
  oracles = [c for c in reproduced if c['oracle']]
  require(bool(oracles), 'multiple reproducing trees without an oracle gitlink')
  return oracles[0]


def replay_check(reference, assembled, number, key):
  """Rebuild equivalence with only the final, single SAE tag renumbered.

  Every other cmdline byte (including whitespace) must match the manual boot.
  Keep this replay-only normalization out of the stock rebuild comparator.
  """
  original = bootimg.parse(reference)['cmdline']
  tokens = list(re.finditer(r'(?<!\S)wpa3\.sae=\S*', original))
  require(len(tokens) == 1 and re.search(r' wpa3\.sae=[1-9][0-9]*$', original),
          'manual replay must have exactly one final positive SAE tag')
  tag = f'wpa3.sae={number}'
  expected = original[:tokens[0].start()] + tag
  require(bootimg.parse(assembled)['cmdline'] == expected, 'replay cmdline differs beyond expected SAE tag')
  normalized = bootimg.with_tag(reference, tag, key)
  same, why = ke.rebuild_equivalent(normalized, assembled)
  require(same, '; '.join(why))
  return ('assembled WPA3 image rebuild-equivalent to device-tested manual image; '
          f'{tokens[0].group()} -> {tag}; ' + '; '.join(why))


def assemble(stock, rebuilt_kernel, wpa_image, key, policy, number, manual, manual_images,
             *, proof=None, pre=None, manifests=None, reference_dir=None, baseline_release=None,
             status=None, auto_pins=None, replay_image=None, patch_dir=ROOT / 'follow/kernel-patches',
             now=None, local=False):
  # wpa_image includes the AGNOS UNCOMPRESSED_IMG wrapper, extracted from
  # Image-dtb or a boot image. The build's raw arm64 Image is not a boot payload.
  gates = Gates()
  facts = {}
  fields = bootimg.parse(stock)
  _, stock_image, chain = ke.split(stock)
  public = bootimg._openssl('rsa', '-in', key, '-pubout')
  rebuilt = None
  def compare():
    nonlocal rebuilt
    rebuilt = stock_rebuild(stock, rebuilt_kernel, key)
    return 'rebuild equivalence re-derived from stock and rebuilt Image-dtb bytes'
  gates.check('K5', compare)
  if proof is None and local:
    gates.skip('K6', 'local Mac artifact check; no build-job patch proof supplied')
  else:
    gates.check('K6', lambda: k6(proof, pre, patch_dir, policy))
  gates.check('K7', lambda: k7(stock_image, wpa_image))
  reference_dir = reference_dir or ROOT / 'follow/reference'
  prefix = reference_dir / str(baseline_release)
  allowed_path = Path(str(prefix) + '.rebuilt-objects.txt')
  wifi_path = Path(str(prefix) + '.wifi-objects.json')
  if manifests is None and local:
    gates.skip('K7b', 'TODO Q1: Mac replay has no CI rebuilt-object manifest')
    gates.skip('K8', 'TODO Q5: compare two CI builds before qualifying object determinism')
  else:
    gates.check('K7b-format', lambda: object_paths(manifests['rebuilt_objects']) and 'build-job object set parsed')
    if allowed_path.exists():
      gates.check('K7b', lambda: k7b(manifests['rebuilt_objects'], allowed_path.read_text().splitlines()))
    else:
      gates.skip('K7b', 'TODO Q1: review and commit rebuilt-object reference; dryrun only')
    gates.check('K8-format', lambda: wifi_manifest(manifests['wifi_objects']) and 'build-job hashes parsed')
    if wifi_path.exists():
      gates.add('K8', manifests['wifi_objects'] == read_json(wifi_path),
                'advisory identity comparison; computed in the build job', 'advisory')
    else:
      gates.skip('K8', 'TODO Q1/Q5: reference missing; run identical tree twice and compare; advisory')
  gates.check('K9-selfcheck', lambda: ondevice_selfcheck(manual, manual_images))
  wpa = bootimg.repack(fields['header'], wpa_image + chain, fields['cmdline'] + f' wpa3.sae={number}', key)
  revert = bootimg.repack(fields['header'], fields['kernel'], fields['cmdline'] + f' wpa3.sae={number + 1}', key)
  def check_image():
    facts['boot'] = image_checks(stock, wpa, public, policy)
    return f"verified signature, header, layout, SAE/RSNXE, stock DTB order; {facts['boot']['hash_raw']}"
  gates.check('K9', check_image)
  def check_revert():
    facts['revert'] = image_checks(stock, revert, public, policy, revert=True)
    return 'unchanged stock kernel; verified tagged header/signature'
  gates.check('K11', check_revert)
  if status is not None:
    gates.check('K12', lambda: k12(status, auto_pins, policy, now or datetime.now(timezone.utc)), 'brake')
  else:
    gates.skip('K12', 'local byte check has no publication state')
  if replay_image is not None:
    gates.check('Q1-WPA3', lambda: replay_check(replay_image, wpa, number, key))
  require(not gates.failed('integrity'), 'integrity hold: ' + '; '.join(
    f"{r['gate']}: {r['detail']}" for r in gates.rows if r['result'] == 'FAIL' and r['kind'] == 'integrity'))
  facts.update(schema=1, mode='dryrun', stock_hash_raw=sha256(stock), gates=gates.rows,
               banners_match_exactly=ke.banner_identity(stock_image) == ke.banner_identity(ke.split(rebuilt)[1]),
               computed_in_build_job=['K6 source link', 'K7b rebuilt objects', 'K8 Wi-Fi object hashes', 'build log'],
               qualified=False, device_tested=False, notice='Dryrun artifacts only. Not device-tested. No WPA3 kernel has been device-tested on comma 3X.')
  return wpa, revert, facts


def write_artifacts(out, wpa, revert, facts):
  out.mkdir(parents=True, exist_ok=True)
  for label, raw in (('boot', wpa), ('revert', revert)):
    path = out / f'{label}-{sha256(raw)}.img.xz'
    path.write_bytes(compress_checked(raw))
    facts[label]['file'] = path.name
  write_json(out / 'provenance.json', facts)
  (out / 'SHA256SUMS').write_text(''.join(f'{sha256(p.read_bytes())}  {p.name}\n' for p in sorted(out.iterdir()) if p.is_file() and p.name != 'SHA256SUMS'))


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--stock', type=Path, required=True)
  parser.add_argument('--rebuilt-stock', type=Path, required=True, help='raw rebuilt Image-dtb')
  parser.add_argument('--wpa3-boot', type=Path, required=True)
  parser.add_argument('--key', type=Path, required=True)
  parser.add_argument('--manual-dir', type=Path, required=True, help='19.8.img and 19.9.img, hash checked against pins')
  parser.add_argument('--replay', choices=('19.8', '19.9'), default='19.9')
  parser.add_argument('--out', type=Path, required=True)
  args = parser.parse_args()
  try:
    import follow_state
    state = follow_state.load()
    manual = {v: read_bytes(args.manual_dir / f'{v}.img') for v in state['manual']}
    number, note = dry_tags(state, args.replay)
    wpa, revert, facts = assemble(read_bytes(args.stock), read_bytes(args.rebuilt_stock),
      ke.split(read_bytes(args.wpa3_boot))[1], args.key, state['policy'], number,
      state['manual'], manual, replay_image=manual[args.replay], local=True)
    facts['K10'] = note
    write_artifacts(args.out, wpa, revert, facts)
    return 0
  except Exception as error:
    print(f'K*: FAIL: {error}', file=sys.stderr)
    return 1


if __name__ == '__main__':
  sys.exit(main())
