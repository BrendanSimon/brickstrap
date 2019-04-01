#!/bin/bash

#!=============================================================================
#!
#! This script checks if the period reboot settings in the user settings file
#! has changed.
#!
#! If it has changed, the script will update the cron file entry,
#! and restart the service.
#!
#!=============================================================================



#! Read user settings file.
source /mnt/data/etc/settings



#!============================================================================
#! Restart cron service
#!============================================================================
function cron_service_restart
{
    local ret

    echo "Restarting cron service..."

    systemctl restart cron.service

    ret=$?
    if (( ret != 0 )); then
        echo "ERROR: Failed to restart cron service !!"
    fi

    return ${ret}
}


#!============================================================================
#! Update Periodic Reboot setting in cron config file.
#!============================================================================
function cron_config_update
{
    local ret

    if [[ "${periodic_reboot_sched}" == "" ]] ; then
        #! remove cron config file
        echo "Removing cron config file: periodic_reboot not set or empty"
        rm -f "${cron_config}"
    else
        #! recreate cron config file
        echo "Updating cron config file with new Periodic Reboot setting: ${periodic_reboot_sched}"
        local msg=""
        msg+="# Perform EFD Periodic Reboot with the following schedule\n"
        msg+="${new_periodic_reboot_setting}\n"
        echo -e "${msg}" > "${cron_config}"
    fi

    ret=$?
    if (( ret != 0 )); then
        echo "ERROR: Failed updating cron config file with new Periodic Reboot setting !!"
    fi

    return ${ret}
}




#!=============================================================================
#!
#! Check if Periodic Reboot setting needs to be updated in cron config file.
#!
#!=============================================================================

#! get periodic reboot setting from user settings file.
periodic_reboot_sched="${PERIODIC_REBOOT_SCHED}"

#! cron config file.
cron_config="/etc/cron.d/efd_periodic_reboot"

#!
#! check if cron config file needs updating or removed
#!

new_periodic_reboot_setting="${periodic_reboot_sched} root /opt/sbin/periodic_reboot.sh"

cur_periodic_reboot_setting=$( fgrep "periodic_reboot.sh" "${cron_config}" 2> /dev/null )

if (( DEBUG )) ; then
    echo "DEBUG: periodic_reboot_sched = ${periodic_reboot_sched}"
    echo "DEBUG: new_periodic_reboot_setting = ${new_periodic_reboot_setting}"
    echo "DEBUG: cur_periodic_reboot_setting = ${cur_periodic_reboot_setting}"
fi

if [[ "${cur_periodic_reboot_setting}" == "${new_periodic_reboot_setting}" ]] ; then
    #! cron file does exist
    echo "EFD Periodic Reboot setting is up to date (enabled)"
elif [[ "${cur_periodic_reboot_setting}" == "${periodic_reboot_sched}" ]] ; then
    #! cron file does not exist
    echo "EFD Periodic Reboot setting is up to date (disabled)"
else
    echo "EFD Periodic Reboot setting is out of date (enabled)"

    #! update Periodic Reboot setting in cron config file.
    cron_config_update
    if (( $? != 0 )); then
        exit $?
    fi

    #! restart cron service.
    cron_service_restart
    if (( $? != 0 )); then
        exit $?
    fi

fi
