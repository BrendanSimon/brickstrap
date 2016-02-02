#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

"""IND Driver Module."""

#from enum import IntEnum

import sys
import time
import argh

import ind

## could make this a runtime option.
DEBUG = False

##============================================================================

def power_off():
    """Power off the modem."""
    print("Turning modem 'off'")
    ind.modem_power_off(dev_hand=dev_hand)

##----------------------------------------------------------------------------

def power_on():
    """Power on the modem."""
    print("Turning modem 'on'")
    ind.modem_power_on(dev_hand=dev_hand)

##----------------------------------------------------------------------------

#@argh.arg('delay', help='delay in seconds between turning off then on.')

def power_cycle(delay=0.5):
    """Power cycle the modem."""

    power_off()
    print("Sleeping {} seconds ...".format(delay))
    time.sleep(delay)
    power_on()

##============================================================================

if __name__ == '__main__':
    ## assembling commands.
    parser = argh.ArghParser()
    commands = [ power_off, power_on, power_cycle ]
    parser.add_commands(commands)

    #with ind.get_device_handle() as dev_hand:
    dev_hand = ind.get_device_handle()

    ## dispatching commands.
    parser.dispatch()

##============================================================================

