#!/usr/bin/env python2

import argh
import sys
from serial import Serial

##============================================================================

#def serial_loopback(port=sys.argv[1], baudrate=115200, timeout=1):
def serial_loopback(port='', baudrate=115200, timeout=1):

    test_str = 'abc123'

    with Serial(port, baudrate=baudrate, timeout=timeout) as ser:
        ser.write(test_str)
        in_str = ser.read(len(test_str))
        if in_str != test_str:
            raise Exception("Loopback error: sent: {!r}, received: {!r}".format(test_str, in_str))

##============================================================================

def main():
    """Main entry if running this module from command line."""
    argh.dispatch_command(serial_loopback)

##============================================================================

if __name__ == "__main__":
    main()
