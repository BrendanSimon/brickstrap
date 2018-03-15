#!/usr/bin/env python2

##############################################################################
#!
#!  Author:     Successful Endeavours Pty Ltd
#!
##############################################################################

'''
This module will generate sinusoidal data that simulates real world
data acquired via a high speed A2D converter.
Default parameters are 250 MS/s 16-bit data.
'''

import argh
import sys
import os
import numpy as np
import time
import arrow
import selectors2 as selectors
import Queue as queue       #! Python 3 renames Queue module as queue.
import traceback
import logging

from collections import namedtuple

from weather import Weather_Station_Thread
from cloud import Cloud, Cloud_Thread
from efd_gps import GPS_Poller_Thread

from efd_measurements import Measurements_Log

from efd_config import Config, PeakDetectMode, TestMode, ADC_Polarity

from efd_sensors import Sensors

#import peak_detect

from tf_mapping import TF_Map
from tf_mapping import tf_map_calculate
#! Disable debugging in tf_mapping module.
import tf_mapping
#tf_mapping.DEBUG = True

import ind

#!============================================================================

def method_name():
    frame = sys._getframe(1)
    class_name = frame.f_locals["self"].__class__.__name__
    func_name = frame.f_code.co_name
    s = "{}.{}()".format(class_name, func_name)
    return s

#!============================================================================

def sign_adjusted_magnitude(magnitude, value):
    '''Returns the sign adjusted magnitude.'''

    return -magnitude if value < 0 else magnitude

#!============================================================================

## Named Tuple for Sample info, with fields 'index' and 'value'
Sample = namedtuple('Sample', ['index', 'value'])

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

#!============================================================================

PeakBase = namedtuple('Peak', ['index', 'value', 'count', 'time_offset', 'voltage'])

PeakBase.__new__.__defaults__ = (0, 0, 0, 0.0, 0.0)     ## list of default values.

class Peak(PeakBase):

    def __repr__(self):
        return "{}( index={:10}, value={:+11}, count={:8}, time_offset={:12.9f}, voltage={:12.9f} )".format(self.__class__.__name__, self.index, self.value, self.count, self.time_offset, self.voltage)

PEAK_DEFAULT = Peak()

#!============================================================================

class EFD_App(object):
    '''The IND Early Fault Detection application class.'''

    def __init__(self, config):
        '''Initialise EFD_App class.'''
        print(self.__doc__)

        self.config = config

        self.dev_name = ind.dev_name
        self.dev_hand = None
        self.adc_capture_array = None
        self.adc_capture_array_0 = None
        self.adc_capture_array_1 = None
        self.adc_capture_array_test_indices = []

        self.red_phase_0 = None
        self.wht_phase_0 = None
        self.blu_phase_0 = None

        self.red_phase_1 = None
        self.wht_phase_1 = None
        self.blu_phase_1 = None

        self.red_phase = None
        self.wht_phase = None
        self.blu_phase = None

        self.peak_normal_max_red = PEAK_DEFAULT
        self.peak_normal_min_red = PEAK_DEFAULT
        self.peak_normal_max_wht = PEAK_DEFAULT
        self.peak_normal_min_wht = PEAK_DEFAULT
        self.peak_normal_max_blu = PEAK_DEFAULT
        self.peak_normal_min_blu = PEAK_DEFAULT

        self.peak_squared_max_red = PEAK_DEFAULT
        self.peak_squared_min_red = PEAK_DEFAULT
        self.peak_squared_max_wht = PEAK_DEFAULT
        self.peak_squared_min_wht = PEAK_DEFAULT
        self.peak_squared_max_blu = PEAK_DEFAULT
        self.peak_squared_min_blu = PEAK_DEFAULT

        self.bank = 0
        self.next_bank = 0
        self.prev_bank = 0
        self.adc_capture_buffer_offset = [ 0 ] * self.config.bank_count

        self.gps_poller = None      #! will be assigned a thread, that polls gpsd info.
        self.gpsd = None            #! will be assigned the gpsd data object.

        self.capture_datetime_utc = None
        self.capture_datetime_local = None

        #! TF_Map is a namedtuple.
        self.tf_map_red = tf_mapping.Null_TF_Map
        self.tf_map_wht = tf_mapping.Null_TF_Map
        self.tf_map_blu = tf_mapping.Null_TF_Map

        self.measurements = {}
        self.measurements_log = Measurements_Log(field_names=self.config.measurements_log_field_names)

        #! Setup thread to retrieve GPS information.
        self.gps_poller = GPS_Poller_Thread()
        self.gpsd = self.gps_poller.gpsd

        #! Setup thread to retrieve Weather Station information.
        self.ws_thread = Weather_Station_Thread()
        self.ws_info = self.ws_thread.weather_station

        #! Setup thread to post information to the cloud service.
        self.cloud_queue = queue.Queue(maxsize=config.max_cloud_queue_size)
        self.cloud = Cloud(config=config, cloud_queue=self.cloud_queue, measurements_log=self.measurements_log)
        self.cloud_thread = Cloud_Thread(self.cloud)

        self.sensors = Sensors()

        self.last_pd_event_report_datetime_utc = arrow.Arrow(1,1,1)

        self.capture_trigger_count = 0

        #!
        #! Error and diagnostics
        #!

        self.buffer_errors_total = 0

        self.peak_index_errors = 0
        self.peak_value_errors = 0
        self.peak_count_errors = 0

        self.peak_index_errors_total = 0
        self.peak_value_errors_total = 0
        self.peak_count_errors_total = 0
        self.peak_errors_total = 0

    def set_capture_count(self, capture_count):
        self.config.set_capture_count(capture_count)

    def set_phases(self):
        '''Set phase arrays to the current capture buffer.'''

        if self.bank == 0:
            #! set phase arrays to associated arrays at start of capture buffer.
            self.red_phase = self.red_phase_0
            self.wht_phase = self.wht_phase_0
            self.blu_phase = self.blu_phase_0
        else:
            #! set phase arrays to associated arrays at middle of capture buffer.
            self.red_phase = self.red_phase_1
            self.wht_phase = self.wht_phase_1
            self.blu_phase = self.blu_phase_1

        #! DEBUG output.
        if 0:
            adc_cap_buf_offset = self.adc_capture_buffer_offset[self.bank]
            print("set_phases(): bank={}".format(self.bank))
            print("set_phases(): adc_capture_buffer_offset=0x{:08X}".format(adc_cap_buf_offset))
            print("set_phases(): red_phase @ 0x{:08X}".format(self.red_phase.__array_interface__['data'][0]))
            print("set_phases(): wht_phase @ 0x{:08X}".format(self.wht_phase.__array_interface__['data'][0]))
            print("set_phases(): blu_phase @ 0x{:08X}".format(self.blu_phase.__array_interface__['data'][0]))
            print

    def init_phase_arrays(self):
        '''Initialise phase arrays for start and middle of capture buffer -- for ping-pong buffering.'''

        num = self.config.capture_count

        #!
        #! set phase arrays at start of capture buffer.
        #!
        beg = 0
        end = beg + num
        self.red_phase_0 = self.adc_capture_array[beg:end]

        beg += num
        end = beg + num
        self.wht_phase_0 = self.adc_capture_array[beg:end]

        beg += num
        end = beg + num
        self.blu_phase_0 = self.adc_capture_array[beg:end]

        #!
        #! set phase arrays at middle of capture buffer.
        #!

        #! get index at middle of capture array.
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

        #! DEBUG output.
        if 0:
            print("init_phase_arrays(): red_phase_0 @ {:08X}:".format(self.red_phase_0.__array_interface__['data'][0]))
            print("init_phase_arrays(): wht_phase_0 @ {:08X}:".format(self.wht_phase_0.__array_interface__['data'][0]))
            print("init_phase_arrays(): blu_phase_0 @ {:08X}:".format(self.blu_phase_0.__array_interface__['data'][0]))

            print("init_phase_arrays(): red_phase_1 @ {:08X}:".format(self.red_phase_1.__array_interface__['data'][0]))
            print("init_phase_arrays(): wht_phase_1 @ {:08X}:".format(self.wht_phase_1.__array_interface__['data'][0]))
            print("init_phase_arrays(): blu_phase_1 @ {:08X}:".format(self.blu_phase_1.__array_interface__['data'][0]))

            print

        #! set phase arrays to for current capture buffer.
        self.set_phases()

    def init(self):
        '''Initialise EFD_App application.'''
        #print(self.__doc__)

        logging.basicConfig(level=self.config.logging_level)
        #logger = logging.getLogger()
        #logger.setLevel(self.config.logging_level)

        logging.info("Python System Version = {}".format(sys.version))

        self.sample_levels = (1 << self.config.sample_bits)
        self.time_resolution = 1.0 / self.config.sample_frequency
        self.voltage_factor = self.config.voltage_range_pp / self.sample_levels

        if not self.dev_hand:
            #! Do NOT use "r+b" with open(), as it allows writing.
            self.dev_hand = open(self.dev_name, "r+b" )
            #self.dev_hand = open(self.dev_name, "rb" )

        #! FIXME: temporary to test recovery of FPGA DMA issues.
        #! FIXME: the FPGA should not be reset in normal operation,
        #! FIXME: except possibly when the driver is probed ??
        #self.fpga_reset()

        #self.adc_dma_reset()

        fpga_version = self.fpga_version_get()
        print("IND FPGA Version = {}.{}".format(fpga_version.major, fpga_version.minor))

        self.adc_stop()

        self.adc_dma_reset()

        self.adc_capture_array = self.adc_numpy_array()

