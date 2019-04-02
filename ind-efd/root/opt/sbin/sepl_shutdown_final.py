#!/usr/bin/env python2

#!============================================================================
#!
#!  This script is intended to run late in the shutdown process to:
#!  * flash some LEDs (for visual indication of shutdown).
#!  * signal the external power management controller that we have shutdown.
#!  * output some messages to log.
#!
#!  Copyright (C) 2017-2019 Successful Endeavours Pty Ltd
#!
#!============================================================================

import sys
import time

import ind

#!============================================================================

def led_off ( dev_hand=None ) :
    """Turn off LEDs."""

    #ind.leds_modify( off=0xfffffff, dev_hand=dev_hand )
    ind.battery_led_off( dev_hand=dev_hand )
    ind.power_led_off( dev_hand=dev_hand )
    ind.alert_led_off( dev_hand=dev_hand )

#!============================================================================

def led_on ( dev_hand=None ) :
    """Turn on LEDs."""

    #ind.leds_modify( on=0xfffffff, dev_hand=dev_hand )
    ind.battery_led_on( dev_hand=dev_hand )
    ind.power_led_on( dev_hand=dev_hand )
    ind.alert_led_on( dev_hand=dev_hand )

#!============================================================================

def led_cycle ( count, delay, dev_hand=None ) :
    """Cycle the on/off the LEDs."""

    for i in range( count ):
        led_on( dev_hand=dev_hand )
        time.sleep( delay )
        led_off( dev_hand=dev_hand )
        time.sleep( delay )

#!============================================================================

def main():
    """Main entry function for the script."""

    print( "SHUTDOWN_FINAL: started" )

    with open( "/dev/IND" ) as dev_hand:

        #! cycle the LEDs for visual indication
        led_cycle( count=8, delay=0.1, dev_hand=dev_hand )

        #! ensure all LEDs are off, except for the alert LED.
        ind.leds_modify( off=0xfffffff, dev_hand=dev_hand )
        ind.alert_led_on( dev_hand=dev_hand )

        #! indicate to external power management controller that we have completed shutdown
        ind.power_os_running_off( dev_hand=dev_hand )

        print( "SHUTDOWN_FINAL: deasserted nOS_RUNNING pin" )

    print( "SHUTDOWN_FINAL: complete" )
    sys.stdout.flush()

#!============================================================================

if __name__ == "__main__":
    main()

#!============================================================================
