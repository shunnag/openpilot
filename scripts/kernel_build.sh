#!/usr/bin/env bash
# Host wrapper. Only git-archive exports and the verified toolchain are mounted.
# SC2016: single-quoted programs are deliberately expanded INSIDE the container.
# shellcheck disable=SC2016
set -euo pipefail

if [[ ${GITHUB_ACTIONS:-false} != true ]]; then
  echo 'K*: FAIL: builds/network are workflow-only; use kernel_dryrun.py for offline checks'
  exit 1
fi

command=${1:?stock or wpa3}
work=$(cd "${2:?prepared work directory}" && pwd)
scripts=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
toolchain_tar=${3:?verified/cache tar.xz path}
image=wpa3-kernel-builder

value() {
  python3 -c 'import json,sys; v=json.load(open(sys.argv[1]));
for key in sys.argv[2].split("."): v=v[key]
print(v)' "$work/build.json" "$1"
}

identity() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$work/$command-identity.json" "$1"
}

container() {
  docker run --rm --network none --cap-drop=ALL --security-opt no-new-privileges \
    --user "$(id -u):$(id -g)" --read-only --tmpfs /tmp:rw,exec,nosuid,size=1g \
    --mount "type=bind,src=$work/source,dst=/source" \
    --mount "type=bind,src=$work/toolchain,dst=/tools,readonly" \
    --workdir /source --entrypoint /bin/bash \
    -e ARCH=arm64 -e CROSS_COMPILE=/tools/bin/aarch64-linux-gnu- \
    -e CC=/tools/bin/aarch64-linux-gnu-gcc -e LD=/tools/bin/aarch64-linux-gnu-ld.bfd \
    -e HOSTCC=/usr/bin/gcc -e HOSTCXX=/usr/bin/g++ -e KCFLAGS=-w -e CCACHE_DISABLE=1 \
    -e "KBUILD_BUILD_USER=$(identity user)" -e "KBUILD_BUILD_HOST=$(identity host)" \
    -e "KBUILD_BUILD_VERSION=$(identity number)" -e "KBUILD_BUILD_TIMESTAMP=$(identity timestamp)" \
    "$image" -euo pipefail -c "$1"
}

# Cache content is checked on every invocation, including cache hits and wpa3.
printf '%s  %s\n' "$(value policy.toolchain.sha256)" "$toolchain_tar" | sha256sum --check --status
case "$command" in
  stock)
    free_kb=$(df -Pk "$work" | awk 'END {print $4}')
    minimum=$(value policy.min_free_gb)
    if (( free_kb < minimum * 1024 * 1024 )); then
      echo "K*: FAIL: infra: less than $minimum GiB free"
      exit 1
    fi
    mkdir "$work/toolchain"
    tar -xJf "$toolchain_tar" --strip-components=1 -C "$work/toolchain"
    base=$(value policy.builder_base_image)
    [[ "$base" =~ ^ubuntu:20\.04@sha256:[0-9a-f]{64}$ ]]
    docker pull --platform linux/amd64 "ubuntu@${base#*@}"
    docker tag "ubuntu@${base#*@}" ubuntu:20.04
    docker build --pull=false --platform linux/amd64 \
      --build-arg "UNAME=wpa3ci" --build-arg "UID=$(id -u)" --build-arg "GID=$(id -g)" \
      -t "$image" -f "$work/image-context/Dockerfile.builder" "$work/image-context"
    docker image inspect "$image" > "$work/artifacts/builder-image.json"
    container 'dpkg -l' > "$work/artifacts/dpkg.txt"
    budget=$(value candidate.full_build_budget)
    printf '0\n' > "$work/full-builds"
    for ((attempt=1; attempt<=budget; attempt++)); do
      container 'make tici_defconfig O=out; make -j"$(nproc)" dtbs O=out'
      python3 "$scripts/kernel_build_data.py" cheap --work "$work"
      printf '%s\n' "$attempt" > "$work/full-builds"
      container 'make -j"$(nproc)" O=out'
      if python3 "$scripts/kernel_build_data.py" stock --work "$work"; then
        # Explicit rebuild-mode CLI as well as the API used by publish.
        python3 "$scripts/kernel_equiv.py" --mode rebuild "$work/stock.img" "$work/artifacts/stock-rebuilt.img"
        exit 0
      else
        rc=$?
        if (( rc != 2 || attempt == budget )); then
          echo 'K5: FAIL: candidate rejected (certificate retry may have exhausted its reserved budget)'
          exit 1
        fi
      fi
      # A certificate-length retry is a FULL build and spends a reserved slot.
      # This path is inside the disposable export; there are no later git calls.
      container 'rm -rf out'
    done
    ;;
  wpa3)
    python3 "$scripts/kernel_build_data.py" patch --work "$work"
    container 'make tici_defconfig O=out; make -j"$(nproc)" O=out'
    python3 "$scripts/kernel_build_data.py" wpa3 --work "$work"
    container '
      dirs=(out/drivers/staging/qcacld-3.0 out/drivers/staging/qca-wifi-host-cmn out/drivers/staging/fw-api out/net/wireless out/net/mac80211)
      for dir in "${dirs[@]}"; do
        if [[ -d "$dir" ]]; then
          while IFS= read -r -d "" object; do
            /tools/bin/aarch64-linux-gnu-objcopy --strip-debug --remove-section=.comment "$object" "$object.stripped"
          done < <(find "$dir" -type f -name "*.o" ! -name built-in.o -print0)
        fi
      done'
    python3 "$scripts/kernel_build_data.py" manifests --work "$work"
    ;;
  *) echo 'K*: FAIL: command must be stock or wpa3'; exit 1 ;;
esac
