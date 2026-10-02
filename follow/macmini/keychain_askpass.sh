#!/bin/bash
set -euo pipefail
set +x
case ${1:-} in
  *Username*) printf '%s\n' 'x-access-token' ;;
  *Password*) /usr/bin/security find-generic-password -s wpa3-test-results -w ;;
  *) exit 1 ;;
esac
