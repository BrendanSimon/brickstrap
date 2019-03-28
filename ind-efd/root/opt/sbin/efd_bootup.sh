#!/bin/bash

#!=============================================================================
#!
#! This script performs EFD specific bootup tasks.
#! e.g. ensuring system settings are configured in the system,
#!      such as creating/removing cron files, etc.
#!
#!=============================================================================



#! Read user settings file.
source /mnt/data/etc/settings



script_name="$( basename $0 )"



echo "Starting '${script_name}'"



#! Run the periodic_reboot_update.sh script to create or remove the
#! cron file according to settings in the user settings file.
echo "Running 'periodic_reboot_update.sh'"
/opt/sbin/periodic_reboot_update.sh



echo "Finished '${script_name}'"
