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
from test_ui_worker import plus_minus

JA_PO = "openpilot/selfdrive/ui/translations/app_ja.po"
# comma's 0.11.3 release (52b2b6265, 2026-11-20) appends these four entries, verbatim, after "✓ SUBSCRIBED".
EXPMODE_JA_TAIL = (
  '#: openpilot/selfdrive/ui/layouts/settings/toggles.py\n'
  'msgid "Enable the openpilot longitudinal control (alpha) toggle to allow Experimental mode."\n'
  'msgstr "openpilot縦制御（アルファ）のトグルを有効にすると実験モードが使用できます。"\n'
  '\n'
  '#: openpilot/selfdrive/ui/layouts/settings/toggles.py\n'
  'msgid "Experimental Mode"\n'
  'msgstr "実験モード"\n'
  '\n'
  '#: openpilot/selfdrive/ui/layouts/settings/toggles.py\n'
  'msgid "Experimental mode is currently unavailable on this car since the car\'s stock ACC is used for longitudinal control."\n'
  'msgstr "この車では縦制御に純正ACCを使用するため、現在実験モードは利用できません。"\n'
  '\n'
  '#: openpilot/selfdrive/ui/layouts/settings/toggles.py\n'
  'msgid "openpilot longitudinal control may come in a future update."\n'
  'msgstr "openpilotの縦制御は将来のアップデートで提供される可能性があります。"\n'
).encode()


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
  snd_variant = fixture.TestAgnos20Compose.snd_variant
  worker_variant = fixture.compose_fixture.TestCompose.worker_variant
  apn_upstream = fixture.TestAgnos20Compose.apn_upstream
  modern_fixture = fixture.TestAgnos20Compose.modern_fixture

  def stacked(self, upstream):
    with compose.temporary_index(self.repo, upstream) as (env, _):
      compose.apply_ui(self.repo, env)
      compose.apply_tether(self.repo, env)
      return compose.git(self.repo, "write-tree", env=env).decode().strip()

  def expmode_variant(self, upstream):
    # The release catalog's new end: the four entries follow the old last entry and its blank line.
    data = compose.blob(self.repo, upstream, JA_PO)
    self.assertTrue(data.endswith('msgid "✓ SUBSCRIBED"\nmsgstr "✓ 登録済み"\n\n'.encode()))
    return self.variant_many({JA_PO: data + EXPMODE_JA_TAIL}, upstream)

  def changed(self, upstream, commit):
    return set(compose.git(self.repo, "diff-tree", "--no-commit-id", "-r", "--name-only", upstream, commit).decode().splitlines())

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
    old, nb = compose.APN_AGNOS20_PATCHES["nightly"]
    snd = self.snd_variant(upstream)
    worker = self.worker_variant(snd)
    expmode = compose.APN_RELEASE_EXPMODE_PATCH
    # Since apn-auth-release-agnos20-nb-expmode.patch, worker trees are frozen at fe9cfa498 for the older APN forms;
    # only the expmode form hashes the live composer, with either UI form.
    for base, ui_patch, apn_patches, sensitive in ((upstream, compose.UI_PATCH, (old, nb), False), (snd, compose.UI_PATCH, (old, nb), False),
                                                   (worker, compose.UI_WORKER_PATCH, (old, nb), False),
                                                   (snd, compose.UI_PATCH, (expmode,), True), (worker, compose.UI_WORKER_PATCH, (expmode,), True)):
      with self.subTest(base=base, ui=ui_patch.name, apn=[p.name for p in apn_patches]):
        launcher = compose.select_launcher_patch(self.repo, base)
        with compose.temporary_index(self.repo, base) as (env, _):
          self.assertEqual(compose.select_ui_patch(self.repo, env)[0], ui_patch)
        before = [compose.inputs_hash(base, resolved, launcher, apn="auto", apn_patch=p, ui_patch=ui_patch) for p in apn_patches]
        with patch.object(compose, "__file__", str(compose.ROOT / "scripts/gates.py")):
          after = [compose.inputs_hash(base, resolved, launcher, apn="auto", apn_patch=p, ui_patch=ui_patch) for p in apn_patches]
        for previous, current in zip(before, after):
          self.assertEqual(previous != current, sensitive)
    # The constant is the actual unmodified 4a387959c composer SHA, not a candidate-list hash.
    self.assertEqual(compose.PYRAY_COMPOSE_SHA256, "9c8211c33bdb984cfbc4c5bc5ba9cffe8b3c52e5a52e2948c4b66aada79ab41d")
    self.assertNotEqual(compose.PYRAY_COMPOSE_SHA256, hashlib.sha256(compose.ROOT.joinpath("scripts/compose.py").read_bytes()).hexdigest())
    self.assertEqual(compose.RAYLIB_NB_COMPOSE_SHA256, "1b96625831a00de86615c0200a95bf5c78acc96ea7c8041c18f1309f51ed2eff")
    # git show 5d8835bd7:scripts/compose.py | shasum -a 256
    self.assertEqual(compose.SND_COMPOSE_SHA256, "007dd6955da3037054ee86464a4b68554c0dc0ad7420b5b77004b2c325736161")
    self.assertNotEqual(compose.SND_COMPOSE_SHA256, hashlib.sha256(compose.ROOT.joinpath("scripts/compose.py").read_bytes()).hexdigest())
    # git show fe9cfa498:scripts/compose.py | shasum -a 256 (unchanged through 873ca9682)
    self.assertEqual(compose.WORKER_COMPOSE_SHA256, "e65e8bed2237556c44b5dc01c07f3575d6c992bd1ce82cec9f4c5277295bfecd")
    self.assertNotEqual(compose.WORKER_COMPOSE_SHA256, hashlib.sha256(compose.ROOT.joinpath("scripts/compose.py").read_bytes()).hexdigest())

  def test_worker_identity_is_unchanged_since_fe9cfa498(self):
    # Captured by executing the unmodified 873ca9682 composer (compose.py e65e8bed, last changed in fe9cfa498),
    # before apn-auth-release-agnos20-nb-expmode.patch.
    nb_upstream, nb_resolved = self.modern_fixture(raylib_nb=True)
    nb = (self.worker_variant(self.snd_variant(nb_upstream)), nb_resolved)
    legacy = (self.worker_variant(), self.resolved)
    for (upstream, resolved), family, tether, apn, commit, inputs, tree in (
      (nb, "nightly", "apply", "auto", "ea8a1685ca28457827926966867e9b7ed10dba03", "f03d2188ce3f2f4d4d0e1722bbd0165bc809eb222c636d1534d1cd90160aaf53", "e791331e54c2874e456e30567d89aa55b0c8ef09"),
      (nb, "nightly", "off", "auto", "8d664b38505bb495f657fd6cb20b994f2cc744ce", "78f103bab3afe6f2a949ceccef41eb9a189656583cc35b02e09517021be512ba", "6764b8eef854c5bdf8ebafbd645f04a236a09c45"),
      (nb, "nightly", "apply", "off", "f19ab9fdfdbce1a5ed234860a66182740e294a7f", "416dcde8a34a2527fc17d2969b1a976fc5f0d11fabf4e8c5de605abbb879a54a", "20a061580e4fbb4ada618ebe461f6cfca548493a"),
      (nb, "nightly", "off", "off", "842adf3df343e5c7f364a0eba43f1f42c5961b90", "74b13f4178eb01c17c35412fa3a95c0103f6d65c842b8f7f2ff0116dd751fd37", "5d191410ad0fa41990b6dc5b5fab89981dc371a1"),
      (nb, "release", "apply", "auto", "189d68119e22a5ba2b75f54c057d4842e5e41197", "c6683f0e32f99ed98883bdbb829782e561b491ed8efd4f8b3ca2e8e5ab30e04f", "4bce95a656e2269e8df608330035f6429ae0e602"),
      (nb, "release", "off", "auto", "05f92a7278ff5e0050741418ec0541bbd29c85f2", "deed01d0632f7e8374b0fd808e86ac66f27cc362d71e637ce185e662a3effe00", "e8920440e6d1087f6d654f5feafa160b9f394eb7"),
      (nb, "release", "apply", "off", "ef7d8e3a2eb31036e6671740a14058f571ae5ec3", "cab05b6c4f502356f1e5889c1862f778478fdfa704c0bfbe89b59424a94f4219", "20a061580e4fbb4ada618ebe461f6cfca548493a"),
      (nb, "release", "off", "off", "e0a4fef084a20ae937348e8e466808c9cd42c8fd", "a0f80681bf12c2da650a4f5c2ba4c0ea6a1a798f77651899e6d7dc31bf01eacc", "5d191410ad0fa41990b6dc5b5fab89981dc371a1"),
      (legacy, "nightly", "apply", "off", "0f2e2f8a557839aab34bd7a67966662e039863b5", "0cb0317e8548664930532e193bf3d5ee2cf5e60243fce53e5f2614a2e795a3ed", "ddb6d74841fa6d4bf05cc552aaed250e5daadeeb"),
      (legacy, "nightly", "off", "off", "f6f07537b112d85f21d3dd0ec261f27734eb6d98", "1efe17e5bab845bdd2b239ea8914380052fa67efc6ae31c12b175cd5d3f8172b", "d58084b82cfbe94298adbc3ddc845d0e0bc05472"),
    ):
      with self.subTest(upstream=upstream, family=family, tether=tether, apn=apn):
        self.assertEqual(compose.compose(self.repo, upstream, resolved, tether, apn, family), (commit, inputs))
        self.assertEqual(compose.compose_inputs(self.repo, upstream, resolved, tether, apn, family), inputs)
        self.assertEqual(compose.git(self.repo, "rev-parse", commit + "^{tree}").decode().strip(), tree)

  def test_expmode_patch_is_the_nb_patch_reanchored(self):
    nb, expmode = (patch_file.read_bytes() for patch_file in (compose.APN_AGNOS20_PATCHES["release"][1], compose.APN_RELEASE_EXPMODE_PATCH))
    self.assertEqual(compose.APN_AGNOS20_PATCHES["release"][2], compose.APN_RELEASE_EXPMODE_PATCH)
    nb_sections, expmode_sections = (dict((s.split(b"\n", 1)[0], s) for s in text.split(b"diff --git ")[1:]) for text in (nb, expmode))
    self.assertEqual(list(nb_sections), list(expmode_sections))
    for header, section in nb_sections.items():
      if not header.endswith(b" b/" + JA_PO.encode()):
        self.assertEqual(expmode_sections[header], section, header)
    # In app_ja.po only the blob index, the hunk header and the three context lines differ; the 51 added lines are the same.
    self.assertEqual(plus_minus(expmode, JA_PO), plus_minus(nb, JA_PO))
    self.assertEqual(len(plus_minus(expmode, JA_PO)), 51)
    section = next(s for h, s in expmode_sections.items() if h.endswith(b" b/" + JA_PO.encode()))
    self.assertEqual([line for line in section.splitlines() if line.startswith(b" ")],
                     [b" " + line for line in EXPMODE_JA_TAIL.splitlines()[-3:]])
    self.assertEqual(sum(line.startswith(b"@@ ") for line in section.splitlines()), 1)

  def test_expmode_release_form_composes_the_same_changes(self):
    nb, resolved = self.modern_fixture(raylib_nb=True)
    old = self.worker_variant(self.snd_variant(nb))
    upstream = self.expmode_variant(old)
    expmode = compose.APN_RELEASE_EXPMODE_PATCH
    pin_file = self.work / "expmode-pin.json"
    pin_file.write_text(json.dumps(resolved))
    # Exactly one release form fits each catalog end; no nightly form fits the new one.
    self.assertEqual(compose.select_apn_patch(self.repo, self.stacked(old), "release"), compose.APN_AGNOS20_PATCHES["release"][1])
    tree = self.stacked(upstream)
    self.assertEqual(compose.select_apn_patch(self.repo, tree, "release"), expmode)
    with self.assertRaisesRegex(ValueError, "no APN patch applies"):
      compose.select_apn_patch(self.repo, tree, "nightly")
    old_commit, _ = compose.compose(self.repo, old, resolved, "apply", "auto", "release")
    commit, inputs = compose.compose(self.repo, upstream, resolved, "apply", "auto", "release")
    self.assertEqual(inputs, compose.compose_inputs(self.repo, upstream, resolved, "apply", "auto", "release"))
    compose.check_modem_bundle(self.repo, commit, resolved, required=True)
    message = compose.git(self.repo, "show", "-s", "--format=%B", commit).decode()
    self.assertIn(f"WPA3-Launcher-Patch: launcher-wpa3-snd.patch\nWPA3-Tethering-Patch: applied\nWPA3-APN-Patch: {expmode.name} applied\n", message)
    # The same composed changes: every other path is byte-identical, and both catalogs get the same appended bytes.
    changed = self.changed(upstream, commit)
    self.assertEqual(changed, self.changed(old, old_commit))
    self.assertIn(JA_PO, changed)
    for path in sorted(changed - {JA_PO}):
      if compose.git(self.repo, "ls-tree", commit, "--", path):
        self.assertEqual(compose.blob(self.repo, commit, path), compose.blob(self.repo, old_commit, path), path)
    appended = []
    for base, composed in ((old, old_commit), (upstream, commit)):
      before, after = compose.blob(self.repo, base, JA_PO), compose.blob(self.repo, composed, JA_PO)
      self.assertTrue(after.startswith(before))
      appended.append(after[len(before):])
    self.assertEqual(appended[0], appended[1])
    catalog = compose.blob(self.repo, commit, JA_PO).splitlines()
    for line in plus_minus(expmode.read_bytes(), JA_PO):
      if line.startswith(b"+msgid "):
        self.assertEqual(catalog.count(line[1:]), 1, line)
    # The new selection hashes the live composer.
    with patch.object(compose, "__file__", str(compose.ROOT / "scripts/gates.py")):
      self.assertNotEqual(compose.compose_inputs(self.repo, upstream, resolved, "apply", "auto", "release"), inputs)
    result = self.cli("gates.py", upstream, "--skip-download", "--tether", "apply", "--apn", "auto", "--apn-family", "release", pin_file=pin_file)
    self.assertIn(f"G5: OK: APN patch {expmode.name} applies cleanly\n", result.stdout)
    self.assertIn("G9: OK: AGNOS-20 APN UI, stdlib modem override and pinned launcher bundle verified\n", result.stdout)
    held = self.cli("gates.py", upstream, "--skip-download", "--tether", "apply", "--apn", "auto", "--apn-family", "nightly",
                    pin_file=pin_file, check=False)
    self.assertEqual(held.returncode, 1)
    self.assertIn("G5: FAIL: no APN patch applies", held.stderr)
    # Once applied, every registered form reports it as already upstream.
    with compose.temporary_index(self.repo, tree) as (env, _):
      compose.git(self.repo, "apply", "--cached", str(expmode), env=env)
      applied = compose.git(self.repo, "write-tree", env=env).decode().strip()
    for family in compose.APN_AGNOS20_PATCHES:
      with self.assertRaisesRegex(ValueError, "APN patch already upstream"):
        compose.select_apn_patch(self.repo, applied, family)

  def test_snd_nb_identity_is_unchanged_for_the_old_ui_form(self):
    # Captured by executing the unmodified 6853d5bab composer (compose.py 007dd695), before ui-wpa3-worker.patch.
    nb, resolved = self.modern_fixture(raylib_nb=True)
    pyray, _ = self.modern_fixture()
    for upstream, family, tether, apn, commit, inputs, tree in (
      (nb, "nightly", "apply", "auto", "fbd28dfb7ce6d3a7afa98c2aadbd526ea7e2e902", "2644c4408e10f97cca775f998ea9fe7b87c07714d14c26a988ff84ed68156712", "7de663cff9156fab2e43d181a2cb544cb7cbe8c1"),
      (nb, "nightly", "off", "auto", "4238085bb0522a6fab035ae012c504b2e78d4aa9", "c6d7fdd8e5ff9bfd2cb48c71fa9f23707ec89d297ec96f141965a909d5f141fc", "b4323e2d88568452e3c868cb7694b5cefda757b2"),
      (nb, "nightly", "off", "off", "6da2c0e33a2fa0a8bb5f5f1065096f0d5d77f945", "271841b7181461c7c7bdbd16b006e5848e28e0fe8722492726fe72578a4991e3", "03380c5c5989e8bb39e38ebb006de32bec8d05fd"),
      (nb, "release", "apply", "auto", "e1f112a7ab8124bb567abb8e8e04db95c720e521", "bde67555402f0e311016d76d3454aa49d978975fadab240de57546b780eb57db", "71ec7221063c3d75e0a14c819b2bbe5d837f1ee4"),
      (nb, "release", "off", "auto", "5cb1610b8cdb7048940dada1dc636f9e579f0830", "087e072880e6a3b6fe22a937757989f5c16f06dbd5842858d89f7303418ef39c", "0036ca6c6f96513a3e2f981d57ca27ff1fbb46e9"),
      (nb, "release", "off", "off", "6d908ca43d69b26e68a697126ba350d77161c4d5", "4e70a2b5badddb48151a2989f0383f60121717f0f813b6134fd5a6fc237ab70a", "03380c5c5989e8bb39e38ebb006de32bec8d05fd"),
      (pyray, "nightly", "apply", "auto", "8699a30ede72fe4cce37f3f96898d7042345cc50", "03f206bb3cc5ed1d3adf51e311d135a26a8de682d7b101b461a64cd15a9133f1", "47a7bdbe1ed76b1b12d688f6f9e1e613fe242e29"),
      (pyray, "nightly", "off", "off", "bbc30fc495ee4fe66395fdb900ed1dfc758804e2", "40ccbc6f79da008af5acf4436c8ffd4915648051796001f35d4ecd5d4138a3d9", "97558aed367ed36927832a34a4402b6b14b06e50"),
      (pyray, "release", "apply", "auto", "b25c5008402fc7cea95545f52f8802774ec489e5", "8027b0846f7e2ac6a8e8fafb2dea845a62e17781de17781599ee4e085b676a45", "278ed294ed7ceb287e8c917c620718723017357a"),
      (pyray, "release", "off", "off", "30daf840346d6e38f328cf38f7cdb491dfc2fde6", "50750e1cee0840024eba66371ffb49908cc4f6b10104f03919080e29a22b1f9f", "97558aed367ed36927832a34a4402b6b14b06e50"),
    ):
      base = self.snd_variant(upstream)
      with self.subTest(upstream=upstream, family=family, tether=tether, apn=apn):
        self.assertEqual(compose.compose(self.repo, base, resolved, tether, apn, family), (commit, inputs))
        self.assertEqual(compose.compose_inputs(self.repo, base, resolved, tether, apn, family), inputs)
        self.assertEqual(compose.git(self.repo, "rev-parse", commit + "^{tree}").decode().strip(), tree)

  def test_nb_identity_is_unchanged_for_existing_launchers(self):
    upstream, resolved = self.modern_fixture(raylib_nb=True)
    release = self.variant_many({"launch_chffrplus.sh": (fixture.compose_fixture.RELEASE_REF / "launch_chffrplus.sh").read_bytes()}, upstream)
    bases = (upstream, release, self.v0112_variant(upstream), self.v0112_variant(release))
    # Captured from the unmodified 8010c379b composer.
    for index, family, commit, inputs in (
      (0, "nightly", "4784c931e4887687984a6068b702ae5cfa5f510f", "de8b6c4246ba49fbdd5795cd9b63975dfc57f19fcafc1a7904634a9336846b47"),
      (0, "release", "09731bc8fc95471f19cd4ef5fb112ac3d88094a1", "5d3849aa9ca102bcf906b2a1067edce5b5f56b9f9760806e2bba9ac5efe47975"),
      (1, "nightly", "800580173babadf456219c9e66017e64e9f6a801", "b9bd3c37e40df2556b7bc1ccd07a56a9d3ebc06d7333f08764dbd2993b5d17b0"),
      (1, "release", "c91469acaa3e07fd056f1d793d76c30fbfc7e2f1", "7b435bf381ecb5711dc821a56a02f1e28f865d75f0ea68cd55473a1e516b4e52"),
      (2, "nightly", "bd049767c471803260c774e3c0453ca7cc928625", "012a78ee759a1d781812a70b7bab806b32082494a8065bda986cc2aec2f28827"),
      (2, "release", "bad281da1cb6c61d1b37f33eb6e927f499335107", "808b24a7b02e96315faf7ccd6062bdf5b6bd4fa1ced40b441740548f49d82d3e"),
      (3, "nightly", "bdf74b05d1ac56498472f60f8c3c8682ed7a8ed7", "710f008fc02ff2bfa51022a2a438ec6065a745763c566c4bbd796ef1f7fbd3cc"),
      (3, "release", "fb0413e9057127029a296036ab8df83f11d22709", "ad1dde8705539807b0f35f0e7c78581881caf20efd5960b62369cb97d9ac7e72"),
    ):
      with self.subTest(launcher=index, family=family):
        self.assertEqual(compose.compose(self.repo, bases[index], resolved, "apply", "auto", family), (commit, inputs))

  def test_nb_patch_static_api_lint(self):
    for candidate in (c for candidates in compose.APN_AGNOS20_PATCHES.values() for c in candidates[1:]):
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
