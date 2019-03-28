#!/bin/bash

#=============================================================================
#!
#! Program/script exit codes, as proposed by:
#!
#!   https://www.tldp.org/LDP/abs/html/exitcodes.html
#!
#!   * user defined exit error codes should be between 64-113
#!   * a generic catch all error code of 1 is permissible.
#!   * 0 for success
#!
#=============================================================================

device="cdc-wdm0"

dev_file="/dev/${device}"

#! Modem now takes longer to come backup
#! (10 was ok for Jessie, need at least 20 for Buster)
retries=40

#! delay in seconds between power-off and power-on of modem
modem_power_cycle_delay=5



#=============================================================================
#! run the argument as a command if DEBUG is set
#=============================================================================
function debug
{
    if (( DEBUG )) ; then
        #echo "@ = $@"
        "$@"
    fi
}



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
    /opt/sbin/modem.py power-cycle --delay="${modem_power_cycle_delay}"
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
    local code="${1:-1}"
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

    for (( i = 1 ; i <= retries ; i++ )) ; do
        debug echo "DEBUG: check modem is off: '${device}' (attempt: ${i})"

        if [ ! -e "${dev_file}" ] ; then
            break
        fi

        sleep 1
        false       #! ensure failure on exit when loop overflows
    done || fatal_error 64 "Modem did not turn off !!"

    echo "Modem is off"
fi



#!
#! Turn on the modem.
#!
modem_power_on

for (( i = 1 ; i <= retries ; i++ )) ; do
    debug echo "DEBUG: check modem is on: '${device}' (attempt: ${i})"

    if [ -e "${dev_file}" ] ; then
        break
    fi

    sleep 1
    false       #! ensure failure on exit when loop overflows
done || fatal_error 65 "Modem did not turn on !!"

echo "Modem is on"



#!
#! Wait until the NetworkManager device is available
#!
echo "Waiting for NetworkManager device..."

for (( i = 1 ; i <= retries ; i++ )) ; do
    debug echo "DEBUG: detect NetworkManager device: ${device} (attempt: ${i})"

    nmcli d | grep --quiet "${device}"
    (( ret = $? ))

    if (( ret == 0 )); then
        break
    fi

    sleep 1
    false       #! ensure failure on exit when loop overflows
done || fatal_error 66 "could not detect NetworkManager device: '${device}' !!"

echo "Detected NetworkManager device"



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
#! nmcli has been know to hang/freeze if chrony has adjusted time forward,
#! causing large delays for this script to complete
#! use `timeout` command to allow 60 seconds to complete,
#! then send TERM signal to terminate the command,
#! then send KILL signal 5 seconds later if still running.
#!
echo "NetworkManager connecting..."

debug echo "DEBUG: modem-power-enable: timeout 0: $(date)"

out=$( timeout --kill-after 5 60 nmcli d connect "${device}" )
(( ret = $? ))

echo "${out}" | grep --quiet -i "error"
(( err = ! $? ))

debug echo "DEBUG: modem-power-enable: timeout 1: ret=$? : $(date)"

if (( ret || err )) ; then
    fatal_error 67 "NetworkManager failed to connect device: '${device}' !!"
fi

echo "NetworkManager connected"



#!
#! Done
#!
echo "Modem connected to Internet"
modem_led_on
