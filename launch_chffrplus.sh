#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

source "$DIR/launch_env.sh"

function wpa3_tag_present {
  local cmdline_path="${WPA3_CMDLINE_PATH:-/proc/cmdline}" token
  local -a tokens
  [ -r "$cmdline_path" ] || return 1
  IFS=$' \t\n' read -r -a tokens <<< "$(< "$cmdline_path")"
  for token in "${tokens[@]}"; do
    [ "$token" = "$WPA3_BOOT_TAG" ] && return 0
  done
  return 1
}

function wpa3_boot_attempt {
  local attempts_path="${WPA3_ATTEMPTS_PATH:-/data/wpa3_boot_attempts}"
  local saved_hash="" count=0 attempts
  if [ -f "$attempts_path" ]; then
    attempts=$(< "$attempts_path")
    read -r saved_hash count <<< "${attempts//$'\n'/ }" || true
  fi
  [ "$saved_hash" = "$WPA3_BOOT_HASH" ] || count=0
  # Invalid counts for this hash also stop retries (fail closed).
  case "$count" in
    0|1|2) ;;
    *) echo "WPA3 boot retry limit reached for $WPA3_BOOT_HASH"; return 1 ;;
  esac
  count=$((count + 1))
  printf '%s %s\n' "$WPA3_BOOT_HASH" "$count" > "$attempts_path" || return 1
  sync || return 1
  echo "WPA3 boot tag missing; attempt $count/3 for $WPA3_BOOT_HASH"
  return 0
}

function wpa3_boot_needed {
  [ -n "${WPA3_BOOT_TAG:-}" ] || return 1
  [ -r "${WPA3_CMDLINE_PATH:-/proc/cmdline}" ] || return 1
  if wpa3_tag_present; then
    rm -f "${WPA3_ATTEMPTS_PATH:-/data/wpa3_boot_attempts}"
    return 1
  fi
  [ -n "${WPA3_BOOT_HASH:-}" ] || return 1
  wpa3_boot_attempt
}

function wpa3_update_manifest {
  MANIFEST="$DIR/openpilot/system/hardware/comma/agnos.json"
  local stock="$DIR/openpilot/common/hardware/comma/agnos.stock.json"
  if [ "$(< "${WPA3_VERSION_PATH:-/VERSION}")" != "$AGNOS_VERSION" ] &&
     [ -n "${WPA3_BOOT_TAG:-}" ] && [ -n "${WPA3_BOOT_HASH:-}" ] && ! wpa3_tag_present; then
    if ! wpa3_boot_attempt && [ -f "$stock" ]; then
      MANIFEST="$stock"
    fi
  fi
  echo "AGNOS update manifest: $MANIFEST"
}

