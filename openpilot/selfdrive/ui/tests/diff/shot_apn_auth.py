#!/usr/bin/env python3
"""Capture APN auth settings with isolated params and credential storage using the desktop raylib backend.

SCALE=1 python3 openpilot/selfdrive/ui/tests/diff/shot_apn_auth.py /tmp/apn_auth_shots/mici
BIG=1 SCALE=0.75 python3 openpilot/selfdrive/ui/tests/diff/shot_apn_auth.py /tmp/apn_auth_shots/tizi
Add --lang ja to render translated strings in Japanese.
"""
import argparse
import os
from collections.abc import Callable
from copy import deepcopy
from tempfile import TemporaryDirectory
from pathlib import Path

BIG = os.getenv("BIG") == "1"
os.environ.setdefault("SCALE", "0.75" if BIG else "1")
os.environ["PRIME_TYPE"] = "0"
os.environ["OFFSCREEN"] = "1"

import pyray as rl
from openpilot.common.params import Params
from openpilot.common.hardware import HARDWARE
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.selfdrive.ui.tests.diff.replay import setup_state

FPS = 60


def main(output: Path, lang: str | None = None):
  output.mkdir(parents=True, exist_ok=True)
  setup_state()
  if lang is not None:
    from openpilot.system.ui.lib.multilang import multilang
    # Select the language before init_window() loads its fallback font.
    multilang.change_language(lang)
  params = Params()

  from openpilot.common.hardware.comma import apn_auth_store

  def seed(populated: bool):
    if populated:
      params.put("GsmApn", "fixture.apn", block=True)
      apn_auth_store.write("chap", "fixture-user@invalid", "fixture-password")
    else:
      params.remove("GsmApn")
      apn_auth_store.clear()

  seed(True)
  from openpilot.selfdrive.ui.ui_state import ui_state, device
  from openpilot.selfdrive.ui.lib.prime_state import PrimeType
  from openpilot.system.ui.lib.application import gui_app

  rl.set_config_flags(rl.ConfigFlags.FLAG_WINDOW_HIDDEN)
  gui_app.init_window("APN authentication screenshots", fps=FPS)
  if gui_app._render_texture is None:
    gui_app._render_texture = rl.load_render_texture(gui_app._scaled_width, gui_app._scaled_height)

  if BIG:
    from openpilot.selfdrive.ui.layouts.settings.settings import SettingsLayout, PanelType
    from openpilot.system.ui.widgets.network import PanelType as NetworkPanel
    root = SettingsLayout()
    gui_app.push_widget(root)
    root.set_current_panel(PanelType.NETWORK)
    network = root._panels[PanelType.NETWORK].instance
    network._set_current_panel(NetworkPanel.ADVANCED)
    panel = network._advanced_panel
  else:
    from openpilot.selfdrive.ui.mici.layouts.settings.network.network_layout import NetworkLayoutMici
    panel = root = NetworkLayoutMici()
    gui_app.push_widget(root)

  def close_dialogs():
    while gui_app.get_active_widget() is not root:
      if BIG and gui_app.get_active_widget() is panel._keyboard:
        panel._keyboard._cancel_button_callback()
      else:
        gui_app.pop_widget()

  def scroll_to(widget):
    scroller = panel._scroller
    if BIG:
      scroller.scroll_panel.set_offset(scroller.scroll_panel.offset + scroller.rect.y - widget.rect.y)
    else:
      scroller._layout()
      scroller.scroll_to(widget.rect.x + widget.rect.width / 2 - (panel.rect.x + panel.rect.width / 2))

  steps: dict[int, Callable] = {}
  captures: dict[int, str] = {}
  next_frame = FPS

  def add(action: Callable, name: str | None = None, close: bool = True):
    nonlocal next_frame

    def run():
      if close:
        close_dialogs()
      action()

    steps[next_frame] = run
    if name:
      captures[next_frame + FPS] = name + ".png"
    next_frame += FPS * 2

  def show_state(populated: bool):
    seed(populated)
    panel.show_event()

  def type_password():
    if BIG:
      panel._keyboard.set_text("fixture-password-typed")
    else:
      gui_app.get_active_widget()._keyboard.set_text("fixture-password-typed")

  def choose_off():
    # Start at CHAP even in the empty fixture so selecting off isn't a no-op.
    panel._set_apn_auth(2 if BIG else "chap")
    panel._set_apn_auth(0 if BIG else "off")

  for state, populated in (("set", True), ("empty", False)):
    add(lambda populated=populated: show_state(populated))
    if BIG:
      add(lambda: scroll_to(panel._apn_btn), f"{state}_rows")
    else:
      for row in ("apn", "apn_user", "apn_password", "apn_auth"):
        add(lambda row=row: scroll_to(getattr(panel, f"_{row}_btn")), f"{state}_{row}_row")
    if populated:
      add(lambda: scroll_to(panel._apn_delete_btn), "set_delete_credentials_row")
      add(panel._delete_apn_credentials, "set_delete_credentials_confirm")
      if not BIG:
        for index, choice in ((1, "no"), (2, "yes")):
          add(lambda index=index: scroll_confirm_choice(index), f"set_delete_credentials_{choice}", close=False)
    add(panel._edit_apn, f"{state}_apn_keyboard")
    add(panel._edit_apn_user, f"{state}_user_keyboard")
    add(panel._edit_apn_password, f"{state}_password_keyboard")
    add(type_password, f"{state}_password_typed", close=False)
    add(choose_off, f"{state}_off_confirm")
    if not BIG:
      for index, choice in ((1, "no"), (2, "yes")):
        add(lambda index=index: scroll_confirm_choice(index), f"{state}_off_{choice}", close=False)

  def scroll_confirm_choice(index: int):
    dialog = gui_app.get_active_widget()
    dialog._scroller._layout()
    choice = dialog._scroller.items[index]
    dialog._scroller.scroll_to(choice.rect.x + choice.rect.width / 2 - (dialog.rect.x + dialog.rect.width / 2))

  if BIG:
    def invalid_input():
      panel._edit_apn_user()
      panel._keyboard.set_text("invalid user")
      panel._keyboard._key_callback("->")

    add(invalid_input, "invalid_credential_alert")

  base = {
    "state": "CONNECTED", "connected": True, "registration": "home", "network_type": "lte", "operator": "Fixture",
    "signal_strength": 72, "diag": {
      "fw": "EG916-fixture", "sim": True, "comma_sim": False, "mcc_mnc": "44020", "roaming_allowed": True,
      "reg": {"creg": "home", "cgreg": "home", "at": 42}, "ceer": {"text": "No report", "at": 40},
      "apn": {"setting": "fixture.apn", "cid1_before": ""},
      "auth": {"mode": "chap", "cmd": "CGAUTH", "warning": "", "user_len": 20, "user_has_at": True, "password_set": True,
               "readback": {"ok": True, "protocol_ok": True, "user_ok": True, "password_ok": None}, "at": 41},
      "ppp": {"fails": 0, "last_exit": None, "ip_present": True},
      "reattach": {"left": 0, "count": 1, "last_reason": "denied", "last_at": 42},
      "times": {"connected_at": 47, "auth_changed_at": 40, "connected_after_change_s": 7},
      "events": ["41s auth applied CGAUTH", "41s auth readback ok", "42s reattach denied", "47s state CONNECTING->CONNECTED"],
    },
  }
  denied = deepcopy(base)
  denied.update(state="SEARCHING", connected=False, registration="denied")
  denied["diag"]["reg"].update(creg="denied", cgreg="searching")
  denied["diag"]["ceer"] = {"text": '"ESM",29', "at": 52}
  denied["diag"]["reattach"].update(left=1, count=1)
  denied["diag"]["ppp"]["ip_present"] = False
  failed = deepcopy(denied)
  failed["diag"]["ppp"].update(fails=3, last_exit=19, last_exit_at=53)
  failed["diag"]["events"] = ["53s PPP fail 3/3 exit=19"]
  fallback = deepcopy(base)
  fallback["diag"]["fw"] = "EG25-fixture"
  fallback["diag"]["auth"]["cmd"] = "QICSGP"
  fallback["diag"]["events"] = ["41s auth applied QICSGP", "41s auth readback ok"]
  fixture_states = {"connected_chap": base, "denied_reattach": denied, "ppp_exit_19": failed, "qicsgp_fallback": fallback, "not_running": {}}
  prime_type = PrimeType.NONE
  original_get_modem_state = HARDWARE.get_modem_state
  fixture_info = {"branch": "fixture", "commit": "123456789", "uptime_s": 3725, "wall_clock": None}

  def show_status(fixture, prime):
    nonlocal prime_type
    prime_type = prime
    ui_state.prime_state.set_type(prime)
    seed(bool(fixture))
    HARDWARE.get_modem_state = lambda: fixture
    panel._show_modem_status()
    # Fixture metadata stays local to the reader; never replace the global clock.
    panel._modem_status._reader._next_read = 0
    panel._modem_status._reader._info = lambda now: fixture_info

  # Use both prime states to exercise the unpaired tizi auth/status gating.
  for prime in (PrimeType.NONE, PrimeType.UNPAIRED):
    def show_prime_rows(prime=prime):
      nonlocal prime_type
      prime_type = prime
      ui_state.prime_state.set_type(prime)
      show_state(True)

    add(show_prime_rows)
    add(lambda: scroll_to(panel._modem_status_btn), f"{prime.name.lower()}_status_row")
    for name, fixture in fixture_states.items():
      add(lambda fixture=fixture, prime=prime: show_status(fixture, prime), f"{prime.name.lower()}_status_{name}")
      if not BIG and fixture:
        add(lambda: panel._modem_status._scroll_panel.set_offset(-220), f"{prime.name.lower()}_status_{name}_details", close=False)

  frame = 0
  written: list[str] = []
  original_end_drawing = rl.end_drawing

  def end_drawing():
    original_end_drawing()
    if frame in captures:
      image = rl.load_image_from_texture(gui_app._render_texture.texture)
      try:
        rl.image_flip_vertical(image)
        name = captures[frame]
        if not rl.export_image(image, str(output / name)):
          raise RuntimeError(f"Could not export {name}")
        written.append(name)
      finally:
        rl.unload_image(image)

  rl.end_drawing = end_drawing
  rl.get_frame_time = lambda: 1.0 / FPS
  rl.get_time = lambda: frame / FPS
  device.set_override_interactive_timeout(99999)
  try:
    for _ in gui_app.render():
      ui_state.update()
      ui_state.prime_state.set_type(prime_type)
      if frame in steps:
        steps[frame]()
      frame += 1
      if frame > max(captures) + 1:
        break
  finally:
    rl.end_drawing = original_end_drawing
    HARDWARE.get_modem_state = original_get_modem_state
    gui_app.close()
  if len(written) != len(captures):
    raise RuntimeError(f"Captured {len(written)} of {len(captures)} screenshots")
  print(f"Wrote {len(written)} screenshots to {output}")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("output", type=Path)
  parser.add_argument("--lang", help="Language code for translated strings (e.g. ja)")
  args = parser.parse_args()
  with TemporaryDirectory(prefix="apn-auth-shots-") as store_dir, OpenpilotPrefix():
    os.environ["APN_AUTH_STORE_DIR"] = store_dir
    main(args.output, args.lang)
