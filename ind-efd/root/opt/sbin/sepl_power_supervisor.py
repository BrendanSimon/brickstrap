#!/usr/bin/env python2

#!============================================================================
#!
#!  This script is run at boot and monitors whether a shutdown has been
#!  requested by the external power management controller and initiates
#!  the shutdown process.
#!
#!  Copyright (C) 2017-2019 Successful Endeavours Pty Ltd
#!
#!============================================================================

import sys
import time
import subprocess

import ind

#!============================================================================

shutdown_cmd = "/sbin/poweroff"

delay = 1

#!============================================================================

def led_off ( dev_hand=None ) :
    """Turn battery and power LED off"""

    ind.battery_led_off( dev_hand=dev_hand )
    ind.power_led_off( dev_hand=dev_hand )

#!============================================================================

def led_on ( dev_hand=None ) :
    """Turn battery and power LED on"""

    ind.battery_led_on( dev_hand=dev_hand )
    ind.power_led_on( dev_hand=dev_hand )

#!============================================================================

def shutdown () :
    """Shutdown the system"""

    print( "SHUTDOWN: calling '{}'".format( shutdown_cmd ) )
    sys.stdout.flush()

    subprocess.call( shutdown_cmd )

#!============================================================================

def main () :
    """Main entry function for the script"""

    with open( "/dev/IND" ) as dev_hand :

        #! indicate to external power management controller that we are up and running.
        ind.power_os_running_on( dev_hand=dev_hand )

        #! turn leds on
        led_on( dev_hand=dev_hand )

        while True:
            #! check if shutdown has been requested (shutdown button pressed)
            shutdown_req = ind.power_shutdown_requested( dev_hand=dev_hand )

            if shutdown_req :
                print( "SHUTDOWN_REQUEST detected" )
                #! kick off the shutdown
                shutdown()

            time.sleep( delay )

#!============================================================================

if __name__ == "__main__":
    main()

#!============================================================================
