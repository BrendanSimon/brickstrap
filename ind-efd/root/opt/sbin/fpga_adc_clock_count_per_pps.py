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

def fpga_adc_clock_count_per_pps_get():
    """Get value of the status register"""
    count = ind.adc_clock_count_per_pps_get()
    print("fpga_adc_clock_count_per_pps = {:10} ({:#08x})".format(count, count))

##============================================================================

def main():
    '''Main entry if running this module from command line.'''
    argh.dispatch_command(fpga_adc_clock_count_per_pps_get)

##============================================================================

if __name__ == "__main__":
    main()

##============================================================================

