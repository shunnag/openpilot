"""Tests for the legacy iptables NAT rule managed by WifiManager tethering."""
import queue
import subprocess
import unittest

from openpilot.common.test import Mocker, OpenpilotTestCase
from openpilot.system.ui.lib import wifi_manager
from openpilot.system.ui.lib.wifi_manager import TETHERING_NAT_RULE, WifiManager

CHECK = ["sudo", "iptables-legacy", "-t", "nat", "-C", *TETHERING_NAT_RULE]
ADD = ["sudo", "iptables-legacy", "-t", "nat", "-A", *TETHERING_NAT_RULE]
DELETE = ["sudo", "iptables-legacy", "-t", "nat", "-D", *TETHERING_NAT_RULE]
SYSCTL = ["sudo", "sysctl", "net.ipv4.ip_forward=0"]


def _make_wm(mocker: Mocker, ipv4_forward: bool = True):
  mocker.patch.object(WifiManager, '_initialize')
  wm = WifiManager.__new__(WifiManager)
  wm._exit = True
  wm._conn_monitor = mocker.MagicMock()
  wm._tethering_ssid = "weedle"
  wm._ipv4_forward = ipv4_forward
  wm.activate_connection = mocker.MagicMock()
  wm._deactivate_connection = mocker.MagicMock()
  # Requests wait on the shared queue until the test runs them
  wm._requests = queue.Queue()
  return wm


def _run_requests(wm: WifiManager):
  while not wm._requests.empty():
    wm._requests.get_nowait()()


class FakeNat:
  """iptables-legacy's nat table, holding only the tethering rule."""
  def __init__(self):
    self.rules = 0

  def __call__(self, cmd, **kwargs):
    returncode = 0
    if cmd == CHECK:
      returncode = 0 if self.rules else 1
    elif cmd == ADD:
      self.rules += 1
    elif cmd == DELETE:
      returncode = 0 if self.rules else 1
      self.rules = max(self.rules - 1, 0)
    return subprocess.CompletedProcess(cmd, returncode)


