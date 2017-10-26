#!/usr/bin/env python2

##############################################################################
#!
#!  Author:     Successful Endeavours Pty Ltd
#!
##############################################################################

'''
This module polls for gps information via the gpsd service.
'''

import argh
import threading
import gps
import time
import sys

#!============================================================================

class GPS_Poller_Thread(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)

        self.gpsd = gps.gps(mode=gps.WATCH_ENABLE) #starting the stream of info
        self.running = True     #! setting the thread running to true

    def run(self):
        while self.running:
            self.gpsd.next()    #! this will continue to loop and grab EACH set of gpsd info to clear the buffer

    def cleanup(self):
        print('INFO: GPS_Poller_Thread: Cleaning up ...')
        self.running = False
        self.join()             #! wait for the thread to finish what it's doing
        print('INFO: GPS_Poller_Thread: Done.')

#!============================================================================


#        self.gps_poller = None      #! will be assinged a thread, that polls gpsd info.
#        self.gpsd = None            #! will be assigned the gpsd data object.
#        #! Setup thread to retrieve GPS information.
#        self.gps_poller = GPS_Poller_Thread()
#        self.gpsd = self.gps_poller.gpsd
#        self.gps_poller.cleanup()
#        self.gps_poller.start()
#            if self.config.append_gps_data_to_measurements_log:
#                gps_latitude           = self.gpsd.fix.latitude
#                gps_longitude          = self.gpsd.fix.longitude
#                print('latitude  : {}'.format(gpsd.fix.latitude))
#                print('longitude : {}'.format(gpsd.fix.longitude))
#                print('time utc  : {}'.format(gpsd.utc))
#                print('fix time  : {}'.format(gpsd.fix.time))


def gps_data_wait(gpsd):
    """Wait for GPS data."""

    ## Wait for gps data.
    loop_again = True
    while loop_again:
        gpsd.next()

        items = [
            gpsd.fix.latitude,
            gpsd.fix.longitude,
            gpsd.utc,
            gpsd.fix.time,
            gpsd.hdop,
            gpsd.vdop,
            gpsd.pdop,
            #gpsd.gdop,
            #gpsd.tdop,
            ]

        loop_again = False
        for item in items:
            if not item:
                loop_again = True
        
    return gpsd

#!============================================================================

def run(count=1, delay=60):
    """
    Get data from GPS daemon.
    Default is to get 1 set of data.
    Default delay is 60 seconds.
    """

    gpsd = gps.gps(mode=gps.WATCH_ENABLE) #starting the stream of info
    #print('gpsd               : {!r}'.format(gpsd))
    #print('gpsd               : {!r}'.format(dir(gpsd)))

    for i in xrange(count):
        gps_data_wait(gpsd)
        print(repr(gpsd))
        sys.stdout.flush()
        if i < count - 1:
            time.sleep(delay)

    #print('gpsd.fix.latitude  : {}'.format(gpsd.fix.latitude))
    #print('gpsd.fix.longitude : {}'.format(gpsd.fix.longitude))
    #print('gpsd.utc           : {}'.format(gpsd.utc))
    #print('gpsd.fix.time      : {}'.format(gpsd.fix.time))

#!============================================================================

def argh_main():

    argh.dispatch_command(run)

#!============================================================================

if __name__ == "__main__":
    argh_main()
