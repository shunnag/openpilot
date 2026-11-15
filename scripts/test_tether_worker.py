#!/usr/bin/env python3
"""Offline tethering form selection, composition, input identity and request-thread behaviour across #39339."""
import __future__
import hashlib
import io
import json
import queue
import subprocess
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import compose
import gates
import test_compose as compose_fixture
import test_modem_agnos20 as agnos20_fixture
from test_ui_worker import NETWORKMANAGER, SECURITY_TEST, WIFI, UiWorkerHelpers, patch_paths, plus_minus

TETHER_TEST = "openpilot/system/ui/lib/tests/test_tethering_nat.py"
G5_WORKER = ("G5: OK: UI patch ui-wpa3-worker.patch applies cleanly\n"
             "G5: OK: tethering patch tethering-nat-worker.patch applies cleanly\n")
SLEEP_LINE = b"          time.sleep(5)\n"
TIMER_LINE = b"          threading.Timer(5, disable_forward).start()\n"
SYSCTL = ("sudo", "sysctl", "net.ipv4.ip_forward=0")


def sha(path):
  return hashlib.sha256(path.read_bytes()).hexdigest()


def new_file(diff, path):
  # The contents of a file the patch creates.
  return b"".join(line[1:] + b"\n" for line in plus_minus(diff, path))


class TetherHelpers(UiWorkerHelpers):
  def stacked(self, upstream, tether=True):
    with compose.temporary_index(self.repo, upstream) as (env, _):
      compose.apply_ui(self.repo, env)
      if tether:
        compose.apply_tether(self.repo, env)
      return compose.git(self.repo, "write-tree", env=env).decode().strip()

  def commit_tree(self, tree, message):
    return compose.git(self.repo, "commit-tree", tree, data=message, env=self.identity).decode().strip()

  def assert_same_tethered_changes(self, old_upstream, old_commit, upstream, commit):
    # Both forms change the same paths; only the rebased WifiManager files and the two test files differ.
    changed = self.changed(upstream, commit)
    self.assertEqual(changed, self.changed(old_upstream, old_commit))
    self.assertTrue({WIFI, NETWORKMANAGER, SECURITY_TEST, TETHER_TEST} <= changed)
    for path in sorted(changed - {WIFI, SECURITY_TEST, TETHER_TEST}):
      if compose.git(self.repo, "ls-tree", commit, "--", path):
        self.assertEqual(compose.blob(self.repo, commit, path), compose.blob(self.repo, old_commit, path), path)
    # The UI and tethering changes together commute with #39339: between the composed files, exactly #39339's lines change.
    old_blob, new_blob = (compose.git(self.repo, "rev-parse", f"{c}:{WIFI}").decode().strip() for c in (old_commit, commit))
    self.assertEqual(plus_minus(compose.git(self.repo, "diff", old_blob, new_blob)), plus_minus(compose_fixture.WORKER_DIFF.read_bytes()))
    self.assertEqual(compose.blob(self.repo, commit, TETHER_TEST), new_file(compose.TETHER_WORKER_PATCH.read_bytes(), TETHER_TEST))
    self.assertEqual(compose.blob(self.repo, old_commit, TETHER_TEST), new_file(compose.TETHER_PATCH.read_bytes(), TETHER_TEST))
    compile(compose.blob(self.repo, commit, WIFI), WIFI, "exec")