#         #!
#         #! test capture array values at the following indices for correct magic value.
#         #! - one past last valid capture value of first array => zero + capture count
#         #! - last index of first capture array => half index of full array - 1
#         #! - one past last valid capture value of second array => half index + capture count
#         #! - last index of second capture array => -1
#         #!
#         ccx = self.config.capture_count * self.config.channel_count
#         self.adc_capture_array_test_indices = [ ccx, (half_index - 1), (half_index + ccx), -1 ]

        if self.config.initialise_capture_memory:
            print("Initialise capture array : filling with 0x6141")
            time0 = time.time()
            self.adc_capture_array.fill(self.config.initialise_capture_memory_magic_value)
            delta = time.time() - time0
            print("DEBUG: time to initialise capture array = {} seconds".format(delta))

        if self.config.show_capture_buffers:
            self.show_all_capture_buffers()

        self.init_phase_arrays()
        if self.config.show_phase_arrays:
            self.show_phase_arrays()

        # setup the selector for adc (uses `selectors2` module instead of `select`)
        # register the IND device for read events.
        self.adc_selector = selectors.DefaultSelector()
        self.adc_selector.register(self.dev_hand, selectors.EVENT_READ)

        self.sensors.init()

        #! Initialise the meausrements_log object.
        self.measurements_log.init()

    def cleanup(self):
        '''Cleanup application before exit.'''

        print("Stopping ADC.")
        self.adc_stop()

        # unregister the IND device from adc selector.
        self.adc_selector.unregister(self.dev_hand)

        print("Waiting for queues to empty...")
        self.cloud_queue.join()
        print("Queues empty.")

        print("Stopping Threads...")
        self.cloud_thread.cleanup()
        self.ws_thread.cleanup()
        self.gps_poller.cleanup()
        print("Threads Stopped.")

        self.sensors.cleanup()

    def adc_numpy_array(self):
        mem = ind.adc_memory_map(dev_hand=self.dev_hand)
        print("ADC Memory: {!r}".format(mem))
        #! Numpy array holds little-endian 16-bit integers.
        signed = self.config.adc_polarity_is_signed()
        dtype = np.dtype('<i2') if signed else np.dtype('<u2')
        dtype_size = dtype.itemsize
        mem_size = len(mem)
        length = mem_size // dtype_size
        print("DEBUG: dtype_size={!r} len(mem)={!r} length={!r}".format(dtype_size, mem_size, length))
        shape = (length,)
        np_array = np.ndarray(shape=shape, dtype=dtype, buffer=mem)

        #! the memory offset for each bank of the capture buffer.
        bank_size = mem_size // self.config.bank_count
        self.adc_capture_buffer_offset = [ bank_size * i for i in range(self.config.bank_count) ]

        return np_array

    def adc_capture_array_tests(self):
        magic = self.config.initialise_capture_memory_magic_value
        for index in self.adc_capture_array_test_indices:
            value = self.adc_capture_array[index]
            if value != magic:
                print("ERROR: Buffer overrun.  adc_capture_array[0x{index:0X}]=0x{value:0X} does not match magic=0x{magic:0X} !!".format(index=index, value=value, magic=magic))

    def fpga_reset(self):
        print("DEBUG: FPGA Resetting ...")
        ind.fpga_reset(dev_hand=self.dev_hand)
        print("DEBUG: FPGA Reset.")

    def fpga_version_get(self):
        print("DEBUG: FPGA Version Get()")
        fpga_version = ind.fpga_version_get(dev_hand=self.dev_hand)
        return fpga_version

    def adc_dma_reset(self):
        print("DEBUG: ADC DMA Resetting ...")
        ind.adc_dma_reset(dev_hand=self.dev_hand)
        print("DEBUG: ADC DMA Reset.")

    def adc_capture_buffer_next(self):
        '''Set next capture buffer for next dma acquisition -- use for ping-pong buffering.'''

        #print("DEBUG: next_capture_buffer: old_bank={}, old_next_bank={}".format(self.bank, self.next_bank))

        self.prev_bank = self.bank

        self.bank = self.next_bank

        self.next_bank = (self.next_bank + 1) % self.config.bank_count

        #self.prev_bank = (self.bank - 1) % self.config.bank_count

        curr_offset = self.adc_capture_buffer_offset[self.bank]
        next_offset = self.adc_capture_buffer_offset[self.next_bank]

        #print("DEBUG: next_capture_buffer: new_bank={}, new_next_bank={}".format(self.bank, self.next_bank))
        #print("DEBUG: next_capture_buffer: curr_offset=0x{:X}, next_offset=0x{:X}".format(curr_offset, next_offset))

        ind.adc_capture_address(address=next_offset, dev_hand=self.dev_hand)

        self.set_phases()

    def adc_stop(self):
        print("ADC Stop")
        ind.adc_capture_stop(dev_hand=self.dev_hand)

    def adc_start(self):
        print("ADC Start")

        signed = self.config.adc_polarity_is_signed()
        print("DEBUG: signed = {!r}".format(signed))

        #peak_detect_start_count=ind.Config.Peak_Start_Disable
        #peak_detect_stop_count=ind.Config.Peak_Stop_Disable
        peak_detect_start_count = 0
        peak_detect_stop_count  = self.config.capture_count

        self.peak_detect_start_count = peak_detect_start_count
        self.peak_detect_stop_count  = peak_detect_stop_count

        ind.adc_capture_start(address=self.adc_capture_buffer_offset[self.next_bank],
                              capture_count=self.config.capture_count,
                              delay_count=self.config.delay_count,
                              capture_mode=self.config.capture_mode,
                              signed=signed,
                              peak_detect_start_count=peak_detect_start_count,
                              peak_detect_stop_count=peak_detect_stop_count,
                              adc_offset=self.config.adc_offset,
                              test_mode=self.config.test_mode,
                              dev_hand=self.dev_hand)

    def adc_semaphore_get(self):
        #print("ADC Semaphore Get")
        sem = ind.adc_semaphore_get(dev_hand=self.dev_hand)
        return sem

    def adc_semaphore_set(self, value):
        #print("ADC Semaphore Set")
        ind.adc_semaphore_set(value=value, dev_hand=self.dev_hand)

    def adc_semaphore_wait(self):
        #print("ADC Semaphore Wait")
        ret = True
        delay = 0.01
        count_max = 1 / delay
        count = 0
        while True:
            sem = self.adc_semaphore_get()
            if sem:
                break
            time.sleep(delay)
            count += 1
            if count > count_max:
                print("DEBUG: TIMEOUT: adc_semaphore_wait()")
                status = ind.status_get(dev_hand=self.dev_hand)
                sem = ind.adc_semaphore_get(dev_hand=self.dev_hand)
                print("DEBUG: status = 0x{:08X}".format(status))
                print("DEBUG: semaphore = 0x{:08X}".format(sem))
                ret = False
                break;

        return ret

    def adc_select_wait(self):
        #print("ADC Select Wait")

        #!
        #! Use `selectors2` module to wait for data to be available.
        #!
        ret = True
        while True:
            have_data = False
            events = self.adc_selector.select(timeout=1.0)
            for key, event in events:
                if event & selectors.EVENT_READ:
                    have_data = True
            if have_data:
                break

            print("DEBUG: TIMEOUT: adc_select_wait()")
            status = ind.status_get(dev_hand=self.dev_hand)
            sem = ind.adc_semaphore_get(dev_hand=self.dev_hand)
            print("DEBUG: status = 0x{:08X}".format(status))
            print("DEBUG: semaphore = 0x{:08X}".format(sem))
            ret = False
            break

        return ret

    def adc_trigger(self):
        #print("ADC Manual Trigger")
        ind.adc_trigger(dev_hand=self.dev_hand)

    def adc_data_ready_wait(self):
        #print("ADC Data Ready Wait")
        if self.config.capture_mode == 'manual':
            #! fake pps delay
            if self.config.pps_delay:
                time.sleep(self.config.pps_delay)

            self.adc_trigger()
            ret = self.adc_semaphore_wait()
        else:
            ret = self.adc_select_wait()

        return ret

    def get_mmap_sample_data(self):
        '''Get sample data from memory mapped buffer.'''

        self.adc_semaphore_set(0)
        ret = self.adc_data_ready_wait()
        return ret

    def get_sample_data(self):
        '''Get sample data from memory mapped buffer or capture files.'''
        '''FIXME: capture files not implemented !!'''

        ret = self.get_mmap_sample_data()
        return ret

    def set_capture_datetime(self, utc_dt):
        '''Set the datetime stamp from utc'''

        self.capture_datetime_utc = utc_dt
        self.capture_datetime_local = utc_dt.to(self.config.timezone)

    def get_capture_datetime(self):
        '''Get the datetime stamp .'''

        utc_dt = arrow.utcnow().floor('second')
        self.set_capture_datetime(utc_dt)

    def show_capture_buffer_part(self, beg, end, offset):
        '''Show partial contents in capture buffer.'''

        for channel in range(self.config.channel_count):
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
                    print(" {:7},".format(val)),
                print

    def show_capture_buffer(self, offset):
        '''Show contents in capture buffer.'''

        print('----------------------------------------')

        beg = 0
        end = self.config.capture_count

        if self.config.capture_count < (self.config.page_size * 2):
            self.show_capture_buffer_part(beg=beg, end=end, offset=offset)
        else:
            #! Display first page.
            end = self.config.page_size
            self.show_capture_buffer_part(beg=beg, end=end, offset=offset)
            #! Display skip message.
            beg = self.config.capture_count - self.config.page_size
            print("   .....")
            print("Skipping samples {:08X}-{:08X}".format(end, beg))
            print("   ....")
            #! Display last page.
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
                print(" {:+11},".format(val)),
            print

    def show_phase(self, phase):
        '''Show data in phase arrays.'''

        beg = 0
        end = self.config.capture_count

        if self.config.capture_count < (self.config.page_size * 2):
            self.show_phase_part(phase, beg, end)
        else:
            #! Display first page.
            end = self.config.page_size
            self.show_phase_part(phase, beg, end)
            #! Display skip message.
            beg = self.config.capture_count - self.config.page_size
            print("   ....")
            #print("Skipping samples {:08X}-{:08X}".format(end, beg))
            #print(".....")
            #! Display last page.
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

        #! we are only going to save one sample file (the "worst" of three channels)
        #! so using a zip archive might be overkill (unless compression is useful).
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

        #! Create directory to store samples log if it doesn't exists.
        if not os.path.exists(path):
            os.makedirs(path)

        self.save_data_numpy(path, utc_filename, phase=phase)
        #self.save_data_numpy(path, loc_filename, phase=phase)

        #self.save_data_numpy_compressed(path, utc_filename, phase=phase)
        #self.save_data_numpy_compressed(path, loc_filename, phase=phase)

        #self.save_data_raw(path, utc_filename, phase=phase)
        #self.save_data_raw(path, loc_filename, phase=phase)

    def generate_sms_message(self):
        '''Generate the SMS message'''

        #!
        #! Example message.
        #! ----------------
        #!
        #! EFD PD Event
        #! Unit: 2
        #! Site: EFD2-Springvale-South
        #! Time (L): 2016-01-18 18:58:15+11:00
        #! RED: Vmax=-0.0004, Vmin=-0.0026, T2=5.7e-09, W2=3.2e13 *
        #! WHT: Vmax=-0.0003, Vmin=-0.0027, T2=5.7e-09, W2=3.4e13
        #! BLU: Vmax=-0.0001, Vmin=-0.0029, T2=5.7e-09, W2=3.2e13
        #! Temp: 28.5C
        #! Humidity: 29.6P
        #! Rain-Int: 0
        #!

        m = self.measurements

        max_volt_red = m.get('max_volt_red', 0.0)
        max_volt_wht = m.get('max_volt_wht', 0.0)
        max_volt_blu = m.get('max_volt_blu', 0.0)

        min_volt_red = m.get('min_volt_red', 0.0)
        min_volt_wht = m.get('min_volt_wht', 0.0)
        min_volt_blu = m.get('min_volt_blu', 0.0)

        t2_red = m.get('t2_red', 0.0)
        t2_wht = m.get('t2_wht', 0.0)
        t2_blu = m.get('t2_blu', 0.0)

        w2_red = m.get('w2_red', 0.0)
        w2_wht = m.get('w2_wht', 0.0)
        w2_blu = m.get('w2_blu', 0.0)

        alert = m.get('alert', '')

        alert_red = '*' if alert == 'R' else ' '
        alert_wht = '*' if alert == 'W' else ' '
        alert_blu = '*' if alert == 'B' else ' '

        sms_message = '\n'.join([
            "EFD PD Event",
            "Unit: {}".format(self.config.serial_number),
            "Site: {}".format(self.config.site_name),
            "Time (L): {}".format(m.get('datetime_local','')),
            "RED: Vmax={:+0.4f}, Vmin={:+0.4f}, T2={:+0.1e}, W2={:+0.1e} {}".format(max_volt_red, min_volt_red, t2_red, w2_red, alert_red),
            "WHT: Vmax={:+0.4f}, Vmin={:+0.4f}, T2={:+0.1e}, W2={:+0.1e} {}".format(max_volt_wht, min_volt_wht, t2_wht, w2_wht, alert_wht),
            "BLU: Vmax={:+0.4f}, Vmin={:+0.4f}, T2={:+0.1e}, W2={:+0.1e} {}".format(max_volt_blu, min_volt_blu, t2_blu, w2_blu, alert_blu),
            "Temp: {}".format(m.get('temperature')),
            "Humidity: {}".format(m.get('humidity')),
            "Rain-Int: {}".format(m.get('rain_intensity')),
            ])

        return sms_message

    def send_sms(self):
        '''Send SMS'''

        message = self.generate_sms_message()

        for phone_number in self.config.reporting_sms_phone_numbers:
            #! Call script to send SMS.
            cmd = "/opt/sbin/send-sms.sh {phone_number} '{message}' &".format(phone_number=phone_number, message=message)
            print("DEBUG: send_sms: cmd = {}".format(cmd))
            #! FIXME: check return/exception for os.system(cmd)
            os.system(cmd)

    ##------------------------------------------------------------------------

    def peak_convert(self, index, value, index_offset, count, voltage_factor):
        '''Convert peak index and value to Peak object, converting to time and voltage.'''

        toff = float(index + index_offset) / self.config.sample_frequency
        #toff = float(index + index_offset) * self.time_resolution
        value -= self.config.sample_offset
        volt = value * voltage_factor
        peak = Peak(index=index, value=value, count=count, time_offset=toff, voltage=volt)
        return peak

    ##------------------------------------------------------------------------

    def peak_by_func(self, func, data, index_offset, voltage_factor):
        '''Search numpy data array (by function) and get the index.'''
        '''Value is converted from sample level to volts.'''

        peak_data = data[self.peak_detect_start_count:self.peak_detect_stop_count]

        time0 = time.time()
        idx = func(peak_data) + self.peak_detect_start_count
        delta = time.time() - time0
        #print("DEBUG: np.min/np.max() took {} seconds".format(delta))
        value = data[idx]

        time0 = time.time()
        condition = (data == value)
        delta = time.time() - time0
        #print("DEBUG: condition compare took {} seconds".format(delta))

        time0 = time.time()
        count = np.count_nonzero(condition)
        delta = time.time() - time0
        #print("DEBUG: np.count_nonzero took {} seconds".format(delta))

        peak = self.peak_convert(index=idx, value=value, index_offset=index_offset, count=count, voltage_factor=voltage_factor)
        return peak

    ##------------------------------------------------------------------------

    def peak_min(self, data, index_offset, voltage_factor):
        '''Search numpy data array for minimum value and the index.'''
        '''Value is converted from sample level to volts.'''

        return self.peak_by_func(func=np.argmin, data=data, index_offset=index_offset, voltage_factor=voltage_factor)

    ##------------------------------------------------------------------------

    def peak_max(self, data, index_offset, voltage_factor):
        '''Search numpy data array for maximum value and the index.'''
        '''Value is converted from sample level to volts.'''

        return self.peak_by_func(func=np.argmax, data=data, index_offset=index_offset, voltage_factor=voltage_factor)

    ##------------------------------------------------------------------------

    def peak_detect_normal_numpy(self):
        '''Perform peak detection on normal current phases using numpy.'''

        voltage_factor = self.voltage_factor

        phase = self.red_phase
        if 0:
            #! FIXME: copy from device memory (non-cached) to normal (cached) memory.
            #! FIXME: for testing only !!
            phase = np.copy(phase)
        offset = self.config.capture_index_offset_red
        t1 = time.time()
        peak_max_red = self.peak_max(phase, index_offset=offset, voltage_factor=voltage_factor)
        t2 = time.time()
        peak_min_red = self.peak_min(phase, index_offset=offset, voltage_factor=voltage_factor)
        t3 = time.time()
        red_time_delta_1 = t2 - t1
        red_time_delta_2 = t3 - t2
        if 0:
            print("DEBUG: RED: time_delta_1={}".format(red_time_delta_1))
            print("DEBUG: RED: time_delta_2={}".format(red_time_delta_2))

        phase = self.wht_phase
        if 0:
            #! FIXME: copy from device memory (non-cached) to normal (cached) memory.
            #! FIXME: for testing only !!
            phase = np.copy(phase)
        offset = self.config.capture_index_offset_wht
        peak_max_wht = self.peak_max(phase, index_offset=offset, voltage_factor=voltage_factor)
        peak_min_wht = self.peak_min(phase, index_offset=offset, voltage_factor=voltage_factor)

        phase = self.blu_phase
        if 0:
            #! FIXME: copy from device memory (non-cached) to normal (cached) memory.
            #! FIXME: for testing only !!
            phase = np.copy(phase)
        offset = self.config.capture_index_offset_blu
        peak_max_blu = self.peak_max(phase, index_offset=offset, voltage_factor=voltage_factor)
        peak_min_blu = self.peak_min(phase, index_offset=offset, voltage_factor=voltage_factor)

        self.peak_normal_max_red = peak_max_red
        self.peak_normal_min_red = peak_min_red
        self.peak_normal_max_wht = peak_max_wht
        self.peak_normal_min_wht = peak_min_wht
        self.peak_normal_max_blu = peak_max_blu
        self.peak_normal_min_blu = peak_min_blu

    ##------------------------------------------------------------------------

    def peak_detect_squared_numpy(self):
        '''Perform peak detection on squared current phases using numpy.'''

        voltage_factor = self.voltage_factor ** 2

        phase = self.red_phase
        phase = phase.astype(np.int32)
        phase = np.square(phase)
        offset = self.config.capture_index_offset_red
        t1 = time.time()
        peak_max_red = self.peak_max(phase, index_offset=offset, voltage_factor=voltage_factor)
        t2 = time.time()
        peak_min_red = self.peak_min(phase, index_offset=offset, voltage_factor=voltage_factor)
        t3 = time.time()
        red_time_delta_1 = t2 - t1
        red_time_delta_2 = t3 - t2
        if 0:
            print("DEBUG: RED: time_delta_1={}".format(red_time_delta_1))
            print("DEBUG: RED: time_delta_2={}".format(red_time_delta_2))

        phase = self.wht_phase
        phase = phase.astype(np.int32)
        phase = np.square(phase)
        offset = self.config.capture_index_offset_wht
        peak_max_wht = self.peak_max(phase, index_offset=offset, voltage_factor=voltage_factor)
        peak_min_wht = self.peak_min(phase, index_offset=offset, voltage_factor=voltage_factor)

        phase = self.blu_phase
        phase = phase.astype(np.int32)
        phase = np.square(phase)
        offset = self.config.capture_index_offset_blu
        peak_max_blu = self.peak_max(phase, index_offset=offset, voltage_factor=voltage_factor)
        peak_min_blu = self.peak_min(phase, index_offset=offset, voltage_factor=voltage_factor)

        self.peak_squared_max_red = peak_max_red
        self.peak_squared_min_red = peak_min_red
        self.peak_squared_max_wht = peak_max_wht
        self.peak_squared_min_wht = peak_min_wht
        self.peak_squared_max_blu = peak_max_blu
        self.peak_squared_min_blu = peak_min_blu

    ##------------------------------------------------------------------------

    def peak_detect_normal_fpga(self):
        '''Get normal peak detection info from FPGA.'''

        t1 = time.time()

        maxmin = self.maxmin_normal
        voltage_factor = self.voltage_factor

        #! channel 0 (red)
        peak_max_red = self.peak_convert(index=(maxmin.max_ch0_addr & 0xffffff), value=maxmin.max_ch0_data, index_offset=self.config.capture_index_offset_red, count=maxmin.max_ch0_count, voltage_factor=voltage_factor)
        peak_min_red = self.peak_convert(index=(maxmin.min_ch0_addr & 0xffffff), value=maxmin.min_ch0_data, index_offset=self.config.capture_index_offset_red, count=maxmin.min_ch0_count, voltage_factor=voltage_factor)

        #! channel 1 (white)
        peak_max_wht = self.peak_convert(index=(maxmin.max_ch1_addr & 0xffffff), value=maxmin.max_ch1_data, index_offset=self.config.capture_index_offset_wht, count=maxmin.max_ch1_count, voltage_factor=voltage_factor)
        peak_min_wht = self.peak_convert(index=(maxmin.min_ch1_addr & 0xffffff), value=maxmin.min_ch1_data, index_offset=self.config.capture_index_offset_wht, count=maxmin.min_ch1_count, voltage_factor=voltage_factor)

        #! channel 2 (blue)
        peak_max_blu = self.peak_convert(index=(maxmin.max_ch2_addr & 0xffffff), value=maxmin.max_ch2_data, index_offset=self.config.capture_index_offset_blu, count=maxmin.max_ch2_count, voltage_factor=voltage_factor)
        peak_min_blu = self.peak_convert(index=(maxmin.min_ch2_addr & 0xffffff), value=maxmin.min_ch2_data, index_offset=self.config.capture_index_offset_blu, count=maxmin.min_ch2_count, voltage_factor=voltage_factor)

        t2 = time.time()
        t_delta_1 = t2 - t1

        self.peak_normal_max_red = peak_max_red
        self.peak_normal_min_red = peak_min_red
        self.peak_normal_max_wht = peak_max_wht
        self.peak_normal_min_wht = peak_min_wht
        self.peak_normal_max_blu = peak_max_blu
        self.peak_normal_min_blu = peak_min_blu

        t_delta_2 = time.time() - t1
        if self.config.peak_detect_fpga_debug:
            print
            print("DEBUG: Peak Detect Normal FPGA: maxmin = {}".format(maxmin))
            print("DEBUG: Peak Detect Normal FPGA: t_delta_1 = {}".format(t_delta_1))
            print("DEBUG: Peak Detect Normal FPGA: t_delta_2 = {}".format(t_delta_2))

    ##------------------------------------------------------------------------

    def peak_detect_squared_fpga(self):
        '''Get squared peak detection info from FPGA.'''

        t1 = time.time()

        maxmin = self.maxmin_squared
        voltage_factor = self.voltage_factor ** 2

        #! channel 0 (red)
        peak_max_red = self.peak_convert(index=maxmin.max_ch0_addr, value=maxmin.max_ch0_data, index_offset=self.config.capture_index_offset_red, count=maxmin.max_ch0_count, voltage_factor=voltage_factor)
        peak_min_red = self.peak_convert(index=maxmin.min_ch0_addr, value=maxmin.min_ch0_data, index_offset=self.config.capture_index_offset_red, count=maxmin.min_ch0_count, voltage_factor=voltage_factor)

        #! channel 1 (white)
        peak_max_wht = self.peak_convert(index=maxmin.max_ch1_addr, value=maxmin.max_ch1_data, index_offset=self.config.capture_index_offset_wht, count=maxmin.max_ch1_count, voltage_factor=voltage_factor)
        peak_min_wht = self.peak_convert(index=maxmin.min_ch1_addr, value=maxmin.min_ch1_data, index_offset=self.config.capture_index_offset_wht, count=maxmin.min_ch1_count, voltage_factor=voltage_factor)

        #! channel 2 (blue)
        peak_max_blu = self.peak_convert(index=maxmin.max_ch2_addr, value=maxmin.max_ch2_data, index_offset=self.config.capture_index_offset_blu, count=maxmin.max_ch2_count, voltage_factor=voltage_factor)
        peak_min_blu = self.peak_convert(index=maxmin.min_ch2_addr, value=maxmin.min_ch2_data, index_offset=self.config.capture_index_offset_blu, count=maxmin.min_ch2_count, voltage_factor=voltage_factor)

        t2 = time.time()
        t_delta_1 = t2 - t1

        self.peak_squared_max_red = peak_max_red
        self.peak_squared_min_red = peak_min_red
        self.peak_squared_max_wht = peak_max_wht
        self.peak_squared_min_wht = peak_min_wht
        self.peak_squared_max_blu = peak_max_blu
        self.peak_squared_min_blu = peak_min_blu

        t_delta_2 = time.time() - t1
        if self.config.peak_detect_fpga_debug:
            print
            print("DEBUG: Peak Detect Squared FPGA: maxmin = {}".format(maxmin))
            print("DEBUG: Peak Detect Squared FPGA: t_delta_1 = {}".format(t_delta_1))
            print("DEBUG: Peak Detect Squared FPGA: t_delta_2 = {}".format(t_delta_2))

    ##------------------------------------------------------------------------

    def peak_detect_normal(self):
        '''Perform normal peak detection on current phases.'''

        peak_index_errors = 0
        peak_value_errors = 0
        peak_count_errors = 0

        #! Do FPGA first (if minmax registers are not double buffered).
        if self.config.peak_detect_fpga:
            time0 = time.time()
            ret = self.peak_detect_normal_fpga()
            time1 = time.time()

            #! Maintain reference to FPGA peak values.
            fpga_peak_normal_max_red = self.peak_normal_max_red
            fpga_peak_normal_min_red = self.peak_normal_min_red
            fpga_peak_normal_max_wht = self.peak_normal_max_wht
            fpga_peak_normal_min_wht = self.peak_normal_min_wht
            fpga_peak_normal_max_blu = self.peak_normal_max_blu
            fpga_peak_normal_min_blu = self.peak_normal_min_blu

            if self.config.peak_detect_fpga_debug:
                print
                print("DEBUG: Peak Detect FPGA (Normal)")
                print("DEBUG: peak_normal_max_red = {}".format(fpga_peak_normal_max_red))
                print("DEBUG: peak_normal_min_red = {}".format(fpga_peak_normal_min_red))
                print("DEBUG: peak_normal_max_wht = {}".format(fpga_peak_normal_max_wht))
                print("DEBUG: peak_normal_min_wht = {}".format(fpga_peak_normal_min_wht))
                print("DEBUG: peak_normal_max_blu = {}".format(fpga_peak_normal_max_blu))
                print("DEBUG: peak_normal_min_blu = {}".format(fpga_peak_normal_min_blu))
                delta = time1 - time0
                print("DEBUG: duration = {} seconds".format(delta))

        if self.config.peak_detect_numpy:
            time0 = time.time()
            ret = self.peak_detect_normal_numpy()
            time1 = time.time()

            #! Maintain reference to numpy peak values.
            numpy_peak_normal_max_red = self.peak_normal_max_red
            numpy_peak_normal_min_red = self.peak_normal_min_red
            numpy_peak_normal_max_wht = self.peak_normal_max_wht
            numpy_peak_normal_min_wht = self.peak_normal_min_wht
            numpy_peak_normal_max_blu = self.peak_normal_max_blu
            numpy_peak_normal_min_blu = self.peak_normal_min_blu

            if self.config.peak_detect_numpy_debug:
                print
                print("DEBUG: Peak Detect Numpy (Normal)")
                print("DEBUG: peak_normal_max_red = {}".format(numpy_peak_normal_max_red))
                print("DEBUG: peak_normal_min_red = {}".format(numpy_peak_normal_min_red))
                print("DEBUG: peak_normal_max_wht = {}".format(numpy_peak_normal_max_wht))
                print("DEBUG: peak_normal_min_wht = {}".format(numpy_peak_normal_min_wht))
                print("DEBUG: peak_normal_max_blu = {}".format(numpy_peak_normal_max_blu))
                print("DEBUG: peak_normal_min_blu = {}".format(numpy_peak_normal_min_blu))
                delta = time1 - time0
                print("DEBUG: duration = {} seconds".format(delta))

            if fpga_peak_normal_max_red is numpy_peak_normal_max_red:
                print("ERROR: SAME OBJECT: fpga_peak_normal_max_red is numpy_peak_normal_max_red !!")

        if self.config.peak_detect_numpy and self.config.peak_detect_fpga:
            print("\nDEBUG: Peak Detect Check (FPGA v Numpy)")

            #! Red Max
            if fpga_peak_normal_max_red.value != numpy_peak_normal_max_red.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_normal_max_red.value={:+8} numpy_peak_normal_max_red.value={:+8}".format(fpga_peak_normal_max_red.value, numpy_peak_normal_max_red.value))
                peak_value_errors += 1
            if fpga_peak_normal_max_red.index != numpy_peak_normal_max_red.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_normal_max_red.index={:8} numpy_peak_normal_max_red.index={:8}".format(fpga_peak_normal_max_red.index, numpy_peak_normal_max_red.index))
                peak_index_errors += 1
            if fpga_peak_normal_max_red.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_normal_max_red.index={:8} peak_detect_start_count={:8}".format(fpga_peak_normal_max_red.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_normal_max_red.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_normal_max_red.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_normal_max_red.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_normal_max_red.count != numpy_peak_normal_max_red.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_normal_max_red.count={:8} numpy_peak_normal_max_red.count={:8}".format(fpga_peak_normal_max_red.count, numpy_peak_normal_max_red.count))
                peak_count_errors += 1

            #! Red Min
            if fpga_peak_normal_min_red.value != numpy_peak_normal_min_red.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_normal_min_red.value={:+8} numpy_peak_normal_min_red.value={:+8}".format(fpga_peak_normal_min_red.value, numpy_peak_normal_min_red.value))
                peak_value_errors += 1
            if fpga_peak_normal_min_red.index != numpy_peak_normal_min_red.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_normal_min_red.index={:8} numpy_peak_normal_min_red.index={:8}".format(fpga_peak_normal_min_red.index, numpy_peak_normal_min_red.index))
                peak_index_errors += 1
            if fpga_peak_normal_min_red.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_normal_min_red.index={:8} peak_detect_start_count={:8}".format(fpga_peak_normal_min_red.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_normal_min_red.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_normal_min_red.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_normal_min_red.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_normal_min_red.count != numpy_peak_normal_min_red.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_normal_min_red.count={:8} numpy_peak_normal_min_red.count={:8}".format(fpga_peak_normal_min_red.count, numpy_peak_normal_min_red.count))
                peak_count_errors += 1

            #! White Max
            if fpga_peak_normal_max_wht.value != numpy_peak_normal_max_wht.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_normal_max_wht.value={:+8} numpy_peak_normal_max_wht.value={:+8}".format(fpga_peak_normal_max_wht.value, numpy_peak_normal_max_wht.value))
                peak_value_errors += 1
            if fpga_peak_normal_max_wht.index != numpy_peak_normal_max_wht.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_normal_max_wht.index={:8} numpy_peak_normal_max_wht.index={:8}".format(fpga_peak_normal_max_wht.index, numpy_peak_normal_max_wht.index))
                peak_index_errors += 1
            if fpga_peak_normal_max_wht.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_normal_max_wht.index={:8} peak_detect_start_count={:8}".format(fpga_peak_normal_max_wht.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_normal_max_wht.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_normal_max_wht.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_normal_max_wht.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_normal_max_wht.count != numpy_peak_normal_max_wht.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_normal_max_wht.count={:8} numpy_peak_normal_max_wht.count={:8}".format(fpga_peak_normal_max_wht.count, numpy_peak_normal_max_wht.count))
                peak_count_errors += 1

            #! White Min
            if fpga_peak_normal_min_wht.value != numpy_peak_normal_min_wht.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_normal_min_wht.value={:+8} numpy_peak_normal_min_wht.value={:+8}".format(fpga_peak_normal_min_wht.value, numpy_peak_normal_min_wht.value))
                peak_value_errors += 1
            if fpga_peak_normal_min_wht.index != numpy_peak_normal_min_wht.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_normal_min_wht.index={:8} numpy_peak_normal_min_wht.index={:8}".format(fpga_peak_normal_min_wht.index, numpy_peak_normal_min_wht.index))
                peak_index_errors += 1
            if fpga_peak_normal_min_wht.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_normal_min_wht.index={:8} peak_detect_start_count={:8}".format(fpga_peak_normal_min_wht.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_normal_min_wht.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_normal_min_wht.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_normal_min_wht.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_normal_min_wht.count != numpy_peak_normal_min_wht.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_normal_min_wht.count={:8} numpy_peak_normal_min_wht.count={:8}".format(fpga_peak_normal_min_wht.count, numpy_peak_normal_min_wht.count))
                peak_count_errors += 1

            #! Blue Max
            if fpga_peak_normal_max_blu.value != numpy_peak_normal_max_blu.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_normal_max_blu.value={:+8} numpy_peak_normal_max_blu.value={:+8}".format(fpga_peak_normal_max_blu.value, numpy_peak_normal_max_blu.value))
                peak_value_errors += 1
            if fpga_peak_normal_max_blu.index != numpy_peak_normal_max_blu.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_normal_max_blu.index={:8} numpy_peak_normal_max_blu.index={:8}".format(fpga_peak_normal_max_blu.index, numpy_peak_normal_max_blu.index))
                peak_index_errors += 1
            if fpga_peak_normal_max_blu.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_normal_max_blu.index={:8} peak_detect_start_count={:8}".format(fpga_peak_normal_max_blu.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_normal_max_blu.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_normal_max_blu.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_normal_max_blu.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_normal_max_blu.count != numpy_peak_normal_max_blu.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_normal_max_blu.count={:8} numpy_peak_normal_max_blu.count={:8}".format(fpga_peak_normal_max_blu.count, numpy_peak_normal_max_blu.count))
                peak_count_errors += 1

            #! Blue Min
            if fpga_peak_normal_min_blu.value != numpy_peak_normal_min_blu.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_normal_min_blu.value={:+8} numpy_peak_normal_min_blu.value={:+8}".format(fpga_peak_normal_min_blu.value, numpy_peak_normal_min_blu.value))
                peak_value_errors += 1
            if fpga_peak_normal_min_blu.index != numpy_peak_normal_min_blu.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_normal_min_blu.index={:8} numpy_peak_normal_min_blu.index={:8}".format(fpga_peak_normal_min_blu.index, numpy_peak_normal_min_blu.index))
                peak_index_errors += 1
            if fpga_peak_normal_min_blu.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_normal_min_blu.index={:8} peak_detect_start_count={:8}".format(fpga_peak_normal_min_blu.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_normal_min_blu.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_normal_min_blu.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_normal_min_blu.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_normal_min_blu.count != numpy_peak_normal_min_blu.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_normal_min_blu.count={:8} numpy_peak_normal_min_blu.count={:8}".format(fpga_peak_normal_min_blu.count, numpy_peak_normal_min_blu.count))
                peak_count_errors += 1

        self.peak_index_errors += peak_index_errors
        self.peak_value_errors += peak_value_errors
        self.peak_count_errors += peak_count_errors

        self.peak_index_errors_total += peak_index_errors
        self.peak_value_errors_total += peak_value_errors
        self.peak_count_errors_total += peak_count_errors

        errors = peak_index_errors + peak_value_errors + peak_count_errors

        return errors

    ##------------------------------------------------------------------------

    def peak_detect_squared(self):
        '''Perform squared peak detection on current phases.'''

        peak_index_errors = 0
        peak_value_errors = 0
        peak_count_errors = 0

        #! Do FPGA first (if minmax registers are not double buffered).
        if self.config.peak_detect_fpga:
            time0 = time.time()
            ret = self.peak_detect_squared_fpga()
            time1 = time.time()

            #! Maintain reference to FPGA peak values.
            fpga_peak_squared_max_red = self.peak_squared_max_red
            fpga_peak_squared_min_red = self.peak_squared_min_red
            fpga_peak_squared_max_wht = self.peak_squared_max_wht
            fpga_peak_squared_min_wht = self.peak_squared_min_wht
            fpga_peak_squared_max_blu = self.peak_squared_max_blu
            fpga_peak_squared_min_blu = self.peak_squared_min_blu

            if self.config.peak_detect_fpga_debug:
                print
                print("DEBUG: Peak Detect FPGA (Squared)")
                print("DEBUG: peak_squared_max_red = {}".format(fpga_peak_squared_max_red))
                print("DEBUG: peak_squared_min_red = {}".format(fpga_peak_squared_min_red))
                print("DEBUG: peak_squared_max_wht = {}".format(fpga_peak_squared_max_wht))
                print("DEBUG: peak_squared_min_wht = {}".format(fpga_peak_squared_min_wht))
                print("DEBUG: peak_squared_max_blu = {}".format(fpga_peak_squared_max_blu))
                print("DEBUG: peak_squared_min_blu = {}".format(fpga_peak_squared_min_blu))
                delta = time1 - time0
                print("DEBUG: duration = {} seconds".format(delta))

        if self.config.peak_detect_numpy:
            time0 = time.time()
            ret = self.peak_detect_squared_numpy()
            time1 = time.time()

            #! Maintain reference to numpy peak values.
            numpy_peak_squared_max_red = self.peak_squared_max_red
            numpy_peak_squared_min_red = self.peak_squared_min_red
            numpy_peak_squared_max_wht = self.peak_squared_max_wht
            numpy_peak_squared_min_wht = self.peak_squared_min_wht
            numpy_peak_squared_max_blu = self.peak_squared_max_blu
            numpy_peak_squared_min_blu = self.peak_squared_min_blu

            if self.config.peak_detect_numpy_debug:
                print
                print("DEBUG: Peak Detect Numpy (Squared)")
                print("DEBUG: peak_squared_max_red = {}".format(numpy_peak_squared_max_red))
                print("DEBUG: peak_squared_min_red = {}".format(numpy_peak_squared_min_red))
                print("DEBUG: peak_squared_max_wht = {}".format(numpy_peak_squared_max_wht))
                print("DEBUG: peak_squared_min_wht = {}".format(numpy_peak_squared_min_wht))
                print("DEBUG: peak_squared_max_blu = {}".format(numpy_peak_squared_max_blu))
                print("DEBUG: peak_squared_min_blu = {}".format(numpy_peak_squared_min_blu))
                delta = time1 - time0
                print("DEBUG: duration = {} seconds".format(delta))

            if fpga_peak_squared_max_red is numpy_peak_squared_max_red:
                print("ERROR: SAME OBJECT: fpga_peak_squared_max_red is numpy_peak_squared_max_red !!")

        if self.config.peak_detect_numpy and self.config.peak_detect_fpga:
            print("\nDEBUG: Peak Detect Check (FPGA v Numpy)")

            #! Red Max
            if fpga_peak_squared_max_red.value != numpy_peak_squared_max_red.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_squared_max_red.value={:+8} numpy_peak_squared_max_red.value={:+8}".format(fpga_peak_squared_max_red.value, numpy_peak_squared_max_red.value))
                peak_value_errors += 1
            if fpga_peak_squared_max_red.index != numpy_peak_squared_max_red.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_squared_max_red.index={:8} numpy_peak_squared_max_red.index={:8}".format(fpga_peak_squared_max_red.index, numpy_peak_squared_max_red.index))
                peak_index_errors += 1
            if fpga_peak_squared_max_red.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_squared_max_red.index={:8} peak_detect_start_count={:8}".format(fpga_peak_squared_max_red.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_squared_max_red.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_squared_max_red.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_squared_max_red.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_squared_max_red.count != numpy_peak_squared_max_red.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_squared_max_red.count={:8} numpy_peak_squared_max_red.count={:8}".format(fpga_peak_squared_max_red.count, numpy_peak_squared_max_red.count))
                peak_count_errors += 1

            #! Red Min
            if fpga_peak_squared_min_red.value != numpy_peak_squared_min_red.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_squared_min_red.value={:+8} numpy_peak_squared_min_red.value={:+8}".format(fpga_peak_squared_min_red.value, numpy_peak_squared_min_red.value))
                peak_value_errors += 1
            if fpga_peak_squared_min_red.index != numpy_peak_squared_min_red.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_squared_min_red.index={:8} numpy_peak_squared_min_red.index={:8}".format(fpga_peak_squared_min_red.index, numpy_peak_squared_min_red.index))
                peak_index_errors += 1
            if fpga_peak_squared_min_red.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_squared_min_red.index={:8} peak_detect_start_count={:8}".format(fpga_peak_squared_min_red.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_squared_min_red.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_squared_min_red.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_squared_min_red.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_squared_min_red.count != numpy_peak_squared_min_red.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_squared_min_red.count={:8} numpy_peak_squared_min_red.count={:8}".format(fpga_peak_squared_min_red.count, numpy_peak_squared_min_red.count))
                peak_count_errors += 1

            #! White Max
            if fpga_peak_squared_max_wht.value != numpy_peak_squared_max_wht.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_squared_max_wht.value={:+8} numpy_peak_squared_max_wht.value={:+8}".format(fpga_peak_squared_max_wht.value, numpy_peak_squared_max_wht.value))
                peak_value_errors += 1
            if fpga_peak_squared_max_wht.index != numpy_peak_squared_max_wht.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_squared_max_wht.index={:8} numpy_peak_squared_max_wht.index={:8}".format(fpga_peak_squared_max_wht.index, numpy_peak_squared_max_wht.index))
                peak_index_errors += 1
            if fpga_peak_squared_max_wht.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_squared_max_wht.index={:8} peak_detect_start_count={:8}".format(fpga_peak_squared_max_wht.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_squared_max_wht.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_squared_max_wht.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_squared_max_wht.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_squared_max_wht.count != numpy_peak_squared_max_wht.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_squared_max_wht.count={:8} numpy_peak_squared_max_wht.count={:8}".format(fpga_peak_squared_max_wht.count, numpy_peak_squared_max_wht.count))
                peak_count_errors += 1

            #! White Min
            if fpga_peak_squared_min_wht.value != numpy_peak_squared_min_wht.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_squared_min_wht.value={:+8} numpy_peak_squared_min_wht.value={:+8}".format(fpga_peak_squared_min_wht.value, numpy_peak_squared_min_wht.value))
                peak_value_errors += 1
            if fpga_peak_squared_min_wht.index != numpy_peak_squared_min_wht.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_squared_min_wht.index={:8} numpy_peak_squared_min_wht.index={:8}".format(fpga_peak_squared_min_wht.index, numpy_peak_squared_min_wht.index))
                peak_index_errors += 1
            if fpga_peak_squared_min_wht.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_squared_min_wht.index={:8} peak_detect_start_count={:8}".format(fpga_peak_squared_min_wht.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_squared_min_wht.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_squared_min_wht.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_squared_min_wht.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_squared_min_wht.count != numpy_peak_squared_min_wht.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_squared_min_wht.count={:8} numpy_peak_squared_min_wht.count={:8}".format(fpga_peak_squared_min_wht.count, numpy_peak_squared_min_wht.count))
                peak_count_errors += 1

            #! Blue Max
            if fpga_peak_squared_max_blu.value != numpy_peak_squared_max_blu.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_squared_max_blu.value={:+8} numpy_peak_squared_max_blu.value={:+8}".format(fpga_peak_squared_max_blu.value, numpy_peak_squared_max_blu.value))
                peak_value_errors += 1
            if fpga_peak_squared_max_blu.index != numpy_peak_squared_max_blu.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_squared_max_blu.index={:8} numpy_peak_squared_max_blu.index={:8}".format(fpga_peak_squared_max_blu.index, numpy_peak_squared_max_blu.index))
                peak_index_errors += 1
            if fpga_peak_squared_max_blu.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_squared_max_blu.index={:8} peak_detect_start_count={:8}".format(fpga_peak_squared_max_blu.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_squared_max_blu.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_squared_max_blu.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_squared_max_blu.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_squared_max_blu.count != numpy_peak_squared_max_blu.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_squared_max_blu.count={:8} numpy_peak_squared_max_blu.count={:8}".format(fpga_peak_squared_max_blu.count, numpy_peak_squared_max_blu.count))
                peak_count_errors += 1

            #! Blue Min
            if fpga_peak_squared_min_blu.value != numpy_peak_squared_min_blu.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_squared_min_blu.value={:+8} numpy_peak_squared_min_blu.value={:+8}".format(fpga_peak_squared_min_blu.value, numpy_peak_squared_min_blu.value))
                peak_value_errors += 1
            if fpga_peak_squared_min_blu.index != numpy_peak_squared_min_blu.index:
                print("ERROR: INDEX NOT EQUAL: fpga_peak_squared_min_blu.index={:8} numpy_peak_squared_min_blu.index={:8}".format(fpga_peak_squared_min_blu.index, numpy_peak_squared_min_blu.index))
                peak_index_errors += 1
            if fpga_peak_squared_min_blu.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:   fpga_peak_squared_min_blu.index={:8} peak_detect_start_count={:8}".format(fpga_peak_squared_min_blu.index, self.peak_detect_start_count))
                peak_index_errors += 1
            if fpga_peak_squared_min_blu.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH:  fpga_peak_squared_min_blu.index={:8} peak_detect_stop_count={:8}".format(fpga_peak_squared_min_blu.index, self.peak_detect_stop_count))
                peak_index_errors += 1
            if fpga_peak_squared_min_blu.count != numpy_peak_squared_min_blu.count:
                print("ERROR: COUNT NOT EQUAL: fpga_peak_squared_min_blu.count={:8} numpy_peak_squared_min_blu.count={:8}".format(fpga_peak_squared_min_blu.count, numpy_peak_squared_min_blu.count))
                peak_count_errors += 1

        self.peak_index_errors += peak_index_errors
        self.peak_value_errors += peak_value_errors
        self.peak_count_errors += peak_count_errors

        self.peak_index_errors_total += peak_index_errors
        self.peak_value_errors_total += peak_value_errors
        self.peak_count_errors_total += peak_count_errors

        errors = peak_index_errors + peak_value_errors + peak_count_errors

        return errors

    ##------------------------------------------------------------------------

    def peak_detect_sanity_check(self):
        '''Perform sanity check on peak detection objects.'''

        logging.debug("trace:{}".format( method_name() ) )

        errors = 0

        #!
        #! red phase
        #!
        test_max = abs(self.peak_normal_max_red.voltage) > abs(self.peak_normal_min_red.voltage)
        test_min = abs(self.peak_normal_max_red.voltage) < abs(self.peak_normal_min_red.voltage)
        test_max |= not (test_max or test_min) and self.peak_normal_max_red.time_offset < self.peak_normal_min_red.time_offset

        if test_max:
            v2, sq = (self.peak_normal_max_red.voltage ** 2), self.peak_squared_max_red.voltage
            if v2 != sq:
                logging.error("peak_normal_max_red.voltage^2={} does not equal peak_squared_max_red.voltage={}".format(v2, sq))
                errors += 1
            t1, t2 = self.peak_normal_max_red.time_offset, self.peak_squared_max_red.time_offset
            if t2 != t1:
                logging.error("peak_normal_max_red.time_offset={} does not equal peak_squared_max_red.time_offset={}".format(t2, t1))
                errors += 1
        else:
            v2, sq = (self.peak_normal_min_red.voltage ** 2), self.peak_squared_max_red.voltage
            if v2 != sq:
                logging.error("peak_normal_min_red.voltage^2={} does not equal peak_squared_max_red.voltage={}".format(v2, sq))
                errors += 1
            t1, t2 = self.peak_normal_min_red.time_offset, self.peak_squared_max_red.time_offset
            if t2 != t1:
                logging.error("peak_normal_min_red.time_offset={} does not equal peak_squared_max_red.time_offset={}".format(t2, t1))
                errors += 1

        #!
        #! white phase
        #!
        test_max = abs(self.peak_normal_max_wht.voltage) > abs(self.peak_normal_min_wht.voltage)
        test_min = abs(self.peak_normal_max_wht.voltage) < abs(self.peak_normal_min_wht.voltage)
        test_max |= not (test_max or test_min) and self.peak_normal_max_wht.time_offset < self.peak_normal_min_wht.time_offset

        if test_max:
            v2, sq = (self.peak_normal_max_wht.voltage ** 2), self.peak_squared_max_wht.voltage
            if v2 != sq:
                logging.error("peak_normal_max_wht.voltage^2={} does not equal peak_squared_max_wht.voltage={}".format(v2, sq))
                errors += 1
            t1, t2 = self.peak_normal_max_wht.time_offset, self.peak_squared_max_wht.time_offset
            if t2 != t1:
                logging.error("peak_normal_max_wht.time_offset={} does not equal peak_squared_max_wht.time_offset={}".format(t2, t1))
                errors += 1
        else:
            v2, sq = (self.peak_normal_min_wht.voltage ** 2), self.peak_squared_max_wht.voltage
            if v2 != sq:
                logging.error("peak_normal_min_wht.voltage^2={} does not equal peak_squared_max_wht.voltage={}".format(v2, sq))
                errors += 1
            t1, t2 = self.peak_normal_min_wht.time_offset, self.peak_squared_max_wht.time_offset
            if t2 != t1:
                logging.error("peak_normal_min_wht.time_offset={} does not equal peak_squared_max_wht.time_offset={}".format(t2, t1))
                errors += 1

        #!
        #! blu phase
        #!
        test_max = abs(self.peak_normal_max_blu.voltage) > abs(self.peak_normal_min_blu.voltage)
        test_min = abs(self.peak_normal_max_blu.voltage) < abs(self.peak_normal_min_blu.voltage)
        test_max |= not (test_max or test_min) and self.peak_normal_max_blu.time_offset < self.peak_normal_min_blu.time_offset

        if test_max:
            v2, sq = (self.peak_normal_max_blu.voltage ** 2), self.peak_squared_max_blu.voltage
            if v2 != sq:
                logging.error("peak_normal_max_blu.voltage^2={} does not equal peak_squared_max_blu.voltage={}".format(v2, sq))
                errors += 1
            t1, t2 = self.peak_normal_max_blu.time_offset, self.peak_squared_max_blu.time_offset
            if t2 != t1:
                logging.error("peak_normal_max_blu.time_offset={} does not equal peak_squared_max_blu.time_offset={}".format(t2, t1))
                errors += 1
        else:
            v2, sq = (self.peak_normal_min_blu.voltage ** 2), self.peak_squared_max_blu.voltage
            if v2 != sq:
                logging.error("peak_normal_min_blu.voltage^2={} does not equal peak_squared_max_blu.voltage={}".format(v2, sq))
                errors += 1
            t1, t2 = self.peak_normal_min_blu.time_offset, self.peak_squared_max_blu.time_offset
            if t2 != t1:
                logging.error("peak_normal_min_blu.time_offset={} does not equal peak_squared_max_blu.time_offset={}".format(t2, t1))
                errors += 1

        return errors

    ##------------------------------------------------------------------------

    def peak_detect(self):
        '''Perform peak detection on current phases.'''

        errors = 0

        #!
        #! Normal Peak Detection.
        #!
        if self.config.peak_detect_normal:
            errors += self.peak_detect_normal()

        #!
        #! Squared Peak Detection.
        #!
        if self.config.peak_detect_squared:
            errors += self.peak_detect_squared()

        return errors

    ##------------------------------------------------------------------------

    def phase_array_around_index(self, phase, index, size_half):
        if index < size_half:
            beg = 0
            end = size_half + size_half
        elif index > (len(phase) - size_half):
            end = len(phase)
            beg = end - size_half - size_half
        else:
            beg = index - size_half
            end = index + size_half

        if 0:
            print("DEBUG: phase_array_around_index: index={:8}".format(index))
            print("DEBUG: phase_array_around_index: size_half={}".format(size_half))
            print("DEBUG: phase_array_around_index: beg={:8}".format(beg))
            print("DEBUG: phase_array_around_index: end={:8}".format(end))

        return phase[beg:end]

    ##------------------------------------------------------------------------

    def tf_map_calculate(self, phase, index):
        #fft_size_half = self.config.fft_size_half
        fft_phase = self.phase_array_around_index(phase, index, size_half=self.config.fft_size_half)
        tstart = 0
        tstop = len(fft_phase)

        #fft_time = np.arange(start=tstart, stop=tstop, step=1, dtype=tf_mapping.DTYPE) / self.config.sample_frequency
        fft_time = np.arange(start=tstart, stop=tstop, step=1, dtype=tf_mapping.DTYPE) * self.time_resolution
        #print("DEBUG: fft_time = {!r}".format(fft_time))

        #fft_phase = phase[beg:end] * self.voltage_factor
        fft_phase = fft_phase * self.voltage_factor
        #print("DEBUG: fft_phase = {!r}".format(fft_phase))

        tf_map = tf_map_calculate(tdata=fft_time, ydata=fft_phase, sample_freq=self.config.sample_frequency, fft_length=0)

        return tf_map

    ##------------------------------------------------------------------------

    def running_led_off(self):
        ind.running_led_off(dev_hand=self.dev_hand)

    def running_led_on(self):
        ind.running_led_on(dev_hand=self.dev_hand)

    def running_led_toggle(self):
        ind.running_led_toggle(dev_hand=self.dev_hand)

    ##------------------------------------------------------------------------

    def main_loop(self):
        '''Run main loop of EFD_App.'''

        self.gps_poller.start()

        #self.ws_thread.init()
        self.ws_thread.start()

        self.cloud_thread.start()

        #! Start the analog acquisition.
        if self.config.capture_mode == 'manual':
            print("Starting Analog Data Acquisition -- Manual Trigger")
        else:
            print("Starting Analog Data Acquisition -- Auto PPS Trigger")
        self.adc_start()

        ## Read back ADC Offset register to see if it was stored correctly.
