#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''Utility to manipulate the FPGA Control Register.'''

import ind
import argh

## could make this a runtime option.
DEBUG = False

##============================================================================
## Commands
##============================================================================

def clear(mask=0):
    """Clear (set to logic 0) the Control Bits specified by MASK."""
    ind.ctrl_modify(off=mask)

##----------------------------------------------------------------------------

def set(mask=0):
    """Set (set to logic 1) the Control Bits specified by MASK."""
    ind.ctrl_modify(on=mask)

##----------------------------------------------------------------------------

def toggle(mask=0):
    """Toggle on the Control Bits specified by MASK."""
    ind.ctrl_modify(toggle=mask)

##============================================================================

def main():
    '''Main entry if running this module from command line.'''

    ## assembling commands.
    parser = argh.ArghParser()
    commands = [ clear, set, toggle ]
    parser.add_commands(commands)

    ## dispatching commands.
    parser.dispatch()

##============================================================================

if __name__ == "__main__":
    main()

##============================================================================

