#!/usr/bin/env python3
"""Offline UI form selection, composition and input-identity checks across #39339."""
import hashlib
import io
import json
import subprocess
import unittest
from unittest.mock import patch

import compose
import gates
import test_compose as compose_fixture
import test_modem_agnos20 as agnos20_fixture

WIFI = "openpilot/system/ui/lib/wifi_manager.py"
NETWORKMANAGER = "openpilot/system/ui/lib/networkmanager.py"
SECURITY_TEST = "openpilot/system/ui/lib/tests/test_security_type.py"


def plus_minus(diff, path=None):
  # The added and removed lines of a diff, optionally of one file section only.
  sections = diff.split(b"diff --git ")[1:]
  if path is not None:
    sections = [s for s in sections if s.split(b"\n", 1)[0].endswith(b" b/" + path.encode())]
    assert len(sections) == 1, path
  return [line for s in sections for line in s.splitlines()
          if line.startswith((b"+", b"-")) and not line.startswith((b"+++ ", b"--- "))]


def patch_paths(diff):
  return {s.split(b"\n", 1)[0].split(b" b/", 1)[1].decode() for s in diff.split(b"diff --git ")[1:]}


class UiWorkerHelpers:
  def changed(self, upstream, commit):
    return set(compose.git(self.repo, "diff-tree", "--no-commit-id", "-r", "--name-only", upstream, commit).decode().splitlines())

  def tree_of(self, commit):
    return compose.git(self.repo, "rev-parse", commit + "^{tree}").decode().strip()

  def payload(self, *args, **kwargs):
    with patch.object(compose.json, "dumps", wraps=json.dumps) as dumps:
      inputs = compose.compose_inputs(self.repo, *args, **kwargs)
    return inputs, dumps.call_args.args[0]

  def assert_same_fork_changes(self, old_upstream, old_commit, upstream, commit):
    # Every composed path matches the old form's, except the two files the worker form rebases.
    changed = self.changed(upstream, commit)
    self.assertEqual(changed, self.changed(old_upstream, old_commit))
    self.assertTrue({WIFI, NETWORKMANAGER, SECURITY_TEST} <= changed)
    for path in sorted(changed - {WIFI, SECURITY_TEST}):
      if compose.git(self.repo, "ls-tree", commit, "--", path):
        self.assertEqual(compose.blob(self.repo, commit, path), compose.blob(self.repo, old_commit, path), path)
    # The fork's WifiManager change commutes with #39339: between the two composed files, exactly #39339's lines change.
    old_blob, new_blob = (compose.git(self.repo, "rev-parse", f"{c}:{WIFI}").decode().strip() for c in (old_commit, commit))
    self.assertEqual(plus_minus(compose.git(self.repo, "diff", old_blob, new_blob)), plus_minus(compose_fixture.WORKER_DIFF.read_bytes()))