#         adc_offset = ind.adc_offset_get(dev_hand=self.dev_hand)
#         print("read back: adc_offset = {} ({})".format(adc_offset, hex(adc_offset)))
#         if adc_offset != self.config.adc_offset:
#             cao = self.config.adc_offset
#             print("ERROR: adc_offset does not match config setting {} ({})".format(cao, hex(cao)))

        capture_count = self.config.capture_count
        self.adc_clock_count_now = 0
        self.adc_clock_count_min = 1000*1000*1000  ## a number > 250MHz + 50ppm
        self.adc_clock_count_max = 0
        self.adc_clock_count_valid_delta = int(self.config.sample_frequency * 0.01)
        self.adc_clock_count_valid_min = self.config.sample_frequency - self.adc_clock_count_valid_delta
        self.adc_clock_count_valid_max = self.config.sample_frequency + self.adc_clock_count_valid_delta

        self.buffer_errors_total = 0

        self.peak_index_errors = 0
        self.peak_value_errors = 0
        self.peak_count_errors = 0

        self.peak_index_errors_total = 0
        self.peak_value_errors_total = 0
        self.peak_count_errors_total = 0
        self.peak_errors_total = 0

        self.capture_trigger_count = 0

        ## main sampling loop.
        while True:
            if self.config.show_capture_debug:
                print("\n========================================")

            sys.stdout.flush()

            self.running_led_off()

            data_ok = self.get_sample_data()    #! wait for data to be available, with timeout.

            self.running_led_on()

            #!
            #! use next capture buffer for ping-pong
            #! sets `self.bank` to the current bank to process
            #! and `self.next_bank` to the next bank to fill.
            #!
            self.adc_capture_buffer_next()

            #!
            #! Get time that `selector` returns and determine the capture time.
            #!
            select_datetime_utc = arrow.utcnow()
            select_datetime_local = select_datetime_utc.to(self.config.timezone)

            if data_ok:
                self.capture_trigger_count += 1

            #!
            #! Retrieve info from FPGA registers.
            #!
            capture_info_lst  = ind.adc_capture_info_list_get(dev_hand=self.dev_hand)
            capture_info_prev = capture_info_lst[self.prev_bank]
            capture_info      = capture_info_lst[self.bank]
            logging.debug("")
            logging.debug("capture_info_prev = {!r}\n".format(capture_info_prev))
            logging.debug("capture_info      = {!r}\n".format(capture_info))

            self.maxmin_normal      = capture_info.maxmin_normal
            self.maxmin_squared     = capture_info.maxmin_squared
            adc_clock_count_per_pps = capture_info.adc_clock_count_per_pps

            #!
            #! convert fpga capture time to Arrow datetime object.
            #!
            timestamp = float(capture_info.irq_time)
            irq_capture_datetime_utc = arrow.get(timestamp)

            #!
            #! set the capture time (truncate to seconds).
            #!
            self.set_capture_datetime(irq_capture_datetime_utc.floor('second'))

            #! Clear terminal screen by sending special chars (ansi sequence?).
            #print("\033c")

            if self.config.show_capture_debug:
                print
                print("Total Capture Trigger Count = {}".format(self.capture_trigger_count))
                print("irq_capture_datetime_utc = {}".format(irq_capture_datetime_utc))
                print("sel_capture_datetime_utc = {}".format(select_datetime_utc))
                print("app_capture_datetime_utc = {}".format(self.capture_datetime_utc))

            if self.config.peak_detect_fpga_debug:
                print("DEBUG: Peak Detect Normal FPGA:  maxmin = {}\n".format(self.maxmin_normal))
                print("DEBUG: Peak Detect Squared FPGA: maxmin = {}\n".format(self.maxmin_squared))
                print("DEBUG: adc_clock_count_per_pps = {:10} (0x{:08X})\n".format(adc_clock_count_per_pps, adc_clock_count_per_pps))
                #print("DEBUG: capture_info_0 = {}\n".format(capture_info_0))
                #print("DEBUG: capture_info_1 = {}\n".format(capture_info_1))
                print("DEBUG: capture_info = {}\n".format(capture_info))

            if not data_ok:
                continue

            #!
            #! Show capture data / phase arrays
            #!
            if self.config.show_capture_buffers:
                self.show_all_capture_buffers()

            if self.config.show_phase_arrays:
                #self.show_phase_arrays(phase_index=0)
                #self.show_phase_arrays(phase_index=1)
                self.show_phase_arrays()

            #! save phase data to disk.
            if self.config.save_capture_data:
                loc_dt = self.capture_datetime_local
                loc_dt_str = loc_dt.format('YYYYMMDDTHHmmssZ')
                #! red
                filename = 'sampledata-{}-red'.format(loc_dt_str)
                np.save(filename, self.red_phase)
                #! white
                filename = 'sampledata-{}-wht'.format(loc_dt_str)
                np.save(filename, self.wht_phase)
                #! blue
                filename = 'sampledata-{}-blu'.format(loc_dt_str)
                np.save(filename, self.blu_phase)

            #!
            #! Sanity check select capture time versus irq capture time.
            #!
            td = select_datetime_utc - irq_capture_datetime_utc
            processing_latency = td.total_seconds()
            logging.info("processing_latency={}, irq_capture_datetime_utc={}, select_datetime_utc={},".format(processing_latency, irq_capture_datetime_utc, select_datetime_utc))
            if processing_latency > 0.200:
                logging.warning("processing_latency={} exceeds 200ms, irq_capture_datetime_utc={}, select_datetime_utc={},".format(processing_latency, irq_capture_datetime_utc, select_datetime_utc))

            #!
            #! Sanity check current bank is actually the latest/newest capture.
            #!
            irq_times = [ float(ci.irq_time) for ci in capture_info_lst ]
            newest_irq_timestamp = max(irq_times)
            newest_irq_index = irq_times.index(newest_irq_timestamp)
            newest_irq_time = capture_info_lst[newest_irq_index].irq_time
            if capture_info.irq_time != newest_irq_time:
                logging.error("capture_info.irq_time={} does not equal newest_irq_time={}".format(capture_info.irq_time, newest_irq_time))

            #!
            #! Sanity check select capture time versus irq capture time.
            #!
            td = select_datetime_utc - irq_capture_datetime_utc
            processing_latency = td.total_seconds()
            if processing_latency > 0.200:
                logging.warning("processing_latency={}, irq_capture_datetime_utc={}, select_datetime_utc={},".format(processing_latency, irq_capture_datetime_utc, select_datetime_utc))

            #!
            #! Skip processing if system date is not set properly (year <= 2015).
            #!
            if select_datetime_utc.year <= 2015:
                print("Data Captured: Skip processing.  year <= 2015.")
                continue

            buffer_errors = 0
            self.peak_index_errors = 0
            self.peak_value_errors = 0
            self.peak_count_errors = 0

            if self.config.initialise_capture_memory:
                self.adc_capture_array_tests()

            if self.config.peak_detect:
                peak_errors = self.peak_detect()
                self.peak_errors_total += peak_errors

                if self.config.peak_detect_debug:
                    print("DEBUG: Peak Detect")
                    print
                    print("Peak Detect Index Errors = {}".format(self.peak_index_errors))
                    print("Peak Detect Value Errors = {}".format(self.peak_value_errors))
                    print("Peak Detect Count Errors = {}".format(self.peak_count_errors))
                    print("Peak Detect Errors = {}".format(peak_errors))
                    print
                    print("Total Peak Detect Index Errors = {}".format(self.peak_index_errors_total))
                    print("Total Peak Detect Value Errors = {}".format(self.peak_value_errors_total))
                    print("Total Peak Detect Count Errors = {}".format(self.peak_count_errors_total))
                    print("Total Peak Detect Errors = {}".format(self.peak_errors_total))

                sanity_check_errors = self.peak_detect_sanity_check()
                if sanity_check_errors:
                    msg = '\n'.join( [
                        "Sanity Check Error !!\n",
                        "capture_info_prev = {!r}\n".format(capture_info_prev),
                        "capture_info      = {!r}\n".format(capture_info),
                        ] )
                    logging.error(msg)

            if self.config.tf_mapping:
                #!
                #! perform TF Mapping calculations for all phases.
                #!
                try:
                    self.tf_map_red = self.tf_map_calculate(phase=self.red_phase, index=self.peak_normal_max_red.index)
                except Exception:
                    self.tf_map_red = tf_mapping.Null_TF_Map
                    print(traceback.format_exc())

                try:
                    self.tf_map_wht = self.tf_map_calculate(phase=self.wht_phase, index=self.peak_normal_max_wht.index)
                except Exception:
                    self.tf_map_wht = tf_mapping.Null_TF_Map
                    print(traceback.format_exc())

                try:
                    self.tf_map_blu = self.tf_map_calculate(phase=self.blu_phase, index=self.peak_normal_max_blu.index)
                except Exception:
                    self.tf_map_blu = tf_mapping.Null_TF_Map
                    print(traceback.format_exc())

                if self.config.tf_mapping_debug:
                    print("DEBUG: TF Mapping")
                    print("DEBUG: tf_map_red={}".format(self.tf_map_red))
                    print("DEBUG: tf_map_wht={}".format(self.tf_map_wht))
                    print("DEBUG: tf_map_blu={}".format(self.tf_map_blu))
                    print

            #!
            #! Peak Threshold Detection.
            #!
            trigger_phase = None
            trigger_alert = '-'

            max_volt = max( (self.peak_normal_max_red.voltage, self.peak_normal_max_wht.voltage, self.peak_normal_max_blu.voltage) )

            if max_volt >= self.config.pd_event_trigger_voltage:
                if self.config.pd_event_reporting_interval:
                    delta_dt = self.capture_datetime_utc - self.last_pd_event_report_datetime_utc
                    if delta_dt.total_seconds() >= self.config.pd_event_reporting_interval:
                        if self.peak_normal_max_red.voltage == max_volt:
                            trigger_phase = self.red_phase
                            trigger_alert = 'R'
                        elif self.peak_normal_max_wht.voltage == max_volt:
                            trigger_phase = self.wht_phase
                            trigger_alert = 'W'
                        elif self.peak_normal_max_blu.voltage == max_volt:
                            trigger_phase = self.blu_phase
                            trigger_alert = 'B'

            #!
            #! Update measurements dictionary.
            #!

            #! Modify utc and local datetimes to output Excel & Matlab compatible ISO datetime strings.
