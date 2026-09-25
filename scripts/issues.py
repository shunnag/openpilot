#!/usr/bin/env python3
"""Maintain one hold/smoke issue per branch and kind. Used only by the publishing workflow."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def gh(*args):
  return subprocess.check_output(["gh", *args, "--repo", os.environ["GH_REPO"]], text=True).strip()


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("kind", choices=("hold", "smoke"))
  parser.add_argument("--branch", required=True)
  parser.add_argument("--close", action="store_true")
  parser.add_argument("--upstream", default="unknown")
  parser.add_argument("--reason", default="workflow failure")
  parser.add_argument("--log", type=Path)
  args = parser.parse_args()
  label = f"nightly-{args.kind}"
  branch_label = f"branch:{args.branch}"
  issues = json.loads(gh("issue", "list", "--state", "open", "--label", label, "--label", branch_label, "--limit", "1000", "--json", "number"))
  numbers = sorted(issue["number"] for issue in issues)
  run_url = f"https://github.com/{os.environ['GH_REPO']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
  if args.close:
    for number in numbers:
      gh("issue", "close", str(number), "--comment", f"Nightly [{args.branch}] succeeded for upstream {args.upstream}.\n\n{run_url}")
    return

  log = args.log.read_text(errors="replace") if args.log and args.log.exists() else "No log was captured."
  failures = ("PIN: FAIL:", *(f"G{i}: FAIL:" for i in range(1, 7)))
  reason = next((line for line in log.splitlines() if line.startswith(failures)), args.reason)
  title = f"nightly {args.kind} [{args.branch}]: {reason}"[:200]
  status = "Publication held; no new nightly was published." if args.kind == "hold" else "Installer smoke test failed; published branch is retained."
  body = f"{status}\n\nBranch: `{args.branch}`\nUpstream: `{args.upstream}`\nRun: {run_url}\n\n```text\n{log[-45000:].replace('```', '` ` `')}\n```\n"
  gh("label", "create", label, "--color", "B60205", "--description", f"WPA3 nightly {args.kind}", "--force")
  gh("label", "create", branch_label, "--color", "1D76DB", "--description", f"WPA3 branch {args.branch}", "--force")
  with tempfile.TemporaryDirectory(prefix="nightly-issue-") as directory:
    body_file = Path(directory) / "body.md"
    body_file.write_text(body)
    if numbers:
      gh("issue", "edit", str(numbers[0]), "--title", title, "--body-file", str(body_file))
      for number in numbers[1:]:
        gh("issue", "close", str(number), "--comment", f"Consolidated into #{numbers[0]}.")
    else:
      gh("issue", "create", "--title", title, "--label", label, "--label", branch_label, "--body-file", str(body_file))


if __name__ == "__main__":
  main()
