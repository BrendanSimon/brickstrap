#!/bin/bash

##
## Use curl to do an EFD Ping to the cloud service.
##

## Read user settings file.
source /mnt/data/etc/settings

web_server="http://portal.efdweb.com"
web_server_ping="${web_server}/api/Ping"
serial_number="${SERIAL_NUMBER:-0}"

url="${web_server_ping}/${serial_number}/"

curl --silent --request GET ${url} > /dev/null

