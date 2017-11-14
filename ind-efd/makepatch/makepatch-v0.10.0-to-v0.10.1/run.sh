#!/bin/bash

prog=$0

archive="ind-efd-patch-v0.10.0-to-v0.10.1.tgz" 

services="serial-getty@ttyS1 chrony gpsd efd"

##===========================================================================

echo "Starting ['${prog}']"

echo "Unpacking patch archive to root ['${archive}' => '/']"
sudo tar zxvf ${archive} -C /

##
## Restart affected services.
##
echo "Reloading systemd service definition files."
sudo systemctl daemon-reload

sudo systemctl enable gpsd
sudo systemctl enable chrony

for srv in ${services}; do
    sleep 2
    echo "Restarting '${srv}' service."
    sudo systemctl restart ${srv}
done

echo "Finished ['${prog}']"

##===========================================================================

