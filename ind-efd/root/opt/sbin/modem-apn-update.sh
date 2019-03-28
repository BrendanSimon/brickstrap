#!/bin/bash

#!=============================================================================
#!
#! This script checks if the apn settings in the user settings file has changed.
#! If it has changed, the script will update the network manager configuration,
#! reload the configuration and restart the service.
#!
#!=============================================================================



#! Read user settings file.
source /mnt/data/etc/settings



#!============================================================================
#! Reload network connection
#!============================================================================
function nm_connection_reload
{
    local ret

    echo "Reloading NetworkManger connection..."

    nmcli con reload

    ret=$?
    if (( ret != 0 )); then
        echo "Error: Failed to reload NetworkManger connection"
    fi

    return $ret
}



#!============================================================================
#! Restart network manager service
#!============================================================================
function nm_service_restart
{
    local ret

    echo "Restarting NetworkManger service..."

    systemctl restart NetworkManager.service

    ret=$?
    if (( ret != 0 )); then
        echo "ERROR: Failed to restart NetworkManger service !!"
    fi

    return $ret
}


#!============================================================================
#! Update GSM APN setting in NetworkManager connection config file.
#!============================================================================
function nm_connection_apn_update
{
    local ret

    echo "Updating NetworkManger connection with new APN setting: ${new_apn_setting}"

    #! replace "apn=" line using sed inline replacement
    pattern="s/apn=.*/${new_apn_setting}/"
    sed -i -- "${pattern}" "${nm_connection_config}"

    ret=$?
    if (( ret != 0 )); then
        echo "ERROR: Failed updating NetworkManger connection with new APN setting !!"
    fi

    return $ret
}




#!=============================================================================
#!
#! Check if APN setting needs to be updated in NetworkManager connection config file.
#!
#! Does NetworkManager need to be explicilty restarted?
#!
#!=============================================================================

#! get gsm network apn info from user settings file.
network_apn="${NETWORK_APN:-telstra.extranet}"

#! NetworkManager connection config file.
nm_connection_config="/etc/NetworkManager/system-connections/telstra-mobile-broadband-1"

#!
#! does connection config have our apn configured?
#!

new_apn_setting="apn=${network_apn}"

cur_apn_setting=$( grep "^apn=.*" "${nm_connection_config}" )

if [ "${cur_apn_setting}" == "${new_apn_setting}" ]; then
    echo "GSM Network APN setting is up to date"
else
    echo "GSM Network APN setting is out of date"

    #! update gsm apn setting in connection config file.
    nm_connection_apn_update
    if (( $? != 0 )); then
        exit $?
    fi

    #! reload NetworkManager connection.
    nm_connection_reload
    if (( $? != 0 )); then
        exit $?
    fi

#    #! restart NetworkManager service.
#    nm_service_restart
#    if (( $? != 0 )); then
#        exit $?
#    fi

fi
