#!/bin/bash

prog=$(basename $0)

dir=$(dirname ${prog})

deb_files="${dir}/deb_files.txt"

archive="${dir}/ind-efd-patch-v0.10.1-to-v0.10.2-dev.tgz" 

services="chrony gpsd efd"

##===========================================================================

echo "Starting ['${prog}']"

## Stop affected services.
for srv in ${services}; do
    sleep 1
    echo "Stopping '${srv}' service."
    sudo systemctl stop ${srv}
done

## Install deb packages.
echo "Deleting old files..."
for f in $(cat ${deb_files}) ; do
    echo "Installing '${f}'"
    sudo dpkg -i ${f}
done

## Unpack new files.
echo "Unpacking patch archive to root ['${archive}' => '/']"
sudo tar zxvf ${archive} -C /

## Reload systemd config.
echo "Reloading systemd service definition files."
sudo systemctl daemon-reload

## Ensure all services are enabled (start on boot)
for srv in ${services}; do
    sudo systemctl enable ${srv}
done

## Restart affected services.
for srv in ${services}; do
    sleep 1
    echo "Restarting '${srv}' service."
    sudo systemctl restart ${srv}
done

echo "Finished ['${prog}']"

