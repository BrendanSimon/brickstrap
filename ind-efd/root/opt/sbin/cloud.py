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

##============================================================================

class Cloud_Thread(threading.Thread):
  
    def __init__(self):
        threading.Thread.__init__(self)
  
        self.cloud = Cloud()    ## starting the stream of info
        self.running = True     ## setting the thread running to true

    def run(self):
        self.cloud.configure()
        while self.running:
            ## continue to loop, wait for data, and process.
            self.cloud.wait_and_process()

    def cleanup(self):
        #print('DEBUG: cleaning up ...')
        self.running = False
        #print('DEBUG: thread join ...')
        self.join()
        #print('DEBUG: thread joined')

##============================================================================

class Cloud(object):

    select_timeout = 1

    serial_timeout = 0.1

    def __init__(self, app_state):

        self.app_state = app_state
        #self.state = state

        self.init()

    def init(self):
        self.measurement_ack = ''

    def configure(self):
            pass

    def post_measurements_data(csv_data):
        '''Post measurements data to the cloud service.'''

        r = requests.post(self.url, data=csv_data)
        print("DEBUG: post measurements data: r = {!r}".format(r))


    def wait_and_process(self):
        '''wait for data and process it.'''

        r = select.select([self.dev_hand], [], [], self.select_timeout)
        #print("DEBUG: r = {!r}".format(r))
        if not r[0]:
            print("DEBUG: TIMEOUT: wait_and_process")
            return

        print("DEBUG: Got data, processing ...")
        #csv_data = ''
        #for s in self.dev_hand.readlines():
        #self.post_measurements_data(csv_data)

        self.app_state['cloud_state'] = self.state

##============================================================================

def main():
    """Main entry if running this module directly."""

    cloud_thread = Cloud_Thread()
    cloud_info = cloud_thread.cloud

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

