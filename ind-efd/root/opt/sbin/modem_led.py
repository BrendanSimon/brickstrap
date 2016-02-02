#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''IND Driver Module.'''

import sys
import time
import ind
import argh

## could make this a runtime option.
DEBUG = False

##============================================================================

def modem_led_set(state):
    """Set the modem LED."""

    led = ind.LED.Modem_OK

    on = 0
    off = 0

    if state:
        ## Led on
        on = led
    else:
        ## Led off
        off = led

    with ind.get_device_handle() as dev_hand:
        ind.leds_modify(on=on, off=off, dev_hand=dev_hand)

##============================================================================
## Commands
##============================================================================

def off():
    """Turn off the modem LED."""
    modem_led_set(False)

##----------------------------------------------------------------------------

def on():
    """Turn on the modem LED."""
    modem_led_set(True)

##============================================================================

def main():
    '''Main entry if running this module from command line.'''

    ## assembling commands.
    parser = argh.ArghParser()
    commands = [ off, on ]
    parser.add_commands(commands)

    #with ind.get_device_handle() as dev_hand:
    dev_hand = ind.get_device_handle()

    ## dispatching commands.
    parser.dispatch()


##============================================================================

if __name__ == "__main__":
    main()

##============================================================================