class TestTetherWorkerPatch(TetherHelpers, unittest.TestCase):
  setUpClass = classmethod(compose_fixture.TestCompose.setUpClass.__func__)
  cli = classmethod(compose_fixture.TestCompose.cli.__func__)
  variant_many = compose_fixture.TestCompose.variant_many
  variant = compose_fixture.TestCompose.variant
  worker_variant = compose_fixture.TestCompose.worker_variant
  apn_upstream = compose_fixture.TestCompose.apn_upstream
  assert_patch_hold = compose_fixture.TestCompose.assert_patch_hold

  def test_worker_form_carries_the_same_wifi_manager_changes(self):
    old, new = (p.read_bytes() for p in (compose.TETHER_PATCH, compose.TETHER_WORKER_PATCH))
    for data in (old, new):
      self.assertEqual(patch_paths(data), compose.TETHER_ALLOWED | {WIFI})
      # Additions only: upstream's lines, including #39339's disable_forward timer, are context.
      self.assertEqual([line for line in plus_minus(data, WIFI) if line.startswith(b"-")], [])
    self.assertEqual(plus_minus(old, WIFI), plus_minus(new, WIFI))
    self.assertIn(b" " + TIMER_LINE, new)
    self.assertNotIn(b"time.sleep", new)

    def tests(data):
      return {line.lstrip(b"+ ")[4:].split(b"(")[0] for line in plus_minus(data, TETHER_TEST) if line.lstrip(b"+ ").startswith(b"def test_")}

    # Every device-tested case is kept, now run from the shared request queue in upstream's test style.
    self.assertEqual(len(tests(old)), 5)
    self.assertLess(tests(old), tests(new))
    added = plus_minus(new, TETHER_TEST)
    for line in (b"+from openpilot.common.test import Mocker, OpenpilotTestCase", b"+    wm._requests.get_nowait()()",
                 b"+    timer = mocker.patch.object(wifi_manager.threading, 'Timer')"):
      self.assertIn(line, added)

  def test_forms_are_exclusive_and_selection_is_read_only(self):
    for upstream, matching in ((self.upstream, compose.TETHER_PATCH), (self.worker_variant(), compose.TETHER_WORKER_PATCH),
                               (self.apn_upstream(), compose.TETHER_PATCH),
                               (self.worker_variant(self.apn_upstream()), compose.TETHER_WORKER_PATCH)):
      other = compose.TETHER_WORKER_PATCH if matching == compose.TETHER_PATCH else compose.TETHER_PATCH
      with self.subTest(upstream=upstream, patch=matching.name), compose.temporary_index(self.repo, upstream) as (env, _):
        compose.apply_ui(self.repo, env)
        before = compose.git(self.repo, "write-tree", env=env)
        self.assertEqual(compose.select_tether_patch(self.repo, env), matching)
        compose.git(self.repo, "apply", "--cached", "--check", "--whitespace=error", str(matching), env=env)
        for reverse in ((), ("--reverse",)):
          with self.assertRaises(subprocess.CalledProcessError):
            compose.git(self.repo, "apply", "--cached", "--check", *reverse, str(other), env=env)
        self.assertEqual(compose.apply_tether(self.repo, env, check=True), "applies cleanly")
        self.assertEqual(compose.git(self.repo, "write-tree", env=env), before)
        self.assertEqual(compose.apply_tether(self.repo, env), "applied")
        applied = compose.git(self.repo, "write-tree", env=env)
        self.assertNotEqual(applied, before)
        # Applied, the form reverse-matches and holds for review; the other form still fits neither way.
        for reverse in ((), ("--reverse",)):
          with self.assertRaises(subprocess.CalledProcessError):
            compose.git(self.repo, "apply", "--cached", "--check", *reverse, str(other), env=env)
        for check in (False, True):
          with self.assertRaisesRegex(ValueError, "^tethering patch already upstream; human review required: ") as raised:
            compose.apply_tether(self.repo, env, check=check)
          self.assertIn(f"{matching.name}: already upstream", str(raised.exception))
        self.assertEqual(compose.git(self.repo, "write-tree", env=env), applied)

  def test_worker_compose_gates_and_parity(self):
    upstream = self.worker_variant()
    flags = ("--tether", "apply")
    result = self.cli("gates.py", upstream, "--skip-download", *flags)
    self.assertIn(G5_WORKER, result.stdout)
    for gate in ("G1", "G2", "G3", "G7"):
      self.assertIn(f"{gate}: OK:", result.stdout)
    self.assertIn("G5: OK: UI patch ui-wpa3.patch applies cleanly\nG5: OK: tethering patch tethering-nat.patch applies cleanly\n",
                  self.cli("gates.py", self.upstream, "--skip-download", *flags).stdout)
    commit, inputs = self.cli("compose.py", upstream, *flags).stdout.splitlines()
    self.assertEqual(self.cli("compose.py", upstream, *flags).stdout.splitlines(), [commit, inputs])
    self.assertEqual(self.cli("compose.py", upstream, *flags, "--inputs-only").stdout.strip(), inputs)
    self.assertEqual(compose.compose(self.repo, upstream, self.resolved, tether="apply"), (commit, inputs))
    message = compose.git(self.repo, "show", "-s", "--format=%B", commit).decode()
    self.assertIn("WPA3-Launcher-Patch: launcher-wpa3.patch\nWPA3-Tethering-Patch: applied\nWPA3-APN-Patch: off\n", message)
    old_commit, old_inputs = compose.compose(self.repo, self.upstream, self.resolved, tether="apply")
    self.assertNotEqual(inputs, old_inputs)
    self.assert_same_tethered_changes(self.upstream, old_commit, upstream, commit)
    # Tethering adds exactly its two files on top of the worker tree, as tethering-nat.patch does on the old tree.
    plain, _ = compose.compose(self.repo, upstream, self.resolved)
    old_plain, _ = compose.compose(self.repo, self.upstream, self.resolved)
    self.assertEqual(self.changed(plain, commit), compose.TETHER_ALLOWED | {WIFI})
    self.assertEqual(self.changed(old_plain, old_commit), compose.TETHER_ALLOWED | {WIFI})
    self.assertEqual(len(compose.blob(self.repo, commit, WIFI).splitlines()) - len(compose.blob(self.repo, plain, WIFI).splitlines()), 18)

  def test_worker_form_already_upstream_holds(self):
    stacked = self.stacked(self.worker_variant())
    with compose.temporary_index(self.repo, stacked) as (env, _):
      before = compose.git(self.repo, "write-tree", env=env)
      for check in (False, True):
        with self.assertRaisesRegex(ValueError, "^tethering patch already upstream; human review required: ") as raised:
          compose.apply_tether(self.repo, env, check=check)
        self.assertIn("tethering-nat-worker.patch: already upstream", str(raised.exception))
      self.assertEqual(compose.git(self.repo, "write-tree", env=env), before)
    upstream = self.commit_tree(stacked, b"Upstream worker tether\n")
    # As with tethering-nat.patch, the UI form's reverse context overlaps _sudo, so the hold comes at the UI check.
    self.assert_patch_hold(upstream, ("--tether", "apply"), "patch does not apply")

  def test_no_form_or_more_than_one_form_holds(self):
    for base, line, drift, ui_name in (
      (self.upstream, SLEEP_LINE, SLEEP_LINE.replace(b"(5)", b"(6)"), "ui-wpa3.patch"),
      (self.worker_variant(), TIMER_LINE, TIMER_LINE.replace(b"(5,", b"(6,"), "ui-wpa3-worker.patch"),
    ):
      data = compose.blob(self.repo, base, WIFI)
      self.assertEqual(data.count(line), 1)
      drifted = self.variant_many({WIFI: data.replace(line, drift)}, base)
      with self.subTest(base=base):
        self.assert_patch_hold(drifted, ("--tether", "apply"), "git apply --check: no tethering patch applies: tethering-nat.patch: git ")
        stderr = self.cli("compose.py", drifted, "--tether", "apply", check=False).stderr
        for candidate in (compose.TETHER_PATCH, compose.TETHER_WORKER_PATCH):
          self.assertIn(f"{candidate.name}: git ", stderr)
        self.assertIn("patch does not apply", stderr)
        held = self.cli("gates.py", drifted, "--skip-download", "--tether", "apply", check=False)
        self.assertIn(f"G5: OK: UI patch {ui_name} applies cleanly\n", held.stdout)
        self.assertNotIn("G5: OK: tethering", held.stdout)
        # Only --tether apply holds: the drift is in tethering context alone.
        self.cli("compose.py", drifted)
        with compose.temporary_index(self.repo, drifted) as (env, _):
          compose.apply_ui(self.repo, env)
          before = compose.git(self.repo, "write-tree", env=env)
          for check in (False, True):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
              compose.apply_tether(self.repo, env, check=check)
            self.assertIn("no tethering patch applies", compose.error_text(raised.exception))
          self.assertEqual(compose.git(self.repo, "write-tree", env=env), before)

    duplicate = self.work / "tethering-nat-copy.patch"
    duplicate.write_bytes(compose.TETHER_PATCH.read_bytes())
    with patch.object(compose, "TETHER_WORKER_PATCH", duplicate):
      with compose.temporary_index(self.repo, self.upstream) as (env, _):
        compose.apply_ui(self.repo, env)
        before = compose.git(self.repo, "write-tree", env=env)
        with self.assertRaisesRegex(ValueError, "more than one tethering patch applies") as raised:
          compose.apply_tether(self.repo, env)
        self.assertEqual(compose.git(self.repo, "write-tree", env=env), before)
      for state in ("tethering-nat.patch: applies cleanly", "tethering-nat-copy.patch: applies cleanly"):
        self.assertIn(state, str(raised.exception))
      for action in (compose.compose, compose.compose_inputs):
        with self.assertRaisesRegex(ValueError, "more than one tethering patch applies"):
          action(self.repo, self.upstream, self.resolved, tether="apply")
      with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO) as stderr:
        self.assertEqual(gates.run_gates(self.repo, self.upstream, self.pin_file, skip_download=True, tether="apply"), 1)
      self.assertIn("G5: FAIL: more than one tethering patch applies", stderr.getvalue())

    # A form already upstream holds even when another form would apply.
    forward = self.work / "tether-forward.patch"
    forward.write_text('diff --git a/new.py b/new.py\nnew file mode 100644\n--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+pass\n')
    stacked = self.stacked(self.upstream)
    with patch.object(compose, "TETHER_WORKER_PATCH", forward), compose.temporary_index(self.repo, stacked) as (env, _):
      with self.assertRaisesRegex(ValueError, "tethering patch already upstream") as raised:
        compose.select_tether_patch(self.repo, env)
      self.assertIn("tethering-nat.patch: already upstream; tether-forward.patch: applies cleanly", str(raised.exception))

  def test_inputs_keep_the_old_form_and_hash_the_worker_form(self):
    launcher = compose.select_launcher_patch(self.repo, self.upstream)
    inputs, payload = self.payload(self.upstream, self.resolved, tether="apply")
    # The old form's payload is exactly what it was before the worker form existed.
    expected = {"upstream": self.upstream, "patches": {launcher.name: sha(launcher), compose.UI_PATCH.name: sha(compose.UI_PATCH)},
                "pin": payload["pin"], "compose.py": compose.LEGACY_COMPOSE_SHA256, "tether": "apply", "tether_patch": sha(compose.TETHER_PATCH)}
    if "wpa_supplicant.copyright" in payload:
      expected["wpa_supplicant.copyright"] = payload["wpa_supplicant.copyright"]
    self.assertEqual(payload, expected)
    self.assertEqual(inputs, compose.inputs_hash(self.upstream, self.resolved, launcher, tether="apply"))
    self.assertEqual(inputs, compose.inputs_hash(self.upstream, self.resolved, launcher, tether="apply", tether_patch=compose.TETHER_PATCH))
    with patch.object(compose, "__file__", str(compose.ROOT / "scripts/gates.py")):
      self.assertEqual(compose.compose_inputs(self.repo, self.upstream, self.resolved, tether="apply"), inputs)

    upstream = self.worker_variant()
    launcher = compose.select_launcher_patch(self.repo, upstream)
    worker_inputs, worker_payload = self.payload(upstream, self.resolved, tether="apply")
    _, plain_payload = self.payload(upstream, self.resolved)
    self.assertEqual(set(worker_payload) - set(plain_payload), {"tether", "tether_patch", "tether_patch_name"})
    self.assertEqual(worker_payload["tether_patch"], sha(compose.TETHER_WORKER_PATCH))
    self.assertEqual(worker_payload["tether_patch_name"], compose.TETHER_WORKER_PATCH.name)
    self.assertEqual(worker_payload["compose.py"], sha(compose.ROOT / "scripts/compose.py"))
    self.assertEqual(worker_inputs, compose.inputs_hash(upstream, self.resolved, launcher, tether="apply", ui_patch=compose.UI_WORKER_PATCH,
                                                        tether_patch=compose.TETHER_WORKER_PATCH))
    self.assertNotEqual(worker_inputs, compose.inputs_hash(upstream, self.resolved, launcher, tether="apply", ui_patch=compose.UI_WORKER_PATCH))
    with patch.object(compose, "__file__", str(compose.ROOT / "scripts/gates.py")):
      self.assertNotEqual(compose.inputs_hash(upstream, self.resolved, launcher, tether="apply", ui_patch=compose.UI_WORKER_PATCH,
                                              tether_patch=compose.TETHER_WORKER_PATCH), worker_inputs)
    copied = self.work / "copied-tether" / compose.TETHER_WORKER_PATCH.name
    copied.parent.mkdir(exist_ok=True)
    copied.write_bytes(compose.TETHER_WORKER_PATCH.read_bytes())
    self.assertEqual(compose.inputs_hash(upstream, self.resolved, launcher, tether="apply", ui_patch=compose.UI_WORKER_PATCH,
                                         tether_patch=copied), worker_inputs)
    copied.write_bytes(copied.read_bytes() + b"\n")
    self.assertNotEqual(compose.inputs_hash(upstream, self.resolved, launcher, tether="apply", ui_patch=compose.UI_WORKER_PATCH,
                                            tether_patch=copied), worker_inputs)
    # The worker tethering form alone already moves off the frozen composer digest.
    with patch.object(compose.json, "dumps", wraps=compose.json.dumps) as dumps:
      compose.inputs_hash(self.upstream, self.resolved, compose.LAUNCHER_PATCHES[0], tether="apply", tether_patch=compose.TETHER_WORKER_PATCH)
    self.assertEqual(dumps.call_args.args[0]["compose.py"], sha(compose.ROOT / "scripts/compose.py"))
    # With tethering off, the selected form is not an input.
    self.assertEqual(compose.inputs_hash(upstream, self.resolved, launcher, ui_patch=compose.UI_WORKER_PATCH, tether_patch=copied),
                     compose.compose_inputs(self.repo, upstream, self.resolved))


