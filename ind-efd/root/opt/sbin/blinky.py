#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

"""Utility to blink/cycle through the status LEDs."""

import argh
import time
import ind

##============================================================================

def blinky(count=0, delay=0.1):
    """Cycle through all the LEDs."""

#    with ind.get_device_handle() as dev_hand:
#        ind.blinky(count=count, delay=delay, dev_hand=dev_hand)
    ind.blinky(count=count, delay=delay)

##============================================================================

if __name__ == "__main__":
    """Main entry if running this module from command line."""
    argh.dispatch_command(blinky)

##============================================================================

