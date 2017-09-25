#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''Utility to retrieve value of the FPGA Status Register.'''

import ind
import argh

## could make this a runtime option.
DEBUG = False

##============================================================================
## Commands
##============================================================================

def status_get():
    """Get value of the status register"""
    value = ind.status_get()
    print("status = {:#08x}".format(value))

##============================================================================

def main():
    '''Main entry if running this module from command line.'''
    argh.dispatch_command(status_get)

##============================================================================

if __name__ == "__main__":
    main()

##============================================================================

