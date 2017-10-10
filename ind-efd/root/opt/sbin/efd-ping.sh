#!/bin/bash

##
## Use curl to do an EFD Ping to the cloud service.
##

## Read user settings file.
#source /mnt/data/etc/settings
source settings

efd_ping_servers="${EFD_PING_SERVERS:-http://portal.efdweb.com}"

efd_ping_api="api/Ping"

serial_number="${SERIAL_NUMBER:-0}"

for server in ${efd_ping_servers} ; do
    url="${server}/${efd_ping_api}/${serial_number}/"
#    echo "DEUBG: url = ${url}"
    curl --silent --request GET ${url} > /dev/null
done

