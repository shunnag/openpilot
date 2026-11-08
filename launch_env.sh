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
  export AGNOS_VERSION="20.3"
fi

export WPA3_BOOT_TAG="wpa3.sae=5"
export WPA3_BOOT_HASH="8781946a19efae45a007c7de683f59a9964f57d603cf75a0fa4339a80090359e"
export WPA3_SUPPLICANT_STOCK_SHA256="b0f1c8ee9bb32153faed468c68390db4691b252ffd6a90e6d3d7b49f4d106bdd"

export WPA3_MODEM_STOCK_SHA256="c4ceaa996ede974fee9ce4c23dfdf8f5f37345d357c8c0ca0144b9539beea2bf"
export WPA3_MODEM_SERVICE_SHA256="371ce23460b7d13a365fb78e27202fbf43c95762a6d9d6b1003f0edd26924dc4"
export WPA3_MODEM_SHA256="908efd1111f3226727376504fe3a7e970130819f0218eb8f57f79a17aa22ed06"

export STAGING_ROOT="/data/safe_staging"
