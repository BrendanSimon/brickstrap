#!/bin/bash

## The modem python script removes power to the modem.
function modem_power_off
{
    /opt/sbin/modem.py power-off
}

## The modem python script restores power to the modem.
function modem_power_on
{
    /opt/sbin/modem.py power-on
}

## The modem python script toggles the modem power line
function modem_power_cycle
{
    /opt/sbin/modem.py power-cycle
}

## period to wait before checking results of a command.
delay=0.5

device=cdc-wdm0
dev_file=/dev/${device}
# If the modem is already ON, we need to power it down first to
# start it in a known state
while [ -e ${dev_file} ];
do
    modem_power_off
    sleep ${delay}
done

## Turn Modem LED off
/opt/sbin/modem_led.py off

while [ ! -e ${dev_file} ];
do
    modem_power_on
    sleep ${delay}
done

# Bring up the network connection once the network interface
# is available
until nmcli d | grep ${device}
do
    sleep ${delay}
done

nmcli d connect cdc-wdm0
if [ $? -ne 0 ] ; then
    exit -1
fi

## Turn Modem LED on
/opt/sbin/modem_led.py on

