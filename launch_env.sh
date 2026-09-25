#!/usr/bin/env bash

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

# models get lower priority than ui
# - ui is ~5ms
# - modeld is 20ms
# - DM is 10ms
# in order to run ui at 60fps (16.67ms), we need to allow
# it to preempt the model workloads. we have enough
# headroom for this until ui is moved to the CPU.
export QCOM_PRIORITY=12

if [ -z "$AGNOS_VERSION" ]; then
  export AGNOS_VERSION="19.8"
fi

export WPA3_BOOT_TAG="wpa3.sae=2"
export WPA3_BOOT_HASH="862b653d80c9d7ac933a60d2bb748371a3267f658194e6ca7273f33c2973de94"
export WPA3_SUPPLICANT_STOCK_SHA256="b0f1c8ee9bb32153faed468c68390db4691b252ffd6a90e6d3d7b49f4d106bdd"

export STAGING_ROOT="/data/safe_staging"
