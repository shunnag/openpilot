import unittest

from jeepney import DBusAddress
from jeepney.low_level import HeaderFields, MessageType

from openpilot.common.parameterized import parameterized
from openpilot.common.test import OpenpilotTestCase
from openpilot.system.ui.lib import wifi_manager
from openpilot.system.ui.lib.networkmanager import NM, NM_PATH, NM_IFACE
from openpilot.system.ui.lib.wifi_manager import AccessPoint, Network, SecurityType, WifiManager, WifiState, get_security_type


class TestSecurityType(OpenpilotTestCase):
  @parameterized.expand([
    (0x0, 0, 0x000, SecurityType.OPEN, SecurityType.OPEN),
    (0x2, 0, 0x000, SecurityType.OPEN, SecurityType.OPEN),
    (0x1, 0, 0x188, SecurityType.WPA, SecurityType.WPA),
    (0x1, 0, 0x588, SecurityType.WPA, SecurityType.WPA),
    (0x1, 0, 0x488, SecurityType.UNSUPPORTED, SecurityType.WPA3),
    (0x3, 0, 0x488, SecurityType.UNSUPPORTED, SecurityType.WPA3),
    (0x1, 0, 0x288, SecurityType.UNSUPPORTED, SecurityType.UNSUPPORTED),
    (0x3, 0, 0x288, SecurityType.UNSUPPORTED, SecurityType.UNSUPPORTED),
    (0x1, 0, 0x688, SecurityType.UNSUPPORTED, SecurityType.UNSUPPORTED),
    (0x1, 0x100, 0x488, SecurityType.WPA, SecurityType.WPA),
    (0x1, 0x200, 0x488, SecurityType.UNSUPPORTED, SecurityType.UNSUPPORTED),
  ])
  def test_security_type(self, flags, wpa_flags, rsn_flags, without_sae, with_sae):
    assert get_security_type(flags, wpa_flags, rsn_flags) == without_sae
    assert get_security_type(flags, wpa_flags, rsn_flags, sae_supported=False) == without_sae
    assert get_security_type(flags, wpa_flags, rsn_flags, sae_supported=True) == with_sae

  @parameterized.expand([(False, SecurityType.UNSUPPORTED), (True, SecurityType.WPA3)])
  def test_network_from_dbus(self, sae_supported, expected):
    aps = [
      AccessPoint("Net", "00:11:22:33:44:55", 30, 0x1, 0, 0x188, "/ap/1"),
      AccessPoint("Net", "00:11:22:33:44:66", 80, 0x1, 0, 0x488, "/ap/2"),
    ]
    network = Network.from_dbus("Net", aps, False, sae_supported)
    assert network.security_type == expected
    assert network.strength == 80


class TestSAECapability(OpenpilotTestCase):
  @parameterized.expand([
    (b"OPEN SHARED LEAP SAE\n", True),
    (b"OPEN SHARED LEAP\n", False),
    (b"OPEN NOT_SAE\n", False),
  ], names=("reply", "expected"))
  def test_reply_is_cached(self, mocker, reply, expected):
    mocker.patch.object(wifi_manager, '_sae_supported', None)
    socket_factory = mocker.patch.object(wifi_manager.socket, 'socket')
    sock = socket_factory.return_value.__enter__.return_value
    sock.recv.side_effect = [b"<3>CTRL-EVENT-SCAN-RESULTS\n", reply]

    assert wifi_manager._supports_sae() is expected
    assert wifi_manager._supports_sae() is expected
    socket_factory.assert_called_once_with(wifi_manager.socket.AF_UNIX, wifi_manager.socket.SOCK_DGRAM)
    sock.settimeout.assert_called_once_with(0.2)
    assert sock.bind.call_args.args[0].startswith("\0openpilot-wpa-")
    sock.connect.assert_called_once_with("/run/wpa_supplicant/wlan0")
    sock.send.assert_called_once_with(b"GET_CAPABILITY auth_alg")

  @parameterized.expand([
    (OSError("socket unavailable"),),
    (TimeoutError("timed out"),),
    (b"FAIL\n",),
    (b"",),
  ], names=("failure",))
  def test_failure_is_not_cached(self, mocker, failure):
    mocker.patch.object(wifi_manager, '_sae_supported', None)
    socket_factory = mocker.patch.object(wifi_manager.socket, 'socket')
    sock = socket_factory.return_value.__enter__.return_value
    sock.recv.side_effect = [failure, b"OPEN SHARED LEAP SAE\n"]

    assert wifi_manager._supports_sae() is False
    assert wifi_manager._sae_supported is None
    assert wifi_manager._supports_sae() is True
    assert socket_factory.call_count == 2


class TestConnectSecurity(OpenpilotTestCase):
  @parameterized.expand([
    (SecurityType.WPA3, False, 'sae'),
    (SecurityType.WPA, False, 'wpa-psk'),
    (SecurityType.WPA3, True, 'wpa-psk'),
  ], names=("security_type", "hidden", "key_mgmt"))
  def test_connection_security(self, mocker, security_type, hidden, key_mgmt):
    wm = WifiManager.__new__(WifiManager)
    wm._exit = True
    wm._networks = [Network("Other", 100, SecurityType.WPA3, False), Network("Net", 80, security_type, False)]
    wm._wifi_state = WifiState()
    wm._user_epoch = 0
    wm._wifi_device = "/org/freedesktop/NetworkManager/Devices/0"
    wm._nm = DBusAddress(NM_PATH, bus_name=NM, interface=NM_IFACE)
    wm._router_main = mocker.MagicMock()
    wm._router_main.send_and_get_reply.return_value.header.message_type = MessageType.method_return
    wm.forget_connection = mocker.MagicMock()
    mocker.patch.object(wifi_manager.threading, 'Thread',
                        side_effect=lambda target, **kw: mocker.Mock(start=target))

    wm.connect_to_network("Net", "password123", hidden=hidden)

    wm.forget_connection.assert_called_once_with("Net", block=True)
    wm._router_main.send_and_get_reply.assert_called_once()
    message = wm._router_main.send_and_get_reply.call_args.args[0]
    assert message.header.fields[HeaderFields.member] == 'AddAndActivateConnection2'
    expected = {'key-mgmt': ('s', key_mgmt), 'psk': ('s', 'password123')}
    if key_mgmt == 'wpa-psk':
      expected['auth-alg'] = ('s', 'open')
    assert message.body[0]['802-11-wireless-security'] == expected
    assert message.body[0]['802-11-wireless']['hidden'] == ('b', hidden)


if __name__ == "__main__":
  unittest.main()
