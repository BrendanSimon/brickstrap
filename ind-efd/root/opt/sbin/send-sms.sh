#!/bin/bash -e

# Simple script to send an SMS using the first modem available in the system.
# invoke with $1 as the phone number and $2 as the message to send
# Depends on mmcli

PHONE="${1}"
MSG="${2}"

if [ -z "${PHONE}" ]; then
        echo "Missing Phone #"
        exit 1
fi

if [ -z "${MSG}" ]; then
        echo "Missing Message"
        exit 1
fi

MODEM=$(mmcli -L | grep "Modem" | sed "s:.*Modem/::" | sed "s: .*::g")

# All the information required for creating the SMS
SMS_INFO="text='${MSG}',number='${PHONE}'"

# The command needed for creating the SMS
CMD="mmcli -m ${MODEM} --messaging-create-sms=\"${SMS_INFO}\""

# Actually create the SMS. We're using the eval builtin because of all the
# quotes and double quotes in the command. eval executes the command. Also
# capture the output of the command in the process
CREATE_OUT=$(eval "$CMD")

# Send the SMS
SMS_ID=$(echo ${CREATE_OUT} | grep "Modem" | sed "s:.*SMS/::g" | sed "s: .*::g")
mmcli -s ${SMS_ID} --send

