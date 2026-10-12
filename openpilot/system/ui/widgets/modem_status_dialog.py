import pyray as rl

from openpilot.selfdrive.ui.lib.modem_status import ModemStatusReader
from openpilot.selfdrive.ui.ui_state import device, ui_state
from openpilot.system.ui.lib.application import FONT_SCALE, font_fallback, gui_app
from openpilot.system.ui.lib.multilang import tr
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.button import Button, ButtonStyle

LABEL_SIZE = 34
VALUE_SIZE = 40
ROW_PITCH = 60


class ModemStatusDialog(Widget):
  def __init__(self):
    super().__init__()
    self._reader = ModemStatusReader()
    self._close_button = Button(tr("Close"), click_callback=gui_app.pop_widget, button_style=ButtonStyle.PRIMARY)
    self._rows: list[tuple[str, str]] = []
    self._title = ""
    self._layout_key = None

  def show_event(self):
    super().show_event()
    device.set_override_interactive_timeout(300)

  def hide_event(self):
    super().hide_event()
    device.set_override_interactive_timeout(None)

  def _update_state(self):
    if gui_app.get_active_widget() is self:
      if ui_state.started:
        gui_app.pop_widget()
        return
      self._reader.update()

  @staticmethod
  def _truncate(font, text: str, font_size: int, max_width: float) -> str:
    def width(value):
      return rl.measure_text_ex(font, value, font_size * FONT_SCALE, 0).x  # noqa: TID251 -- Avoid the unbounded text cache.

    if width(text) <= max_width:
      return text
    ellipsis = "..."
    if width(ellipsis) > max_width:
      return ""
    left, right = 0, len(text)
    while left < right:
      mid = (left + right + 1) // 2
      if width(text[:mid] + ellipsis) <= max_width:
        left = mid
      else:
        right = mid - 1
    return text[:left] + ellipsis

  def _render(self, rect: rl.Rectangle):
    font = font_fallback(gui_app.font())
    content = rl.Rectangle(rect.x + 50, rect.y + 120, rect.width - 100, rect.height - 290)
    column_gap = 60
    column_width = (content.width - column_gap) / 2
    label_width = 320
    value_offset = label_width + 20
    rows_per_column = max(1, int(content.height // ROW_PITCH))
    layout_key = (id(self._reader.lines), content.width, content.height)
    if self._layout_key != layout_key:
      metadata = dict(self._reader.lines)
      title = f"MODEM STATUS  {metadata.get('Build', '')}  {metadata.get('Clock', 'clock not set')}"
      self._title = self._truncate(font, title, VALUE_SIZE, content.width)
      self._rows = [
        (self._truncate(font, label, LABEL_SIZE, label_width),
         self._truncate(font, str(value), VALUE_SIZE, column_width - value_offset))
        for label, value in self._reader.lines if label not in ("Build", "Clock")
      ]
      self._layout_key = layout_key
    rl.draw_text_ex(font, self._title, rl.Vector2(content.x, rect.y + 35), VALUE_SIZE, 0, rl.WHITE)
    rl.begin_scissor_mode(int(content.x), int(content.y), int(content.width), int(content.height))
    for i, (label, value) in enumerate(self._rows):
      column, row = divmod(i, rows_per_column)
      x = content.x + column * (column_width + column_gap)
      y = content.y + row * ROW_PITCH
      rl.draw_text_ex(font, label, rl.Vector2(x, y + 4), LABEL_SIZE, 0, rl.GRAY)
      rl.draw_text_ex(font, value, rl.Vector2(x + value_offset, y), VALUE_SIZE, 0, rl.WHITE)
    rl.end_scissor_mode()
    self._close_button.render(rl.Rectangle(rect.x + rect.width - 490, rect.y + rect.height - 170, 440, 120))