#             self.measurements['datetime_utc']               = self.capture_datetime_utc.isoformat(sep=' ')
#             self.measurements['datetime_local']             = self.capture_datetime_local.isoformat(sep=' ')
            self.measurements['datetime_utc']               = self.capture_datetime_utc
            self.measurements['datetime_local']             = self.capture_datetime_local

            #! FIXME: should use a class to encapsulate measurements for each phase (red, white, blue).
            phase = self.red_phase
            self.measurements['max_volt_red']               = self.peak_normal_max_red.voltage
            self.measurements['min_volt_red']               = self.peak_normal_min_red.voltage
            self.measurements['max_time_offset_red']        = self.peak_normal_max_red.time_offset
            self.measurements['min_time_offset_red']        = self.peak_normal_min_red.time_offset
            self.measurements['max_count_red']              = self.peak_normal_max_red.count
            self.measurements['min_count_red']              = self.peak_normal_min_red.count
            self.measurements['t2_red']                     = self.tf_map_red.T2
            self.measurements['w2_red']                     = self.tf_map_red.F2
            self.measurements['max_volt_sq_red']            = sign_adjusted_magnitude(magnitude=self.peak_squared_max_red.voltage, value=phase[self.peak_squared_max_red.index])
            self.measurements['min_volt_sq_red']            = sign_adjusted_magnitude(magnitude=self.peak_squared_min_red.voltage, value=phase[self.peak_squared_min_red.index])
