#!/bin/bash
# Runs only inside the dedicated disposable Ubuntu colima profile, as root.
set -euo pipefail
[[ $EUID == 0 && $(uname -m) == aarch64 ]]
grep -qx 'VERSION_ID="24.04"' /etc/os-release
cd /tmp/wpa3-hwsim
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends "linux-modules-extra-$(uname -r)" iw hostapd wpasupplicant python3 iproute2
systemctl stop hostapd wpa_supplicant 2>/dev/null || true
ip netns del wpa3-hwsim 2>/dev/null || true
modprobe -r mac80211_hwsim 2>/dev/null || true
modprobe mac80211_hwsim radios=2
ip netns add wpa3-hwsim
cleanup() { ip netns del wpa3-hwsim; modprobe -r mac80211_hwsim; }
trap cleanup EXIT
radios=()
for phy in /sys/class/ieee80211/*; do
  if [[ $(basename "$(readlink -f "$phy/device/driver")") == mac80211_hwsim ]]; then radios+=("$(basename "$phy")"); fi
done
[[ ${#radios[@]} == 2 ]]
for i in 0 1; do
  phy=${radios[$i]}
  interfaces=("/sys/class/ieee80211/$phy/device/net/"*)
  [[ ${#interfaces[@]} == 1 && -e ${interfaces[0]} ]]
  iface=$(basename "${interfaces[0]}")
  ip link set "$iface" down
  iw phy "$phy" set netns name wpa3-hwsim
  name=ap0
  if [[ $i == 1 ]]; then name=sta0; fi
  ip netns exec wpa3-hwsim ip link set "$iface" name "$name"
done
ip netns exec wpa3-hwsim ip link set lo up
chmod 755 candidate stock
# Candidate .deb maintainer scripts and test bundles are never installed/executed.
uname -r > kernel.txt
ip netns exec wpa3-hwsim python3 suite.py --candidate /tmp/wpa3-hwsim/candidate --stock /tmp/wpa3-hwsim/stock --out /tmp/wpa3-hwsim/suite-result.json
