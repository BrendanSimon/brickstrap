#!/usr/bin/env python2

##############################################################################
#!
#!  Author:     Successful Endeavours Pty Ltd
#!
##############################################################################

'''
This module contains a class to manage measurement logs.
'''

import argh
import sys
import os.path
import Queue as queue       #! Python 3 renames Queue module as queue.
import csv
import copy

from cStringIO import StringIO

from efd_config import PeakDetectMode

#!============================================================================

#!FIXME: including saving the csv file, posting to the web and sending sms alerts.
class Measurements_Log(object):
    '''Manage logging measurement data to log files.'''
    '''Uses csv module and csv.DictWriter object.'''
    '''Rotate log files each day, based on 'datetime_utc' field.'''

    #! FIXME: not sure if putting the measurements_log_field_names in the config object is the right thing.
    def __init__(self, field_names):
        self.field_names = field_names
        self.csv_file = None
        self.path = os.path.join(os.sep, 'mnt', 'data', 'log', 'measurements')
        self.filename = ''
        self.filename_prefix = 'measurements-'
        self.filename_extension = '.csv'
        self.day_saved = 0

        #! initialise csv header string.
        hdr_sio = StringIO()
        writer = csv.DictWriter(hdr_sio, fieldnames=self.field_names, extrasaction='ignore')
        writer.writeheader()
        self.csv_header = hdr_sio.getvalue()
        hdr_sio.close()

    def init(self):
        '''Runtime intialisation method.'''

        #! Create directory to store measurements log if it doesn't exists.
        if not os.path.exists(self.path):
            os.makedirs(self.path)

    def to_csv(self, measurements, peak_detect_mode):
        '''
        Convert measurements to a csv record.

        NOTE: in some modes, some csv fields are used for a different purpose
        than originally intended !!  Some measurement fields are replaced !!
        '''

        #!
        #! Take a copy of the measurements so we can modify it.
        #!
        m = copy.deepcopy(measurements)

        #!
        #! Some modes reuse the csv fields for different purposes,
        #! so copy the necessary measurements to the appropriate csv fields.
        #! This was chosen by IND to minimise changing the web backend API !!
        #!

        if peak_detect_mode == PeakDetectMode.NORMAL:
            pass

# Uncomment to enable Absolute peak detection mode (WIP, needs testing !!)
# Note: has not been formally asked for or quoted !!
#
#         elif peak_detect_mode == PeakDetectMode.ABSOLUTE:
#             #! Work out if min or max has largest magnitude.
#             #! (important for correct time index/offset !!)
#             #! max_volt_* contains signed adjusted squared voltage.
#             #! min_volt_* contains the total count of peaks.
#
#             #! red
#             if abs(m['min_volt_red']) > abs(m['max_volt_red']):
#                 m['max_volt_red']           = abs(m['min_volt_red'])
#                 m['max_time_offset_red']    = m['min_time_offset_red']
#                 m['min_volt_red']           = m['min_volt_count_red']
#             else:
#                 m['max_volt_red']           = abs(m['max_volt_red'])
#                 m['max_time_offset_red']    = m['max_time_offset_red']
#                 m['min_volt_red']           = m['max_volt_count_red']
#             #! white
#             if abs(m['min_volt_wht']) > abs(m['max_volt_wht']):
#                 m['max_volt_wht']           = abs(m['min_volt_wht'])
#                 m['max_time_offset_wht']    = m['min_time_offset_wht']
#                 m['min_volt_wht']           = m['min_volt_count_wht']
#             else:
#                 m['max_volt_wht']           = abs(m['max_volt_wht'])
#                 m['max_time_offset_wht']    = m['max_time_offset_wht']
#                 m['min_volt_wht']           = m['max_volt_count_wht']
#             #! blue
#             if abs(m['min_volt_blu']) > abs(m['max_volt_blu']):
#                 m['max_volt_blu']           = abs(m['min_volt_blu'])
#                 m['max_time_offset_blu']    = m['min_time_offset_blu']
#                 m['min_volt_blu']           = m['min_volt_count_blu']
#             else:
#                 m['max_volt_blu']           = abs(m['max_volt_blu'])
#                 m['max_time_offset_blu']    = m['max_time_offset_blu']
#                 m['min_volt_blu']           = m['max_volt_count_blu']

        elif peak_detect_mode == PeakDetectMode.SQUARED:
            #! max_volt_* contains signed adjusted squared voltage.
            #! min_volt_* contains the total count of peaks.

            #! red
            m['max_volt_red']           = m['max_volt_squared_red']
            m['max_time_offset_red']    = m['max_time_offset_squared_red']
            m['min_volt_red']           = m['max_volt_squared_count_red']
            #! white
            m['max_volt_wht']           = m['max_volt_squared_wht']
            m['max_time_offset_wht']    = m['max_time_offset_squared_wht']
            m['min_volt_wht']           = m['max_volt_squared_count_wht']
            #! blue
            m['max_volt_blu']           = m['max_volt_squared_blu']
            m['max_time_offset_blu']    = m['max_time_offset_squared_blu']
            m['min_volt_blu']           = m['max_volt_squared_count_blu']

        else:
            #! shouldn't get here !!
            #! FIXME: print an error or raise an exception.
            pass

        #!
        #! Convert dates to strings that are compatible with Microsoft Excel.
        #!
        m['datetime_utc']   = m['datetime_utc'].isoformat(sep=' ')
        m['datetime_local'] = m['datetime_local'].isoformat(sep=' ')

        #! format csv output to a string (not a file) so the same output
        #! can be efficiently saved to a file and post to web server.
        row_sio= StringIO()
        writer = csv.DictWriter(row_sio, fieldnames=self.field_names, extrasaction='ignore')
        writer.writerow(m)
        csv_data = row_sio.getvalue()
        row_sio.close()
        #print("DEBUG: csv_data =", csv_data)
        return csv_data

    def write(self, csv_data, datetime):
        '''Write measurements to file in CSV format.'''

        dt = datetime

        if not self.filename or (dt.day != self.day_saved):
            dt_str = dt.floor('day').format('YYYYMMDDTHHmmssZ')
            #dt_str = dt.format('YYYYMMDDTZ')
            #dt_str = dt.format('YYYYMMDDZ')
            filename = '{prefix}{dtstr}{extension}'.format(prefix=self.filename_prefix, dtstr=dt_str, extension=self.filename_extension)
            self.filename = filename

        self.day_saved = dt.day

        #!
        #! Write measurements to log file; and header if it's a new file.
        #!
        path_filename = os.path.join(self.path, self.filename)
        new_file = not os.path.exists(path_filename)
        with open(path_filename, 'a') as csvfile:
            if new_file:
                #! write header to new file.
                csvfile.write(self.csv_header)
            #! write measurements to file.
            csvfile.write(csv_data)

#!============================================================================

def app_main():
    """Main entry if running this module directly."""

    print(__name__)
    #m_log = Measurements_Log()
    #m_log.init()

#!============================================================================

def argh_main():

    argh.dispatch_command(app_main)

#!============================================================================

if __name__ == "__main__":
    argh_main()
