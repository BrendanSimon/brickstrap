#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''Utility to manipulate the nOS_RUNNING control output.'''

import ind
import argh

## could make this a runtime option.
DEBUG = False

##============================================================================
## Commands
##============================================================================

def off():
    """Turn off the `not_os_running` control signal."""
    ind.power_os_running_off()

##----------------------------------------------------------------------------

def on():
    """Turn on the `not_os_running` control signal."""
    ind.power_os_running_on()

##----------------------------------------------------------------------------

def toggle():
    """Toggle on the `not_os_running` control signal."""
    ind.power_os_running_toggle()

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