class TestTetherWorkerAgnos20(TetherHelpers, unittest.TestCase):
  setUpClass = classmethod(agnos20_fixture.TestAgnos20Compose.setUpClass.__func__)
  cli = classmethod(agnos20_fixture.TestAgnos20Compose.cli.__func__)
  variant_many = agnos20_fixture.TestAgnos20Compose.variant_many
  variant = agnos20_fixture.TestAgnos20Compose.variant
  v0112_variant = agnos20_fixture.TestAgnos20Compose.v0112_variant
  snd_variant = agnos20_fixture.TestAgnos20Compose.snd_variant
  apn_upstream = agnos20_fixture.TestAgnos20Compose.apn_upstream
  modern_fixture = agnos20_fixture.TestAgnos20Compose.modern_fixture
  worker_variant = compose_fixture.TestCompose.worker_variant

  def test_worker_tree_composes_with_tethering_apn_and_modem_bundle(self):
    nb, resolved = self.modern_fixture(raylib_nb=True)
    old = self.snd_variant(nb)
    upstream = self.worker_variant(old)
    pin_file = self.work / "tether-worker-pin.json"
    pin_file.write_text(json.dumps(resolved))
    for family, candidates in compose.APN_AGNOS20_PATCHES.items():
      with self.subTest(family=family):
        old_commit, old_inputs = compose.compose(self.repo, old, resolved, "apply", "auto", family)
        _, old_payload = self.payload(old, resolved, "apply", "auto", family)
        # The old tree keeps 5d8835bd7's frozen composer digest and the two original tethering keys.
        self.assertEqual(old_payload["compose.py"], compose.SND_COMPOSE_SHA256)
        self.assertEqual(old_payload["tether_patch"], sha(compose.TETHER_PATCH))
        self.assertNotIn("tether_patch_name", old_payload)
        commit, inputs = compose.compose(self.repo, upstream, resolved, "apply", "auto", family)
        self.assertEqual(inputs, compose.compose_inputs(self.repo, upstream, resolved, "apply", "auto", family))
        self.assertNotEqual(inputs, old_inputs)
        compose.check_modem_bundle(self.repo, commit, resolved, required=True)
        self.assert_same_tethered_changes(old, old_commit, upstream, commit)
        message = compose.git(self.repo, "show", "-s", "--format=%B", commit).decode()
        self.assertIn(f"WPA3-Launcher-Patch: launcher-wpa3-snd.patch\nWPA3-Tethering-Patch: applied\nWPA3-APN-Patch: {candidates[1].name} applied\n", message)
        result = self.cli("gates.py", upstream, "--skip-download", "--tether", "apply", "--apn", "auto", "--apn-family", family, pin_file=pin_file)
        self.assertIn(G5_WORKER + f"G5: OK: APN patch {candidates[1].name} applies cleanly\n", result.stdout)
        self.assertIn("G9: OK: AGNOS-20 APN UI, stdlib modem override and pinned launcher bundle verified\n", result.stdout)