class TestUiWorkerPatch(UiWorkerHelpers, unittest.TestCase):
  setUpClass = classmethod(compose_fixture.TestCompose.setUpClass.__func__)
  cli = classmethod(compose_fixture.TestCompose.cli.__func__)
  variant_many = compose_fixture.TestCompose.variant_many
  variant = compose_fixture.TestCompose.variant
  worker_variant = compose_fixture.TestCompose.worker_variant
  apn_upstream = compose_fixture.TestCompose.apn_upstream
  assert_patch_hold = compose_fixture.TestCompose.assert_patch_hold

  def test_worker_patch_carries_the_same_wifi_manager_changes(self):
    self.assertEqual(compose.UI_PATCHES, (compose.UI_PATCH, compose.UI_WORKER_PATCH))
    old, new = (p.read_bytes() for p in compose.UI_PATCHES)
    self.assertEqual(patch_paths(old), compose.UI_ALLOWED)
    self.assertEqual(patch_paths(new), compose.UI_ALLOWED)
    for path in (WIFI, NETWORKMANAGER):
      self.assertEqual(plus_minus(old, path), plus_minus(new, path), path)
    # The test only swaps the patched threading.Thread for a synchronous run of the shared request queue.
    expected = [b"+import queue", *plus_minus(old, SECURITY_TEST)]
    thread = expected.index(b"+    mocker.patch.object(wifi_manager.threading, 'Thread',")
    self.assertEqual(expected[thread + 1], b"+                        side_effect=lambda target, **kw: mocker.Mock(start=target))")
    expected[thread:thread + 2] = [b"+    # Run the request synchronously", b"+    wm._requests = queue.Queue()"]
    connect = expected.index(b'+    wm.connect_to_network("Net", "password123", hidden=hidden)')
    expected[connect + 1:connect + 1] = [b"+    wm._requests.get_nowait()()", b"+    assert wm._requests.empty()"]
    self.assertEqual(plus_minus(new, SECURITY_TEST), expected)

  def test_forms_are_exclusive_and_selection_is_read_only(self):
    for upstream, matching in ((self.upstream, compose.UI_PATCH), (self.worker_variant(), compose.UI_WORKER_PATCH),
                               (self.apn_upstream(), compose.UI_PATCH), (self.worker_variant(self.apn_upstream()), compose.UI_WORKER_PATCH)):
      with self.subTest(upstream=upstream, patch=matching.name), compose.temporary_index(self.repo, upstream) as (env, _):
        before = compose.git(self.repo, "write-tree", env=env)
        self.assertEqual(compose.select_ui_patch(self.repo, env), (matching, "applies cleanly"))
        for candidate in compose.UI_PATCHES:
          if candidate == matching:
            compose.git(self.repo, "apply", "--cached", "--check", "--whitespace=error", str(candidate), env=env)
            continue
          for reverse in ((), ("--reverse",)):
            with self.assertRaises(subprocess.CalledProcessError):
              compose.git(self.repo, "apply", "--cached", "--check", *reverse, str(candidate), env=env)
        self.assertEqual(compose.apply_ui(self.repo, env, check=True), "applies cleanly")
        self.assertEqual(compose.git(self.repo, "write-tree", env=env), before)
        self.assertEqual(compose.apply_ui(self.repo, env), "applied")
        self.assertNotEqual(compose.git(self.repo, "write-tree", env=env), before)
        # Once applied, the same form is the only match, now in the already-applied state.
        self.assertEqual(compose.select_ui_patch(self.repo, env), (matching, "already applied"))
        for candidate in compose.UI_PATCHES:
          if candidate != matching:
            for reverse in ((), ("--reverse",)):
              with self.assertRaises(subprocess.CalledProcessError):
                compose.git(self.repo, "apply", "--cached", "--check", *reverse, str(candidate), env=env)
        self.assertEqual(compose.apply_ui(self.repo, env), "already applied")

  def test_worker_compose_gates_and_parity(self):
    self.assertIn("G5: OK: UI patch ui-wpa3.patch applies cleanly\n", self.cli("gates.py", self.upstream, "--skip-download").stdout)
    upstream = self.worker_variant()
    result = self.cli("gates.py", upstream, "--skip-download")
    self.assertIn("G5: OK: UI patch ui-wpa3-worker.patch applies cleanly\n", result.stdout)
    for gate in ("G1", "G2", "G3", "G7"):
      self.assertIn(f"{gate}: OK:", result.stdout)
    commit, inputs = self.cli("compose.py", upstream).stdout.splitlines()
    self.assertEqual(self.cli("compose.py", upstream, "--inputs-only").stdout.strip(), inputs)
    self.assertEqual(compose.compose(self.repo, upstream, self.resolved), (commit, inputs))
    self.assertNotEqual(inputs, self.inputs)
    message = compose.git(self.repo, "show", "-s", "--format=%B", commit).decode()
    self.assertIn("WPA3-Launcher-Patch: launcher-wpa3.patch\nWPA3-Tethering-Patch: off\nWPA3-APN-Patch: off\n", message)
    self.assert_same_fork_changes(self.upstream, self.commit, upstream, commit)
    for path in (WIFI, SECURITY_TEST):
      self.assertNotEqual(compose.blob(self.repo, commit, path), compose.blob(self.repo, self.commit, path))

  def test_worker_already_applied(self):
    upstream = self.worker_variant()
    with compose.temporary_index(self.repo, upstream) as (env, _):
      self.assertEqual(compose.apply_ui(self.repo, env), "applied")
      tree = compose.git(self.repo, "write-tree", env=env).decode().strip()
    applied = compose.git(self.repo, "commit-tree", tree, data=b"Upstream includes worker UI patch\n", env=self.identity).decode().strip()
    self.assertIn("G5: OK: UI patch ui-wpa3-worker.patch already applied\n", self.cli("gates.py", applied, "--skip-download").stdout)
    commit, _ = compose.compose(self.repo, upstream, self.resolved)
    new_commit, new_inputs = compose.compose(self.repo, applied, self.resolved)
    self.assertEqual(self.tree_of(new_commit), self.tree_of(commit))
    inputs, payload = self.payload(applied, self.resolved)
    self.assertEqual(inputs, new_inputs)
    self.assertIn(compose.UI_WORKER_PATCH.name, payload["patches"])
    self.assertNotIn(compose.UI_PATCH.name, payload["patches"])

  def test_no_form_or_more_than_one_form_holds(self):
    data = compose.blob(self.repo, self.upstream, WIFI)
    anchor = b"def get_security_type(flags: int, wpa_flags: int, rsn_flags: int) -> SecurityType:\n"
    self.assertEqual(data.count(anchor), 1)
    drift = anchor.replace(b"rsn_flags: int)", b"rsn_flags: int, extra: int = 0)")
    for base in (self.upstream, self.worker_variant()):
      drifted = self.variant_many({WIFI: compose.blob(self.repo, base, WIFI).replace(anchor, drift)}, base)
      with self.subTest(base=base):
        # --inputs-only now selects the UI form even with tethering and APN off, so it holds as well.
        self.assert_patch_hold(drifted, (), "no UI patch applies")
        stderr = self.cli("gates.py", drifted, "--skip-download", check=False).stderr
        for candidate in compose.UI_PATCHES:
          self.assertIn(f"{candidate.name}: git ", stderr)
        self.assertIn("patch does not apply", stderr)
        with compose.temporary_index(self.repo, drifted) as (env, _):
          before = compose.git(self.repo, "write-tree", env=env)
          with self.assertRaisesRegex(ValueError, "no UI patch applies"):
            compose.apply_ui(self.repo, env)
          self.assertEqual(compose.git(self.repo, "write-tree", env=env), before)
    duplicate = self.work / "ui-wpa3-copy.patch"
    duplicate.write_bytes(compose.UI_PATCH.read_bytes())
    forward = self.work / "ui-forward.patch"
    forward.write_text('diff --git a/new.py b/new.py\nnew file mode 100644\n--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+pass\n')
    with compose.temporary_index(self.repo, self.upstream) as (env, _):
      compose.apply_ui(self.repo, env)
      applied = compose.git(self.repo, "commit-tree", compose.git(self.repo, "write-tree", env=env).decode().strip(),
                            data=b"Upstream includes UI patch\n", env=self.identity).decode().strip()
    # Applicable and already-applied forms count together: exactly one may fit.
    for upstream, registered, states in (
      (self.upstream, (compose.UI_PATCH, compose.UI_WORKER_PATCH, duplicate), ("ui-wpa3.patch: applies cleanly", "ui-wpa3-copy.patch: applies cleanly")),
      (applied, (compose.UI_PATCH, compose.UI_WORKER_PATCH, duplicate), ("ui-wpa3.patch: already applied", "ui-wpa3-copy.patch: already applied")),
      (applied, (compose.UI_PATCH, forward), ("ui-wpa3.patch: already applied", "ui-forward.patch: applies cleanly")),
    ):
      with self.subTest(upstream=upstream, registered=[p.name for p in registered]), patch.object(compose, "UI_PATCHES", registered):
        with compose.temporary_index(self.repo, upstream) as (env, _):
          before = compose.git(self.repo, "write-tree", env=env)
          with self.assertRaisesRegex(ValueError, "more than one UI patch applies") as raised:
            compose.apply_ui(self.repo, env)
          self.assertEqual(compose.git(self.repo, "write-tree", env=env), before)
        for state in states:
          self.assertIn(state, str(raised.exception))
        for action in (compose.compose, compose.compose_inputs):
          with self.assertRaisesRegex(ValueError, "more than one UI patch applies"):
            action(self.repo, upstream, self.resolved)
        with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO) as stderr:
          self.assertEqual(gates.run_gates(self.repo, upstream, self.pin_file, skip_download=True), 1)
        self.assertIn("G5: FAIL: more than one UI patch applies", stderr.getvalue())

  def test_worker_inputs_hash_the_selected_form_and_frozen_composer(self):
    upstream = self.worker_variant()
    launcher = compose.select_launcher_patch(self.repo, upstream)
    inputs, payload = self.payload(upstream, self.resolved)

    def sha(path):
      return hashlib.sha256(path.read_bytes()).hexdigest()

    self.assertEqual(payload["patches"], {launcher.name: sha(launcher), compose.UI_WORKER_PATCH.name: sha(compose.UI_WORKER_PATCH)})
    self.assertEqual(payload["compose.py"], compose.WORKER_COMPOSE_SHA256)
    self.assertEqual(inputs, compose.inputs_hash(upstream, self.resolved, launcher, ui_patch=compose.UI_WORKER_PATCH))
    self.assertNotEqual(inputs, compose.inputs_hash(upstream, self.resolved, launcher))
    with patch.object(compose, "__file__", str(compose.ROOT / "scripts/gates.py")):
      # The worker form keeps fe9cfa498's composer digest when compose.py changes.
      self.assertEqual(compose.inputs_hash(upstream, self.resolved, launcher, ui_patch=compose.UI_WORKER_PATCH), inputs)
      # Trees that take ui-wpa3.patch keep the frozen composer digest.
      self.assertEqual(compose.inputs_hash(self.upstream, self.resolved, compose.LAUNCHER_PATCHES[0]), self.inputs)
      self.assertEqual(compose.compose_inputs(self.repo, self.upstream, self.resolved), self.inputs)
    copied = self.work / "copied" / compose.UI_WORKER_PATCH.name
    copied.parent.mkdir(exist_ok=True)
    copied.write_bytes(compose.UI_WORKER_PATCH.read_bytes())
    self.assertEqual(compose.inputs_hash(upstream, self.resolved, launcher, ui_patch=copied), inputs)
    copied.write_bytes(copied.read_bytes() + b"\n")
    self.assertNotEqual(compose.inputs_hash(upstream, self.resolved, launcher, ui_patch=copied), inputs)

  def test_worker_tree_with_tethering_takes_the_worker_tethering_form(self):
    # tethering-nat.patch predates #39339's threading.Timer and request queue; its worker form applies instead.
    upstream = self.worker_variant()
    with compose.temporary_index(self.repo, upstream) as (env, _):
      compose.apply_ui(self.repo, env)
      with self.assertRaises(subprocess.CalledProcessError):
        compose.git(self.repo, "apply", "--cached", "--check", str(compose.TETHER_PATCH), env=env)
    result = self.cli("gates.py", upstream, "--skip-download", "--tether", "apply")
    self.assertIn("G5: OK: UI patch ui-wpa3-worker.patch applies cleanly\n"
                  "G5: OK: tethering patch tethering-nat-worker.patch applies cleanly\n", result.stdout)
    commit, inputs = self.cli("compose.py", upstream, "--tether", "apply").stdout.splitlines()
    self.assertEqual(self.cli("compose.py", upstream, "--tether", "apply", "--inputs-only").stdout.strip(), inputs)
    self.assertIn("WPA3-Tethering-Patch: applied\n", compose.git(self.repo, "show", "-s", "--format=%B", commit).decode())


