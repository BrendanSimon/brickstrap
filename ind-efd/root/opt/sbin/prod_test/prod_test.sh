#!/bin/bash

set -e

PROD_TEST_DIR="/opt/sbin/prod_test"

PROD_TEST="${PROD_TEST_DIR}/prod_test.py"

LOG_DIR="/boot/flash"
LOG_FILE="${LOG_DIR}/prodtest.txt"
LOG_FILE_TMP="/tmp/prod_tmp.txt"

sudo mount -o remount,rw ${LOG_DIR}

#cd ${PROD_TEST_DIR}
#pwd
#echo "Executing ${PROD_TEST}"
sudo ${PROD_TEST} 2>&1 | tee ${LOG_FILE_TMP}
sudo bash -c "cat ${LOG_FILE_TMP} >> ${LOG_FILE}"
rm ${LOG_FILE_TMP}

sync
sudo mount -o remount,ro ${LOG_DIR}
sync

