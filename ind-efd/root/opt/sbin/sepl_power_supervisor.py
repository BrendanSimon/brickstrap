#!/usr/bin/env python2

from time import sleep
import subprocess

import ind

##============================================================================

shutdown_cmd = "/sbin/poweroff"

delay = 1

##============================================================================

def led_off(dev_hand=None):
    ind.battery_led_off(dev_hand=dev_hand)
    ind.power_led_off(dev_hand=dev_hand)

##============================================================================

def led_on(dev_hand=None):
    ind.battery_led_on(dev_hand=dev_hand)
    ind.power_led_on(dev_hand=dev_hand)

##============================================================================

def shutdown():
    print("Calling command: {}".format(shutdown_cmd))
    subprocess.call(shutdown_cmd)
    
##============================================================================

def main():

    with open("/dev/IND") as dev_hand:
        ## Indicate we are up and running.
        ind.power_os_running_on(dev_hand=dev_hand)
        led_on(dev_hand=dev_hand)

        while True:
            shutdown_req = ind.power_shutdown_requested(dev_hand=dev_hand)
            if shutdown_req:
                shutdown()

            sleep(delay)

##============================================================================

if __name__ == "__main__":
    main()

