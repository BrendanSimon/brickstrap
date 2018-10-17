#!/bin/bash

set -e

BOOT_DIR="/boot/flash"

PROG_DIR="${PROG_DIR:-/opt/sbin/prod_test}"

PROG="${PROG:-${PROG_DIR}/prod_test.py}"

LOG_DIR="${LOG_DIR:-${BOOT_DIR}}"

LOG_FILE="${LOG_FILE:-${LOG_DIR}/prodtest.txt}"



#! is log file in the read-only boot filesystem?
#! use base (( )) arithmentic operator to evaluate.
#! e.g. if (( log_file_in_boot )) ...
log_file_in_boot=$( [[ "${LOG_FILE}" == "${BOOT_DIR}"* ]] && echo 1 || echo 0 )



#!
#! cleanup function
#!
function cleanup
{
    #echo "CLEANUP"

    #!
    #! Remount the boot filesystem with read-only permission
    #!
    sync
    if (( log_file_in_boot )) ; then
        echo "Mount boot filesystem read-only"
        sudo -- mount -o remount,ro "${BOOT_DIR}"
    fi
    sync
}

#! call cleanup function on exit (even for ctrl-c interrupt)
trap cleanup EXIT



#!
#! Remount the boot filesystem with read-write permission
#!
if (( log_file_in_boot )) ; then
    echo "Mount boot filesystem read-write"
    sudo -- mount -o remount,rw "${BOOT_DIR}"
fi



#!
#! Execute prod_test.py script
#!

#cd ${PROG_DIR}
#echo "Executing ${PROG}"

sudo -- "${PROG}" -o "${LOG_FILE}" "$@"



#! Exit
#! cleanup function will be called now (due to trap exit)