function wpa3_supplicant_override {
  local sys="${WPA3_SUPPLICANT_SYS:-/usr/sbin/wpa_supplicant}"
  local bin="${WPA3_SUPPLICANT_BIN:-$DIR/wpa3/wpa_supplicant}"
  local failed="${WPA3_SUPPLICANT_FAILED:-/data/wpa3_supplicant_failed}"
  local dropin_dir="${WPA3_SUPPLICANT_DROPIN_DIR:-/run/systemd/system/wpa_supplicant.service.d}"
  local bin_hash sys_hash deadline arg stop_post pid exe_hash
  local -a dropin_args
  [ -n "${WPA3_SUPPLICANT_STOCK_SHA256:-}" ] || return 0
  [ -f "$bin" ] && [ -x "$bin" ] || return 0
  if ! bin_hash=$(sha256sum < "$bin") || ! sys_hash=$(sha256sum < "$sys"); then
    echo "WPA3: cannot hash wpa_supplicant; not overriding"
    return 0
  fi
  bin_hash="${bin_hash%% *}"
  sys_hash="${sys_hash%% *}"
  if [ "$sys_hash" = "$bin_hash" ]; then
    echo "WPA3: patched wpa_supplicant already active"
    return 0
  fi
  if [ "$sys_hash" != "$WPA3_SUPPLICANT_STOCK_SHA256" ]; then
    echo "WPA3: stock wpa_supplicant differs; not overriding"
    return 0
  fi
  if ! "$bin" -v; then
    echo "WPA3: patched wpa_supplicant -v failed; not overriding"
    return 0
  fi
  if [ -f "$failed" ] && awk -v hash="$bin_hash" '
    NF == 2 && $1 == hash { count++; if ($2 == "start") start = 1 }
    END { exit !(start || count >= 3) }
  ' "$failed"; then
    echo "WPA3: this wpa_supplicant failed to start or failed three times; not overriding"
    return 0
  fi

  # Escape unit arguments separately from the shell command. systemd consumes
  # $$ and %% itself; the shell must receive the literal dollars and percent.
  for arg in "$sys" "$bin_hash" "$failed" "$WPA3_SUPPLICANT_STOCK_SHA256" "$dropin_dir/wpa3.conf"; do
    arg="${arg//\\/\\\\}"
    arg="${arg//\"/\\\"}"
    arg="${arg//$/\$\$}"
    arg="${arg//%/%%}"
    dropin_args+=("\"$arg\"")
  done
  printf -v stop_post '%s' \
    'if [ "$$SERVICE_RESULT" != "success" ]; then ' \
    'umount -l "$$1"; printf "%%s %%s\\n" "$$2" "$$SERVICE_RESULT" >> "$$3"; ' \
    'stock=$$(sha256sum < "$$1" | cut -d " " -f 1); if [ "$$stock" = "$$4" ]; then ' \
    'rm -f "$$5"; systemctl daemon-reload; echo "WPA3: reverted to stock wpa_supplicant after service failure"; ' \
    'else echo "WPA3: ERROR: stock wpa_supplicant not restored; crash hook remains armed"; fi; fi'
  # /run is tmpfs. A later crash removes the bind before D-Bus reactivation,
  # so NetworkManager's next activation runs stock without launcher involvement.
  if ! sudo mkdir -p "$dropin_dir"; then
    echo "WPA3: cannot create wpa_supplicant drop-in; not overriding"
    return 0
  fi
  if ! {
    printf '%s\n' '[Service]'
    printf "ExecStopPost=/bin/sh -c '%s' wpa3 %s\n" "$stop_post" "${dropin_args[*]}"
  } | sudo tee "$dropin_dir/wpa3.conf" >/dev/null; then
    sudo rm -f "$dropin_dir/wpa3.conf" || true
    sudo systemctl daemon-reload || true
    echo "WPA3: cannot install wpa_supplicant drop-in; not overriding"
    return 0
  fi
  if ! sudo systemctl daemon-reload || ! sudo mount --bind "$bin" "$sys"; then
    sudo rm -f "$dropin_dir/wpa3.conf" || true
    sudo systemctl daemon-reload || true
    echo "WPA3: cannot bind wpa_supplicant; not overriding"
    return 0
  fi

  sudo systemctl --no-block restart wpa_supplicant || echo "WPA3: wpa_supplicant restart request failed"
  deadline=$((SECONDS + 15))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if sudo systemctl is-active --quiet wpa_supplicant && pid=$(systemctl show -p MainPID --value wpa_supplicant) && [ "${pid:-0}" != 0 ] && exe_hash=$(sudo sha256sum "/proc/$pid/exe") && [ "${exe_hash%% *}" = "$bin_hash" ]; then
      echo "WPA3: patched wpa_supplicant active"
      return 0
    fi
    sleep 1 || break
  done
  sudo umount -l "$sys" || echo "WPA3: lazy unmount of wpa_supplicant failed"
  printf '%s start\n' "$bin_hash" | sudo tee -a "$failed" >/dev/null || echo "WPA3: cannot record failed wpa_supplicant"
  if sys_hash=$(sha256sum < "$sys") && [ "${sys_hash%% *}" = "$WPA3_SUPPLICANT_STOCK_SHA256" ]; then
    sudo rm -f "$dropin_dir/wpa3.conf" || true
    sudo systemctl daemon-reload || true
    echo "WPA3: reverted to stock wpa_supplicant"
  else
    echo "WPA3: ERROR: stock wpa_supplicant not restored; crash hook remains armed"
  fi
  sudo systemctl reset-failed wpa_supplicant || true
  sudo systemctl --no-block restart wpa_supplicant || true
  return 0
}

