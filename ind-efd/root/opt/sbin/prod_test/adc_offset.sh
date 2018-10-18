#!/bin/bash

set -e

BOOT_DIR="/boot/flash"

PROG_DIR="${PROG_DIR:-/opt/sbin/prod_test}"

PROG="${PROG:-${PROG_DIR}/adc_offset.py}"

LOG_DIR="${LOG_DIR:-${BOOT_DIR}}"

LOG_FILE="${LOG_FILE:-${LOG_DIR}/adc_off.txt}"

LOG_FILE_TMP="${LOG_FILE_TMP:-/tmp/adc_tmp.txt}"



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

    sudo -- rm -f "${LOG_FILE_TMP}"

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
#! Execute main program/script
#!

#cd ${PROG_DIR}
#echo "Executing ${PROG}"

#! use this if prog does stdout redirection, not this script !!
#sudo -- "${PROG}" -o "${LOG_FILE}" "$@"

#! use `script` to allow colours to work with redirection.
cmd="${PROG} $@ 2>&1"
sudo -- script -q -c "${cmd}" "${LOG_FILE_TMP}"

#! use `sed` strip colour codes from output and save to file
sudo -- bash -c "cat ${LOG_FILE_TMP} | sed -r 's/(\x9B|\x1B\[)([0-9]{1,2}(;[0-9]{1,2})?)?[mGK]//g' >> ${LOG_FILE}"



#! Exit
#! cleanup function will be called now (due to trap exit)