class TestTetheringNat(OpenpilotTestCase):
  def test_activate_adds_missing_rule_after_connection(self, mocker):
    wm = _make_wm(mocker)
    run = mocker.patch.object(wifi_manager.subprocess, 'run',
                              side_effect=[subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)])
    calls = mocker.MagicMock()
    calls.attach_mock(wm.activate_connection, 'activate')
    calls.attach_mock(run, 'run')

    wm.set_tethering_active(True)
    assert calls.mock_calls == []
    _run_requests(wm)

    assert calls.mock_calls == [
      mocker.call.activate(wm._tethering_ssid, block=True),
      mocker.call.run(CHECK, check=False, capture_output=True, text=True),
      mocker.call.run(ADD, check=True, capture_output=True, text=True),
    ]

  def test_activate_keeps_existing_rule(self, mocker):
    wm = _make_wm(mocker)
    run = mocker.patch.object(wifi_manager.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0))

    wm.set_tethering_active(True)
    _run_requests(wm)

    run.assert_called_once_with(CHECK, check=False, capture_output=True, text=True)

  def test_activate_missing_iptables_does_not_raise(self, mocker):
    wm = _make_wm(mocker)
    run = mocker.patch.object(wifi_manager.subprocess, 'run', side_effect=FileNotFoundError("iptables-legacy"))
    log_exception = mocker.patch.object(wifi_manager.cloudlog, 'exception')

    wm.set_tethering_active(True)
    _run_requests(wm)

    run.assert_called_once_with(CHECK, check=False, capture_output=True, text=True)
    log_exception.assert_called_once_with("Failed to add tethering NAT rule")

  def test_deactivate_removes_rule_after_connection(self, mocker):
    wm = _make_wm(mocker)
    run = mocker.patch.object(wifi_manager.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1))
    calls = mocker.MagicMock()
    calls.attach_mock(wm._deactivate_connection, 'deactivate')
    calls.attach_mock(run, 'run')

    wm.set_tethering_active(False)
    _run_requests(wm)

    assert calls.mock_calls == [
      mocker.call.deactivate(wm._tethering_ssid),
      mocker.call.run(DELETE, check=False, capture_output=True, text=True),
    ]

  def test_activate_without_forwarding_still_disables_ip_forward(self, mocker):
    wm = _make_wm(mocker, ipv4_forward=False)
    run = mocker.patch.object(wifi_manager.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0))
    timer = mocker.patch.object(wifi_manager.threading, 'Timer')
    sleep = mocker.patch.object(wifi_manager.time, 'sleep')
    calls = mocker.MagicMock()
    calls.attach_mock(run, 'run')
    calls.attach_mock(timer, 'timer')

    wm.set_tethering_active(True)
    _run_requests(wm)

    # The rule is checked on the request thread; a timer turns forwarding off 5 s later, without blocking the queue.
    disable_forward = timer.call_args.args[1]
    assert calls.mock_calls == [
      mocker.call.run(CHECK, check=False, capture_output=True, text=True),
      mocker.call.timer(5, disable_forward),
      mocker.call.timer().start(),
    ]
    sleep.assert_not_called()
    disable_forward()
    assert run.call_args_list[1:] == [mocker.call(SYSCTL, check=False)]

  def test_activate_with_forwarding_keeps_ip_forward(self, mocker):
    wm = _make_wm(mocker, ipv4_forward=True)
    mocker.patch.object(wifi_manager.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0))
    timer = mocker.patch.object(wifi_manager.threading, 'Timer')

    wm.set_tethering_active(True)
    _run_requests(wm)

    timer.assert_not_called()

  def test_failed_rule_still_disables_ip_forward(self, mocker):
    wm = _make_wm(mocker, ipv4_forward=False)
    run = mocker.patch.object(wifi_manager.subprocess, 'run',
                              side_effect=[subprocess.CompletedProcess([], 1), subprocess.CalledProcessError(4, ADD)])
    timer = mocker.patch.object(wifi_manager.threading, 'Timer')
    log_exception = mocker.patch.object(wifi_manager.cloudlog, 'exception')

    wm.set_tethering_active(True)
    _run_requests(wm)

    log_exception.assert_called_once_with("Failed to add tethering NAT rule")
    timer.assert_called_once()
    assert timer.call_args.args[0] == 5
    timer.return_value.start.assert_called_once_with()
    assert run.call_count == 2

  def test_on_off_on_runs_in_order_and_keeps_one_rule(self, mocker):
    wm = _make_wm(mocker, ipv4_forward=False)
    nat = FakeNat()
    run = mocker.patch.object(wifi_manager.subprocess, 'run', side_effect=nat)
    timer = mocker.patch.object(wifi_manager.threading, 'Timer')
    calls = mocker.MagicMock()
    calls.attach_mock(wm.activate_connection, 'activate')
    calls.attach_mock(wm._deactivate_connection, 'deactivate')
    calls.attach_mock(run, 'run')

    for active in (True, False, True):
      wm.set_tethering_active(active)
    _run_requests(wm)

    assert [c for c in calls.mock_calls if c[0] != 'run'] == [
      mocker.call.activate(wm._tethering_ssid, block=True),
      mocker.call.deactivate(wm._tethering_ssid),
      mocker.call.activate(wm._tethering_ssid, block=True),
    ]
    assert [c.args[0] for c in run.call_args_list] == [CHECK, ADD, DELETE, CHECK, ADD]
    assert nat.rules == 1

    # The first activation's timer fires after tethering was turned on again: it only turns forwarding off.
    callbacks = [c.args[1] for c in timer.call_args_list]
    assert [c.args[0] for c in timer.call_args_list] == [5, 5]
    for disable_forward in callbacks:
      disable_forward()
    assert [c.args[0] for c in run.call_args_list[5:]] == [SYSCTL, SYSCTL]
    assert nat.rules == 1
    assert wm.activate_connection.call_count == 2
    assert wm._deactivate_connection.call_count == 1

  def test_on_off_leaves_no_rule(self, mocker):
    wm = _make_wm(mocker, ipv4_forward=False)
    nat = FakeNat()
    run = mocker.patch.object(wifi_manager.subprocess, 'run', side_effect=nat)
    timer = mocker.patch.object(wifi_manager.threading, 'Timer')

    wm.set_tethering_active(True)
    wm.set_tethering_active(False)
    _run_requests(wm)
    timer.call_args.args[1]()

    assert [c.args[0] for c in run.call_args_list] == [CHECK, ADD, DELETE, SYSCTL]
    assert nat.rules == 0

  def test_repeated_activate_adds_rule_once(self, mocker):
    wm = _make_wm(mocker)
    nat = FakeNat()
    run = mocker.patch.object(wifi_manager.subprocess, 'run', side_effect=nat)

    wm.set_tethering_active(True)
    wm.set_tethering_active(True)
    _run_requests(wm)

    assert [c.args[0] for c in run.call_args_list] == [CHECK, ADD, CHECK]
    assert nat.rules == 1


if __name__ == "__main__":
  unittest.main()
