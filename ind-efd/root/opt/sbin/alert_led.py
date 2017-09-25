#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''Utility to manipulate the Alert status LED.'''

import ind
import argh

## could make this a runtime option.
DEBUG = False

##============================================================================
## Commands
##============================================================================

def off():
    """Turn off the alert LED."""
    ind.alert_led_off()

##----------------------------------------------------------------------------

def on():
    """Turn on the alert LED."""
    ind.alert_led_on()

##----------------------------------------------------------------------------

def toggle():
    """Toggle on the alert LED."""
    ind.alert_led_toggle()

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

