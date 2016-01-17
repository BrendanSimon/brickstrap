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

import sys
import os.path
import numpy as np
import math
import time
#import datetime
import arrow
import select
import threading
import gps
import csv
import requests
import shelve

from cStringIO import StringIO
from collections import namedtuple

from persistent_dict import PersistentDict



from weather import Weather_Station_Thread

#import peak_detect

from tf_mapping import TF_Map
from tf_mapping import tf_map_calculate
## Disable debbuing in tf_mapping module.
import tf_mapping
#tf_mapping.DEBUG = True

import ind

##============================================================================

## FIXME: should probably be in a separate module.

class GPS_Poller_Thread(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)

        self.gpsd = gps.gps(mode=gps.WATCH_ENABLE) #starting the stream of info
        self.running = True #setting the thread running to true

    def run(self):
        while self.running:
            self.gpsd.next() #this will continue to loop and grab EACH set of gpsd info to clear the buffer

    def cleanup(self):
        self.running = False
        self.join() # wait for the thread to finish what it's doing

##============================================================================

## Named Tuple for Sample info, with fields 'index' and 'value'
Sample = namedtuple('Sample', ['index', 'value'])

Peak = namedtuple('Peak', ['index', 'value', 'time_offset', 'voltage'])

def sample_min(data):
    '''Search numpy data array for minimum value and the index.'''
    idx = np.argmin(data)
    val = data[idx]
    sample = Sample(index=idx, value=val)
    return sample

def sample_max(data):
    '''Search numpy data array for maximum value and the index.'''
    idx = np.argmax(data)
    val = data[idx]
    sample = Sample(index=idx, value=val)
    return sample

##============================================================================

class Config(object):

    serial_number = '123'

    web_server = 'http://portal.efdweb.com'

    web_server_ping = '{ws}/api/Ping/{sn}'.format(ws=web_server, sn=serial_number)
    web_server_measurements_log = '{ws}/api/AddEFDLog/{sn}'.format(ws=web_server, sn=serial_number)

    num_channels = 3

    ## 16-bits
    sample_bits = 16

    ## Sample Frequency 250 MS/s
    sample_frequency = 250 * 1000 * 1000

    ## 0x8000 if using offset-binary, 0 if using signed-binary.
    sample_offset = 0
    #sample_offset = 0x8000

    voltage_range_pp = 2.5
    #voltage_range_pp = 2.0
    #voltage_range_pp = 1.0

    #pd_event_trigger_voltage = 0.4
    pd_event_trigger_voltage = 0.10

    #capture_count = 10*1000*1000
    #capture_count = 4*1000*1000
    #capture_count = 2*1000*1000
    #capture_count = 1*1000*1000
    ## FIXME: There is bug in FGPA preventing capturing 10M samples (x3 channels).
    ## FIXME: there is bug in FPGA which prevents back-to-back DMA transfers.
    ## FIXME: we are limited to 8MB => 1,398,100 samples (x3 channels).
    #capture_count = 1398100

    ## FIXME: back-to-back DMA transfers are now working, but only 4 transactions.
    ## FIXME: we are now limited to 20MB => 3,495,252 samples (x3 channels).
    #capture_count = 3495252

    ## FIXME: back-to-back DMA transfers are now working, but only 4 transactions.
    ## FIXME: dma transaction size is now optimise to allow
    ## we are now limited to just under 40MB => 6,990,500 samples (x3 channels).
    ## I couldn't get 6,900,000 working, but 6,800,000 worked ok.
    #capture_count = 5000000
    capture_count = 6800000

    total_count = sample_frequency * 50 // 1000         ## total of 50ms between start of channel sampling.
    #total_count = sample_frequency * 100 // 1000        ## total of 100ms between start of channel sampling.

    delay_count = total_count - capture_count

    initialise_capture_memory = False
    show_intialised_capture_buffers = False
    show_intialised_phase_arrays = False

    show_capture_debug = False

    capture_index_offset_red = 0
    capture_index_offset_wht = total_count
    capture_index_offset_blu = total_count * 2

    fft_size = 1 << 16      ## 65,536 fft points
    fft_size_half = fft_size >> 1

    show_phase_arrays = False
    show_phase_arrays_on_pd_event = True
    show_capture_buffers = False

    peak_detect_numpy_capture_count_limit = 1*1000*1000
    peak_detect_numpy = False
    peak_detect_numpy_debug = False

    peak_detect_fpga = True
    peak_detect_fpga_debug = False

    peak_detect_fpga_fix = True
    peak_detect_fpga_fix_debug = True

    peak_detection = True
    peak_detection_debug = False

    tf_mapping = True
    tf_mapping_debug = False

    show_measurements = False
    show_measurements_post = False

    #page_size = 1024
    page_size = 32
    #page_size = 16

    page_width = 8

    data_dir = os.path.join('/mnt', 'data')

    state_filename = os.path.join(data_dir, 'efd_app.state')

    def __init__(self):
        self.set_capture_count()
        self.set_fft_size()

    def set_capture_count(self, capture_count=None):
        if capture_count:
            self.capture_count = capture_count

        self.delay_count = self.total_count - self.capture_count

        print("INFO: capture_count set to {}".format(self.capture_count))
        print("INFO: delay_count set to {}".format(self.delay_count))
        print("INFO: total_count is {}".format(self.total_count))

        if self.capture_count < self.fft_size:
            print("WARN: fft_size lowered")
            self.set_fft_size(self.capture_count)

    def set_fft_size(self, fft_size=None):
        if fft_size:
            self.fft_size = fft_size

        self.fft_size_half = self.fft_size >> 1

        print("INFO: fft_size set to {}".format(self.fft_size))
        print("INFO: fft_size_half set to {}".format(self.fft_size_half))

    def capture_data_polarity_is_signed(self):
        return self.sample_offset == 0

##============================================================================

