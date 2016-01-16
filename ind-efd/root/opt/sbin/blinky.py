"""IND Driver Module."""

import time
import ind

## could make this a runtime option.
DEBUG = False

def main():
    '''Main entry if running this module from command line.'''

    led_seq = [ ind.LED.PPS_OK, ind.LED.Running, ind.LED.Modem_OK, ind.LED.Alert, ind.LED.Weather_Station_OK, ind.LED.Spare ]
    ## append leds in reverse order, omitting end LEDs.
    led_seq += led_seq[1:-1][::-1]

    dev_name = ind.dev_name
    print("DEBUG: opening device name '{}'".format(dev_name))
    #with open(dev_name, 'rw') as dev_hand:
    with ind.get_device_handle() as dev_hand:
        while True:
            for count, led in enumerate(led_seq):
                on = led & ind.LED.All
                off = ~led & ind.LED.All
                ind.leds_modify(on=on, off=off, dev_hand=dev_hand)

                time.sleep(0.1)

if __name__ == "__main__":
    main()

