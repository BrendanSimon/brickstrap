#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''Utility to manipulate the Debug status LEDs.'''

import ind
import argh

## could make this a runtime option.
DEBUG = False

##============================================================================
## Commands
##============================================================================

def off():
    """Turn off the debug LEDs."""
    ind.debug_led_off()

##----------------------------------------------------------------------------

def on():
    """Turn on the debug LEDs."""
    ind.debug_led_on()

##----------------------------------------------------------------------------

def toggle():
    """Toggle on the debug LEDs."""
    ind.debug_led_toggle()

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

