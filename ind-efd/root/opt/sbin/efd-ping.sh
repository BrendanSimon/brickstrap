#!/bin/bash

## Use curl to do an EFD Ping to the cloud service.

## Read user settings file.
#source ~/tmp/settings
source /mnt/data/etc/settings

web_server="http://portal.efdweb.com"
web_server_ping="${web_server}/api/Ping"
serial_number="${SERIAL_NUMBER:-0}"

url="${web_server_ping}/${serial_number}/"

echo "url = ${url}"

curl -i -X GET ${url}