function agnos_init {
  # TODO: move this to agnos
  sudo rm -f /data/etc/NetworkManager/system-connections/*.nmmeta
  rm -f /data/scons_cache/config.lock

  # set success flag for current boot slot
  sudo abctl --set_success

  # TODO: do this without udev in AGNOS
  # udev does this, but sometimes we startup faster
  sudo chgrp gpu /dev/adsprpc-smd /dev/ion /dev/kgsl-3d0
  sudo chmod 660 /dev/adsprpc-smd /dev/ion /dev/kgsl-3d0

  # Check if AGNOS update is required
  if [ "$(< "${WPA3_VERSION_PATH:-/VERSION}")" != "$AGNOS_VERSION" ] || wpa3_boot_needed; then
    AGNOS_PY="$DIR/openpilot/common/hardware/comma/agnos.py"
    wpa3_update_manifest
    if "$AGNOS_PY" --verify "$MANIFEST"; then
      sudo reboot
    fi
    while true; do
      "$DIR/openpilot/common/hardware/comma/updater" "$AGNOS_PY" "$MANIFEST"
    done
  fi

  wpa3_supplicant_override
}

function launch {
  # Remove orphaned git lock if it exists on boot
  [ -f "$DIR/.git/index.lock" ] && rm -f "$DIR/.git/index.lock"

  # Check to see if there's a valid overlay-based update available. Conditions
  # are as follows:
  #
  # 1. The DIR init file has to exist, with a newer modtime than anything in
  #    the DIR Git repo. This checks for local development work or the user
  #    switching branches/forks, which should not be overwritten.
  # 2. The FINALIZED consistent file has to exist, indicating there's an update
  #    that completed successfully and synced to disk.

  if [ -f "${DIR}/.overlay_init" ]; then
    find "${DIR}/.git" -newer "${DIR}/.overlay_init" | grep -q '.' 2> /dev/null
    if [ $? -eq 0 ]; then
      echo "${DIR} has been modified, skipping overlay update installation"
    else
      if [ -f "${STAGING_ROOT}/finalized/.overlay_consistent" ]; then
        if [ ! -d /data/safe_staging/old_openpilot ]; then
          echo "Valid overlay update found, installing"
          LAUNCHER_LOCATION="${BASH_SOURCE[0]}"

          mv "$DIR" /data/safe_staging/old_openpilot
          mv "${STAGING_ROOT}/finalized" "$DIR"
          cd "$DIR"

          echo "Restarting launch script ${LAUNCHER_LOCATION}"
          unset AGNOS_VERSION
          exec "${LAUNCHER_LOCATION}"
        else
          echo "openpilot backup found, not updating"
          # TODO: restore backup? This means the updater didn't start after swapping
        fi
      fi
    fi
  fi

  # handle pythonpath
  ln -sfn "$(pwd)" /data/pythonpath
  export PYTHONPATH="$PWD"

  # submodule package symlinks for PYTHONPATH imports on device.
  # on PC these come from editable installs via pyproject.toml / uv.
  ln -sfn msgq_repo/msgq msgq
  ln -sfn opendbc_repo/opendbc opendbc
  ln -sfn rednose_repo/rednose rednose
  ln -sfn teleoprtc_repo/teleoprtc teleoprtc
  ln -sfn tinygrad_repo/tinygrad tinygrad

  # hardware specific init
  if [ -f /AGNOS ]; then
    agnos_init
  fi

  # write tmux scrollback to a file
  tmux capture-pane -pq -S-1000 > /tmp/launch_log

  # start manager
  cd openpilot/system/manager
  if [ ! -f "$DIR/prebuilt" ]; then
    ./build.py
  fi
  ./manager.py

  # if broken, keep on screen error
  while true; do sleep 1; done
}

launch
