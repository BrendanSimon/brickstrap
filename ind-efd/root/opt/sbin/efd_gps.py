#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''
This module polls for gps information via the gpsd service.
'''

import argh
import threading
import gps

##============================================================================

class GPS_Poller_Thread(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)

        self.gpsd = gps.gps(mode=gps.WATCH_ENABLE) #starting the stream of info
        self.running = True #setting the thread running to true

    def run(self):
        while self.running:
            self.gpsd.next() #this will continue to loop and grab EACH set of gpsd info to clear the buffer

    def cleanup(self):
        print('INFO: GPS_Poller_Thread: Cleaning up ...')
        self.running = False
        self.join() # wait for the thread to finish what it's doing
        print('INFO: GPS_Poller_Thread: Done.')

##############################################################################

def app_main():
    """Main entry if running this module directly."""

    print(__name__)

##============================================================================

def argh_main():

    argh.dispatch_command(app_main)

##============================================================================

if __name__ == "__main__":
    argh_main()
