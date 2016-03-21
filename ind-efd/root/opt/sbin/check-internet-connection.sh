#!/bin/bash

##
## This script periodically checks to see if the internet connection is up,
## and will attempt to reconnect if it is down.
##
## This script is called from systemd and will be restarted if it exits.
##
## The modem-power-enable.sh script is non-renetrant, which therefore makes
## this script non-rentrant too.
## i.e. it must only be invoked once (by systemd) and no other scripts can
## call the modem-power-enable.sh script.
##

## Read user settings file.
source /mnt/data/etc/settings

##
## FIXME: get ping server info from user settings file.
##

##
## Ping servers.
## -------------
## 8.8.8.8      => Google nameserver.
## 203.14.0.250 => Telstra ntp server (tic.ntp.telstra.net).
## 203.14.0.251 => Telstra ntp server (toc.ntp.telstra.net).
##

ping_server="${PING_SERVER:-203.14.0.251}"

while true ; do
    echo "Pinging ${ping_server}"
    ping -c 3 ${ping_server} > /dev/null
    if [ $? -ne 0 ]; then
        echo "Ping failed.  Attempting to restart internet connection ..."
        /opt/sbin/modem-power-enable.sh
    fi

    ## Sleep for 1 minute.
    sleep 60
done

