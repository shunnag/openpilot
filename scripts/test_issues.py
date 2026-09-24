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


class TestNightlyWorkflow(unittest.TestCase):
  def test_branch_names_only_in_matrix(self):
    workflow = (ROOT / ".github/workflows/nightly.yml").read_text()
    matrix = "branch: [nightly, nightly-chestnut]"
    self.assertIn(matrix, workflow)
    self.assertNotIn("nightly-chestnut", workflow.replace(matrix, ""))

  def test_branch_environment_refs_and_job_concurrency(self):
    workflow = (ROOT / ".github/workflows/nightly.yml").read_text()
    for expected in (
      "fail-fast: false",
      "group: publish-${{ matrix.branch }}",
      "BRANCH: ${{ matrix.branch }}",
      '"refs/heads/$BRANCH"',
      "refs/heads/$BRANCH-lastgood",
      '$NEW:refs/heads/$BRANCH"',
      '--force-with-lease="refs/heads/$BRANCH:$FORK"',
      '$OWNER/$BRANCH"',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, workflow)
    self.assertNotRegex(workflow, r'refs/heads/nightly|/nightly(?:-chestnut)?["\']')
    self.assertNotRegex(workflow, r"(?m)^concurrency\s*:")

  def test_every_issue_call_passes_branch(self):
    workflow = (ROOT / ".github/workflows/nightly.yml").read_text()
    calls = [line for line in workflow.splitlines() if "scripts/issues.py" in line]
    self.assertTrue(calls)
    for call in calls:
      with self.subTest(call=call):
        self.assertIn('--branch "$BRANCH"', call)


class TestRollbackWorkflow(unittest.TestCase):
  def test_branch_environment_refs_concurrency_and_guard(self):
    workflow = (ROOT / ".github/workflows/rollback.yml").read_text()
    for expected in (
      "group: publish-${{ inputs.branch }}",
      "BRANCH: ${{ inputs.branch }}",
      '"refs/heads/$BRANCH"',
      '"refs/heads/$BRANCH-lastgood"',
      '$GOOD:refs/heads/$BRANCH"',
      '--force-with-lease="refs/heads/$BRANCH:$F"',
      "default: select-a-branch",
      'case "$BRANCH" in',
      "nightly|nightly-chestnut) ;;",
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
      self.assertEqual(result.stdout.strip(), "::error::Choose nightly or nightly-chestnut; nothing was changed.")
      self.assertEqual(log.read_text(), "")


if __name__ == "__main__":
  unittest.main()
