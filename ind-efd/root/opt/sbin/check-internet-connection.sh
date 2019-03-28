#!/bin/bash

#!=============================================================================
#!
#! This script periodically checks to see if the internet connection is up,
#! and will attempt to reconnect if it is down.
#!
#! This script is called from systemd and will be restarted if it exits.
#!
#! The modem-power-enable.sh script is non-renetrant, which therefore makes
#! this script non-rentrant too.
#! i.e. it must only be invoked once (by systemd) and no other scripts can
#! call the modem-power-enable.sh script.
#!
#!=============================================================================



#! Use an emulated version of the BASH internal SECONDS feature
#! (avoids issues with system wall clock adjustments)
source /opt/sbin/bash_seconds.sh



#! Read user settings file.
source /mnt/data/etc/settings



#!=============================================================================
#!
#! Check if APN setting needs to be updated in NetworkManager connection profile.
#!
#!=============================================================================

/opt/sbin/modem-apn-update.sh



#!=============================================================================
#!
#! Periodically check internet connection by pinging servers that are
#! known to have high availability.
#!
#! Attempt recovery by power cycling modem if pings response fails.
#!
#! Attempt recovery by rebooting system if no response for long period.
#!
#! Ping servers:
#! -------------
#! 8.8.8.8      => Google nameserver.
#! 203.14.0.250 => Telstra ntp server (tic.ntp.telstra.net).
#! 203.14.0.251 => Telstra ntp server (toc.ntp.telstra.net).
#!
#!=============================================================================

#! get ping server info from user settings file.
ping_server="${PING_SERVER:-203.14.0.251}"

#! number of ping packets to send (default is 10)
ping_count="${PING_COUNT:-10}"

#! ping reboot timeout (default is 10 minutes => 600 seconds)
reboot_timeout="${PING_REBOOT_TIMEOUT:-600}"



#!=============================================================================
#!
#! Function to reboot the system.
#!
#! Currently this is a warm reboot, rather than a cold reboot via `poweroff`
#! so as to avoid undesireable behaviour of some Power Management Control
#! systems.
#!
#! This function might be expanded to check settings to do a warm or cold reboot.
#!
#!=============================================================================

function do_reboot
{
    local msg="Ping server reboot timeout (SECONDS=${SECONDS} > reboot_timeout=${reboot_timeout})"

    if (( 0 )) ; then
        echo "POWEROFF: ${msg}"
        /sbin/poweroff
    else
        echo "REBOOT: ${msg}"
        /sbin/reboot
    fi
}



#!=============================================================================
#!
#! Periodically check for ping responses
#!
#! Attempt recovery by power cycling modem if pings response fails.
#!
#! Attempt recovery by rebooting system if no response for long period.
#!
#!=============================================================================

while true ; do
    #! get the emulated BASH internal SECONDS counter
    bash_seconds_update

    #! get modem number.
    modem=$(mmcli -L | grep -oP '/Modem/\K\d+(?= )')

    #! get modem status information
    mmcli_out=$(mmcli -m ${modem})

    #! get modem signal quality.
    signal_quality=$(echo "${mmcli_out}" | grep -oP 'signal quality:.*')

    #! get modem access technology
    access_tech=$(echo "${mmcli_out}" | grep -oP 'access tech:.*')

    #! output modem status info
    echo "modem: ${modem}, ${signal_quality}, ${access_tech}"

    echo "Pinging ${ping_server} (count=${ping_count})"
    ping -c ${ping_count} ${ping_server} > /dev/null
    if (( $? == 0 )); then
        #! got a response => reset timer.
        SECONDS=0
        echo "Got ping response (SECONDS=${SECONDS}, reboot_timeout=${reboot_timeout})"
    elif (( SECONDS > reboot_timeout )); then
        #! no reponse for a long time => time to reboot.
        do_reboot
    else
        #! no reponse => try power cycling modem.
        echo "Ping failed (SECONDS=${SECONDS}, reboot_timeout=${reboot_timeout}).  Attempting to restart modem and internet connection..."
        /opt/sbin/modem-power-enable.sh
    fi

    #! Sleep for 1 minute.
    sleep 60
done
