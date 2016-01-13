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

import ind

## could make this a runtime option.
DEBUG = False

if __name__ == "__main__":
    try:
        delay = float(sys.argv[1])
    except:
        raise Exception("must specify delay as first parameter")

    with ind.get_device_handle() as dev_hand:

        while True:
            ##
            ## Pulse power key to turn it on.
            ##

            print("Turning modem 'off'")
            ind.modem_power_off(dev_hand=dev_hand)

            print("Sleeping {} seconds ...".format(delay))
            time.sleep(delay)

            print("Turning modem 'on'")
            ind.modem_power_on(dev_hand=dev_hand)

            break