measurements_log_field_names = [
    'datetime_utc', 'datetime_local',
    'max_volt_red', 'min_volt_red', 'max_time_offset_red', #'min_time_offset_red',
    'T2_red', 'W2_red',
    'max_volt_wht', 'min_volt_wht', 'max_time_offset_wht', #'min_time_offset_wht',
    'T2_red', 'W2_wht',
    'max_volt_blu', 'min_volt_blu', 'max_time_offset_blu', #'min_time_offset_blu',
    'T2_blu', 'W2_blu',
    'temperature', 'humidity', 'rain_intensity',
    ]

class Measuremenets_Log(object):
    '''Manage logging measurement data to log files.'''
    '''Uses csv module and csv.DictWriter object.'''
    '''Rotate log files each day, based on 'datetime_utc' field.'''

    def __init__(self, url, field_names=measurements_log_field_names):
        self.url = url
        self.field_names = field_names
        self.csv_file = None
        #self.path = '/mnt/data/log/measurements'
        self.path = os.path.join(os.sep, 'mnt', 'data', 'log', 'measurements')
        self.filename = ''
        self.filename_prefix = 'measurements-'
        self.filename_extension = '.csv'
        self.day_saved = 0

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

        ## Modify utc and local datetimes to output Excel & Matlab compatible ISO datetime strings.
        #measurements['datetime_utc'] = utc_dt.isoformat(sep=' ')
        #measurements['datetime_local'] = loc_dt.isoformat(sep=' ')


        ## FIXME: can initialise hdr_str once and reuse !!
        hdr_sio = StringIO()
        writer = csv.DictWriter(hdr_sio, fieldnames=self.field_names, extrasaction='ignore')
        writer.writeheader()
        hdr_str = hdr_sio.getvalue()
        hdr_sio.close()

        ## format csv output to a string (not a file) so the same output
        ## can be efficiently saved to a file and post to web server.
        row_sio= StringIO()
        writer = csv.DictWriter(row_sio, fieldnames=self.field_names, extrasaction='ignore')
        writer.writerow(measurements)
        row_str = row_sio.getvalue()
        row_sio.close()

        ##
        ## Write measurements to log file; and header if it's a new file.
        ##
        path_filename = os.path.join(self.path, self.filename)
        new_file = not os.path.exists(path_filename)
        with open(path_filename, 'a') as csvfile:
            #writer = csv.DictWriter(csvfile, fieldnames=self.field_names, extrasaction='ignore')
            if new_file:
                ## write header to new file.
                #writer.writeheader()
                csvfile.write(hdr_str)
            ## write measurements to file.
            #writer.writerow(measurements)
            csvfile.write(row_str)

        ##
        ## Post csv info to web server.
        ##
        #r = requests.post("http://httpbin.org/post", data=payload)
        csv_data = "{hdr}{row}".format(hdr=hdr_str, row=row_str)
        #r = requests.get(self.url, data=csv_data)
        #print("DEBUG: requests get response = {}".format(r))
        r = requests.post(self.url, data=csv_data)
        if config.show_measurements_post:
            print("DEBUG: url = {}".format(self.url))
            print("DEBUG: csv_data = ...")
            print(csv_data)
            print("DEBUG: requests post response = {}".format(r))

##============================================================================

