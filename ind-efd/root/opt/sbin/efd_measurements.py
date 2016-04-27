#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''
This module will generate sinusoidal data that simulates real world
data acquired via a high speed A2D converter.
Default parameters are 250 MS/s 16-bit data.
'''

import argh
import sys
import os.path
import Queue as queue       ## Python 3 renames Queue module as queue.
import csv

from cStringIO import StringIO

##============================================================================

##FIXME: including saving the csv file, posting to the web and sending sms alerts.
class Measurements_Log(object):
    '''Manage logging measurement data to log files.'''
    '''Uses csv module and csv.DictWriter object.'''
    '''Rotate log files each day, based on 'datetime_utc' field.'''

    ## FIXME: not sure if putting the measurements_log_field_names in the config object is the right thing.

    #def __init__(self, cloud_queue, url, field_names=Config.measurements_log_field_names):
    def __init__(self, cloud_queue, url, field_names):
        self.cloud_queue = cloud_queue
        self.url = url
        self.field_names = field_names
        self.csv_file = None
        self.path = os.path.join(os.sep, 'mnt', 'data', 'log', 'measurements')
        self.filename = ''
        self.filename_prefix = 'measurements-'
        self.filename_extension = '.csv'
        self.day_saved = 0

        ## initialise csv header string.
        hdr_sio = StringIO()
        writer = csv.DictWriter(hdr_sio, fieldnames=self.field_names, extrasaction='ignore')
        writer.writeheader()
        self.csv_header = hdr_sio.getvalue()
        hdr_sio.close()

    def init(self):
        '''Runtime intialisation method.'''
        ## Create directory to store measurements log if it doesn't exists.
        if not os.path.exists(self.path):
            os.makedirs(self.path)

    def write(self, measurements, datetime):
        dt = datetime
        if not self.filename or (dt.day != self.day_saved):
            dt_str = dt.floor('day').format('YYYYMMDDTHHmmssZ')
            #dt_str = dt.format('YYYYMMDDTZ')
            #dt_str = dt.format('YYYYMMDDZ')
            filename = '{prefix}{dtstr}{extension}'.format(prefix=self.filename_prefix, dtstr=dt_str, extension=self.filename_extension)
            self.filename = filename


        self.day_saved = dt.day

        ## format csv output to a string (not a file) so the same output
        ## can be efficiently saved to a file and post to web server.
        row_sio= StringIO()
        writer = csv.DictWriter(row_sio, fieldnames=self.field_names, extrasaction='ignore')
        writer.writerow(measurements)
        self.csv_data = row_sio.getvalue()
        row_sio.close()

        ##
        ## Write measurements to log file; and header if it's a new file.
        ##
        path_filename = os.path.join(self.path, self.filename)
        new_file = not os.path.exists(path_filename)
        with open(path_filename, 'a') as csvfile:
            if new_file:
                ## write header to new file.
                csvfile.write(self.csv_header)
            ## write measurements to file.
            csvfile.write(self.csv_data)

        ##
        ## use queue to send the csv row to the cloud thread.
        ## NOTE: could send the measurement dict to the cloud thread and let it:
        ## generate the csv for saving to file and posting to web, and send sms.
        ##
        try:
            self.cloud_queue.put(item=self.csv_data, block=False)
        except queue.Full:
            print("EXCEPTION: could not queue measurement data to cloud thread. qsize={}".format(self.cloud_queue.qsize()))
            sys.stdout.flush()

##############################################################################

def app_main():
    """Main entry if running this module directly."""

    print(__name__)
    #m_log = Measurements_Log()
    #m_log.init()

##============================================================================

def argh_main():

    argh.dispatch_command(app_main)

##============================================================================

if __name__ == "__main__":
    argh_main()
