#!/bin/bash

#=============================================================================

device="cdc-wdm0"

dev_file="/dev/${device}"

#! Modem now takes longer to come backup
#! (10 was ok for Jessie, need at least 20 for Buster)
retries=40

#=============================================================================
#! Power OFF the modem (takes approximately 2-3 seconds).
#!
#! NOTE: be careful calling this repeatedly !!
#!       This will actually:
#!          * turn OFF the modem if it is ON.
#!          * turn ON  the modem if it is OFF.
#=============================================================================
function modem_power_off
{
    /opt/sbin/modem.py power-off
}

#=============================================================================
#! Power ON the modem (takes approximately 4-5 seconds).
#=============================================================================
function modem_power_on
{
    /opt/sbin/modem.py power-on
}

#=============================================================================
#! The modem python script toggles the modem power line
#=============================================================================
function modem_power_cycle
{
    /opt/sbin/modem.py power-cycle --delay=5
}

#=============================================================================
#! Turn Modem LED off
#=============================================================================
function modem_led_off
{
    /opt/sbin/modem_led.py off
}

#=============================================================================
#! Turn Modem LED on
#=============================================================================
function modem_led_on
{
    /opt/sbin/modem_led.py on
}

#=============================================================================
#! Display error message and exit with an error code
#=============================================================================
function fatal_error
{
    local code="${1:--1}"
    local mesg="ERROR: $2"
    echo "${mesg}"
    exit ${code}
}

#=============================================================================
#! Main
#=============================================================================

modem_led_off

#!
#! If modem is already on, turn it off to start it in a known state.
#! NOTE: should only be done once as another attempt will turn the modem on !!
#!
if [ ! -e "${dev_file}" ] ; then
    echo "Modem already off"
else
    modem_power_off
    for i in $(seq ${retries}) ; do
        #echo "DEBUG: check modem is off: '${device}' (attempt: ${i})"
        if [ ! -e "${dev_file}" ] ; then
            break
        fi
        sleep 1
    done || fatal_error 1 "Modem did not turn off !!"
    echo "Modem is off"
fi

#!
#! Turn on the modem.
#!
modem_power_on
for i in $(seq ${retries}) ; do
    #echo "DEBUG: check modem is on: '${device}' (attempt: ${i})"
    if [ -e "${dev_file}" ] ; then
        break
    fi
    sleep 1
done || fatal_error 2 "Modem did not turn on !!"
echo "Modem is on"

#!
#! Wait until the network interface is available
#!
for i in $(seq ${retries}) ; do
    #echo "DEBUG: detect NetworkManager device: ${device} (attempt: ${i})"
    nmcli d | grep --quiet "${device}"
    if [ $? -eq 0 ] ; then
        break
    fi
    sleep 1
done || fatal_error 3 "could not detect NetworkManager device: '${device}' !!"

#!
#! Bring up the network connection.
#!
#! note: nmlci returns 0 on some errors :(
#!
#!  # nmcli d connect cdc-wdm0
#!  Error: Connection activation failed: (1) Unknown error.
#!  # echo $?
#!  0
#!
out=$( nmcli d connect "${device}" )
ret=$?
echo "${out}" | grep --quiet -i "error"
err=$?
if (( ret != 0 || err == 0 )) ; then
    fatal_error 4 "NetworkManager failed to connect device: '${device}' !!"
fi

#!
#! Done
#!
echo "Modem connected to Internet"
modem_led_on
