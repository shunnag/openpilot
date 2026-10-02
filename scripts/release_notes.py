#!/usr/bin/env python3
"""Render release notices using only the supplied provenance, never live state."""
import argparse
import json
from pathlib import Path
import re
from string import Template

ROOT = Path(__file__).resolve().parents[1]
# Literal factual tokens in templates must be supported by the input document.
TOKENS = re.compile(r'\b(?:[GKPRTW]\d+(?:\([a-z]\)|[a-z])?|[\w*-]+\.(?:json|txt|log|pem|patch|img(?:\.xz)?|tar\.(?:xz|gz)|deb)|(?:gcc|clang)[\w.+/-]*)\b')


def scalar(value):
  return str(value).replace('@', '@\u200b').replace('|', '&#124;').replace('\n', '<br>')


def validate_template(template, provenance):
  supplied = set(TOKENS.findall(json.dumps(provenance, ensure_ascii=False)))
  missing = set(TOKENS.findall(template)) - supplied
  if missing:
    raise ValueError('template facts absent from provenance: ' + ', '.join(sorted(missing)))


def gate_rows(value):
  rows = []
  if isinstance(value, dict):
    if {'gate', 'result', 'detail'} <= value.keys():
      rows.append(value)
    else:
      for child in value.values():
        rows.extend(gate_rows(child))
  elif isinstance(value, list):
    for child in value:
      rows.extend(gate_rows(child))
  return rows


def evidence(provenance):
  rows = gate_rows(provenance['facts'])
  checks = '| Check | Exact output |\n|---|---|\n' + '\n'.join(
    f"| {scalar(r['gate'])} | {scalar(r.get('line', r['gate'] + ': ' + r['result'] + ': ' + r['detail']))} |" for r in rows)
  tool = provenance['facts'].get('toolchain')
  toolchain = 'Toolchain: ' + (json.dumps(tool, sort_keys=True) if tool else 'not recorded')
  assets = 'Assets:\n' + '\n'.join(f'- `{scalar(name)}`' for name in provenance['assets'])
  return checks, toolchain, assets


def render(provenance, kind='kernel', *, template=None):
  template = template if template is not None else (ROOT / f'follow/templates/{kind}-release.md').read_text()
  validate_template(template, provenance)
  checks, toolchain, assets = evidence(provenance)
  approval = provenance.get('approval')
  tested = provenance.get('device_tested', {})
  devices = tested.get('devices', [])
  if approval and approval['device_tested']:
    devices = sorted(set(devices) | {approval['device']})
  device_text = ', '.join(devices) or 'NOT device-tested'
  baseline = provenance.get('baseline_tested')
  baseline_text = json.dumps(baseline, sort_keys=True, ensure_ascii=False) if baseline else 'not recorded'
  risks = [r['gate'] for r in gate_rows(provenance['facts']) if r['result'] == 'FAIL']
  risk_text = ('Risk checks FAILED: ' + ', '.join(risks) +
               ('. Maintainer approved this risk.' if approval else '. Maintainer approval is required.')) if risks else ''
  if kind == 'kernel':
    pin = provenance['pin']
    title = f"AGNOS {provenance['version']} WPA3 boot image ({pin['tag']}): auto-built, {device_text}"
    if risks:
      title += '; risk check ' + ', '.join(risks) + ' FAILED'
    marker = (f"<!-- wpa3-follow key={provenance['key']} stock={pin['derived_from']['boot_hash_raw']} -->\n\n"
              f"<!-- wpa3-follow-gates: {pin['auto']['gate_version']} -->")
    identity = (f"Source: `{pin['auto']['kernel_commit']}`. Baseline: `{pin['auto']['baseline_release']}`.\n\n"
                f"Run: {pin['auto']['run_url']}\n\nStock revert: `{pin['revert']['tag']}`.")
  else:
    title = f"WPA T3 request {provenance['request']['id']} ({provenance['publication_status']})"
    marker = f"<!-- wpa3-wpa:{provenance['request']['id']} -->"
    identity = f"Stock SHA-256: `{provenance['request']['assets']['stock']['sha256']}`.\n\n" + provenance['publication_status']
  body = Template(template).substitute(marker=marker, identity=identity, device_tested=device_text,
    baseline_tested=baseline_text, wpa_status=scalar(provenance['wpa_status']), checks=checks,
    toolchain=toolchain, assets=assets, risks=risk_text, requirements=provenance.get("publication_requirements", ""))
  return title, body


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('kind', choices=('kernel', 'wpa'))
  parser.add_argument('provenance', type=Path)
  args = parser.parse_args()
  title, body = render(json.loads(args.provenance.read_text()), args.kind)
  print(title + '\n\n' + body)


if __name__ == '__main__':
  main()