class TestUiWorkerAgnos20(UiWorkerHelpers, unittest.TestCase):
  setUpClass = classmethod(agnos20_fixture.TestAgnos20Compose.setUpClass.__func__)
  cli = classmethod(agnos20_fixture.TestAgnos20Compose.cli.__func__)
  variant_many = agnos20_fixture.TestAgnos20Compose.variant_many
  variant = agnos20_fixture.TestAgnos20Compose.variant
  v0112_variant = agnos20_fixture.TestAgnos20Compose.v0112_variant
  snd_variant = agnos20_fixture.TestAgnos20Compose.snd_variant
  apn_upstream = agnos20_fixture.TestAgnos20Compose.apn_upstream
  modern_fixture = agnos20_fixture.TestAgnos20Compose.modern_fixture
  worker_variant = compose_fixture.TestCompose.worker_variant

  def test_worker_tree_composes_with_apn_and_modem_bundle(self):
    nb, resolved = self.modern_fixture(raylib_nb=True)
    old = self.snd_variant(nb)
    upstream = self.worker_variant(old)
    pin_file = self.work / "ui-worker-pin.json"
    pin_file.write_text(json.dumps(resolved))
    for family, candidates in compose.APN_AGNOS20_PATCHES.items():
      with self.subTest(family=family):
        old_commit, old_inputs = compose.compose(self.repo, old, resolved, "off", "auto", family)
        commit, inputs = compose.compose(self.repo, upstream, resolved, "off", "auto", family)
        self.assertEqual(inputs, compose.compose_inputs(self.repo, upstream, resolved, "off", "auto", family))
        self.assertNotEqual(inputs, old_inputs)
        compose.check_modem_bundle(self.repo, commit, resolved, required=True)
        self.assert_same_fork_changes(old, old_commit, upstream, commit)
        message = compose.git(self.repo, "show", "-s", "--format=%B", commit).decode()
        self.assertIn(f"WPA3-Launcher-Patch: launcher-wpa3-snd.patch\nWPA3-Tethering-Patch: off\nWPA3-APN-Patch: {candidates[1].name} applied\n", message)
        result = self.cli("gates.py", upstream, "--skip-download", "--tether", "off", "--apn", "auto", "--apn-family", family, pin_file=pin_file)
        self.assertIn("G3: OK: agnos.py blob matches and launcher patch launcher-wpa3-snd.patch applies\n", result.stdout)
        self.assertIn("G5: OK: UI patch ui-wpa3-worker.patch applies cleanly\n", result.stdout)
        self.assertIn(f"G5: OK: APN patch {candidates[1].name} applies cleanly\n", result.stdout)
        self.assertIn("G9: OK: AGNOS-20 APN UI, stdlib modem override and pinned launcher bundle verified\n", result.stdout)
        tethered = self.cli("gates.py", upstream, "--skip-download", "--tether", "apply", "--apn", "auto", "--apn-family", family,
                            pin_file=pin_file)
        self.assertIn("G5: OK: UI patch ui-wpa3-worker.patch applies cleanly\n"
                      "G5: OK: tethering patch tethering-nat-worker.patch applies cleanly\n"
                      f"G5: OK: APN patch {candidates[1].name} applies cleanly\n", tethered.stdout)
        self.assertIn("G9: OK: AGNOS-20 APN UI, stdlib modem override and pinned launcher bundle verified\n", tethered.stdout)


if __name__ == "__main__":
  unittest.main()
