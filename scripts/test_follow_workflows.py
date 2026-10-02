"""Structural YAML policy tests, using only the Python standard library."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def legacy_controls(path):
  """Parse the block-mapping control projection of the two legacy workflows.

  Steps/strategy/dispatch sequences are not part of this projection. Unlike a
  grep, indentation associates every permission/concurrency map with its actual
  workflow or job. New workflows use JSON (a YAML subset) and are fully parsed.
  """
  lines = path.read_text().splitlines()
  def scalar(value):
    return {'false': False, 'true': True, '{}': {}}.get(value, value.strip("'\""))
  def mapping(start, indent):
    result = {}
    for line in lines[start + 1:]:
      if not line.strip() or line.lstrip().startswith('#'):
        continue
      space = len(line) - len(line.lstrip())
      if space <= indent:
        break
      if space == indent + 2:
        key, value = line.strip().split(':', 1)
        result[key] = scalar(value.strip())
    return result
  workflow, job = {'jobs': {}}, None
  in_jobs = False
  for index, line in enumerate(lines):
    match = re.fullmatch(r'( *)([A-Za-z0-9_-]+):(?: (.*))?', line)
    if not match:
      continue
    indent, key, value = len(match[1]), match[2], match[3]
    if indent == 0:
      in_jobs = key == 'jobs'
      job = None
      if key in ('permissions', 'concurrency'):
        workflow[key] = scalar(value) if value else mapping(index, indent)
    elif in_jobs and indent == 2:
      job = workflow['jobs'].setdefault(key, {})
    elif in_jobs and indent == 4 and job is not None and key in ('permissions', 'concurrency'):
      job[key] = scalar(value) if value else mapping(index, indent)
  return workflow


class WorkflowPolicyTests(unittest.TestCase):
  def test_every_job_permissions_and_state_concurrency(self):
    follow = json.loads((ROOT / '.github/workflows/follow.yml').read_text())
    admin = json.loads((ROOT / '.github/workflows/follow-admin.yml').read_text())
    nightly = legacy_controls(ROOT / '.github/workflows/nightly.yml')
    rollback = legacy_controls(ROOT / '.github/workflows/rollback.yml')
    workflows = {'follow': follow, 'admin': admin, 'nightly': nightly, 'rollback': rollback}
    expected = {
      ('follow', 'detect'): {'contents': 'read'}, ('follow', 'probe'): {'contents': 'read'},
      ('follow', 'kernel-build'): {'contents': 'read'}, ('follow', 'wpa-classify'): {'contents': 'read'},
      ('follow', 'wpa-build'): {'contents': 'read'}, ('follow', 'wpa-test'): {'contents': 'read'},
      ('follow', 'publish'): {'contents': 'write', 'issues': 'write', 'actions': 'write'},
      ('follow', 'report'): {'issues': 'write'},
      ('admin', 'admin'): {'contents': 'write', 'issues': 'write', 'actions': 'write'},
      ('nightly', 'publish'): {'contents': 'write', 'issues': 'write'},
      ('rollback', 'rollback'): {'contents': 'write', 'actions': 'write'},
    }
    self.assertEqual({(name, job) for name, w in workflows.items() for job in w['jobs']}, set(expected))
    for name, workflow in workflows.items():
      for job_name, job in workflow['jobs'].items():
        with self.subTest(workflow=name, job=job_name):
          self.assertEqual(job.get('permissions', workflow['permissions']), expected[name, job_name])
          concurrency = job.get('concurrency', workflow.get('concurrency'))
          if (name, job_name) in (('follow', 'publish'), ('admin', 'admin')):
            self.assertNotIn('concurrency', workflow)
            self.assertEqual(concurrency, {'group': 'wpa3-state', 'queue': 'max', 'cancel-in-progress': False})
          elif name == 'nightly':
            self.assertEqual(concurrency, {'group': 'publish-${{ matrix.branch }}', 'cancel-in-progress': False})
          elif name == 'rollback':
            self.assertEqual(concurrency, {'group': 'publish-${{ inputs.branch }}', 'cancel-in-progress': False})
          else:
            self.assertIsNone(concurrency)

  def test_owner_knobs_inputs_actions_and_mode_guards(self):
    for name in ('follow', 'follow-admin'):
      workflow = json.loads((ROOT / f'.github/workflows/{name}.yml').read_text())
      self.assertNotIn('mode', workflow['on']['workflow_dispatch']['inputs'])
      self.assertEqual(workflow['permissions'], {})
      for job_name, job in workflow['jobs'].items():
        for step in job['steps']:
          if 'uses' in step:
            self.assertRegex(step['uses'], r'^[\w/-]+@[0-9a-f]{40}$')
            if step['uses'].startswith('actions/checkout@'):
              self.assertIs(step['with']['persist-credentials'], False)
            if job['permissions'].get('contents') == 'write':
              self.assertNotIn('cache', step['uses'])
          script = step.get('run', '')
          self.assertNotIn('${{', script, 'dispatch inputs must arrive only through env')
          self.assertNotRegex(script, r'gh\s+(?:variable|api[^\n]*actions/variables)')
      if name == 'follow':
        job = workflow['jobs']['publish']
        self.assertEqual(job['env']['FOLLOW_MODE'], "${{ vars.WPA3_FOLLOW_MODE || 'off' }}")
        write = next(s for s in job['steps'] if s.get('name') == 'Verify and write under the owner mode switch')
        self.assertIn("env.FOLLOW_MODE == 'state' || env.FOLLOW_MODE == 'on'", write['if'])
        self.assertIn("inputs.replay == ''", write['if'])
        self.assertIn('inputs.wpa_reference != true', write['if'])
        self.assertIn('gh auth setup-git', write['run'])
      else:
        job = workflow['jobs']['admin']
        self.assertIn('github.actor == github.repository_owner', job['if'])
        self.assertIn('github.triggering_actor == github.repository_owner', job['if'])
        self.assertIn("vars.WPA3_FOLLOW_MODE == 'state' || vars.WPA3_FOLLOW_MODE == 'on'", job['if'])
        cleanup = job['steps'][-1]
        self.assertEqual(cleanup['if'], 'always()')
        self.assertEqual(cleanup['env']['ADMIN_ACTION'], 'restore-nightly')

  def test_rollback_disables_follow_before_branch_restore(self):
    workflow = (ROOT / '.github/workflows/rollback.yml').read_text()
    self.assertLess(workflow.index('gh workflow disable follow.yml'), workflow.index('push --force-with-lease'))
    self.assertIn('gh workflow disable nightly.yml', workflow)
    self.assertNotIn('wpa3-ci', workflow)


if __name__ == '__main__':
  unittest.main()
