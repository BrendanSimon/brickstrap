#!/usr/bin/env python2

from time import sleep

import ind

##============================================================================

def led_off(dev_hand=None):
    #ind.leds_modify(off=0xfffffff, dev_hand=dev_hand)
    ind.battery_led_off(dev_hand=dev_hand)
    ind.power_led_off(dev_hand=dev_hand)
    ind.alert_led_off(dev_hand=dev_hand)

##============================================================================

def led_on(dev_hand=None):
    #ind.leds_modify(on=0xfffffff, dev_hand=dev_hand)
    ind.battery_led_on(dev_hand=dev_hand)
    ind.power_led_on(dev_hand=dev_hand)
    ind.alert_led_on(dev_hand=dev_hand)

##============================================================================

def led_cycle(count, delay, dev_hand=None):
    for i in range(count):
        led_on(dev_hand=dev_hand)
        sleep(delay)
        led_off(dev_hand=dev_hand)
        sleep(delay)

##============================================================================

def main():
    with open("/dev/IND") as dev_hand:
        led_cycle(count=8, delay=0.1, dev_hand=dev_hand)
        ind.alert_led_on(dev_hand=dev_hand)
        ind.power_os_running_off(dev_hand=dev_hand)
        print("Deasserted nOS_RUNNING pin")

##============================================================================

if __name__ == "__main__":
    main()

