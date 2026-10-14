"""Photo-safe modem status formatting and an on-demand, one Hz reader."""
import time
from datetime import datetime

from openpilot.common.hardware.comma import apn_auth_store

EXIT_MEANINGS = {8: "connect script failed", 10: "negotiation failed", 16: "hangup", 19: "auth failed"}


def _yes(value) -> str:
  return "unknown" if value is None else "yes" if value else "no"


def _uptime(seconds) -> str:
  seconds = max(0, int(seconds or 0))
  return f"{seconds // 3600}h{seconds // 60 % 60:02d}m{seconds % 60:02d}s"


def _captured(text: str, seconds, prefix: str = "at ") -> str:
  return text if seconds is None else f"{text} ({prefix}{int(seconds)}s)"


def status_lines(state: dict, store: tuple[str, str, str], info: dict) -> list[tuple[str, str]]:
  diag = state.get("diag", {})
  reg, auth, ppp = (diag.get(section, {}) for section in ("reg", "auth", "ppp"))
  apn, reattach, times = (diag.get(section, {}) for section in ("apn", "reattach", "times"))
  mode, user, password = store
  mode = mode if mode in ("none", "pap", "chap") else "invalid" if mode else "unmanaged"
  readback = auth.get("readback", {})
  verdict = "n/a" if readback.get("ok") is None else "ok" if readback["ok"] else "failed"
  code = ppp.get("last_exit")
  exit_text = "-" if code is None else f"pppd exit {code}"
  if code in EXIT_MEANINGS:
    exit_text += f" ({EXIT_MEANINGS[code]})"
  ppp_text = _captured(f"{int(ppp.get('fails', 0))}/3; {exit_text}", ppp.get("last_exit_at"))
  if ppp.get("ip_present") or state.get("state") == "CONNECTED" and state.get("connected"):
    ppp_text = "up"
    if code is not None:
      retry = f"pppd exit {code}"
      if code in EXIT_MEANINGS:
        retry += f" {EXIT_MEANINGS[code]}"
      if ppp.get("last_exit_at") is not None:
        retry += f" at {int(ppp['last_exit_at'])}s"
      ppp_text += f" (last retry: {retry})"
  build = f"{info.get('branch', '-') or '-'} {str(info.get('commit', '-'))[:9]}  up {_uptime(info.get('uptime_s'))}"
  lines = [
    ("State", state.get("state", "modem not running / no state yet")),
    ("Registration", _captured(f"{reg.get('creg', state.get('registration', 'unknown'))} / {reg.get('cgreg', 'unknown')}", reg.get("at"), "")),
    ("Auth", _captured(f"{auth.get('mode', mode)} {auth.get('cmd', '-')} / readback {verdict}", auth.get("at"))),
    ("PPP", ppp_text),
    ("Data", _yes(ppp.get("ip_present", bool(state.get("connected"))))),
    ("Build", build),
    ("Clock", str(info.get("wall_clock") or "clock not set")),
  ]
  if not state:
    return lines
  ceer = diag.get("ceer", {})
  reattach_text = f"left {int(reattach.get('left', 0))}, count {int(reattach.get('count', 0))}, {reattach.get('last_reason', '-') or '-'}"
  lines += [
    ("CEER (last)", _captured(ceer.get("text", "-"), ceer.get("at"))),
    ("SIM", f"present {_yes(diag.get('sim'))}, comma SIM {_yes(diag.get('comma_sim'))}"),
    ("MCC-MNC", str(diag.get("mcc_mnc", state.get("mcc_mnc", "")))[:5] or "-"),
    ("APN setting", apn.get("setting") or "(network)"),
    ("CID1 before", apn.get("cid1_before") or "(network)"),
    ("Readback", f"proto {_yes(readback.get('protocol_ok'))}, user {_yes(readback.get('user_ok'))}, pass {_yes(readback.get('password_ok'))}"),
    ("User / password", f"{len(user)} chars, @ {_yes('@' in user)} / set {_yes(bool(password))}"),
    ("Re-registrations", _captured(reattach_text, reattach.get("last_at"))),
    ("Roaming allowed", _yes(diag.get("roaming_allowed"))),
    ("Modem fw", diag.get("fw", state.get("modem_version", "")) or "-"),
    ("After change", f"{int(times['connected_after_change_s'])}s" if times.get("connected_after_change_s") is not None else "-"),
  ]
  if state.get("state") == "CONNECTED":
    network = f"{state.get('network_type', '')} {state.get('operator', '')}".strip() or "-"
    lines.append(("Network / signal", f"{network} / {round(state.get('signal_strength', 0))}%"))
  if auth.get("warning"):
    lines.append(("Auth warning", auth["warning"]))
  lines.extend(("Event", event) for event in diag.get("events", [])[-6:])
  return lines


class ModemStatusReader:
  def __init__(self):
    from openpilot.common.params import Params
    self._params = Params()
    self._next_read = 0.0
    self.lines: list[tuple[str, str]] = []

  def _info(self, now: float) -> dict:
    from openpilot.common.time_helpers import system_time_valid
    return {"branch": self._params.get("GitBranch"), "commit": self._params.get("GitCommit") or "-",
            "uptime_s": int(now), "wall_clock": datetime.now().strftime("%Y-%m-%d %H:%M:%S") if system_time_valid() else None}

  def update(self) -> bool:
    from openpilot.common.hardware import HARDWARE
    now = time.monotonic()
    if now < self._next_read:
      return False
    self._next_read = now + 1.0
    lines = status_lines(HARDWARE.get_modem_state(), apn_auth_store.read(), self._info(now))
    if lines == self.lines:
      return False
    self.lines = lines
    return True
