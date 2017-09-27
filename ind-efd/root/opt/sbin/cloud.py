#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''\
This module posts data to a service in the "cloud".
'''


import sys
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

            sys.stdout.flush()

        self.cloud.cleanup()

    def cleanup(self):
        print('INFO: Cloud_Thread: Cleaning up ...')
        self.running = False
        self.join()
        print('INFO: Cloud_Thread: Done.')

##============================================================================

class Cloud(object):

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
        self.last_post_time = time.time()

        ## initialise to earliest possible datetime value.
        self.last_measurements_log_datetime_utc = arrow.Arrow(year=1, month=1, day=1)

        ##
        ## initialise csv header string.
        ##
        ## FIXME: this is duplicated from efd_app.py
        hdr_sio = StringIO()
        hdr_sio.write("data=")
        writer = csv.DictWriter(hdr_sio, fieldnames=self.config.measurements_log_field_names, extrasaction='ignore')
        writer.writeheader()
        self.measurements_log_csv_header = hdr_sio.getvalue()
        hdr_sio.close()

        ## list of csv data records to post.
        self.csv_data = []

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
            r = requests.get(self.config.web_server_ping, timeout=5)
        except Exception as exc:
            print(repr(exc))
            print(traceback.format_exc())

    ##------------------------------------------------------------------------

    def post_measurements_data(self, data):
        '''Post measurements data to the cloud service.'''

        try:
            r = requests.post(self.config.web_server_measurements_log, headers=self.web_server_headers, data=data, timeout=30)
        except Exception as exc:
            print(repr(exc))
            #print(traceback.format_exc())
            raise
        else:
            if 0:
                print("DEBUG: *******************************************")
                print("DEBUG: requests.post:")
                print("DEBUG: requests.headers: data = {}".format(self.web_server_headers))
                print("DEBUG: requests.post: data = {}".format(data))
                print("DEBUG: -------------------------------------------")
                print("DEBUG: post measurements data: r = {!r}".format(r))
                print("DEBUG: post measurements r.status_code = {}".format(r.status_code))
                print("DEBUG: post measurements r.headers = {}".format(r.headers))
                print("DEBUG: post measurements r.text = {}".format(r.text))
                print("DEBUG: *******************************************")

    ##------------------------------------------------------------------------

    def spare_led_off(self):
        ind.spare_led_off(dev_hand=self.ind_dev_hand)

    def spare_led_on(self):
        ind.spare_led_on(dev_hand=self.ind_dev_hand)

    def spare_led_toggle(self):
        ind.spare_led_toggle(dev_hand=self.ind_dev_hand)

    ##------------------------------------------------------------------------

    def wait_and_process(self):
        '''wait for data and process it.'''

        ##
        ## Batch up max_records_per_post into a single post to reduce data usage costs.
        ##
        ## A single csv record per post is approx 602 bytes (250 csv header + CRLF + 350 csv record).
        ## The total bytes transferred is approximately 1456 (IP bytes) or 1594 (Ethernet bytes)
        ## per single csv record post (over 9 packets) => almost 4GB per month !!
        ##
        ## Batching 60 csv records into a single http post will improve efficiency and should
        ## bring the data usage to approximately 1GB per month.
        ## Estimate: 600 (Eth/IP bytes) + 252 (csv_header) + 302*60 (csv record) + 34*60 (reply)
        ##        => 895MB per month (approx 1GB per month)
        ##
        ## Telstra billing shows data usage has reduced to approximately 1.4-1.6MB/hour (~1.2GB/31days),
        ## down from 8MB/hour (~6GB/31days).
        ##

        new_data = False

        ##
        ## Get next item in the queue (wait if necessary) if number of records to post is not at limit.
        ##
        while len(self.csv_data) < self.config.max_records_per_post:

            self.spare_led_off()

            ##
            ## Block on receive queue for first time in the receive queue.
            ##
            try:
                item = self.cloud_queue.get(block=True, timeout=2)
            except queue.Empty as exc:
                print(repr(exc))
                break

            self.spare_led_on()

            #print("DEBUG: appending next csv_data.")
            self.csv_data.append(item)
            #print("DEBUG: appended next csv_data (len={})".format(len(self.csv_data)))

            new_data = True

            try:
                #print("DEBUG: inform queue that next item has been processed.")
                self.cloud_queue.task_done()
            except Exception as exc:
                print("EXCEPTION: issue task_done() to cloud queue after getting next item !!")
                print(repr(exc))
                sys.stdout.flush()

        ##
        ## Check if there is enough data to post.
        ##
        if len(self.csv_data) < self.config.max_records_per_post:
            ## Not enough data to post.
            print("DEBUG: Not enough data records to post ({}).".format(len(self.csv_data)))
            return

        ##
        ## Always post data if new data was added, otherwise check if time to repost last data.
        ##
        now = time.time()
        if not new_data:
            time_diff = now - self.last_post_time
            #print("DEBUG: now={}, last_post_time={}, time_diff={}".format(now, self.last_post_time, time_diff))
            if time_diff < self.config.measurments_post_retry_time_interval:
                ## Not time to retry last post.
                print("DEBUG: Not time to retry last post.")
                time.sleep(1)
                return

        self.last_post_time = now

        ##
        ## concatenate csv row header and data into a single string.
        ##
        post_data = self.measurements_log_csv_header + ''.join(self.csv_data)
        print("DEBUG: Posting data: len(csv_data)={}".format(len(self.csv_data)))
        #print("DEBUG: post_data={}".format(post_data))

        ##
        ## post the data to the web server.
        ##
        try:
            self.post_measurements_data(data=post_data)
        except Exception as exc:
            print(repr(exc))
            print(traceback.format_exc())
        else:
            #print("INFO: Posted Measurement Data OK.  rows={}".format(len(self.csv_data)))
            ## clear list to allow more csv data to accumulate from the queue.
            self.csv_data = []

        return

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
            'alert',
            'adc_clock_count_per_pps',
            ]

        max_cloud_queue_size = 10

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

    cloud_queue = queue.Queue(maxsize=config.max_cloud_queue_size)

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
            if data_index >= len(data_count):
                data_index = 0
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
