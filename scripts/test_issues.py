#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
ISSUES = {
  ("hold", "nightly"): [102, 101],
  ("hold", "nightly-chestnut"): [202, 201],
  ("smoke", "nightly"): [302, 301],
  ("smoke", "nightly-chestnut"): [402, 401],
}


def flag_values(args, flag):
  return [args[i + 1] for i, value in enumerate(args) if value == flag]


class TestIssues(unittest.TestCase):
  def setUp(self):
    (ROOT / ".tmp").mkdir(exist_ok=True)
    temp = tempfile.TemporaryDirectory(prefix="test-issues-", dir=ROOT / ".tmp")
    self.addCleanup(temp.cleanup)
    self.work = Path(temp.name)
    self.log = self.work / "gh.jsonl"
    self.bodies = self.work / "bodies.jsonl"
    fake = self.work / "gh"
    fake.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''\
      import json
      import os
      from pathlib import Path
      import sys

      args = sys.argv[1:]
      with open(os.environ["FAKE_GH_LOG"], "a") as log:
        log.write(json.dumps(args) + "\\n")
      if "--body-file" in args:
        body = Path(args[args.index("--body-file") + 1]).read_text()
        with open(os.environ["FAKE_GH_BODIES"], "a") as log:
          log.write(json.dumps(body) + "\\n")
      if args[:2] == ["issue", "list"]:
        labels = [args[i + 1] for i, arg in enumerate(args) if arg == "--label"]
        numbers = json.loads(os.environ["FAKE_GH_ISSUES"]).get(" ".join(sorted(labels)), [])
        print(json.dumps([{"number": number} for number in numbers]))
      '''))
    fake.chmod(0o755)
    self.env = {
      **os.environ,
      "PATH": str(self.work) + os.pathsep + os.environ.get("PATH", ""),
      "TMPDIR": str(self.work),
      "GH_REPO": "example/openpilot",
      "GITHUB_RUN_ID": "12345",
      "FAKE_GH_LOG": str(self.log),
      "FAKE_GH_BODIES": str(self.bodies),
    }

  def run_issues(self, kind, branch, *args, listed=None):
    self.log.write_text("")
    self.bodies.write_text("")
    fixtures = {f"branch:{branch} nightly-{kind}": numbers for (kind, branch), numbers in (listed or {}).items()}
    result = subprocess.run([sys.executable, str(ROOT / "scripts/issues.py"), kind, "--branch", branch, *args],
                            env={**self.env, "FAKE_GH_ISSUES": json.dumps(fixtures)}, text=True, capture_output=True)
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    return [json.loads(line) for line in self.log.read_text().splitlines()]

  def assert_list_labels(self, calls, kind, branch):
    lists = [call for call in calls if call[:2] == ["issue", "list"]]
    self.assertEqual(len(lists), 1)
    self.assertEqual(flag_values(lists[0], "--label"), [f"nightly-{kind}", f"branch:{branch}"])
    for call in calls:
      self.assertEqual(call[-2:], ["--repo", "example/openpilot"])

  def test_branch_is_required(self):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/issues.py"), "hold"],
                            env=self.env, text=True, capture_output=True)
    self.assertEqual(result.returncode, 2)
    self.assertIn("--branch", result.stderr)
    self.assertFalse(self.log.exists())

  def test_create_uses_both_labels_and_branch_title_and_body(self):
    for kind, branch in ISSUES:
      with self.subTest(kind=kind, branch=branch):
        reason = "gate checks failed" if kind == "hold" else "installer failure " * 20
        calls = self.run_issues(kind, branch, "--reason", reason)
        self.assert_list_labels(calls, kind, branch)
        labels = [f"nightly-{kind}", f"branch:{branch}"]
        label_creates = [call for call in calls if call[:2] == ["label", "create"]]
        self.assertEqual([call[2] for call in label_creates], labels)
        for call in label_creates:
          self.assertIn("--force", call)
        creates = [call for call in calls if call[:2] == ["issue", "create"]]
        self.assertEqual(len(creates), 1)
        self.assertEqual(flag_values(creates[0], "--label"), labels)
        title, = flag_values(creates[0], "--title")
        self.assertEqual(title, f"nightly {kind} [{branch}]: {reason}"[:200])
        self.assertLessEqual(len(title), 200)
        body, = [json.loads(line) for line in self.bodies.read_text().splitlines()]
        self.assertIn(f"Branch: `{branch}`", body)
        self.assertIn("https://github.com/example/openpilot/actions/runs/12345", body)

  def test_edit_and_consolidation_are_isolated_by_branch_and_kind(self):
    for (kind, branch), numbers in ISSUES.items():
      with self.subTest(kind=kind, branch=branch):
        calls = self.run_issues(kind, branch, listed=ISSUES)
        self.assert_list_labels(calls, kind, branch)
        changes = [call for call in calls if call[0] == "issue" and call[1] != "list"]
        first, second = sorted(numbers)
        self.assertEqual([call[:3] for call in changes], [["issue", "edit", str(first)], ["issue", "close", str(second)]])
        self.assertEqual(flag_values(changes[0], "--title"), [f"nightly {kind} [{branch}]: workflow failure"])
        self.assertEqual(flag_values(changes[1], "--comment"), [f"Consolidated into #{first}."])

  def test_close_only_listed_issues_for_branch_and_kind(self):
    for (kind, branch), numbers in ISSUES.items():
      with self.subTest(kind=kind, branch=branch):
        calls = self.run_issues(kind, branch, "--close", "--upstream", "abc123", listed=ISSUES)
        self.assert_list_labels(calls, kind, branch)
        self.assertEqual([call[:3] for call in calls[1:]], [["issue", "close", str(number)] for number in sorted(numbers)])
        for call in calls[1:]:
          comment, = flag_values(call, "--comment")
          self.assertIn(f"[{branch}] succeeded for upstream abc123", comment)

  def test_close_without_matches_leaves_other_branch_alone(self):
    calls = self.run_issues("hold", "nightly", "--close", listed={("hold", "nightly-chestnut"): [202, 201]})
    self.assert_list_labels(calls, "hold", "nightly")
    self.assertEqual(len(calls), 1)

  def test_pin_and_gate_failure_reason_from_log(self):
    for reason in ("PIN: FAIL: agnos.py changed since 19.8", "G3: FAIL: launcher patch does not apply",
                   "G6: FAIL: published tag/hash conflict", "G7: FAIL: wpa_supplicant SHA-256 differs from pin"):
      with self.subTest(reason=reason):
        log = self.work / "nightly.log"
        log.write_text(f"Upstream: abc123\n{reason}\n")
        calls = self.run_issues("hold", "nightly", "--reason", "fallback", "--log", str(log))
        create, = [call for call in calls if call[:2] == ["issue", "create"]]
        self.assertEqual(flag_values(create, "--title"), [f"nightly hold [nightly]: {reason}"])


class TestNightlyWorkflow(unittest.TestCase):
  def test_resolve_step_and_pin_file_plumbing(self):
    workflow = (ROOT / ".github/workflows/nightly.yml").read_text()
    script = (ROOT / "scripts/publish_branch.sh").read_text()
    self.assertIn('bash -eu -o pipefail scripts/publish_branch.sh', workflow)
    self.assertIn('python3 scripts/pins.py --repo "$BARE_REPO" --upstream "$UPSTREAM" --out "$PIN_FILE" --follow-mode "$MODE" --branch "$BRANCH" 2>&1 | tee -a "$NIGHTLY_LOG"', script)
    self.assertIn("if pin['mode'] != 'pinned':", script)
    self.assertIn('::notice::AGNOS pin:', script)
    self.assertIn("REASON='AGNOS pin could not be resolved'", script)
    self.assertIn('PUBLISHED_ARGS=()\nif [ -n "$FORK" ]; then\n  PUBLISHED_ARGS=(--published "$FORK")\nfi', script)
    self.assertIn('"${PUBLISHED_ARGS[@]}"', script)
    consumers = [line for line in script.splitlines() if "scripts/compose.py" in line or "scripts/gates.py" in line]
    self.assertEqual(len(consumers), 3)
    for line in consumers:
      self.assertIn('--pin-file "$PIN_FILE"', line)
      self.assertIn('--tether "$TETHER" --apn "$APN"', line)
    self.assertNotIn('--modem', script)
    self.assertNotIn('MODEM=', script)
    for step in workflow.split("      - "):
      if "        run:" in step:
        self.assertNotIn("${{", step.split("        run:", 1)[1])

  def test_branch_names_only_in_list_patch_selection_and_smoke(self):
    workflow = (ROOT / ".github/workflows/nightly.yml").read_text()
    script = (ROOT / "scripts/publish_branch.sh").read_text()
    branches = "BRANCHES: 'nightly nightly-chestnut release-mici-staging release-tizi-staging'"
    self.assertEqual(workflow.count(branches), 1)
    selector = 'case "$BRANCH" in' + script.split('case "$BRANCH" in', 1)[1].split("esac", 1)[0] + "esac"
    smoke_selector = 'if [ "$BRANCH" = release-tizi-staging ]; then DEVICE_TYPE=tizi; fi'
    for branch in ("nightly", "nightly-chestnut", "release-mici-staging", "release-tizi-staging", "unknown"):
      result = subprocess.run(["bash", "-eu", "-c", selector + '\nprintf "%s %s" "$TETHER" "$APN"'],
                              env={**os.environ, "BRANCH": branch}, text=True, capture_output=True, check=True)
      self.assertEqual(result.stdout, "off off" if branch == "unknown" else "apply auto")
      smoke = subprocess.run(["bash", "-eu", "-c", 'DEVICE_TYPE=mici\n' + smoke_selector + '\nprintf "%s" "$DEVICE_TYPE"'],
                             env={**os.environ, "BRANCH": branch}, text=True, capture_output=True, check=True)
      self.assertEqual(smoke.stdout, "tizi" if branch == "release-tizi-staging" else "mici")
    self.assertIn('-H "X-openpilot-device-type: $DEVICE_TYPE"', script)
    combined = workflow.replace(branches, "") + script.replace(selector, "").replace(smoke_selector, "")
    for branch in ("nightly-chestnut", "release-mici-staging", "release-tizi-staging"):
      self.assertNotIn(branch, combined)

  def test_branch_environment_refs_and_job_concurrency(self):
    workflow = (ROOT / ".github/workflows/nightly.yml").read_text()
    script = (ROOT / "scripts/publish_branch.sh").read_text()
    for expected in ('"refs/heads/$BRANCH"', "refs/heads/$BRANCH-lastgood", '$NEW:refs/heads/$BRANCH"',
                     '--force-with-lease="refs/heads/$BRANCH:$FORK"', '$OWNER/$BRANCH"'):
      self.assertIn(expected, script)
    self.assertIn("      group: publish\n      queue: max\n      cancel-in-progress: false", workflow)
    self.assertIn("timeout-minutes: 90", workflow)
    self.assertNotIn("matrix:", workflow)
    self.assertNotRegex(workflow + script, r'refs/heads/nightly|/nightly(?:-chestnut)?["\']')
    self.assertNotRegex(workflow, r"(?m)^concurrency\s*:")

  def test_every_issue_call_passes_branch(self):
    script = (ROOT / "scripts/publish_branch.sh").read_text()
    calls = [line for line in script.splitlines() if "scripts/issues.py" in line]
    self.assertTrue(calls)
    for call in calls:
      self.assertIn('--branch "$BRANCH"', call)
      self.assertIn('write python3', call)


class TestRollbackWorkflow(unittest.TestCase):
  def test_branch_environment_refs_concurrency_and_guard(self):
    workflow = (ROOT / ".github/workflows/rollback.yml").read_text()
    for expected in (
      "group: publish\n  queue: max",
      "BRANCH: ${{ inputs.branch }}",
      '"refs/heads/$BRANCH"',
      '"refs/heads/$BRANCH-lastgood"',
      '$GOOD:refs/heads/$BRANCH"',
      '--force-with-lease="refs/heads/$BRANCH:$F"',
      "default: select-a-branch",
      'case "$BRANCH" in',
      "nightly|nightly-chestnut|release-mici-staging|release-tizi-staging) ;;",
      "          - release-mici-staging\n          - release-tizi-staging\n",
      "publishing for all four branches (nightly, nightly-chestnut, release-mici-staging and release-tizi-staging) is paused",
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, workflow)
    self.assertRegex(workflow, r"(?m)^        options:\n          - select-a-branch\n")
    self.assertNotRegex(workflow, r'refs/heads/nightly|/nightly(?:-chestnut)?["\']')

  def test_placeholder_exits_before_git_or_gh(self):
    workflow = (ROOT / ".github/workflows/rollback.yml").read_text()
    script = textwrap.dedent(workflow.split("        run: |\n", 1)[1])
    (ROOT / ".tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="test-rollback-", dir=ROOT / ".tmp") as directory:
      work = Path(directory)
      log = work / "calls.log"
      log.write_text("")
      for name in ("git", "gh"):
        stub = work / name
        stub.write_text('#!/bin/sh\nprintf "%s\\n" "$0 $*" >> "$ROLLBACK_CALL_LOG"\nexit 99\n')
        stub.chmod(0o755)
      result = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail"], input=script,
                              text=True, capture_output=True, cwd=work, env={
                                **os.environ,
                                "PATH": str(work) + os.pathsep + os.environ.get("PATH", ""),
                                "BRANCH": "select-a-branch",
                                "GH_REPO": "example/openpilot",
                                "RUNNER_TEMP": str(work),
                                "ROLLBACK_CALL_LOG": str(log),
                              })
      self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
      self.assertEqual(result.stdout.strip(), "::error::Choose nightly, nightly-chestnut, release-mici-staging or release-tizi-staging; nothing was changed.")
      self.assertEqual(log.read_text(), "")


if __name__ == "__main__":
  unittest.main()