#             self.measurements['max_volt_sq_red']            = sign_adjusted_magnitude(magnitude=self.peak_squared_max_red.voltage, value=phase[self.peak_squared_max_red.index])
#             self.measurements['min_volt_sq_red']            = sign_adjusted_magnitude(magnitude=self.peak_squared_min_red.voltage, value=phase[self.peak_squared_min_red.index])
            self.measurements['max_time_offset_sq_red']     = self.peak_squared_max_red.time_offset
            self.measurements['min_time_offset_sq_red']     = self.peak_squared_min_red.time_offset
            self.measurements['max_count_sq_red']           = self.peak_squared_max_red.count
            self.measurements['min_count_sq_red']           = self.peak_squared_min_red.count

            #! FIXME: should use a class to encapsulate measumenets for each phase (red, white, blue).
            phase = self.wht_phase
            self.measurements['max_volt_wht']               = self.peak_normal_max_wht.voltage
            self.measurements['min_volt_wht']               = self.peak_normal_min_wht.voltage
            self.measurements['max_time_offset_wht']        = self.peak_normal_max_wht.time_offset
            self.measurements['min_time_offset_wht']        = self.peak_normal_min_wht.time_offset
            self.measurements['max_count_wht']              = self.peak_normal_max_wht.count
            self.measurements['min_count_wht']              = self.peak_normal_min_wht.count
            self.measurements['t2_wht']                     = self.tf_map_wht.T2
            self.measurements['w2_wht']                     = self.tf_map_wht.F2
            self.measurements['max_volt_sq_wht']            = sign_adjusted_magnitude(magnitude=self.peak_squared_max_wht.voltage, value=phase[self.peak_squared_max_wht.index])
            self.measurements['min_volt_sq_wht']            = sign_adjusted_magnitude(magnitude=self.peak_squared_min_wht.voltage, value=phase[self.peak_squared_min_wht.index])