class EFD_App(object):
    '''The IND Early Fault Detection application class.'''

    def __init__(self, config):
        '''Initialise EFD_App class.'''
        print(self.__doc__)

        self.config = config

        self.dev_name = ind.dev_name
        self.dev_hand = None
        self.adc_capture_array = None

        self.red_phase_0 = None
        self.wht_phase_0 = None
        self.blu_phase_0 = None

        self.red_phase_1 = None
        self.wht_phase_1 = None
        self.blu_phase_1 = None

        self.red_phase = None
        self.wht_phase = None
        self.blu_phase = None

        self.peak_max_red = Peak(index=0, value=0, time_offset=0, voltage=0)
        self.peak_min_red = Peak(index=0, value=0, time_offset=0, voltage=0)
        self.peak_max_wht = Peak(index=0, value=0, time_offset=0, voltage=0)
        self.peak_min_wht = Peak(index=0, value=0, time_offset=0, voltage=0)
        self.peak_max_blu = Peak(index=0, value=0, time_offset=0, voltage=0)
        self.peak_min_blu = Peak(index=0, value=0, time_offset=0, voltage=0)

        self.adc_capture_buffer_offset = 0
        self.adc_capture_buffer_offset_half = None     ## should be set to 64MB (128MB / 2)

        self.gps_poller = None      ## will be assinged a thread, that polls gpsd info.
        self.gpsd = None            ## will be assigned the gpsd data object.

        self.capture_datetime_utc = None
        self.capture_datetime_local = None

        ## TF_Map is a namedtuple.
        #self.tf_map = TF_Map(t0=None, T=None, T2=None, F=None, F2=None)
        self.tf_map = tf_mapping.Null_TF_Map

        self.measurements = {}
        self.measurements_log = Measuremenets_Log(url=self.config.web_server_measurements_log)

        ## Setup thread to retrieve GPS information.
        self.gps_poller = GPS_Poller_Thread()
        self.gpsd = self.gps_poller.gpsd

        ## Setup thread to retrieve Weather Station information.
        self.ws_thread = Weather_Station_Thread()
        self.ws_info = self.ws_thread.weather_station

        ## Shelf is used to mainstate accross program invokation.
        ## Shelf naitively supports pickle format, however the
        ## PersistentDict object can be used to provide picket, json or cvs.
        ## json was chosen to text readability.  It is also more portable,
        ## though it is not expected to move away from Python for the app.
        pd = PersistentDict(self.config.state_filename, 'c', format='json')
        self.app_state = shelve.Shelf(pd)

    def set_capture_count(self, capture_count):
        self.config.set_capture_count(capture_count)

    def set_phases(self):
        '''Set phase arrays to the current capture buffer.'''

        if self.adc_capture_buffer_offset == 0:
            ## set phase arrays to associated arrays at start of capture buffer.
            self.red_phase = self.red_phase_0
            self.wht_phase = self.wht_phase_0
            self.blu_phase = self.blu_phase_0
        else:
            ## set phase arrays to associated arrays at middle of capture buffer.
            self.red_phase = self.red_phase_1
            self.wht_phase = self.wht_phase_1
            self.blu_phase = self.blu_phase_1

        ## DEBUG output.
        if 0:
            print("set_phases(): red_phase @ {:08X}:".format(self.red_phase.__array_interface__['data'][0]))
            print("set_phases(): wht_phase @ {:08X}:".format(self.wht_phase.__array_interface__['data'][0]))
            print("set_phases(): blu_phase @ {:08X}:".format(self.blu_phase.__array_interface__['data'][0]))
            print

    def init_phase_arrays(self):
        '''Initialise phase arrays for start and middle of capture buffer -- for ping-pong buffering.'''

        num = self.config.capture_count

        ##
        ## set phase arrays at start of capture buffer.
        ##
        beg = 0
        end = beg + num
        self.red_phase_0 = self.adc_capture_array[beg:end]

        beg += num
        end = beg + num
        self.wht_phase_0 = self.adc_capture_array[beg:end]

        beg += num
        end = beg + num
        self.blu_phase_0 = self.adc_capture_array[beg:end]

        ##
        ## set phase arrays at middle of capture buffer.
        ##

        ## get index at middle of capture array.
        beg = len(self.adc_capture_array) // 2
        #beg += num
        end = beg + num
        self.red_phase_1 = self.adc_capture_array[beg:end]

        beg += num
        end = beg + num
        self.wht_phase_1 = self.adc_capture_array[beg:end]

        beg += num
        end = beg + num
        self.blu_phase_1 = self.adc_capture_array[beg:end]

        ## DEBUG output.
        if 0:
            print("init_phase_arrays(): red_phase_0 @ {:08X}:".format(self.red_phase_0.__array_interface__['data'][0]))
            print("init_phase_arrays(): wht_phase_0 @ {:08X}:".format(self.wht_phase_0.__array_interface__['data'][0]))
            print("init_phase_arrays(): blu_phase_0 @ {:08X}:".format(self.blu_phase_0.__array_interface__['data'][0]))

            print("init_phase_arrays(): red_phase_1 @ {:08X}:".format(self.red_phase_1.__array_interface__['data'][0]))
            print("init_phase_arrays(): wht_phase_1 @ {:08X}:".format(self.wht_phase_1.__array_interface__['data'][0]))
            print("init_phase_arrays(): blu_phase_1 @ {:08X}:".format(self.blu_phase_1.__array_interface__['data'][0]))

            print

        ## set phase arrays to for current capture buffer.
        self.set_phases()

    def init(self):
        '''Initialise EFD_App application.'''
        #print(self.__doc__)

        print("Python System Version = {}".format(sys.version))
        print

        self.sample_levels = (1 << self.config.sample_bits)
        self.time_resolution = 1.0 / self.config.sample_frequency
        self.voltage_factor = self.config.voltage_range_pp / self.sample_levels

        if not self.dev_hand:
            ## Do NOT use "r+b" with open(), as it allows writing.
            self.dev_hand = open(self.dev_name, "r+b" )
            #self.dev_hand = open(self.dev_name, "rb" )

        ## FIXME: temporary to test recovery of FPGA DMA issues.
        ## FIXME: the FPGA should not be reset in normal operation,
        ## FIXME: except possibly when the driver is probed ??
        #self.fpga_reset()

        #self.adc_dma_reset()

        self.adc_stop()

        self.adc_capture_array = self.adc_numpy_array()
        if self.config.initialise_capture_memory:
            print("Initialise capture array : filling with 0x6141")
            self.adc_capture_array.fill(0x6141)

        if self.config.show_intialised_capture_buffers:
            self.show_all_capture_buffers()

        self.init_phase_arrays()
        if self.config.show_intialised_phase_arrays:
            self.show_phase_arrays()

    def cleanup(self):
        '''Cleanup application before exit.'''

        print "\nStopping ADC."
        self.adc_stop()

        print "\nStopping Threads..."
        self.gps_poller.cleanup()
        self.ws_thread.cleanup()
        print "\nThreads Stopped."

    def adc_numpy_array(self):
        mem = ind.adc_memory_map(dev_hand=self.dev_hand)
        print("ADC Memory: {!r}".format(mem))
        ## Numpy array holds little-endian 16-bit integers.
        signed = self.config.capture_data_polarity_is_signed()
        dtype = np.dtype('<i2') if signed else np.dtype('<u2')
        dtype_size = dtype.itemsize
        mem_size = len(mem)
        length = mem_size // dtype_size
        print("DEBUG: dtype_size={!r} len(mem)={!r} length={!r}".format(dtype_size, mem_size, length))
        shape = (length,)
        np_array = np.ndarray(shape=shape, dtype=dtype, buffer=mem)

        ## the memory offset for half the capture buffer.
        self.adc_capture_buffer_offset_half = mem_size // 2

        return np_array

    def fpga_reset(self):
        print("DEBUG: FPGA Resetting ...")
        ind.fpga_reset(dev_hand=self.dev_hand)
        print("DEBUG: FPGA Reset.")

    def adc_dma_reset(self):
        print("DEBUG: ADC DMA Resetting ...")
        ind.adc_dma_reset(dev_hand=self.dev_hand)
        print("DEBUG: ADC DMA Reset.")

    def adc_capture_buffer_next(self):
        '''Set next capture bufer for next dma acquisition -- use for ping-pong buffering.'''
        curr_offset = self.adc_capture_buffer_offset

        self.set_phases()

        next_offset = self.adc_capture_buffer_offset_half if curr_offset == 0 else 0
        #print("DEBUG: next_capture_buffer: curr_offset={:X}, next_offset={:X}".format(curr_offset, next_offset))
        self.adc_capture_buffer_offset = next_offset

        ind.adc_capture_address(address=next_offset, dev_hand=self.dev_hand)

    def adc_stop(self):
        print("ADC Stop")
        ind.adc_capture_stop(dev_hand=self.dev_hand)

    def adc_start(self):
        print("ADC Start")

        signed = self.config.capture_data_polarity_is_signed()
        print("DEBUG: signed = {!r}".format(signed))

        #peak_detect_start_count=ind.Config.Peak_Start_Disable
        #peak_detect_stop_count=ind.Config.Peak_Stop_Disable
        peak_detect_start_count = 0
        peak_detect_stop_count = self.config.capture_count - 1

        ind.adc_capture_start(address=0, capture_count=self.config.capture_count, delay_count=self.config.delay_count, signed=signed, peak_detect_start_count=peak_detect_start_count, peak_detect_stop_count=peak_detect_stop_count, dev_hand=self.dev_hand)

    def adc_semaphore_get(self):
        #print("ADC Semaphore Get")
        sem = ind.adc_semaphore_get(dev_hand=self.dev_hand)
        return sem

    def adc_semaphore_set(self, value):
        #print("ADC Semaphore Set")
        ind.adc_semaphore_set(value=value, dev_hand=self.dev_hand)

    def adc_semaphore_wait(self):
        print("ADC Semaphore Wait")
        while True:
            sem = self.adc_semaphore_get()
            if sem:
                break
            time.sleep(0.01)

    def adc_select_wait(self):
        #print("ADC Select Wait")

        ##
        ##  Using select.  NOTE: very simple and it works :)
        ##
        while True:
            r = select.select([self.dev_hand], [], [], 1)
            if r[0]:
                break
            print("DEBUG: TIMEOUT: adc_select_wait()")
            status = ind.status_get(dev_hand=self.dev_hand)
            sem = ind.adc_semaphore_get(dev_hand=self.dev_hand)
            print("DEBUG: status = 0x{:08X}".format(status))
            print("DEBUG: semaphore = 0x{:08X}".format(sem))
        return

        ##
        ##  Using epoll.  NOTE: doesn't work yet :(
        ##
        epoll = select.epoll()
        ## If not provided, event-mask defaults to (POLLIN | POLLPRI | POLLOUT).
        ## It can be modified later with modify().
        fileno = self.dev_hand.fileno()
        epoll.register(fileno)
        try:
            while True:
                #events = epoll.poll(3)  ## 3 second timeout
                events = epoll.poll()
                #for fd, event_type in events:
                #    _handle_inotify_event(e, s, fd, event_type)
        finally:
            epoll.unregister(fileno)
            epoll.close()

    def adc_data_ready_wait(self):
        #print("ADC Data Ready Wait")
        self.adc_select_wait()
        #self.adc_semaphore_wait()

    def get_mmap_sample_data(self):
        '''Get sample data from memory mapped buffer.'''
        self.adc_semaphore_set(0)
        self.adc_data_ready_wait()

    def get_sample_data(self):
        '''Get sample data from memory mapped buffer or capture files.'''
        '''FIXME: capture files not implemented !!'''
        self.get_mmap_sample_data()

    def get_capture_datetime(self):
        '''Get the datetime stamp .'''
        utc_dt = arrow.utcnow().floor('second')
        self.capture_datetime_utc = utc_dt
        self.capture_datetime_local = utc_dt.to('local')

    def show_capture_buffer_part(self, beg, end, offset):
        '''Show partial contents in capture buffer.'''
        for channel in range(self.config.num_channels):
            buf = self.adc_capture_array[channel*self.config.capture_count+offset:]
            #buf = self.adc_capture_array[channel*self.config.capture_count:]
            #print("Channel {}: {!r}:".format(channel, buf.__array_interface__))
            print("Channel {}: @ 0x{:08X}:".format(channel, buf.__array_interface__['data'][0]))
            for i in range(beg, end, self.config.page_width):
                print("[{:08X}]:".format(i)),
                for w in range(self.config.page_width):
                    idx = i + w
                    if idx >= end:
                        break
                    val = buf[idx]
                    #print(" 0x{:04x},".format(val)),
                    val -= self.config.sample_offset
                    print(" {:6},".format(val)),
                print

    def show_capture_buffer(self, offset):
        '''Show contents in capture buffer.'''

        print('----------------------------------------')

        beg = 0
        end = self.config.capture_count

        if self.config.capture_count < (self.config.page_size * 2):
            self.show_capture_buffer_part(beg=beg, end=end, offset=offset)
        else:
            ## Display first page.
            end = self.config.page_size
            self.show_capture_buffer_part(beg=beg, end=end, offset=offset)
            ## Display skip message.
            beg = self.config.capture_count - self.config.page_size
            print("   .....")
            print("Skipping samples {:08X}-{:08X}".format(end, beg))
            print("   ....")
            ## Display last page.
            end = self.config.capture_count
            self.show_capture_buffer_part(beg=beg, end=end, offset=offset)
        print

    def show_all_capture_buffers(self):
        '''Show contents in all capture buffer.'''

        self.show_capture_buffer(offset=0)
        self.show_capture_buffer(offset=len(self.adc_capture_array)//2)

    def show_phase_part(self, phase, beg, end):
        '''Show partial contents of phase buffer.'''
        buf = phase
        for i in range(beg, end, self.config.page_width):
            print("[{:08X}]:".format(i)),
            for w in range(self.config.page_width):
                idx = i + w
                if idx >= end:
                    break
                val = buf[idx]
                #print(" 0x{:04x},".format(val)),
                val -= self.config.sample_offset
                print(" {:6},".format(val)),
            print

    def show_phase(self, phase):
        '''Show data in phase arrays.'''

        beg = 0
        end = self.config.capture_count

        if self.config.capture_count < (self.config.page_size * 2):
            self.show_phase_part(phase, beg, end)
        else:
            ## Display first page.
            end = self.config.page_size
            self.show_phase_part(phase, beg, end)
            ## Display skip message.
            beg = self.config.capture_count - self.config.page_size
            print("   ....")
            #print("Skipping samples {:08X}-{:08X}".format(end, beg))
            #print(".....")
            ## Display last page.
            end = self.config.capture_count
            self.show_phase_part(phase, beg, end)

        print

    def show_phase_arrays(self, phase_index=None):
        '''Show data in phase arrays.'''

        if phase_index == 0:
            red_phase = self.red_phase_0
            wht_phase = self.wht_phase_0
            blu_phase = self.blu_phase_0
        elif phase_index == 1:
            red_phase = self.red_phase_1
            wht_phase = self.wht_phase_1
            blu_phase = self.blu_phase_1
        else:
            red_phase = self.red_phase
            wht_phase = self.wht_phase
            blu_phase = self.blu_phase

        print('----------------------------------------')

        print("RED: buffer @ 0x{:08X}:".format(red_phase.__array_interface__['data'][0]))
        self.show_phase(red_phase)

        print("WHT: buffer @ 0x{:08X}:".format(wht_phase.__array_interface__['data'][0]))
        self.show_phase(wht_phase)

        print("BLU: buffer @ 0x{:08X}:".format(blu_phase.__array_interface__['data'][0]))
        self.show_phase(blu_phase)

    def save_data_numpy(self, path, filename, phase):
        '''Save data to disk in numpy format -- uncompressed zip archive.'''

        if phase is self.red_phase:
            filename = "{}-red".format(filename)
        elif phase is self.wht_phase:
            filename = "{}-wht".format(filename)
        elif phase is self.blu_phase:
            filename = "{}-blu".format(filename)
        else:
            raise ValueError('phase value not valid')

        np.save(os.path.join(path, filename), phase)

        ## we are only going to save one sample file (the "worst" of three channels)
        ## so using a zip archive might be overkill (unless compression is useful).
        #np.savez(filename, red=red_arr, white=wht_arr, blue=blu_arr)

    def save_data_numpy_compressed(self, path, filename, phase=None):
        '''Save data to disk in numpy compressed format -- compressed zip archive.'''
        np.savez_compressed(os.path.join(path, filename), phase)

    def save_data_raw(self, path, filename, phase=None):
        '''Save data to disk in raw binary format.'''
        np.ndarray.tofile(os.path.join(path, filename), phase)

    def save_data(self, phase):
        '''Save data to disk.'''

        utc_dt = self.capture_datetime_utc
        loc_dt = self.capture_datetime_local
        #print("DEBUG: utc_dt={!r}".format(utc_dt))
        #print("DEBUG: loc_dt={!r}".format(loc_dt))
        #utc_dt_str = utc_dt.isoformat()
        #loc_dt_str = loc_dt.isoformat()
        #print("DEBUG: utc_dt_str={!r}".format(utc_dt_str))
        #print("DEBUG: loc_dt_str={!r}".format(loc_dt_str))
        #utc_dt_str = utc_dt.format('YYYYMMDDTHHmmssZZ')
        #loc_dt_str = loc_dt.format('YYYYMMDDTHHmmssZZ')
        #print("DEBUG: utc_dt_str={!r}".format(utc_dt_str))
        #print("DEBUG: loc_dt_str={!r}".format(loc_dt_str))
        #utc_dt_str = utc_dt.format('YYYY-MM-DDTHH:mm:ssZZ')
        #loc_dt_str = loc_dt.format('YYYY-MM-DDTHH:mm:ssZZ')
        #print("DEBUG: utc_dt_str={!r}".format(utc_dt_str))
        #print("DEBUG: loc_dt_str={!r}".format(loc_dt_str))
        utc_dt_str = utc_dt.format('YYYYMMDDTHHmmssZ')
        loc_dt_str = loc_dt.format('YYYYMMDDTHHmmssZ')
        #print("DEBUG: utc_dt_str={!r}".format(utc_dt_str))
        #print("DEBUG: loc_dt_str={!r}".format(loc_dt_str))
        utc_filename = 'sampledata-{}'.format(utc_dt_str)
        loc_filename = 'sampledata-{}'.format(loc_dt_str)
        print("DEBUG: utc_filename={!r}".format(utc_filename))
        print("DEBUG: loc_filename={!r}".format(loc_filename))

        #path = '/mnt/data/log/samples'
        path = os.path.join(os.sep, 'mnt', 'data', 'log', 'samples')

        self.save_data_numpy(path, utc_filename, phase=phase)
        #self.save_data_numpy(path, loc_filename, phase=phase)

        #self.save_data_numpy_compressed(path, utc_filename, phase=phase)
        #self.save_data_numpy_compressed(path, loc_filename, phase=phase)

        #self.save_data_raw(path, utc_filename, phase=phase)
        #self.save_data_raw(path, loc_filename, phase=phase)

    def peak_convert_numpy(self, index, data, index_offset):
        '''Convert peak index and value to Peak object, converting to time and voltage.'''
        toff = float(index + index_offset) / self.config.sample_frequency
        #toff = float(index + index_offset) * self.time_resolution
        value = data[index] - self.config.sample_offset
        volt = value * self.voltage_factor
        peak = Peak(index=index, value=value, time_offset=toff, voltage=volt)
        return peak

    def peak_min(self, data, index_offset):
        '''Search numpy data array for minimum value and the index.'''
        '''Value is converted from sample level to volts.'''
        idx = np.argmin(data)
        peak = self.peak_convert_numpy(index=idx, data=data, index_offset=index_offset)
        return peak

    def peak_max(self, data, index_offset):
        '''Search numpy data array for maximum value and the index.'''
        '''Value is converted from sample level to volts.'''
        idx = np.argmax(data)
        peak = self.peak_convert_numpy(index=idx, data=data, index_offset=index_offset)
        return peak

    def peak_detection_numpy(self):
        '''Perform peak detection on current phases using numpy.'''

        t1 = time.time()
        peak_max_red = self.peak_max(self.red_phase, index_offset=self.config.capture_index_offset_red)
        t2 = time.time()
        peak_min_red = self.peak_min(self.red_phase, index_offset=self.config.capture_index_offset_red)
        t3 = time.time()
        red_time_delta_1 = t2 - t1
        red_time_delta_2 = t3 - t2
        #print("DEBUG: RED: time_delta_1={}".format(red_time_delta_1))
        #print("DEBUG: RED: time_delta_2={}".format(red_time_delta_2))

        peak_max_wht = self.peak_max(self.wht_phase, index_offset=self.config.capture_index_offset_wht)
        peak_min_wht = self.peak_min(self.wht_phase, index_offset=self.config.capture_index_offset_wht)

        peak_max_blu = self.peak_max(self.blu_phase, index_offset=self.config.capture_index_offset_blu)
        peak_min_blu = self.peak_min(self.blu_phase, index_offset=self.config.capture_index_offset_blu)

        self.peak_max_red = peak_max_red
        self.peak_min_red = peak_min_red
        self.peak_max_wht = peak_max_wht
        self.peak_min_wht = peak_min_wht
        self.peak_max_blu = peak_max_blu
        self.peak_min_blu = peak_min_blu

    def peak_convert_fpga(self, index, value, index_offset):
        '''Convert peak index and value to Peak object, converting to time and voltage.'''
        toff = float(index + index_offset) / self.config.sample_frequency
        #toff = float(index + index_offset) * self.time_resolution
        value -= self.config.sample_offset
        volt = value * self.voltage_factor
        peak = Peak(index=index, value=value, time_offset=toff, voltage=volt)
        return peak

    def peak_detection_fpga(self):
        '''Get peak detection info from FPGA.'''

        t1 = time.time()

        ## Read the maxmin registers from the fpga.
        maxmin = ind.adc_capture_maxmin_get(dev_hand=self.dev_hand)

        ## Red
        peak_max_red = self.peak_convert_fpga(index=maxmin.max_ch0_addr, value=maxmin.max_ch0_data, index_offset=self.config.capture_index_offset_red)
        peak_min_red = self.peak_convert_fpga(index=maxmin.min_ch0_addr, value=maxmin.min_ch0_data, index_offset=self.config.capture_index_offset_red)

        ## Wht
        peak_max_wht = self.peak_convert_fpga(index=maxmin.max_ch1_addr, value=maxmin.max_ch1_data, index_offset=self.config.capture_index_offset_wht)
        peak_min_wht = self.peak_convert_fpga(index=maxmin.min_ch1_addr, value=maxmin.min_ch1_data, index_offset=self.config.capture_index_offset_wht)

        ## Blu
        peak_max_blu = self.peak_convert_fpga(index=maxmin.max_ch2_addr, value=maxmin.max_ch2_data, index_offset=self.config.capture_index_offset_blu)
        peak_min_blu = self.peak_convert_fpga(index=maxmin.min_ch2_addr, value=maxmin.min_ch2_data, index_offset=self.config.capture_index_offset_blu)

        t2 = time.time()
        t_delta_1 = t2 - t1

        self.peak_max_red = peak_max_red
        self.peak_min_red = peak_min_red
        self.peak_max_wht = peak_max_wht
        self.peak_min_wht = peak_min_wht
        self.peak_max_blu = peak_max_blu
        self.peak_min_blu = peak_min_blu

        t_delta_2 = time.time() - t1
        if config.peak_detect_fpga_debug:
            print("DEBUG: Peak Detect FPGA: maxmin = {}".format(maxmin))
            print("DEBUG: Peak Detect FPGA: t_delta_1 = {}".format(t_delta_1))
            print("DEBUG: Peak Detect FPGA: t_delta_2 = {}".format(t_delta_2))

    def peak_detection(self):
        '''Perform peak detection on current phases.'''

        ## Do FPGA first, as minmax registers are not double buffered.
        if self.config.peak_detect_fpga:
            ret = self.peak_detection_fpga()

            if self.config.peak_detect_fpga_debug:
                print
                print("DEBUG: Peak Detect FPGA")
                print("DEBUG: peak_max_red = {}".format(self.peak_max_red))
                print("DEBUG: peak_min_red = {}".format(self.peak_min_red))
                print("DEBUG: peak_max_wht = {}".format(self.peak_max_wht))
                print("DEBUG: peak_min_wht = {}".format(self.peak_min_wht))
                print("DEBUG: peak_max_blu = {}".format(self.peak_max_blu))
                print("DEBUG: peak_min_blu = {}".format(self.peak_min_blu))

        if self.config.peak_detect_numpy:
            if self.config.capture_count > self.config.peak_detect_numpy_capture_count_limit:
                print("FIXME: skipping numpy peak detection as capture_count ({}) too high (> {})".format(self.config.capture_count, self.config.peak_detect_numpy_capture_count_limit))
            else:
                ret = self.peak_detection_numpy()

                if self.config.peak_detect_numpy_debug:
                    print
                    print("DEBUG: Peak Detect NUMPY")
                    print("DEBUG: peak_max_red = {}".format(self.peak_max_red))
                    print("DEBUG: peak_min_red = {}".format(self.peak_min_red))
                    print("DEBUG: peak_max_wht = {}".format(self.peak_max_wht))
                    print("DEBUG: peak_min_wht = {}".format(self.peak_min_wht))
                    print("DEBUG: peak_max_blu = {}".format(self.peak_max_blu))
                    print("DEBUG: peak_min_blu = {}".format(self.peak_min_blu))

        if self.config.peak_detect_numpy_debug and self.config.peak_detect_fpga_debug:
            print
            print("DEBUG: Peak Detect Check FPGA v Numpy")
            value = self.red_phase[self.peak_max_red.index] - self.config.sample_offset
            print("DEBUG: peak_max_red: fpga={} numpy={}".format(self.peak_max_red.value, value))
            value = self.red_phase[self.peak_min_red.index] - self.config.sample_offset
            print("DEBUG: peak_min_red: fpga={} numpy={}".format(self.peak_min_red.value, value))

            value = self.wht_phase[self.peak_max_wht.index] - self.config.sample_offset
            print("DEBUG: peak_max_wht: fpga={} numpy={}".format(self.peak_max_wht.value, value))
            value = self.wht_phase[self.peak_min_wht.index] - self.config.sample_offset
            print("DEBUG: peak_min_wht: fpga={} numpy={}".format(self.peak_min_wht.value, value))

            value = self.blu_phase[self.peak_max_blu.index] - self.config.sample_offset
            print("DEBUG: peak_max_blu: fpga={} numpy={}".format(self.peak_max_blu.value, value))
            value = self.blu_phase[self.peak_min_blu.index] - self.config.sample_offset
            print("DEBUG: peak_min_blu: fpga={} numpy={}".format(self.peak_min_blu.value, value))

        return ret


    def tf_map_calculate(self, phase, index):
        fft_size_half = self.config.fft_size_half
        if index < fft_size_half:
            beg = 0
            end = self.config.fft_size
        elif index > (len(phase) - fft_size_half):
            end = len(phase)
            beg = end - self.config.fft_size
            fft_phase = phase[0:self.config.fft_size]
        else:
            beg = index - fft_size_half
            end = index + fft_size_half

        tstart = beg
        tstop = end

        #fft_time = np.arange(start=tstart, stop=tstop, step=1, dtype=tf_mapping.DTYPE) / self.config.sample_frequency
        fft_time = np.arange(start=tstart, stop=tstop, step=1, dtype=tf_mapping.DTYPE) * self.time_resolution
        #print("DEBUG: fft_time = {!r}".format(fft_time))

        fft_phase = phase[beg:end] * self.voltage_factor
        #print("DEBUG: fft_phase = {!r}".format(fft_phase))

        tf_map = tf_map_calculate(tdata=fft_time, ydata=fft_phase, sample_freq=self.config.sample_frequency, fft_length=0)

        return tf_map

    def main_loop(self):
        '''Run main loop of EFD_App.'''

        self.gps_poller.start()

        #self.ws_thread.init()
        self.ws_thread.start()

        print("DEBUG: capture_count = {}".format(self.config.capture_count))
        print("DEBUG: delay_count   = {}".format(self.config.delay_count))
        ## Start the analog acquisition.
        self.adc_start()

        while True:
            self.get_sample_data()          ## wait for data to be available.

            select_datetime_utc = arrow.utcnow()
            select_datetime_local = select_datetime_utc.to('local')

            ## Clear terminal screen by sending special chars (ansi sequence?).
            #print("\033c")

            if config.show_capture_debug:
                print("\n========================================")

            ## Temporary hack to work around multiple interrupts with BOOT-20160110.BIN
            ## Getting 3 interrupts, after each channel DMA, instead of 1 interrupt after last channel DMA.
            ## don't process if microsecond field is less than 30ms.
            if 0:
                microsecond = select_datetime_utc.microsecond
                total_us = (self.config.num_channels-1) * self.config.total_count // (250)
                print("FIXME: total_us = {}".format(total_us))
                print("FIXME: utc.microsend = {}".format(microsecond))
                if microsecond < total_us:
                    print("FIXME: skip processing! utc.microsend ({}) < {}".format(microsecond, total_us))
                    print("FIXME: capture_count={}, delay_count={}, total_count={}".format(self.config.capture_count, self.config.delay_count, self.config.total_count))
                    continue

            if config.show_capture_debug:
                print("DEBUG: Data Captured - Processing ...")

            self.adc_capture_buffer_next()  ## use next capture bufer for ping-pong

            self.get_capture_datetime()

            if self.config.peak_detection:
                self.peak_detection()

            if self.config.peak_detection_debug:
                print("DEBUG: Peak Detection")
                print("DEBUG: RED: max_idx={:6} max_val={:6}".format(self.peak_max_red.index, self.peak_max_red.value))
                print("DEBUG: RED: min_idx={:6} min_val={:6}".format(self.peak_min_red.index, self.peak_min_red.value))
                print("DEBUG: WHT: max_idx={:6} max_val={:6}".format(self.peak_max_wht.index, self.peak_max_wht.value))
                print("DEBUG: WHT: min_idx={:6} min_val={:6}".format(self.peak_min_wht.index, self.peak_min_wht.value))
                print("DEBUG: BLU: max_idx={:6} max_val={:6}".format(self.peak_max_blu.index, self.peak_max_blu.value))
                print("DEBUG: BLU: min_idx={:6} min_val={:6}".format(self.peak_min_blu.index, self.peak_min_blu.value))
                print

            if self.config.tf_mapping:
                ## FIXME: do we do this for all phases, or just the 'worst' phase (based on peak results)?
                self.tf_map_red = self.tf_map_calculate(phase=self.red_phase, index=self.peak_max_red.index)
                self.tf_map_wht = self.tf_map_calculate(phase=self.wht_phase, index=self.peak_max_wht.index)
                self.tf_map_blu = self.tf_map_calculate(phase=self.blu_phase, index=self.peak_max_blu.index)

            if self.config.tf_mapping_debug:
                print("DEBUG: TF Mapping")
                print("DEBUG: tf_map_red={}".format(self.tf_map_red))
                print("DEBUG: tf_map_wht={}".format(self.tf_map_wht))
                print("DEBUG: tf_map_blu={}".format(self.tf_map_blu))
                print

            ##
            ## Update measurements dictionary.
            ##
            self.measurements['datetime_utc'] = self.capture_datetime_utc.isoformat(sep=' ')
            self.measurements['datetime_local'] = self.capture_datetime_local.isoformat(sep=' ')
            self.measurements['max_volt_red'] = self.peak_max_red.voltage
            self.measurements['min_volt_red'] = self.peak_min_red.voltage
            self.measurements['max_time_offset_red'] = self.peak_max_red.time_offset
            self.measurements['min_time_offset_red'] = self.peak_min_red.time_offset
            self.measurements['T2_red'] = self.tf_map_red.T2
            self.measurements['W2_red'] = self.tf_map_red.F2
            self.measurements['max_volt_wht'] = self.peak_max_wht.voltage
            self.measurements['min_volt_wht'] = self.peak_min_wht.voltage
            self.measurements['max_time_offset_wht'] = self.peak_max_wht.time_offset
            self.measurements['min_time_offset_wht'] = self.peak_min_wht.time_offset
            self.measurements['T2_wht'] = self.tf_map_wht.T2
            self.measurements['W2_wht'] = self.tf_map_wht.F2
            self.measurements['max_volt_blu'] = self.peak_max_blu.voltage
            self.measurements['min_volt_blu'] = self.peak_min_blu.voltage
            self.measurements['max_time_offset_blu'] = self.peak_max_blu.time_offset
            self.measurements['min_time_offset_blu'] = self.peak_min_blu.time_offset
            self.measurements['T2_blu'] = self.tf_map_blu.T2
            self.measurements['W2_blu'] = self.tf_map_blu.F2
            self.measurements['temperature'] = self.ws_info.temperature
            self.measurements['humidity'] = self.ws_info.humidity
            self.measurements['rain_intensity'] = self.ws_info.rain_intensity

            ## write measurements dictionary to measurements log file.
            self.measurements_log.write(measurements=self.measurements, datetime=self.capture_datetime_utc)

            if self.config.show_measurements:
                print('----------------------------------------')
                print
                print('select datetime utc    : {}'.format(select_datetime_utc))
                print('select datetime local  : {}'.format(select_datetime_local))
                print
                print('system datetime utc   : {}'.format(self.capture_datetime_utc))
                print('system datetime local : {}'.format(self.capture_datetime_local))
                print
                print('latitude  : {}'.format(self.gpsd.fix.latitude))
                print('longitude : {}'.format(self.gpsd.fix.longitude))
                print('time utc  : {}'.format(self.gpsd.utc))
                print('fix time  : {}'.format(self.gpsd.fix.time))
                print
                print('peak_max_red : {}'.format(self.peak_max_red))
                print('peak_min_red : {}'.format(self.peak_min_red))
                print
                print('peak_max_wht : {}'.format(self.peak_max_wht))
                print('peak_min_wht : {}'.format(self.peak_min_wht))
                print
                print('peak_max_blu : {}'.format(self.peak_max_blu))
                print('peak_min_blu : {}'.format(self.peak_min_blu))
                print
                print('temperature    : {}'.format(self.ws_info.temperature))
                print('humidity       : {}'.format(self.ws_info.humidity))
                print('rain intensity : {}'.format(self.ws_info.rain_intensity))
                print
                print('tf_map : {!r}'.format(self.tf_map))
                print

            ##
            ## Peak Threshold Detection.
            ## FIXME: this is ugly and not very pythonic.
            ##
            trigger_phase = None
            trigger_peak = None
            if self.peak_max_red.voltage >= self.config.pd_event_trigger_voltage:
                trigger_peak = self.peak_max_red
                trigger_phase = self.red_phase

            if self.peak_max_wht.voltage >= self.config.pd_event_trigger_voltage:
                if trigger_peak == None or self.peak_max_wht.voltage > trigger_peak.voltage:
                    trigger_peak = self.peak_max_wht
                    trigger_phase = self.wht_phase

            if self.peak_max_blu.voltage >= self.config.pd_event_trigger_voltage:
                if trigger_peak == None or self.peak_max_blu.voltage > trigger_peak.voltage:
                    trigger_peak = self.peak_max_blu
                    trigger_phase = self.blu_phase

            if trigger_phase is not None:
                self.save_data(phase=trigger_phase)
                if self.config.show_phase_arrays_on_pd_event:
                    self.show_phase_arrays()
                    #self.show_all_capture_buffers()

            ##
            ## Show capture data / phase arrays
            ##
            #self.show_phase_arrays(phase_index=0)
            #self.show_phase_arrays(phase_index=1)

            if self.config.show_phase_arrays:
                self.show_phase_arrays()

            if self.config.show_capture_buffers:
                self.show_all_capture_buffers()

            ## FIXME: DEBUG: exit after one cycle.
            #break

            self.app_state['last_capture_datetime_utc'] = self.capture_datetime_utc
            self.app_state['last_capture_datetime_local'] = self.capture_datetime_local

##----------------------------------------------------------------------------

##############################################################################

## Make config object global.
config = Config()

def main():
    """Main entry if running this module directly."""

    ## FIXME: should use argparse module !!
    try:
        capture_count = int(sys.argv[1],0)
        config.set_capture_count(capture_count)
    except:
        print("EXCEPTION: no argument supplied for capture_count.  Defaulting to {}".format(config.capture_count))
        #raise

    app = EFD_App(config=config)
    app.init()
    try:
        app.main_loop()
    except (KeyboardInterrupt, SystemExit):
        ## ctrl+c key press.
        print("KeyboardInterrupt -- exiting ...")
    except (SystemExit):
        ## sys.exit() called.
        print("SystemExit -- exiting ...")
    finally:
        print("Cleaning up.")
        app.cleanup()
        print("Done.  Exiting.")

##============================================================================

if __name__ == "__main__":
    main()
