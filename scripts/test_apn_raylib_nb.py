#!/usr/bin/env python3
"""Offline APN candidate, bundle and input-identity checks across #39193."""
import hashlib
import json
import re
import subprocess
import unittest
from unittest.mock import patch

import compose
import test_modem_agnos20 as fixture


def tuple_positions(added):
  # Deliberately a lint: catch simple inline/multiline tuple positions, not Python syntax.
  lines = re.sub(r",\s*\n\s*", ", ", added)
  return re.findall(r"rl\.(?:draw_\w+|check_collision_\w+)\((?:[^\n]*?,[ \t]*)?\([^()\n]*,", lines)


class TestApnRaylibNb(unittest.TestCase):
  setUpClass = classmethod(fixture.TestAgnos20Compose.setUpClass.__func__)
  cli = classmethod(fixture.TestAgnos20Compose.cli.__func__)
  variant_many = fixture.TestAgnos20Compose.variant_many
  variant = fixture.TestAgnos20Compose.variant
  v0112_variant = fixture.TestAgnos20Compose.v0112_variant
  apn_upstream = fixture.TestAgnos20Compose.apn_upstream
  modern_fixture = fixture.TestAgnos20Compose.modern_fixture

  def stacked(self, upstream):
    with compose.temporary_index(self.repo, upstream) as (env, _):
      compose.apply_ui(self.repo, env)
      compose.apply_tether(self.repo, env)
      return compose.git(self.repo, "write-tree", env=env).decode().strip()

  def test_exactly_one_candidate_per_family_and_binding(self):
    for nb in (False, True):
      upstream, _ = self.modern_fixture(raylib_nb=nb)
      tree = self.stacked(upstream)
      for family, candidates in compose.APN_AGNOS20_PATCHES.items():
        with self.subTest(nb=nb, family=family):
          matches = []
          for candidate in candidates:
            with compose.temporary_index(self.repo, tree) as (env, _):
              try:
                compose.git(self.repo, "apply", "--cached", "--check", "--whitespace=error", str(candidate), env=env)
              except subprocess.CalledProcessError:
                pass
              else:
                matches.append(candidate)
          self.assertEqual(matches, [candidates[int(nb)]])
          self.assertEqual(compose.select_apn_patch(self.repo, tree, family), matches[0])

  def test_nb_compose_g5_g9_and_functional_parity(self):
    old, resolved = self.modern_fixture()
    upstream, _ = self.modern_fixture(raylib_nb=True)
    pin_file = self.work / "raylib-nb-pin.json"
    pin_file.write_text(json.dumps(resolved))
    for family, candidates in compose.APN_AGNOS20_PATCHES.items():
      with self.subTest(family=family):
        old_commit, _ = compose.compose(self.repo, old, resolved, "apply", "auto", family)
        commit, inputs = compose.compose(self.repo, upstream, resolved, "apply", "auto", family)
        self.assertEqual(inputs, compose.compose_inputs(self.repo, upstream, resolved, "apply", "auto", family))
        self.assertNotEqual(inputs, compose.inputs_hash(upstream, resolved, compose.select_launcher_patch(self.repo, upstream),
                                                       "apply", "auto", candidates[0], family))
        compose.check_modem_bundle(self.repo, commit, resolved, required=True)
        for path in compose.APN_ALLOWED - {"openpilot/common/hardware/comma/modem.py"}:
          self.assertEqual(compose.blob(self.repo, old_commit, path).replace(b"import pyray as rl", b"import raylib_nb as rl"),
                           compose.blob(self.repo, commit, path), path)
        result = self.cli("gates.py", upstream, "--skip-download", "--tether", "apply", "--apn", "auto",
                          "--apn-family", family, pin_file=pin_file)
        self.assertIn(f"G5: OK: APN patch {candidates[1].name} applies cleanly", result.stdout)
        self.assertIn("G9: OK: AGNOS-20 APN UI, stdlib modem override and pinned launcher bundle verified", result.stdout)
        # All registered forms must be reverse-checked, including the other family.
        tree = self.stacked(upstream)
        with compose.temporary_index(self.repo, tree) as (env, _):
          compose.git(self.repo, "apply", "--cached", str(candidates[1]), env=env)
          applied = compose.git(self.repo, "write-tree", env=env).decode().strip()
          for selected_family in compose.APN_AGNOS20_PATCHES:
            with self.assertRaisesRegex(ValueError, "APN patch already upstream"):
              compose.select_apn_patch(self.repo, applied, selected_family)

  def test_pyray_identity_matches_4a387959c(self):
    upstream, resolved = self.modern_fixture()
    self.assertEqual(upstream, "1c793f3cb0f9ae2396e94ccd874353f62568bd31")
    # Captured by executing the unmodified 4a387959c composer, before this change.
    for family, tether, apn, commit, inputs, tree in (
      ("nightly", "off", "off", "673a74b7989a99329aae4abc55dc62b13dc6911c", "e32f917f1d4012b881ce6a3201351f23652341df33dc4ad9bc004e8094ed3470", "452093b1ef160846a4e9339a3e003746f3cc03bc"),
      ("nightly", "apply", "auto", "4b4b73220eb495dfb1c494291c8a5e953187de91", "3cf14eb8f7e02ee7c774cb2c5b560208309c9b55113eab5d86430ee157d86e7e", "0db53fd5366461ec2e0a64e9352c15087a8368bd"),
      ("release", "off", "off", "f264a6b3ecfb486a3860e2c00eacfd75d731ec90", "ce25b5b66455f1b9a71eff6415e3376a9494f77b955036ed42b03523071a340b", "452093b1ef160846a4e9339a3e003746f3cc03bc"),
      ("release", "apply", "auto", "ff7cd48e90a2848df9795a1b4b6e90b365c09d97", "353f37e197430d4e891598ef508568f7addf7b8fac2c3e4399c8a01bf6689fec", "04b8b0caacfbf7f692d517c9c4d764d29657c38f"),
    ):
      with self.subTest(family=family, tether=tether, apn=apn):
        self.assertEqual(compose.compose(self.repo, upstream, resolved, tether, apn, family), (commit, inputs))
        self.assertEqual(compose.git(self.repo, "rev-parse", commit + "^{tree}").decode().strip(), tree)

  def test_composer_digest_is_frozen_only_for_existing_paths(self):
    upstream, resolved = self.modern_fixture()
    launcher = compose.select_launcher_patch(self.repo, upstream)
    old, nb = compose.APN_AGNOS20_PATCHES["nightly"]
    before = [compose.inputs_hash(upstream, resolved, launcher, apn="auto", apn_patch=p) for p in (old, nb)]
    with patch.object(compose, "__file__", str(compose.ROOT / "scripts/gates.py")):
      after = [compose.inputs_hash(upstream, resolved, launcher, apn="auto", apn_patch=p) for p in (old, nb)]
    self.assertEqual(before[0], after[0])
    self.assertNotEqual(before[1], after[1])
    # The constant is the actual unmodified 4a387959c composer SHA, not a candidate-list hash.
    self.assertEqual(compose.PYRAY_COMPOSE_SHA256, "9c8211c33bdb984cfbc4c5bc5ba9cffe8b3c52e5a52e2948c4b66aada79ab41d")
    self.assertNotEqual(compose.PYRAY_COMPOSE_SHA256, hashlib.sha256(compose.ROOT.joinpath("scripts/compose.py").read_bytes()).hexdigest())

  def test_nb_patch_static_api_lint(self):
    for candidates in compose.APN_AGNOS20_PATCHES.values():
      candidate = candidates[1]
      text = candidate.read_text()
      with self.subTest(candidate=candidate.name):
        self.assertNotRegex(text, r"\b(?:import|from) pyray\b")
        for section in text.split("diff --git ")[1:]:
          path = section.splitlines()[0].split(" b/", 1)[1]
          if not path.endswith(".py"):
            continue
          added = "\n".join(line[1:] for line in section.splitlines() if line.startswith("+") and not line.startswith("+++"))
          if "new file mode" in section.split("@@", 1)[0] and "rl." in added:
            self.assertIn("import raylib_nb as rl", added, path)
          self.assertFalse(tuple_positions(added), path)
        self.assertIn(" import raylib_nb as rl", text)

  def test_tuple_position_lint_examples(self):
    for source in ("rl.draw_text_ex(font, text, (x, y), 40, 0, rl.WHITE)",
                   "rl.draw_texture_ex(texture,\n  (x, y), 0, 1, rl.WHITE)",
                   "rl.check_collision_point_rec((x, y), rect)",
                   "rl.draw_line_ex(start, (x, y), 3, rl.WHITE)"):
      self.assertTrue(tuple_positions(source), source)
    self.assertFalse(tuple_positions("rl.draw_text_ex(font, text, rl.Vector2(x, y), 40, 0, rl.WHITE)"))


if __name__ == "__main__":
  unittest.main()
