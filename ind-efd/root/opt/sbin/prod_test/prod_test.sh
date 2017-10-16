#!/bin/bash

set -e

PROD_TEST_DIR="/opt/sbin/prod_test"

PROD_TEST="./prod_test.py"

LOG_DIR="/boot/flash"

LOG_FILE="${LOG_DIR}/prodtest.txt"
LOG_FILE_NEW="${LOG_DIR}/prod_new.txt"

sudo mount -o remount,rw ${LOG_DIR}

cd ${PROD_TEST_DIR}
sudo ${PROD_TEST} 2>&1 | tee ${LOG_FILE_NEW}
sudo cat ${LOG_FILE_NEW} >> ${LOG_FILE}
sudo rm ${LOG_FILE_NEW}

sync