def load_wifi_manager(source, networkmanager):
  # Execute a composed wifi_manager.py with stand-ins for jeepney and openpilot, without leaving them in sys.modules.
  stubs = {}

  def module(name, **attrs):
    stubs[name] = types.ModuleType(name)
    stubs[name].__dict__.update(attrs)
    return stubs[name]

  for name in ("jeepney.io", "openpilot", "openpilot.common", "openpilot.system", "openpilot.system.ui", "openpilot.system.ui.lib"):
    module(name)
  module("jeepney", DBusAddress=MagicMock(), new_method_call=MagicMock())
  module("jeepney.bus_messages", MatchRule=MagicMock(), message_bus=MagicMock())
  module("jeepney.io.blocking", DBusConnection=MagicMock(), open_dbus_connection=MagicMock())
  module("jeepney.io.threading", DBusRouter=MagicMock(), open_dbus_connection=MagicMock())
  module("jeepney.low_level", MessageType=MagicMock())
  module("jeepney.wrappers", Properties=MagicMock())
  module("openpilot.common.swaglog", cloudlog=MagicMock())
  nm = module("openpilot.system.ui.lib.networkmanager")
  wifi = module("composed_wifi_manager")
  with patch.dict(sys.modules, stubs):
    # Postponed annotations let upstream's `str | None` dataclass fields load on Python < 3.10 as well.
    flags = __future__.annotations.compiler_flag
    exec(compile(networkmanager, NETWORKMANAGER, "exec", flags=flags, dont_inherit=True), nm.__dict__)
    exec(compile(source, WIFI, "exec", flags=flags, dont_inherit=True), wifi.__dict__)
  return wifi


