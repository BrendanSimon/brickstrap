#!/bin/bash

#!
#! Use curl to do an EFD Ping to the cloud service.
#!
#! EFD_PING_SERVERS must be set in the settings file.
#! If not set, then no efd-pings will occur.
#!

#! Read user settings file.
source /mnt/data/etc/settings

efd_ping_servers="${EFD_PING_SERVERS}"

efd_ping_api="api/Ping"

serial_number="${SERIAL_NUMBER:-0}"

for server in ${efd_ping_servers} ; do
    url="${server}/${efd_ping_api}/${serial_number}/"
    #echo "DEUBG: url = ${url}"
    curl --silent --request GET ${url} > /dev/null
done

