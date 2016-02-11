#!/bin/bash

##
## This script periodically checks to see if the internet connection is up,
## and will attempt to reconnect if it is down.
## This script is called from systemd and will be restarted if it exits.
##

ping_server="pool.ntp.org"

while true ; do
    echo "Pinging ${ping_server}"
    ping -c 1 ${ping_server} > /dev/null
    if [ $? -ne 0 ]; then
        echo "Ping failed.  Attempting to restart internet connection ..."
        /opt/sbin/modem-power-enable.sh
    fi

    ## Sleep for 1 minute.
    sleep 60
done

