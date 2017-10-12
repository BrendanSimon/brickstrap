#!/usr/bin/env python2

import argh
from efd_config import Config
import time
import arrow
import sys

from efd_modem_status import run as efd_modem_status_run
from efd_gps import run as efd_gps_status_run

def show_rf_status():
    print("------------------------------------------------------------")

    utc_dt = arrow.utcnow().floor('second')
    loc_dt = utc_dt.to(config.timezone)
    dt = loc_dt.format('YYYY-MM-DD HH:mm:ss Z')
    #dt = loc_dt
    print("Date: {}".format(dt))
    print

    print("=== Modem Status === ")
    efd_modem_status_run()
    print

    print("=== GPS Status === ")
    efd_gps_status_run()
    print

    sys.stdout.flush()

#!============================================================================

#! Make config object global.
config = Config()

#!============================================================================

def main(count=0, delay=60):
    """
    count = number of repetiions.  default 0 => loop forever
    delay = number of seconds to wait for repeating.
    """
    i = 0
    while True:
        show_rf_status()
        if count == 0 or i < (count - 1):
            i += 1
            time.sleep(delay)

#!============================================================================

if __name__ == "__main__":
    argh.dispatch_command(main)

