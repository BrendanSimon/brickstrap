#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''\
This module posts data to a service in the "cloud".
'''


#import sys
#from collections import namedtuple
import traceback
import threading
import time
import arrow
import mmap
import csv
import requests
import Queue as queue

from cStringIO import StringIO

import ind

##============================================================================

class Cloud_Thread(threading.Thread):

    def __init__(self, config, app_state, cloud_queue):
        threading.Thread.__init__(self)

        self.cloud = Cloud(config=config, app_state=app_state, cloud_queue=cloud_queue)
        self.running = True

    def run(self):
        while self.running:
            ## continue to loop, wait for data, and process.
            try:
                self.cloud.wait_and_process()
            except Exception as exc:
                print(repr(exc))
                print(traceback.format_exc())

        self.cloud.cleanup()

    def cleanup(self):
        print('INFO: Cloud_Thread: Cleaning up ...')
        self.running = False
        self.join()
        print('INFO: Cloud_Thread: Done.')

##============================================================================

class Cloud(object):

    #select_timeout = 1

    ##------------------------------------------------------------------------

    def __init__(self, config, app_state, cloud_queue):

        self.config = config
        self.app_state = app_state
        self.cloud_queue = cloud_queue
        self.ind_dev_hand = None

        self.init()

    ##------------------------------------------------------------------------

    def init(self):

        self.cleanup()

        self.ind_dev_hand = ind.get_device_handle()

        self.measurement_ack = ''
        self.last_measurements_log_path = ''
        self.last_measurements_log_data = ''
        self.measurements_log_file = None
        self.measurements_log_mmap = None

        ## initialise to earliest possible datetime value.
        self.last_measurements_log_datetime_utc = arrow.Arrow(year=1, month=1, day=1)

        ## initialise csv header string.
        ## FIXME: this is duplicated from efd_app.py
        hdr_sio = StringIO()
        hdr_sio.write("data=")
        writer = csv.DictWriter(hdr_sio, fieldnames=self.config.measurements_log_field_names, extrasaction='ignore')
        writer.writeheader()
        self.measurements_log_csv_header = hdr_sio.getvalue()
        hdr_sio.close()

        self.web_server_headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    ##------------------------------------------------------------------------

    def cleanup(self):

        if self.ind_dev_hand:
            self.ind_dev_hand.close()
            self.ind_dev_hand = None

    ##------------------------------------------------------------------------

    def post_ping(self):
        '''Post measurements data to the cloud service.'''

        try:
            r = requests.get(self.config.web_server_ping)
        except Exception as exc:
            print(repr(exc))
            print(traceback.format_exc())

    ##------------------------------------------------------------------------

    def post_measurements_data(self, data):
        '''Post measurements data to the cloud service.'''

        try:
            r = requests.post(self.config.web_server_measurements_log, headers=self.web_server_headers, data=data)
        except Exception as exc:
            print(repr(exc))
            print(traceback.format_exc())
        else:
            if 0:
                print("DEBUG: *******************************************")
                print("DEBUG: requests.post:")
                print("DEBUG: requests.headers: data = {}".format(self.web_server_headers))
                print("DEBUG: requests.post: data = {}".format(data))
                print("DEBUG: -------------------------------------------")
                print("DEBUG: post measurements data: r = {!r}".format(r))
                print("DEBUG: post measurements r.status_code = {}".format(r.status_code
))
                print("DEBUG: post measurements r.headers = {}".format(r.headers))
                print("DEBUG: post measurements r.text = {}".format(r.text))
                print("DEBUG: *******************************************")

    ##------------------------------------------------------------------------

    def running_led_off(self):
        ind.running_led_off(dev_hand=self.ind_dev_hand)

    def running_led_on(self):
        ind.running_led_on(dev_hand=self.ind_dev_hand)

    def running_led_toggle(self):
        ind.running_led_toggle(dev_hand=self.ind_dev_hand)

    ##------------------------------------------------------------------------

    def wait_and_process(self):
        '''wait for data and process it.'''

        #csv_data = []
        csv_data = [self.measurements_log_csv_header]

        self.running_led_off()

        ## Block on receive queue for first time in the receive queue.
        try:
            item = self.cloud_queue.get(block=True, timeout=2)
        except queue.Empty as exc:
            print(repr(exc))
            return
        else:
            #print("DEBUG: appending first csv_data.")
            csv_data.append(item)

        self.running_led_on()

        ## Remove any remaining items in the queue without blocking
        ## max limit of 10 items.
        for i in range(10):
            try:
                item = self.cloud_queue.get(block=False)
            except queue.Empty:
                break
            else:
                #print("DEBUG: appending extra csv_data.")
                csv_data.append(item)

        ## concatenate csv row data to form a single string.
        post_data = ''.join(csv_data)
        #print("DEBUG: post_data={}".format(post_data))

        try:
            self.post_measurements_data(data=post_data)
        except Exception as exc:
            print(repr(exc))
            print(traceback.format_exc())

        for i in range(len(csv_data)-1):
            #print("DEBUG: cloud_queue.task_done()")
            self.cloud_queue.task_done()      ## inform queue that item has been processed.

        return

        ##
        ## FIXME: app_state was being used (abused) for inter-thread comms.
        ## FIXME: should delete these old app_state entries as they are no longer used.
        ## FIXME: this should be done during app initialisation.
        ##
        #m_log_path = self.app_state['measurements_log_path']
        #m_log_data = self.app_state['measurements_log_data']
        #m_log_datetime = self.app_state['measurements_log_datetime']
        #m_log_datetime = self.app_state['capture_datetime_utc']
        #capture_datetime_utc = self.app_state['capture_datetime_utc']
        #capture_datetime_local = self.app_state['capture_datetime_local']

##============================================================================

def main():
    """Main entry if running this module directly."""

    ##--------------------------------

    class Config:
        web_server_ping = 'http://portal.efdweb.com/api/Ping/0/'
        web_server_measurements_log = 'http://portal.efdweb.com/api/AddEFDLog/0/'
        measurements_log_field_names = [
            'datetime_utc', 'datetime_local',
            'max_volt_red', 'min_volt_red', 'max_time_offset_red', #'min_time_offset_red',
            't2_red', 'w2_red',
            'max_volt_wht', 'min_volt_wht', 'max_time_offset_wht', #'min_time_offset_wht',
            't2_wht', 'w2_wht',
            'max_volt_blu', 'min_volt_blu', 'max_time_offset_blu', #'min_time_offset_blu',
            't2_blu', 'w2_blu',
            'temperature', 'humidity', 'rain_intensity',
            ]

    config = Config()

    ##--------------------------------

    #measurements = {}
    #measurements['datetime_utc']           = self.capture_datetime_utc.isoformat(sep=' ')
    #measurements['datetime_local']         = self.capture_datetime_local.isoformat(sep=' ')
    #measurements['max_volt_red']           = self.peak_max_red.voltage
    #measurements['min_volt_red']           = self.peak_min_red.voltage
    #measurements['max_time_offset_red']    = self.peak_max_red.time_offset
    #measurements['min_time_offset_red']    = self.peak_min_red.time_offset
    #measurements['t2_red']                 = self.tf_map_red.T2
    #measurements['w2_red']                 = self.tf_map_red.F2
    #measurements['max_volt_wht']           = self.peak_max_wht.voltage
    #measurements['min_volt_wht']           = self.peak_min_wht.voltage
    #measurements['max_time_offset_wht']    = self.peak_max_wht.time_offset
    #measurements['min_time_offset_wht']    = self.peak_min_wht.time_offset
    #measurements['t2_wht']                 = self.tf_map_wht.T2
    #measurements['w2_wht']                 = self.tf_map_wht.F2
    #measurements['max_volt_blu']           = self.peak_max_blu.voltage
    #measurements['min_volt_blu']           = self.peak_min_blu.voltage
    #measurements['max_time_offset_blu']    = self.peak_max_blu.time_offset
    #measurements['min_time_offset_blu']    = self.peak_min_blu.time_offset
    #measurements['t2_blu']                 = self.tf_map_blu.T2
    #measurements['w2_blu']                 = self.tf_map_blu.F2
    #measurements['temperature']            = self.ws_info.temperature
    #measurements['humidity']               = self.ws_info.humidity
    #measurements['rain_intensity']         = self.ws_info.rain_intensity

    csv_str = '2016-01-12 15:04:12+00:00,2016-01-13 02:04:12+11:00,-0.00034332275390625,-0.0017547607421875,0.001766072,5.7265854614087719e-09,29205329.549096104,0.0016021728515625,-0.003662109375,0.00355964,5.7265854614087719e-09,31948299.751001682,-0.00034332275390625,-0.00171661376953125,0.001133052,5.7266116565935494e-09,29143762.475214832,20.2C,56.4P,0\n'

    cloud_queue = queue.Queue()

    cloud_thread = Cloud_Thread(config=config, app_state=None, cloud_queue=cloud_queue)
    cloud = cloud_thread.cloud

    #cloud_thread.init()
    cloud_thread.start()
    delay = 3
    data_count = [ 1, 5, 9, 100 ]
    data_index = 0
    try:
        while True:
            print('Sleeping for {} seconds'.format(delay))
            time.sleep(delay)
            count = data_count[data_index]
            data_index += 1
            if data_index >= len(data_count): data_index = 0
            print("Queueing {} csv rows".format(count))
            for i in range(count):
                try:
                    #cloud_queue.put(item=csv_str, block=False)
                    cloud_queue.put(item=csv_str, block=True)
                except queue.Full as exc:
                    print("EXCEPTION: queue is full.  i={}".format(i))
                    print(traceback.format_exc())
            print('----------------------------------------')

    except (KeyboardInterrupt, SystemExit) as exc:
        ## ctrl+c key press or sys.exit() called.
        print("EXCEPTION: KeyboardInterrupt or SystemExit")
        print(repr(exc))
    finally:
        print("Nearly done ...")
        print("joining queue ...")
        cloud_queue.join()
        print("queue joined.")
        cloud_thread.cleanup()

    print("Done.  Exiting.")

##============================================================================

if __name__ == "__main__":
    main()

