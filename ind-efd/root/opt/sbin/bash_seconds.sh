#!/bin/bash

#!=============================================================================
#!
#! This script emulates the BASH internal SECONDS counter.
#!
#! BASH SECONDS appears to be derived from the system wall clock time,
#! which causes issues when the wall clock time jumps unexpectedly
#! (e.g. when chrony time daemon makes a large adjustment)
#!
#! Disable by unsetting SECONDS, then use SECONDS as a normal variable.
#!
#! Use this script by "sourcing" it, then calling the `bash_seconds_update`
#! function to get an updated value for SECONDS.
#!
#!=============================================================================


#! disable BASH internal SECONDS counter
unset SECONDS


#!
#! Get number of seconds since boot (using internal kernel timer)
#!
function bash_seconds_get_timer_count_seconds
{
    local count_ns
    local count_sec

    count_ns=$(cat /proc/timer_list | grep now | cut -d" " -f 3)

    (( count_sec = count_ns / 1000000000 ))

    echo ${count_sec}
}


#! Initialise the last second count (i.e. the current count value)
SECONDS_LAST=$(bash_seconds_get_timer_count_seconds)


#!
#! Emulate bash SECONDS feature (update the SECONDS variable)
#!
function bash_seconds_update
{
    local count_sec

    count_sec=$(bash_seconds_get_timer_count_seconds)

    (( count_since_last = count_sec - SECONDS_LAST ))

    (( SECONDS += count_since_last ))

    (( SECONDS_LAST = count_sec ))
}
