#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''IND Driver Module.'''

import sys
import time
import ind

## could make this a runtime option.
DEBUG = False

def main():
    '''Main entry if running this module from command line.'''

    app = sys.argv[0]

    try:
        status = sys.argv[1]
    except:
        status = None
    
    if not (status == '0' or status == '1'):
        print("{app}: Invalid parameter: {param}".format(app=app, param=status))
        return

    led = ind.LED.Weather_Station_OK

    on = 0
    off = 0

    if status == '0':
        ## Led off
        off = led

    if status == '1':
        ## Led on
        on = led

    dev_name = ind.dev_name
    #with open(dev_name, 'rw') as dev_hand:
    with ind.get_device_handle() as dev_hand:
        ind.leds_modify(on=on, off=off, dev_hand=dev_hand)

if __name__ == "__main__":
    main()