#             self.measurements['max_volt_sq_wht']            = sign_adjusted_magnitude(magnitude=self.peak_squared_max_wht.voltage, value=phase[self.peak_squared_max_wht.index])
#             self.measurements['min_volt_sq_wht']            = sign_adjusted_magnitude(magnitude=self.peak_squared_min_wht.voltage, value=phase[self.peak_squared_min_wht.index])
            self.measurements['max_time_offset_sq_wht']     = self.peak_squared_max_wht.time_offset
            self.measurements['min_time_offset_sq_wht']     = self.peak_squared_min_wht.time_offset
            self.measurements['max_count_sq_wht']           = self.peak_squared_max_wht.count
            self.measurements['min_count_sq_wht']           = self.peak_squared_min_wht.count

            #! FIXME: should use a class to encapsulate measumenets for each phase (red, white, blue).
            phase = self.blu_phase
            self.measurements['max_volt_blu']               = self.peak_normal_max_blu.voltage
            self.measurements['min_volt_blu']               = self.peak_normal_min_blu.voltage
            self.measurements['max_time_offset_blu']        = self.peak_normal_max_blu.time_offset
            self.measurements['min_time_offset_blu']        = self.peak_normal_min_blu.time_offset
            self.measurements['max_count_blu']              = self.peak_normal_max_blu.count
            self.measurements['min_count_blu']              = self.peak_normal_min_blu.count
            self.measurements['t2_blu']                     = self.tf_map_blu.T2
            self.measurements['w2_blu']                     = self.tf_map_blu.F2
            self.measurements['max_volt_sq_blu']            = sign_adjusted_magnitude(magnitude=self.peak_squared_max_blu.voltage, value=phase[self.peak_squared_max_blu.index])
            self.measurements['min_volt_sq_blu']            = sign_adjusted_magnitude(magnitude=self.peak_squared_min_blu.voltage, value=phase[self.peak_squared_min_blu.index])
