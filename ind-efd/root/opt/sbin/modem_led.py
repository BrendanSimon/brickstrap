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

LED = ind.LED.Modem_OK

##============================================================================
## Commands
##============================================================================

def off():
    """Turn off the modem LED."""
    with ind.get_device_handle() as dev_hand:
        ind.leds_modify(off=LED, dev_hand=dev_hand)

##----------------------------------------------------------------------------

def on():
    """Turn on the modem LED."""
    with ind.get_device_handle() as dev_hand:
        ind.leds_modify(on=LED, dev_hand=dev_hand)

##----------------------------------------------------------------------------

def toggle():
    """Toggle on the modem LED."""
    with ind.get_device_handle() as dev_hand:
        ind.leds_modify(toggle=LED, dev_hand=dev_hand)

##============================================================================

def main():
    '''Main entry if running this module from command line.'''

    ## assembling commands.
    parser = argh.ArghParser()
    commands = [ off, on, toggle ]
    parser.add_commands(commands)

    ## dispatching commands.
    parser.dispatch()


##============================================================================

if __name__ == "__main__":
    main()

##============================================================================

