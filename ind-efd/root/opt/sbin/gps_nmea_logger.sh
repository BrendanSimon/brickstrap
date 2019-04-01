#!/bin/bash

#!=============================================================================
#!
#! This script logs GPS NMEA sentences to disk for diagnostics.
#!
#! This script is called from systemd and will be restarted if it exits.
#!
#! It defaults to being disabled so users can explicitly start or enable it
#! on only the units of interest.
#!
#!=============================================================================



#! Use an emulated version of the BASH internal SECONDS feature
#! (avoids issues with system wall clock adjustments)
#source /opt/sbin/bash_seconds.sh



#! Read user settings file.
#source /mnt/data/etc/settings



#! Read gpsd settings file
source /etc/default/gpsd

gps_dev="${DEVICES}"


#! directory to log output fle to.
log_dir="/mnt/data/log/gps_nmea"

#! file to log output data to.
log_file="${log_dir}/gps_nmea.log"



#=============================================================================
#! output arguments to stdout if DEBUG is set
#=============================================================================
function debug
{
    if (( DEBUG )) ; then
        echo "DEBUG: $@"
    fi
}



#=============================================================================
#! echo arguments to stdout if DRYRUN is set, else run the arguments as a command
#=============================================================================
function run
{
    if (( DRYRUN )) ; then
        echo "DRYRUN: $@"
    else
        debug "$@"
        "$@"
    fi
}



#!=============================================================================
#! main
#!=============================================================================

#! output settings (debug mode)
debug "log_dir  = ${log_dir}"
debug "log_file = ${log_file}"
debug "gps_dev  = ${gps_dev}"

#! make sure log directory exisits
mkdir -p "${log_dir}"

#! log output of gpscat to log file.
run gpscat "${gps_dev}" >> "${log_file}"



#!=============================================================================