#             self.measurements['max_volt_sq_blu']            = sign_adjusted_magnitude(magnitude=self.peak_squared_max_blu.voltage, value=phase[self.peak_squared_max_blu.index])
#             self.measurements['min_volt_sq_blu']            = sign_adjusted_magnitude(magnitude=self.peak_squared_min_blu.voltage, value=phase[self.peak_squared_min_blu.index])
            self.measurements['max_time_offset_sq_blu']     = self.peak_squared_max_blu.time_offset
            self.measurements['min_time_offset_sq_blu']     = self.peak_squared_min_blu.time_offset
            self.measurements['max_count_sq_blu']           = self.peak_squared_max_blu.count
            self.measurements['min_count_sq_blu']           = self.peak_squared_min_blu.count

            self.measurements['temperature']                = self.ws_info.temperature
            self.measurements['humidity']                   = self.ws_info.humidity
            self.measurements['rain_intensity']             = self.ws_info.rain_intensity
            self.measurements['alert']                      = trigger_alert
            self.measurements['adc_clock_count_per_pps']    = adc_clock_count_per_pps

            #! FIXME: Temporary fields for testing of new web server being developed by IND.
            if self.config.append_gps_data_to_measurements_log:
                self.measurements['gps_latitude']           = self.gpsd.fix.latitude
                self.measurements['gps_longitude']          = self.gpsd.fix.longitude
                self.measurements['battery_volt']           = "{:0.1f}".format(self.sensors.battery_voltage())
                self.measurements['solar_volt']             = "{:0.1f}".format(self.sensors.solar_voltage())
                self.measurements['box_temperature']        = "{:0.1f}".format(self.sensors.box_temperature())

            #!
            #! push measurements to cloud queue for logging, posting, etc.
            #!
            try:
                self.cloud_queue.put(item=self.measurements, block=False)
            except queue.Full:
                print("EXCEPTION: could not queue measurement data to cloud thread. qsize={}".format(self.cloud_queue.qsize()))
                sys.stdout.flush()

            #! FIXME: this could be done in the cloud thread !!
            #! Save sample data and send SMS if a trigger event detected.
            if trigger_phase is not None:
                print("PD Event Detected @ {} UTC, {} LOCAL", self.capture_datetime_utc, self.capture_datetime_local)
                self.save_data(phase=trigger_phase)
                self.send_sms()
                self.last_pd_event_report_datetime_utc = self.capture_datetime_utc

                if self.config.show_phase_arrays_on_pd_event:
                    self.show_phase_arrays()
                    #self.show_all_capture_buffers()

            #! Get time when "real processing" has completed.
            end_process_datetime_utc = arrow.utcnow()
            end_process_datetime_local = end_process_datetime_utc.to(self.config.timezone)

            process_duration = end_process_datetime_utc - select_datetime_utc

            if self.config.show_capture_debug:
                print
                print("irq_capture_datetime_utc = {}".format(irq_capture_datetime_utc))
                print("sel_capture_datetime_utc = {}".format(select_datetime_utc))
                print("app_capture_datetime_utc = {}".format(self.capture_datetime_utc))
                print("end_process_datetime_utc = {}".format(end_process_datetime_utc))
                print("process_duration = {} seconds".format(process_duration.total_seconds()))

            if self.config.show_measurements:
                print('\n----------------------------------------')
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
                print('peak_normal_max_red : {}'.format(self.peak_normal_max_red))
                print('peak_normal_min_red : {}'.format(self.peak_normal_min_red))
                print
                print('peak_normal_max_wht : {}'.format(self.peak_normal_max_wht))
                print('peak_normal_min_wht : {}'.format(self.peak_normal_min_wht))
                print
                print('peak_normal_max_blu : {}'.format(self.peak_normal_max_blu))
                print('peak_normal_min_blu : {}'.format(self.peak_normal_min_blu))
                print
                print('peak_squared_max_red : {}'.format(self.peak_squared_max_red))
                print('peak_squared_min_red : {}'.format(self.peak_squared_min_red))
                print
                print('peak_squared_max_wht : {}'.format(self.peak_squared_max_wht))
                print('peak_squared_min_wht : {}'.format(self.peak_squared_min_wht))
                print
                print('peak_squared_max_blu : {}'.format(self.peak_squared_max_blu))
                print('peak_squared_min_blu : {}'.format(self.peak_squared_min_blu))
                print
                print('temperature    : {}'.format(self.ws_info.temperature))
                print('humidity       : {}'.format(self.ws_info.humidity))
                print('rain intensity : {}'.format(self.ws_info.rain_intensity))
                print
                print('trigger_alert : {}'.format(trigger_alert))
                print
                print('adc_clock_count_per_pps : {}'.format(adc_clock_count_per_pps))
                print
                print('tf_map_red : {!r}'.format(self.tf_map_red))
                print('tf_map_wht : {!r}'.format(self.tf_map_wht))
                print('tf_map_blu : {!r}'.format(self.tf_map_blu))
                print

                #! FIXME: Temporary fields for testing of new web server being developed by IND.
                if self.config.append_gps_data_to_measurements_log:
                    #print 'latitude    ' , gpsd.fix.latitude
                    #print 'longitude   ' , gpsd.fix.longitude
                    #print 'time utc    ' , gpsd.utc,' + ', gpsd.fix.time
                    print('gps_latitude : {}'.format(self.measurements['gps_latitude']))
                    print('gps_longitude : {}'.format(self.measurements['gps_longitude']))
                    print('battery_volt : {}'.format(self.measurements['battery_volt']))
                    print('solar_volt : {}'.format(self.measurements['solar_volt']))
                    print('box_temperature : {}'.format(self.measurements['box_temperature']))

            #!
            #! Show capture data / phase arrays
            #!
            #self.show_phase_arrays(phase_index=0)
            #self.show_phase_arrays(phase_index=1)

            if self.config.show_phase_arrays:
                self.show_phase_arrays()

            if self.config.show_capture_buffers:
                self.show_all_capture_buffers()

            #! FIXME: DEBUG: exit after one cycle.
            #break

