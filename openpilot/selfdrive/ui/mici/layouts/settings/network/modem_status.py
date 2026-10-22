import pyray as rl

from openpilot.selfdrive.ui.lib.modem_status import ModemStatusReader
from openpilot.selfdrive.ui.ui_state import device
from openpilot.system.ui.lib.application import FONT_SCALE, font_fallback, gui_app
from openpilot.system.ui.widgets.scroller import NavRawScrollPanel


class ModemStatusMici(NavRawScrollPanel):
  def __init__(self):
    super().__init__()
    self._reader = ModemStatusReader()
    self._rows: list[str] = []

  def show_event(self):
    super().show_event()
    device.set_override_interactive_timeout(300)

  def hide_event(self):
    super().hide_event()
    device.set_override_interactive_timeout(None)

  def _update_state(self):
    super()._update_state()
    if gui_app.get_active_widget() is self and self._reader.update():
      font = font_fallback(gui_app.font())
      self._rows = []
      for label, value in self._reader.lines:
        words = f"{label}: {value}".split()
        row = ""
        for word in words:
          candidate = (row + " " + word).strip()
          width = rl.measure_text_ex(font, candidate, 26 * FONT_SCALE, 0).x  # noqa: TID251 -- Avoid the unbounded text cache.
          if row and width > gui_app.width - 24:
            self._rows.append(row)
            row = word
          else:
            row = candidate
        self._rows.append(row)

  def _render(self, rect: rl.Rectangle):
    offset = round(self._scroll_panel.update(rect, 24 + len(self._rows) * 34))
    rl.begin_scissor_mode(int(rect.x), int(rect.y), int(rect.width), int(rect.height))
    for i, text in enumerate(self._rows):
      rl.draw_text_ex(gui_app.font(), text, rl.Vector2(rect.x + 12, rect.y + 24 + i * 34 + offset), 26, 0, rl.WHITE)
    rl.end_scissor_mode()
