#!/bin/bash

set -e

PROG_DIR="/opt/sbin/prod_test"

PROG="${PROG_DIR}/adc_offset.py"

LOG_DIR="/boot/flash"
LOG_FILE="${LOG_DIR}/adc_off.txt"
LOG_FILE_TMP="/tmp/adc_tmp.txt"

sudo mount -o remount,rw ${LOG_DIR}

#cd ${PROG_DIR}
#pwd
#echo "Executing ${PROG}"
sudo ${PROG} "$@" 2>&1 | tee ${LOG_FILE_TMP}
sudo bash -c "cat ${LOG_FILE_TMP} >> ${LOG_FILE}"
rm ${LOG_FILE_TMP}

sync
sudo mount -o remount,ro ${LOG_DIR}
sync

