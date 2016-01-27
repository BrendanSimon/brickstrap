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
import threading
import time
import arrow
import mmap
import csv
import requests

from cStringIO import StringIO

##============================================================================

class Cloud_Thread(threading.Thread):
  
    def __init__(self, config, app_state):
        threading.Thread.__init__(self)
  
        self.cloud = Cloud(config=config, app_state=app_state)
        self.running = True

    def run(self):
        while self.running:
            ## continue to loop, wait for data, and process.
            self.cloud.wait_and_process()

    def cleanup(self):
        print('INFO: Cloud_Thread: Cleaning up ...')
        self.running = False
        self.join()
        print('INFO: Cloud_Thread: Done.')

##============================================================================

class Cloud(object):

    #select_timeout = 1

    ##------------------------------------------------------------------------

    def __init__(self, config, app_state):

        self.config = config
        self.app_state = app_state

        self.init()

    ##------------------------------------------------------------------------

    def init(self):
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

    def post_ping(self):
        '''Post measurements data to the cloud service.'''

        print("DEBUG: requests.post:")
        r = requests.get(self.config.web_server_ping)
        print("DEBUG: post measurements data: r = {!r}".format(r))

    ##------------------------------------------------------------------------

    def post_measurements_data(self, csv_data):
        '''Post measurements data to the cloud service.'''

        data = self.measurements_log_csv_header + csv_data

        r = requests.post(self.config.web_server_measurements_log, headers=self.web_server_headers, data=data)
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

    def wait_and_process(self):
        '''wait for data and process it.'''

#        r = select.select([self.dev_hand], [], [], self.select_timeout)
#        #print("DEBUG: r = {!r}".format(r))
#        if not r[0]:
#            print("DEBUG: TIMEOUT: wait_and_process")
#            return
        m_log_path = self.app_state.get('measurements_log_path', '')
        m_log_data = self.app_state.get('measurements_log_data', '')

        #m_log_datetime = self.app_state['measurements_log_datetime']
        m_log_datetime = self.app_state.get('capture_datetime_utc')
        #capture_datetime_utc = self.app_state['capture_datetime_utc']
        #capture_datetime_local = self.app_state['capture_datetime_local']



        ## FIXME: more sophistated code below (buggy, not ready).
        ## FIXME: just post latest measurements for now and return.
        ## 
        if m_log_data == self.last_measurements_log_data:
            delay = 0.1
            #delay = 3
            #print("DEBUG: Cloud: sleeping for {} second/s.".format(delay))
            #time.sleep(delay)
            return

        #if m_log_data != self.last_measurements_log_data:
        else:
            self.post_measurements_data(csv_data=m_log_data)
            self.last_measurements_log_data = m_log_data

        return


##FIXME: get the following going later !!

        if m_log_data != self.last_measurements_log_data:
            if 1:
                print("DEBUG: Cloud: measurements_log_data changed:")
                print("              last_data = {}".format(self.last_measurements_log_data))
                print("              this_data = {}".format(m_log_data))
            self.last_measurements_log_data = m_log_data

            print("DEBUG: Cloud: Got data, processing ...")

            if m_log_path != self.last_measurements_log_path:
                ## Rollover of file, or no previous file.
                if 1:
                    print("DEBUG: Cloud: measurements_log_path changed:")
                    print("              last_path = {}".format(self.last_measurements_log_path))
                    print("              this_path = {}".format(m_log_path))

                    ## Close memory mapped file.
                    if self.measurements_log_mmap:
                        self.measurements_log_mmap.close()

                    ## Close file.
                    if self.measurements_log_file:
                        self.measurements_log_file.close()
                
                self.last_measurements_log_path = m_log_path

            if not self.measurements_log_file:
                mlf = self.measurements_log_file = open(m_log_path, 'r')
                #with open(m_log_path, 'r') as mlf:
                try:
                    print("DEBUG: Cloud: mmap file: {}".format(m_log_path))
                    mem = mmap.mmap(mlf.fileno(), length=0, access=mmap.ACCESS_READ, offset=0)
                    self.measurements_log_mmap = mem
                except:
                    print("EXCEPTION: getting ADC Memory Map.")
                    raise

            if self.last_measurements_log_data:
                print("DEBUG: Cloud: rfind: {}".format(self.last_measurements_log_data))
                pos = mem.rfind(self.last_measurements_log_data)
                print("DEBUG: Cloud: rfind: pos = {}".format(pos))
                if pos >= 0:
                    ## seek to pos, and post.
                    pos += len(self.last_measurements_log_data)
                    print("DEBUG: Cloud: increment pos = {}".format(pos))
                    data = mem[pos:]
                    print("DEBUG: Cloud: posting data ...")
                    print("{}".format(data))
                    self.post_measurements_data(csv_data=data)

            ## log data for 
            if self.last_measurements_log_datetime_utc.year > 2015:
                pass
            #csv_data = ''
            #for s in self.dev_hand.readlines():
            #self.post_measurements_data(csv_data)

            #self.app_state['cloud_state'] = self.state

##============================================================================

def main():
    """Main entry if running this module directly."""

    cloud_thread = Cloud_Thread()
    cloud = cloud_thread.cloud

    #cloud_thread.init()
    cloud_thread.start()
    delay = 2
    try:
        while True:
            print('Sleeping for {} seconds'.format(delay))
            time.sleep(delay)
            print('----------------------------------------')

    except (KeyboardInterrupt, SystemExit):
        ## ctrl+c key press or sys.exit() called.
        print("EXCEPTION: KeyboardInterrupt or SystemExit")
    finally:
        print("Nearly done ...")
        cloud_thread.cleanup()

    print "Done.\nExiting."

##============================================================================

if __name__ == "__main__":
    main()