#############################################################################!

def argh_main():
    """Main entry if running this module directly."""

    config = Config()

    #! override defaults with settings in user settings file.
    config.read_settings_file()

    #!------------------------------------------------------------------------

    def app_main(capture_count          = config.capture_count,
                 capture_mode           = config.capture_mode,
                 pps_delay              = config.pps_delay,
                 adc_polarity           = config.adc_polarity.name.lower(),
                 adc_offset             = config.adc_offset,
                 peak_detect_mode       = config.peak_detect_mode.name.lower(),
                 peak_detect_normal     = config.peak_detect_normal,
                 peak_detect_squared    = config.peak_detect_squared,
                 fft_size               = config.fft_size,
                 web_server             = config.web_server,
                 show_measurements      = config.show_measurements,
                 show_capture_buffers   = config.show_capture_buffers,
                 show_capture_debug     = config.show_capture_debug,
                 append_gps_data        = config.append_gps_data_to_measurements_log,
                 save_capture_data      = config.save_capture_data,
                 test_mode              = config.test_mode.name.lower(),
                 debug                  = False,
                 logging_level          = config.logging_level,
                 ):

        print(__name__)

        #! override user settings file if command line argument differs.

        if capture_count != config.capture_count:
            config.set_capture_count(capture_count)

        if capture_mode != config.capture_mode:
            config.set_capture_mode(capture_mode)

        if pps_delay != config.pps_delay:
            config.set_pps_delay(pps_delay)

        if adc_polarity != config.adc_polarity.name.lower():
            config.set_adc_polarity(adc_polarity)

        if adc_offset != config.adc_offset:
            config.set_adc_offset(adc_offset)

        if peak_detect_mode != config.peak_detect_mode.name.lower():
            config.set_peak_detect_mode(peak_detect_mode)

        if peak_detect_normal != config.peak_detect_normal:
            config.set_peak_detect_normal(peak_detect_normal)

        if peak_detect_squared != config.peak_detect_squared:
            config.set_peak_detect_squared(peak_detect_squared)

        if fft_size != config.fft_size:
            config.set_fft_size(fft_size)

        if web_server != config.web_server:
            config.set_web_server(web_server)

        if show_measurements != config.show_measurements:
            config.set_show_measurements(show_measurements)

        if show_capture_buffers != config.show_capture_buffers:
            config.set_show_capture_buffers(show_capture_buffers)

        if show_capture_debug != config.show_capture_debug:
            config.set_show_capture_debug(show_capture_debug)

        if append_gps_data != config.append_gps_data_to_measurements_log:
            config.set_append_gps_data(append_gps_data)

        if save_capture_data != config.save_capture_data:
            config.set_save_capture_data(save_capture_data)

        if test_mode != config.test_mode.name.lower():
            config.set_test_mode(test_mode)

        if debug:
            config.peak_detect_numpy_debug  = True
            config.peak_detect_fpga_debug   = True
            config.peak_detect_debug        = True
            logging_level                   = 'debug'

        if logging_level != config.logging_level:
            config.set_logging_level(logging_level)

        config.show_all()

        #!--------------------------------------------------------------------

        app = EFD_App(config=config)
        app.init()
        try:
            app.main_loop()
        except (KeyboardInterrupt):
            #! ctrl+c key press.
            print("KeyboardInterrupt -- exiting ...")
        except (SystemExit):
            #! sys.exit() called.
            print("SystemExit -- exiting ...")
        except (Exception) as exc:
            #! An unhandled exception !!
            print(traceback.format_exc())
            print("Exception: {}".format(exc.message))
            print("Unhandled Exception -- exiting...")
        finally:
            print("Cleaning up.")
            app.cleanup()
            print("Done.  Exiting.")

        #!--------------------------------------------------------------------

    argh.dispatch_command(app_main)

#!============================================================================

if __name__ == "__main__":
    argh_main()
