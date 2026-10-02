#!/bin/bash
# Derived from agnos-builder 2c74c82 userspace/compile-wpasupplicant.sh.
# Inputs were downloaded and authenticated by wpa_classify.py; never run a .deb.
set -euo pipefail
: "${WPA_VERSION:?}" "${DSC_SHA256:?}" "${WPA_SNAPSHOT:?}" "${CHANGELOG_DATE:?}"
[[ $WPA_VERSION =~ ^2:2\.10-21ubuntu0\.[0-9]+$ ]]
[[ $DSC_SHA256 =~ ^[0-9a-f]{64}$ && $WPA_SNAPSHOT =~ ^[0-9]{8}T[0-9]{6}Z$ ]]
[[ $(uname -m) == aarch64 ]]
export LC_ALL=C.UTF-8 TZ=UTC CCACHE_DISABLE=1
mkdir -p /etc/ssl/certs
cp /recipe/bootstrap-ca.crt /etc/ssl/certs/ca-certificates.crt
# Every apt operation uses this one immutable snapshot, including build-dep.
rm -f /etc/apt/sources.list /etc/apt/sources.list.d/*
cat > /etc/apt/sources.list <<EOF
deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/$WPA_SNAPSHOT/ noble main universe
deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/$WPA_SNAPSHOT/ noble-updates main universe
deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/$WPA_SNAPSHOT/ noble-security main universe
deb-src [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/$WPA_SNAPSHOT/ noble main universe
deb-src [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/$WPA_SNAPSHOT/ noble-updates main universe
deb-src [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/$WPA_SNAPSHOT/ noble-security main universe
EOF
apt-get update
apt-get install -yq --no-install-recommends ca-certificates dpkg-dev xz-utils quilt git python3 build-essential devscripts
cd /tmp
cp /input/archive/wpa_* .
printf '%s  %s\n' "$DSC_SHA256" "wpa_${WPA_VERSION#*:}.dsc" | sha256sum -c -
dpkg-source -x "wpa_${WPA_VERSION#*:}.dsc" wpa
mkdir reference-source
cp /input/reference/wpa_* reference-source/
cd reference-source
dpkg-source -x wpa_2.10-21ubuntu0.4.dsc /tmp/reference
diff_status=0
debdiff --no-conf --no-diffstat /input/reference/wpa_2.10-21ubuntu0.4.dsc \
  "/input/archive/wpa_${WPA_VERSION#*:}.dsc" > /output/debdiff.txt || diff_status=$?
[[ $diff_status == 0 || $diff_status == 1 ]]
cd /tmp/wpa
apt-get build-dep -yq --no-install-recommends -P pkg.wpa.nogui ./
python3 /recipe/scripts/wpa_patch.py /tmp/reference /tmp/wpa /recipe/userspace/wpa-build/patches
cat > debian/changelog.agnos <<EOF
wpa (${WPA_VERSION}+agnos1) noble; urgency=medium

  * Backport SAE Rejected Groups length checks and the H2E token parser NULL
    pointer fix from hostap 2.11/2.12.
  * Require matching network context and AKMP for PMKSA cache entries
    (hostap advisory 2026-2).
  * Backport the SAE PT derivation check for SAE profiles (438a27b36).
  * Default global sae_pwe to 2, preserving overrides across SAVE_CONFIG
    and leaving D-Bus KeyMgmt reporting unchanged.

 -- AGNOS <agnos@localhost>  $CHANGELOG_DATE

EOF
cat debian/changelog >> debian/changelog.agnos
mv debian/changelog.agnos debian/changelog
DEB_BUILD_OPTIONS="nocheck parallel=$(nproc)" dpkg-buildpackage -b -uc -us -Ppkg.wpa.nogui
cp ../wpasupplicant_*_arm64.deb /output/candidate.deb
cp ../*.buildinfo /output/
dpkg-deb -x /output/candidate.deb /tmp/installed
cp /tmp/installed/usr/sbin/wpa_supplicant /output/candidate
cp /tmp/installed/usr/share/doc/wpasupplicant/copyright /output/candidate.copyright
cp /tmp/debian-function-diff.txt /output/
dpkg-query -W > /output/toolchain-manifest.txt
