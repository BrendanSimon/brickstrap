#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''Utility to manipulate the status LEDs.'''

import ind
import argh

## could make this a runtime option.
DEBUG = False

##============================================================================
## Commands
##============================================================================

def off(mask=0):
    """Turn off the LEDs specified by MASK."""
    ind.leds_modify(off=mask)

##----------------------------------------------------------------------------

def on(mask=0):
    """Turn on the LEDs specified by MASK."""
    ind.leds_modify(on=mask)

##----------------------------------------------------------------------------

def toggle(mask=0):
    """Toggle on the LEDs specified by MASK."""
    ind.leds_modify(toggle=mask)

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

