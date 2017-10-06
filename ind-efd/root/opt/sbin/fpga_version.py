#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''Utility to retrieve value of the FPGA Status Register.'''

import ind
import argh

##============================================================================
## Commands
##============================================================================

def fpga_version_get():
    """Get value of the status register"""
    fpga_version = ind.fpga_version_get()
    print("fpga_version._unused_0_ = {:#08x}".format(fpga_version._unused_0_))
    print("fpga_version.major      = {:#08x}".format(fpga_version.major))
    print("fpga_version.minor      = {:#08x}".format(fpga_version.minor))

##============================================================================

def main():
    '''Main entry if running this module from command line.'''
    argh.dispatch_command(fpga_version_get)

##============================================================================

if __name__ == "__main__":
    main()

##============================================================================

