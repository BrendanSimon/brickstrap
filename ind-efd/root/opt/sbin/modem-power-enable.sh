#!/bin/bash

# The modem python script toggles the modem power
# line
function toggle_power {
        /opt/sbin/modem.py 0.2
}

## Turn Modem LED off
/opt/sbin/modem_led.py 0

device=cdc-wdm0
dev_file=/dev/${device}
# If the modem is already ON, we need to power it down first to
# start it in a known state
if [ -e $dev_file ]
then
        toggle_power
        while [ -e $dev_file ];
        do
                sleep 0.1
        done
fi
toggle_power

# Bring up the network connection once the network interface
# is available
until nmcli d | grep $device
do
        sleep 0.1
done
nmcli d connect cdc-wdm0

## Turn Modem LED on
/opt/sbin/modem_led.py 1

