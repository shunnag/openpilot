# Recorded replay inputs

`19.8.json` and `19.9.json` contain the actual comma openpilot manifests and
agnos.py blob IDs at cached upstream commits `cab53438ae` and `134517ceb3`.
The kernel heads snapshot comes from the research cache captured 2026-10-01.
The compare fixture records the ancestry/count fields documented in DESIGN V8;
its file list is deliberately omitted because K3 computes a two-tree git diff.

`builder-prs.json` is empty because the offline cache lacks the deleted head
of PR #631. It is not used for network discovery, which reads all PR API pages.
The source is still found through the cached release branch. Synthetic local
git repositories in the unit tests cover PR-head acceptance and rejection.

These are historical inputs, not assertions about current upstream heads.