class Device:
  """NetworkManager, iptables-legacy's nat table and the clock, as one WifiManager sees them."""
  def __init__(self, wifi, *, ipv4_forward, rule=False, fail=(), error=None):
    self.events, self.sleeps, self.timers = [], [], []
    self.rules = int(rule)
    self.fail, self.error = fail, error
    wm = wifi.WifiManager.__new__(wifi.WifiManager)
    wm._exit = True
    wm._tethering_ssid = "weedle"
    wm._ipv4_forward = ipv4_forward
    wm.activate_connection = lambda ssid, block=False: self.events.append(("activate", ssid, block))
    wm._deactivate_connection = lambda ssid: self.events.append(("deactivate", ssid))
    wm._requests = queue.Queue()
    self.wm = wm
    log = types.SimpleNamespace(warning=lambda message: self.events.append(("warning", message)),
                                exception=lambda message: self.events.append(("exception", message)))
    stand_ins = types.SimpleNamespace(run=self.run, CalledProcessError=subprocess.CalledProcessError, CompletedProcess=subprocess.CompletedProcess)
    self.patches = [patch.object(wifi, "subprocess", stand_ins), patch.object(wifi, "cloudlog", log),
                    patch.object(wifi, "threading", types.SimpleNamespace(Thread=self.thread, Timer=self.timer)),
                    patch.object(wifi, "time", types.SimpleNamespace(sleep=self.sleep))]

  def __enter__(self):
    for p in self.patches:
      p.start()
    return self

  def __exit__(self, *exc):
    for p in reversed(self.patches):
      p.stop()

  def run(self, cmd, check=False, **kwargs):
    cmd = tuple(cmd)
    self.events.append(("run", cmd))
    returncode = 0
    if cmd[:2] == ("sudo", "iptables-legacy"):
      op = cmd[4]
      if op in self.fail:
        if isinstance(self.error, int):
          returncode = self.error
        else:
          raise self.error
      elif op == "-C":
        returncode = 0 if self.rules else 1
      elif op == "-A":
        self.rules += 1
      elif op == "-D":
        returncode = 0 if self.rules else 1
        self.rules = max(self.rules - 1, 0)
    if check and returncode:
      raise subprocess.CalledProcessError(returncode, cmd)
    return subprocess.CompletedProcess(cmd, returncode)

  def thread(self, target, daemon):
    # tethering-nat.patch's thread per request, run to completion
    return types.SimpleNamespace(start=target)

  def sleep(self, seconds):
    self.sleeps.append(seconds)
    self.events.append(("wait", seconds))

  def timer(self, interval, function):
    self.events.append(("wait", interval))
    timer = types.SimpleNamespace(started=False, function=function)
    timer.start = lambda: setattr(timer, "started", True)
    self.timers.append(timer)
    return timer

  def settle(self):
    # The shared request thread, in queue order
    while not self.wm._requests.empty():
      self.wm._requests.get_nowait()()

  def fire(self):
    timers, self.timers = self.timers, []
    for timer in timers:
      assert timer.started
      timer.function()


