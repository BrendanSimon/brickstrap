#!/bin/bash

#!=============================================================================
#!
#! This script monitors chrony for time synchronisation.
#! and will reboot the system if it loses sync.
#!
#! It is intended to be called periodically (e.g. via cron)
#!
#! override DRYRUN on command line for testing.
#! e.g. DRYRUN=1 ./chrony_watchdog.sh
#!
#! override DEBUG on command line for extra debug output.
#! e.g. DEBUG=1 ./chrony_watchdog.sh
#!
#!=============================================================================



#! Read user settings file.
source /mnt/data/etc/settings



script_name="$( basename $0 )"

status_file="/tmp/efd_chrony_watchdog"



function do_reboot
{
    local msg="Performing EFD Chrony Watchdog Reboot"

    #! send message to stdout
    echo "${msg}"

    #! send message journald/syslog (tag = name of this script)
    echo "${msg}" | systemd-cat -t "${script_name}"

    #! warm reboot
    if (( DRYRUN )) ; then
        echo "DRYRUN: /sbin/reboot"
    else
        /sbin/reboot
    fi
}



#! test existance of status file to determine if this first run or not
[[ -e "${status_file}" ]]
#not_first_run=$?
#(( first_run = ! $? ))
(( first_run = $? ))

#! get output of "chronyc sources" command
chronyc_sources="$( chronyc sources )"

#! extract the status field
status_field="$( echo "${chronyc_sources}" | grep GPS | cut -c 2 )"

if (( first_run )) ; then
    status="FIRST-BOOT"
else
    case "${status_field}" in
        "*")
            status="OK"
            ;;
        "?")
            status="BAD"
            ;;
        *)
            status="UNKNOWN"
            ;;
    esac
fi



#! debug output
if (( DEBUG )) ; then
    echo "DEBUG: first_run = ${first_run}"
    echo "DEBUG: status_field = ${status_field}"
    echo "DEBUG: status = ${status}"
fi



#! send status to stdout
echo "status = ${status}"

#! send status journald/syslog (tag = name of this script)
echo "status = ${status}" | systemd-cat -t "${script_name}"



#! send status and chrony sources to status file.
rm -f "${status_file}"
echo -e "${status}" >> "${status_file}"
echo "" >> "${status_file}"
echo -e "${chronyc_sources}" >> "${status_file}"



#! check chrony status
if [[ "${status}" == "BAD" ]] ; then
    #! call reboot function
    do_reboot
fi
