#!/bin/bash

#!=============================================================================
#!
#! This script performs a system reboot.
#!
#! It is intended to be called by anohter process (e.g. a cron job)
#!
#!=============================================================================



#! Read user settings file.
source /mnt/data/etc/settings



script_name="$( basename $0 )"



function do_reboot
{
    local cmd="false"
    local msg="Performing EFD Periodic Reboot"

    #! Ignore `shutdown` type for now, until we check battery voltage is ok !!
    if (( 0 )) ; then
#    if [[ "${PERIODIC_REBOOT_TYPE}" == "shutdown" ]] ; then
        #! shutdown the system will force a power-cycle via the external PMC
        msg="SHUTDOWN: ${msg}"
        cmd="/sbin/poweroff"
    else
        #! default is warm reboot
        msg="REBOOT: ${msg}"
        cmd="/sbin/reboot"
    fi

    #! send message to stdout
    echo "${msg}"

    #! send message journald/syslog (tag = name of this script)
    echo "${msg}" | systemd-cat -t "${script_name}"

    #! do the command
    ${cmd}
}



#! call reboot function
do_reboot