class TestTetherRequestBehaviour(unittest.TestCase):
  cli = classmethod(compose_fixture.TestCompose.cli.__func__)

  @classmethod
  def setUpClass(cls):
    compose_fixture.TestCompose.setUpClass.__func__(cls)
    old, _ = compose.compose(cls.repo, cls.upstream, cls.resolved, tether="apply")
    worker, _ = compose.compose(cls.repo, compose_fixture.TestCompose.worker_variant(cls), cls.resolved, tether="apply")
    cls.forms = {name: load_wifi_manager(compose.blob(cls.repo, commit, WIFI), compose.blob(cls.repo, commit, NETWORKMANAGER))
                 for name, commit in (("old", old), ("worker", worker))}
    cls.rule = {op: ("sudo", "iptables-legacy", "-t", "nat", op, *cls.forms["worker"].TETHERING_NAT_RULE) for op in ("-C", "-A", "-D")}

  def sequential(self, form, toggles, **device):
    with Device(self.forms[form], **device) as d:
      for active in toggles:
        d.wm.set_tethering_active(active)
        d.settle()
        d.fire()
      return d.events, d.rules

  def test_stand_ins_do_not_leak(self):
    for name in ("jeepney", "openpilot", "openpilot.system.ui.lib.networkmanager", "composed_wifi_manager"):
      self.assertNotIn(name, sys.modules)
    self.assertEqual(self.forms["old"].TETHERING_NAT_RULE, self.forms["worker"].TETHERING_NAT_RULE)

  def test_sequential_toggles_match_the_device_tested_form(self):
    on = [("activate", "weedle", True), ("run", self.rule["-C"]), ("run", self.rule["-A"])]
    self.assertEqual(self.sequential("worker", (True,), ipv4_forward=False),
                     (on + [("wait", 5), ("warning", "net.ipv4.ip_forward = 0"), ("run", SYSCTL)], 1))
    self.assertEqual(self.sequential("worker", (True, False), ipv4_forward=True),
                     (on + [("deactivate", "weedle"), ("run", self.rule["-D"])], 0))
    failures = ((), {}), (("-C", "-A", "-D"), {"error": FileNotFoundError("iptables-legacy")}), (("-A",), {"error": 4})
    for toggles in ((True,), (False,), (True, False), (False, True), (True, True), (True, False, True), (True, False, True, False)):
      for ipv4_forward in (False, True):
        for rule in (False, True):
          for fail, extra in failures:
            with self.subTest(toggles=toggles, ipv4_forward=ipv4_forward, rule=rule, fail=fail):
              device = dict(ipv4_forward=ipv4_forward, rule=rule, fail=fail, **extra)
              self.assertEqual(self.sequential("worker", toggles, **device), self.sequential("old", toggles, **device))

  def test_requests_run_in_order_and_never_sleep(self):
    with Device(self.forms["worker"], ipv4_forward=False) as d:
      for active in (True, False, True):
        d.wm.set_tethering_active(active)
      self.assertEqual(d.events, [])  # nothing runs on the caller's (UI) thread
      d.settle()
      on = [("activate", "weedle", True), ("run", self.rule["-C"]), ("run", self.rule["-A"]), ("wait", 5)]
      self.assertEqual(d.events, on + [("deactivate", "weedle"), ("run", self.rule["-D"])] + on)
      self.assertEqual(d.rules, 1)
      self.assertEqual(d.sleeps, [])
      self.assertEqual(len(d.timers), 2)
      # The first timer fires after tethering was turned on again: both only turn forwarding off.
      d.fire()
      self.assertEqual(d.events[10:], [("warning", "net.ipv4.ip_forward = 0"), ("run", SYSCTL)] * 2)
      self.assertEqual(d.rules, 1)

  def test_on_off_within_the_timer_leaves_no_rule(self):
    for toggles, rules, adds in (((True, False), 0, 1), ((False, True, False), 0, 1), ((True, True), 1, 1), ((True, False, True, False, True), 1, 3)):
      with self.subTest(toggles=toggles), Device(self.forms["worker"], ipv4_forward=False) as d:
        for active in toggles:
          d.wm.set_tethering_active(active)
        d.settle()
        before = list(d.events)
        d.fire()
        self.assertEqual(d.events[len(before):], [("warning", "net.ipv4.ip_forward = 0"), ("run", SYSCTL)] * toggles.count(True))
        self.assertEqual(d.rules, rules)
        self.assertEqual(d.events.count(("run", self.rule["-A"])), adds)
        self.assertEqual(d.sleeps, [])

  def test_with_forwarding_no_timer(self):
    with Device(self.forms["worker"], ipv4_forward=True) as d:
      d.wm.set_tethering_active(True)
      d.settle()
      self.assertEqual(d.timers, [])
      self.assertNotIn(("run", SYSCTL), d.events)

  def test_rule_failure_still_turns_forwarding_off(self):
    for fail, error, logged in ((("-A",), 4, [("exception", "Failed to add tethering NAT rule")]),
                                (("-C", "-A", "-D"), FileNotFoundError("sudo"), [("exception", "Failed to add tethering NAT rule")]),
                                (("-C", "-A", "-D"), PermissionError("sudo"), [("exception", "Failed to add tethering NAT rule")])):
      with self.subTest(fail=fail, error=error), Device(self.forms["worker"], ipv4_forward=False, fail=fail, error=error) as d:
        d.wm.set_tethering_active(True)
        d.settle()
        self.assertEqual([e for e in d.events if e[0] == "exception"], logged)
        self.assertEqual(d.events[-1], ("wait", 5))
        d.fire()
        self.assertEqual(d.events[-1], ("run", SYSCTL))
        d.wm.set_tethering_active(False)
        d.settle()
        self.assertEqual(d.events[-1][0], "exception" if isinstance(error, OSError) else "run")

  def test_stale_timer_keeps_upstreams_forwarding_rule(self):
    # Upstream's timer does not re-check _ipv4_forward, as time.sleep did not before #39339; the fork leaves comma's rule as is.
    with Device(self.forms["worker"], ipv4_forward=False) as d:
      d.wm.set_tethering_active(True)
      d.settle()
      d.wm.set_ipv4_forward(True)
      d.wm.set_tethering_active(False)
      d.wm.set_tethering_active(True)
      d.settle()
      self.assertEqual(len(d.timers), 1)
      count = len(d.events)
      d.fire()
      self.assertEqual(d.events[count:], [("warning", "net.ipv4.ip_forward = 0"), ("run", SYSCTL)])
      self.assertEqual(d.rules, 1)


if __name__ == "__main__":
  unittest.main()
