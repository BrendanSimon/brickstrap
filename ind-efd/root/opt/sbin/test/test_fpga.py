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
import os
import numpy as np
import math
import time
import arrow
import selectors2 as selectors
import traceback

from collections import namedtuple

sys.path.append('..')

from efd_config import Config, PeakDetectMode, TestMode, ADC_Polarity
from efd_app import Peak, PEAK_DEFAULT
from efd_app import Sample, sample_min, sample_max

import ind

##============================================================================

class Read_Capture_Buffers_App(object):
    '''The IND Early Fault Detection application class.'''

    def __init__(self, config):
        '''Initialise Read_Capture_Buffers_App class.'''
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
        self.adc_capture_buffer_offset = [ 0 ] * self.config.bank_count

        self.capture_datetime_utc = None
        self.capture_datetime_local = None

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
        if 1:
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
        if 1:
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
        '''Initialise Read_Capture_Buffers_App application.'''
        #print(self.__doc__)

        print("INFO: Python System Version = {}".format(sys.version))

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

        fpga_version = self.fpga_version_get()
        print("IND FPGA Version = {}.{}".format(fpga_version.major, fpga_version.minor))

        self.adc_stop()

        self.adc_capture_array = self.adc_numpy_array()
        if self.config.initialise_capture_memory:
            print("Initialise capture array : filling with 0x6141")

            time0 = time.time()
            self.adc_capture_array.fill(self.config.initialise_capture_memory_magic_value)
            delta = time.time() - time0
            print("DEBUG: time to initialise capture array = {} seconds".format(delta))

            time0 = time.time()
            self.adc_capture_array.fill(self.config.initialise_capture_memory_magic_value)
            delta = time.time() - time0
            print("DEBUG: time to initialise capture array = {} seconds".format(delta))

            time0 = time.time()
            self.adc_capture_array.fill(self.config.initialise_capture_memory_magic_value)
            delta = time.time() - time0
            print("DEBUG: time to initialise capture array = {} seconds".format(delta))

            time0 = time.time()
            temp1 = np.copy(self.adc_capture_array)
            delta = time.time() - time0
            print("DEBUG: time to copy capture array = {} seconds".format(delta))
            time0 = time.time()
            same = np.array_equal(temp1, self.adc_capture_array)
            delta = time.time() - time0
            print("DEBUG: same = {} , time compare = {} seconds".format(same, delta))

            time0 = time.time()
            temp2 = np.copy(self.adc_capture_array)
            delta = time.time() - time0
            print("DEBUG: time to copy capture array = {} seconds".format(delta))
            time0 = time.time()
            same = np.array_equal(temp2, self.adc_capture_array)
            delta = time.time() - time0
            print("DEBUG: same = {} , time compare = {} seconds".format(same, delta))

            time0 = time.time()
            temp3 = np.copy(self.adc_capture_array)
            delta = time.time() - time0
            print("DEBUG: time to copy capture array = {} seconds".format(delta))
            time0 = time.time()
            same = np.array_equal(temp3, self.adc_capture_array)
            delta = time.time() - time0
            print("DEBUG: same = {} , time compare = {} seconds".format(same, delta))

            time0 = time.time()
            temp11 = np.copy(temp1)
            delta = time.time() - time0
            print("DEBUG: time to copy copy of capture array = {} seconds".format(delta))
            time0 = time.time()
            same = np.array_equal(temp11, temp1)
            delta = time.time() - time0
            print("DEBUG: same = {} , time compare = {} seconds".format(same, delta))

            time0 = time.time()
            temp12 = np.copy(temp2)
            delta = time.time() - time0
            print("DEBUG: time to copy copy of capture array = {} seconds".format(delta))
            time0 = time.time()
            same = np.array_equal(temp12, temp2)
            delta = time.time() - time0
            print("DEBUG: same = {} , time compare = {} seconds".format(same, delta))

            time0 = time.time()
            temp13 = np.copy(temp3)
            delta = time.time() - time0
            print("DEBUG: time to copy copy of capture array = {} seconds".format(delta))
            time0 = time.time()
            same = np.array_equal(temp13, temp3)
            delta = time.time() - time0
            print("DEBUG: same = {} , time compare = {} seconds".format(same, delta))

#         if self.config.show_intialised_capture_buffers:
        if self.config.show_capture_buffers:
            self.show_all_capture_buffers()

        self.init_phase_arrays()
#         if self.config.show_intialised_phase_arrays:
        if self.config.show_phase_arrays:
            self.show_phase_arrays()

        # setup the selector for adc (uses `selectors2` module instead of `select`)
        # register the IND device for read events.
        self.adc_selector = selectors.DefaultSelector()
        self.adc_selector.register(self.dev_hand, selectors.EVENT_READ)

    def cleanup(self):
        '''Cleanup application before exit.'''

        print("Stopping ADC.")
        self.adc_stop()

        # unregister the IND device from adc selector.
        self.adc_selector.unregister(self.dev_hand)

    def adc_numpy_array(self):
        mem = ind.adc_memory_map(dev_hand=self.dev_hand)
        print("ADC Memory: {!r}".format(mem))
        print("ADC Memory: {}".format(mem))
        ## Numpy array holds little-endian 16-bit integers.
        signed = self.config.adc_polarity_is_signed()
        dtype = np.dtype('<i2') if signed else np.dtype('<u2')
        dtype_size = dtype.itemsize
        mem_size = len(mem)
        length = mem_size // dtype_size
        print("DEBUG: dtype={!r} dtype_size={!r} len(mem)={!r} length={!r}".format(dtype, dtype_size, mem_size, length))
        shape = (length,)
        np_array = np.ndarray(shape=shape, dtype=dtype, buffer=mem)

        ## the memory offset for half the capture buffer.
        bank_size = mem_size // self.config.bank_count
        self.adc_capture_buffer_offset = [ bank_size * i for i in range(self.config.bank_count) ]

        return np_array

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

        print("DEBUG: next_capture_buffer: old_bank={}, old_next_bank={}".format(self.bank, self.next_bank))

        self.bank = self.next_bank

        self.next_bank = (self.next_bank + 1) % self.config.bank_count

        curr_offset = self.adc_capture_buffer_offset[self.bank]
        next_offset = self.adc_capture_buffer_offset[self.next_bank]

        print("DEBUG: next_capture_buffer: new_bank={}, new_next_bank={}".format(self.bank, self.next_bank))
        print("DEBUG: next_capture_buffer: curr_offset=0x{:X}, next_offset=0x{:X}".format(curr_offset, next_offset))

        ind.adc_capture_address(address=next_offset, dev_hand=self.dev_hand)

        self.set_phases()

    def adc_stop(self):
        print("ADC Stop")
        ind.adc_capture_stop(dev_hand=self.dev_hand)

    def adc_start(self):
        print("ADC Start")

        signed = self.config.adc_polarity_is_signed()
        print("DEBUG: signed = {!r}".format(signed))

        ##
        ## peak detect start/stop count are in multiples of 8.
        ## i.e. the lower 3 bits are ignored and treated as zeros.
        ##
        ## range of indices returned are from start to (stop-1).
        ## range of indices returned are from start to (stop-1).
        ##
        ## Notes from Greg Smart (FPGA developer).
        ## ---------------------------------------
        ## 1. Both start and end points are a multiple of 8, lower bits are truncated if anything else is passed.
        ## 2. If start == stop, then the behaviour is a start.  start now overides stop, and it will run to the end.
        ## 3. To start at 0, the start_index must be 0.  If the start_index > number of samples, the result will be nothing (0x7fff,0x8000), address from previous run.
        ## 4. If the stop occurs before the start, the result is from the start to the end.
        ## 5. If start_index = 32, the first value used is 32.  If the end_index = 40, the values tested are 32 -> 39.  40 is not tested.
        ##

        ##
        ## peak detection disabled.
        ##
        #peak_detect_start_count = ind.Config.Peak_Start_Disable
        #peak_detect_stop_count = ind.Config.Peak_Stop_Disable

        ##
        ## peak detection over entire sample range.
        ##
        peak_detect_start_count = 0
        peak_detect_stop_count = self.config.capture_count

        #peak_detect_start_count = 0
        #peak_detect_start_count = 1
        #peak_detect_start_count = 2
        #peak_detect_start_count = 7
        #peak_detect_start_count = 8
        #peak_detect_start_count = 16
        #peak_detect_start_count = 32
        #peak_detect_start_count = 0x80000
        #peak_detect_start_count = 0x90000
        #peak_detect_start_count = 0x90010
        #peak_detect_start_count = 0x90020
        #peak_detect_start_count = 0x90030
        #peak_detect_start_count = 0x90040
        #peak_detect_stop_count = 0
        #peak_detect_stop_count = 1
        #peak_detect_stop_count = 2
        #peak_detect_stop_count = 7
        #peak_detect_stop_count = 8
        #peak_detect_stop_count = 9
        #peak_detect_stop_count = 15
        #peak_detect_stop_count = 16
        #peak_detect_stop_count = 17
        #peak_detect_stop_count = 32
        #peak_detect_stop_count = 64
        #peak_detect_stop_count = 0x90000
        #peak_detect_stop_count = 0x90001
        #peak_detect_stop_count = 0x90007
        #peak_detect_stop_count = 0x90008
        #peak_detect_stop_count = 0x90009
        #peak_detect_stop_count = 0x9000F
        #peak_detect_stop_count = 0x90010
        #peak_detect_stop_count = 0x90011
        #peak_detect_stop_count = 0x90020
        #peak_detect_stop_count = 0x90030
        #peak_detect_stop_count = 0x90040
        #peak_detect_stop_count = 0x100000
        #peak_detect_stop_count = self.config.capture_count - 8
        #peak_detect_stop_count = self.config.capture_count - 6
        #peak_detect_stop_count = self.config.capture_count - 5
        #peak_detect_stop_count = self.config.capture_count - 4
        #peak_detect_stop_count = self.config.capture_count - 3
        #peak_detect_stop_count = self.config.capture_count - 2
        #peak_detect_stop_count = self.config.capture_count - 1
        #peak_detect_stop_count = self.config.capture_count - 0
        #peak_detect_stop_count = self.config.capture_count + 16
        #peak_detect_stop_count = self.config.capture_count + 8
        #peak_detect_stop_count = self.config.capture_count + 4
        #peak_detect_stop_count = self.config.capture_count + 3
        #peak_detect_stop_count = self.config.capture_count + 2
        #peak_detect_stop_count = self.config.capture_count + 1

        self.peak_detect_start_count = peak_detect_start_count
        self.peak_detect_stop_count = peak_detect_stop_count

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
        print("ADC Semaphore Wait")
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
        print("ADC Select Wait")

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
        print("ADC Manual Trigger")
        ind.adc_trigger(dev_hand=self.dev_hand)

    def adc_data_ready_wait(self):
        print("ADC Data Ready Wait")
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
                print(" {:+11},".format(val)),
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

    ##------------------------------------------------------------------------

    def peak_convert(self, index, value, index_offset, count):
        '''Convert peak index and value to Peak object, converting to time and voltage.'''

        toff = float(index + index_offset) / self.config.sample_frequency
        #toff = float(index + index_offset) * self.time_resolution
        value -= self.config.sample_offset
        volt = value * self.voltage_factor
        if self.config.peak_detect_mode == PeakDetectMode.SQUARED:
            volt *= self.voltage_factor
        peak = Peak(index=index, value=value, count=count, time_offset=toff, voltage=volt)
        return peak

    ##------------------------------------------------------------------------

    def peak_by_func(self, func, data, index_offset):
        '''Search numpy data array (by function) and get the index.'''
        '''Value is converted from sample level to volts.'''

        peak_data = data[self.peak_detect_start_count:self.peak_detect_stop_count]
        time0 = time.time()
        idx = func(peak_data) + self.peak_detect_start_count
        delta = time.time() - time0
        print("DEBUG: np.min/np.max() took {} seconds".format(delta))
        value = data[idx]
        time0 = time.time()
        condition = (data == value)
        delta = time.time() - time0
        print("DEBUG: condition compare took {} seconds".format(delta))
        time0 = time.time()
        count = np.count_nonzero(condition)
        delta = time.time() - time0
        print("DEBUG: np.count_nonzero took {} seconds".format(delta))
        peak = self.peak_convert(index=idx, value=value, index_offset=index_offset, count=count)
        return peak

    ##------------------------------------------------------------------------

    def peak_min(self, data, index_offset):
        '''Search numpy data array for minimum value and the index.'''
        '''Value is converted from sample level to volts.'''

        return self.peak_by_func(func=np.argmin, data=data, index_offset=index_offset)

    ##------------------------------------------------------------------------

    def peak_max(self, data, index_offset):
        '''Search numpy data array for maximum value and the index.'''
        '''Value is converted from sample level to volts.'''

        return self.peak_by_func(func=np.argmax, data=data, index_offset=index_offset)

    ##------------------------------------------------------------------------

    def peak_detect_normal_numpy(self):
        '''Perform peak detection on normal current phases using numpy.'''

        phase = self.red_phase
        if 0:
            #! FIXME: copy from device memory (non-cached) to normal (cached) memory.
            #! FIXME: for testing only !!
            phase = np.copy(phase)
        offset = self.config.capture_index_offset_red
        t1 = time.time()
        peak_max_red = self.peak_max(phase, index_offset=offset)
        t2 = time.time()
        peak_min_red = self.peak_min(phase, index_offset=offset)
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
        peak_max_wht = self.peak_max(phase, index_offset=offset)
        peak_min_wht = self.peak_min(phase, index_offset=offset)

        phase = self.blu_phase
        if 0:
            #! FIXME: copy from device memory (non-cached) to normal (cached) memory.
            #! FIXME: for testing only !!
            phase = np.copy(phase)
        offset = self.config.capture_index_offset_blu
        peak_max_blu = self.peak_max(phase, index_offset=offset)
        peak_min_blu = self.peak_min(phase, index_offset=offset)

        self.peak_normal_max_red = peak_max_red
        self.peak_normal_min_red = peak_min_red
        self.peak_normal_max_wht = peak_max_wht
        self.peak_normal_min_wht = peak_min_wht
        self.peak_normal_max_blu = peak_max_blu
        self.peak_normal_min_blu = peak_min_blu

    ##------------------------------------------------------------------------

    def peak_detect_squared_numpy(self):
        '''Perform peak detection on squared current phases using numpy.'''

        phase = self.red_phase
        if 0:
            print("RED phase (normal):")
            self.show_phase(phase)
#         phase = np.square(phase)
        phase = np.square(phase.astype(np.int32))
        if 0:
            print("RED phase (squared):")
            self.show_phase(phase)
        offset = self.config.capture_index_offset_red
        t1 = time.time()
        peak_max_red = self.peak_max(phase, index_offset=offset)
        t2 = time.time()
        peak_min_red = self.peak_min(phase, index_offset=offset)
        t3 = time.time()
        red_time_delta_1 = t2 - t1
        red_time_delta_2 = t3 - t2
        if 0:
            print("DEBUG: RED: time_delta_1={}".format(red_time_delta_1))
            print("DEBUG: RED: time_delta_2={}".format(red_time_delta_2))

        phase = self.wht_phase
#         phase = np.square(phase)
        phase = np.square(phase.astype(np.int32))
        offset = self.config.capture_index_offset_wht
        peak_max_wht = self.peak_max(phase, index_offset=offset)
        peak_min_wht = self.peak_min(phase, index_offset=offset)

        phase = self.blu_phase
#         phase = np.square(phase)
        phase = np.square(phase.astype(np.int32))
        offset = self.config.capture_index_offset_blu
        peak_max_blu = self.peak_max(phase, index_offset=offset)
        peak_min_blu = self.peak_min(phase, index_offset=offset)

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

        #! channel 0 (red)
        peak_max_red = self.peak_convert(index=maxmin.max_ch0_addr, value=maxmin.max_ch0_data, index_offset=self.config.capture_index_offset_red, count=maxmin.max_ch0_count)
        peak_min_red = self.peak_convert(index=maxmin.min_ch0_addr, value=maxmin.min_ch0_data, index_offset=self.config.capture_index_offset_red, count=maxmin.min_ch0_count)

        ## channel 1 (white)
        peak_max_wht = self.peak_convert(index=maxmin.max_ch1_addr, value=maxmin.max_ch1_data, index_offset=self.config.capture_index_offset_wht, count=maxmin.max_ch1_count)
        peak_min_wht = self.peak_convert(index=maxmin.min_ch1_addr, value=maxmin.min_ch1_data, index_offset=self.config.capture_index_offset_wht, count=maxmin.min_ch1_count)

        ## channel 2 (blue)
        peak_max_blu = self.peak_convert(index=maxmin.max_ch2_addr, value=maxmin.max_ch2_data, index_offset=self.config.capture_index_offset_blu, count=maxmin.max_ch2_count)
        peak_min_blu = self.peak_convert(index=maxmin.min_ch2_addr, value=maxmin.min_ch2_data, index_offset=self.config.capture_index_offset_blu, count=maxmin.min_ch2_count)

        t2 = time.time()
        t_delta_1 = t2 - t1

        self.peak_normal_max_red = peak_max_red
        self.peak_normal_min_red = peak_min_red
        self.peak_normal_max_wht = peak_max_wht
        self.peak_normal_min_wht = peak_min_wht
        self.peak_normal_max_blu = peak_max_blu
        self.peak_normal_min_blu = peak_min_blu

        t_delta_2 = time.time() - t1
        if config.peak_detect_fpga_debug:
            print
            print("DEBUG: Peak Detect Normal FPGA: maxmin = {}".format(maxmin))
            print("DEBUG: Peak Detect Normal FPGA: t_delta_1 = {}".format(t_delta_1))
            print("DEBUG: Peak Detect Normal FPGA: t_delta_2 = {}".format(t_delta_2))

    ##------------------------------------------------------------------------

    def peak_detect_squared_fpga(self):
        '''Get squared peak detection info from FPGA.'''

        t1 = time.time()

        maxmin = self.maxmin_squared

        #! channel 0 (red)
        peak_max_red = self.peak_convert(index=maxmin.max_ch0_addr, value=maxmin.max_ch0_data, index_offset=self.config.capture_index_offset_red, count=maxmin.max_ch0_count)
        peak_min_red = self.peak_convert(index=maxmin.min_ch0_addr, value=maxmin.min_ch0_data, index_offset=self.config.capture_index_offset_red, count=maxmin.min_ch0_count)

        ## channel 1 (white)
        peak_max_wht = self.peak_convert(index=maxmin.max_ch1_addr, value=maxmin.max_ch1_data, index_offset=self.config.capture_index_offset_wht, count=maxmin.max_ch1_count)
        peak_min_wht = self.peak_convert(index=maxmin.min_ch1_addr, value=maxmin.min_ch1_data, index_offset=self.config.capture_index_offset_wht, count=maxmin.min_ch1_count)

        ## channel 2 (blue)
        peak_max_blu = self.peak_convert(index=maxmin.max_ch2_addr, value=maxmin.max_ch2_data, index_offset=self.config.capture_index_offset_blu, count=maxmin.max_ch2_count)
        peak_min_blu = self.peak_convert(index=maxmin.min_ch2_addr, value=maxmin.min_ch2_data, index_offset=self.config.capture_index_offset_blu, count=maxmin.min_ch2_count)

        t2 = time.time()
        t_delta_1 = t2 - t1

        self.peak_squared_max_red = peak_max_red
        self.peak_squared_min_red = peak_min_red
        self.peak_squared_max_wht = peak_max_wht
        self.peak_squared_min_wht = peak_min_wht
        self.peak_squared_max_blu = peak_max_blu
        self.peak_squared_min_blu = peak_min_blu

        t_delta_2 = time.time() - t1
        if config.peak_detect_fpga_debug:
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

        ## Do FPGA first, as minmax registers are not double buffered.
        if self.config.peak_detect_fpga:
            time0 = time.time()
            ret = self.peak_detect_normal_fpga()
            time1 = time.time()

            ## Maintain reference to FPGA peak values.
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

            ## Maintain reference to numpy peak values.
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
            print("\nDEBUG: Peak Detect Check FPGA v Numpy")

            ## Red Max
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

            ## Red Min
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


            ## White Max
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


            ## White Min
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


            ## Blue Max
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


            ## Blue Min
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

        ## Do FPGA first, as minmax registers are not double buffered.
        if self.config.peak_detect_fpga:
            time0 = time.time()
            ret = self.peak_detect_squared_fpga()
            time1 = time.time()

            ## Maintain reference to FPGA peak values.
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

            ## Maintain reference to numpy peak values.
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
            print("\nDEBUG: Peak Detect Check FPGA v Numpy")

            ## Red Max
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


            ## Red Min
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


            ## White Max
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


            ## White Min
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


            ## Blue Max
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


            ## Blue Min
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

    def peak_detect(self):
        '''Perform peak detection on current phases.'''

        errors = 0

        ##
        ## Normal Peak Detection.
        ##
        if self.config.peak_detect_normal:
            errors += self.peak_detect_normal()

        ##
        ## Squared Peak Detection.
        ##
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
            print("DEBUG: phase_array_around_index: size_half={:8}".format(size_half))
            print("DEBUG: phase_array_around_index: beg={:8}".format(beg))
            print("DEBUG: phase_array_around_index: end={:8}".format(end))

        return phase[beg:end]

    ##------------------------------------------------------------------------

    def running_led_off(self):
        ind.running_led_off(dev_hand=self.dev_hand)

    def running_led_on(self):
        ind.running_led_on(dev_hand=self.dev_hand)

    def running_led_toggle(self):
        ind.running_led_toggle(dev_hand=self.dev_hand)

    ##------------------------------------------------------------------------

    def spare_led_off(self):
        ind.spare_led_off(dev_hand=self.dev_hand)

    def spare_led_on(self):
        ind.spare_led_on(dev_hand=self.dev_hand)

    def spare_led_toggle(self):
        ind.spare_led_toggle(dev_hand=self.dev_hand)

    ##------------------------------------------------------------------------

    def main_loop(self):
        '''Run main loop of Read_Capture_Buffers_App.'''

        ## FIXME: should probably have two ping-pong arrays assigned in init()
        adc_capture_array_len = len(self.adc_capture_array)
        adc_capture_array_0_len = adc_capture_array_len // 2
        adc_capture_array_0 = self.adc_capture_array[(adc_capture_array_0_len*0):(adc_capture_array_0_len*1)]
        adc_capture_array_1 = self.adc_capture_array[(adc_capture_array_0_len*1):(adc_capture_array_0_len*2)]

        print("adc_capture_array_len = {:8}".format(adc_capture_array_len))
        print("adc_capture_array_0_len = {:8}".format(adc_capture_array_0_len))

        assert(adc_capture_array_0_len == len(adc_capture_array_0))
        assert(adc_capture_array_0_len == len(adc_capture_array_1))

        ## Start the analog acquisition.
        if self.config.capture_mode == 'manual':
            print("Starting Analog Data Acquisition -- Manual Trigger")
        else:
            print("Starting Analog Data Acquisition -- Auto PPS Trigger")
        self.adc_start()

        ## Read back ADC Offset register to see if it was stored correctly.
        adc_offset = ind.adc_offset_get(dev_hand=self.dev_hand)
        print("read back: adc_offset = {} ({})".format(adc_offset, hex(adc_offset)))
        if adc_offset != self.config.adc_offset:
            cao = self.config.adc_offset
            print("ERROR: adc_offset does not match config setting {} ({})".format(cao, hex(cao)))

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

        ## flush buffers with a few samples before actual testing.
        ## Suppresses an error on the first pass where `get_sample_data()`
        ## returns immediately with no data written to the capture buffers.
        ## Only affects manual trigger mode.
#         if self.config.capture_mode == 'manual':
#             self.get_sample_data()          ## wait for data to be available.

        ## main sampling and testing loop.
        while True:
            if 1:
                print("\n========================================")

            sys.stdout.flush()

            #self.running_led_off()

            data_ok = self.get_sample_data()    ## wait for data to be available, with timeout.

            if data_ok:
                self.capture_trigger_count += 1

            #self.running_led_on()
            self.running_led_toggle()

            #! Get time that `selector` returns.
            select_datetime_utc = arrow.utcnow()
            select_datetime_local = select_datetime_utc.to(self.config.timezone)

            #! use next capture buffer for ping-pong.  Updates self.bank to captured buffer bank.
            self.adc_capture_buffer_next()

            ## Retrieve info from FPGA registers first (especially if not double buffered).
            ## Would be better to double buffer in the interrupt routine and save
            ## to kernel memory, then retrieve via a single IOCTL (BB#105).
            ##
            capture_info = ind.adc_capture_info_get(self.bank, dev_hand=self.dev_hand)

            if 1:
                self.maxmin_normal      = capture_info.maxmin_normal
                self.maxmin_squared     = capture_info.maxmin_squared
                adc_clock_count_per_pps = capture_info.adc_clock_count_per_pps
            else:
                ## Read the normal maxmin registers from the fpga.
                self.maxmin_normal = ind.adc_capture_maxmin_normal_get(dev_hand=self.dev_hand)
                ##
                ## Read the squared maxmin registers from the fpga.
                self.maxmin_squared = ind.adc_capture_maxmin_squared_get(dev_hand=self.dev_hand)

                #! Read the `adc_clock_count_per_pps` register from the fpga.
                adc_clock_count_per_pps = ind.adc_clock_count_per_pps_get(dev_hand=self.dev_hand)

            timestamp = float(capture_info.irq_time.tv_sec) + (float(capture_info.irq_time.tv_nsec) / 1000000000.0)
            irq_capture_datetime_utc = arrow.get(timestamp)

            #! set the capture time (truncate to seconds).
            if 1:
                self.set_capture_datetime(irq_capture_datetime_utc.floor('second'))
            else:
                self.set_capture_datetime(select_datetime_utc.floor('second'))

            #! Clear terminal screen by sending special chars (ansi sequence?).
            #print("\033c")

            if config.show_capture_debug:
                print
                #print("========================================")
                print("Total Capture Trigger Count = {}".format(self.capture_trigger_count))
                print("irq_capture_datetime_utc = {}".format(irq_capture_datetime_utc))
                print("sel_capture_datetime_utc = {}".format(select_datetime_utc))
                print("app_capture_datetime_utc = {}".format(self.capture_datetime_utc))

            if config.peak_detect_fpga_debug:
                print("\nDEBUG: Peak Detect Normal FPGA:  maxmin = {}".format(self.maxmin_normal))
                print("\nDEBUG: Peak Detect Squared FPGA: maxmin = {}".format(self.maxmin_squared))
                print("\nDEBUG: adc_clock_count_per_pps = {:10} (0x{:08X})".format(adc_clock_count_per_pps, adc_clock_count_per_pps))
                #print("\nDEBUG: capture_info_0 = {}".format(capture_info_0))
                #print("\nDEBUG: capture_info_1 = {}".format(capture_info_1))
                print("\nDEBUG: capture_info = {}".format(capture_info))

            if not data_ok:
                continue

            ##
            ## Show capture data / phase arrays
            ##
            if self.config.show_capture_buffers:
                self.show_all_capture_buffers()

            if self.config.show_phase_arrays:
                #self.show_phase_arrays(phase_index=0)
                #self.show_phase_arrays(phase_index=1)
                self.show_phase_arrays()

            ## save phase data to disk.
            if config.save_capture_data:
                loc_dt = self.capture_datetime_local
                loc_dt_str = loc_dt.format('YYYYMMDDTHHmmssZ')
                ## red
                filename = 'sampledata-{}-red'.format(loc_dt_str)
                np.save(filename, self.red_phase)
                ## white
                filename = 'sampledata-{}-wht'.format(loc_dt_str)
                np.save(filename, self.wht_phase)
                ## blue
                filename = 'sampledata-{}-blu'.format(loc_dt_str)
                np.save(filename, self.blu_phase)

            self.spare_led_on()

            buffer_errors = 0
            self.peak_index_errors = 0
            self.peak_value_errors = 0
            self.peak_count_errors = 0

            ##
            ## Read capture memory
            ## NOTE: with non-cache memory, CANNOT copy/memcpy large arrays (within PPS one second period)
            ##
            if 0:
                print("\nCopying adc_capture_array_0 to tmp_array_0")
                tmp_array_0 = np.array(adc_capture_array_0[0:(capture_count*3+1)])
                #tmp_array_0 = adc_capture_array_0.copy()
                x = adc_capture_array_0[0:(capture_count*3+1)].copy()
                if tmp_array_0[0] != x[0]:
                    print("ERROR: tmp_array_0[0] NOT EQUAL x[0]")
                if tmp_array_0[-2] != x[-2]:
                    print("ERROR: tmp_array_0[-2] NOT EQUAL x[-2]")
                if tmp_array_0[-1] != x[-1]:
                    print("ERROR: tmp_array_0[-1] NOT EQUAL x[-1]")
            if 0:
                print("Copying adc_capture_array_1 to tmp_array_1")
                tmp_array_1 = adc_capture_array_1.copy()

            self.spare_led_off()

            ##
            ## Check that read was ok.
            ##
            if 0:
                for index in [0, (capture_count*1)-1, (capture_count*1), (capture_count*2)-1, (capture_count*2), (capture_count*3)-1, (capture_count*4)]:
                    print("\nChecking adc_capture_array_0 and tmp_array_0 at index={:8}".format(index))
                    value = adc_capture_array_0[index]
                    temp = tmp_array_0[index]
                    if value != temp:
                        print("ERROR: adc_capture_array_0 ({:+8}) does not match tmp_array_0 ({:+8}) at index={:8} !!".format(value, temp, index))
                        buffer_errors += 1

            ##
            ## Check for buffer overrun in initialise_capture_memory config is set.
            ##
            if self.config.initialise_capture_memory:
                magic_value = self.config.initialise_capture_memory_magic_value

                print("\nChecking adc_capture_array for magic number")

                index = (capture_count * 3) - 1
                #print("DEBUG: adc_capture_array_0[CC] index={:8}".format(index))
                value = adc_capture_array_0[index]
                if value == magic_value:
                    print("ERROR: Buffer underrun.  adc_capture_array_0[CC-1] ({:+8}) matches initialised magic value ({:+8}) at index={:8} !!".format(value, magic_value, index))
                    adc_capture_array_0[index] = magic_value
                    buffer_errors += 1
                    while True:
                        index += 1
                        if index >= adc_capture_array_0_len:
                            print("ERROR: Reached end of adc_capture_array_0 !!")
                            break
                        value = adc_capture_array_0[index]
                        if value == magic_value:
                            print("DEBUG: adc_capture_array_0 magic ok at index={:8}".format(index))
                            break

                index = capture_count * 3
                #print("DEBUG: adc_capture_array_0[CC] index={:8}".format(index))
                value = adc_capture_array_0[index]
                if value != magic_value:
                    print("ERROR: Buffer overrun.  adc_capture_array_0[CC] ({:+8}) does not match initialised magic value ({:+8}) at index={:8} !!".format(value, magic_value, index))
                    adc_capture_array_0[index] = magic_value
                    buffer_errors += 1
                    while True:
                        index += 1
                        if index >= adc_capture_array_0_len:
                            print("ERROR: Reached end of adc_capture_array_0 !!")
                            break
                        value = adc_capture_array_0[index]
                        if value == magic_value:
                            print("DEBUG: adc_capture_array_0 magic ok at index={:8}".format(index))
                            break

                index = -1
                value = adc_capture_array_0[index]
                if value != magic_value:
                    print("ERROR: Buffer overrun.  adc_capture_array_0[-1] ({:+8}) does not match initialised magic value ({:+8}) at index={:8} !!".format(value, magic_value, index))
                    adc_capture_array_0[index] = magic_value
                    buffer_errors += 1

                index = capture_count * 3
                value = adc_capture_array_1[index]
                if value != magic_value:
                    print("ERROR: Buffer overrun.  adc_capture_array_1[CC] ({:+8}) does not match initialised magic value ({:+8}) at index={:8} !!".format(value, magic_value, index))
                    adc_capture_array_1[index] = magic_value
                    buffer_errors += 1

                index = -1
                value = adc_capture_array_1[index]
                if value != magic_value:
                    print("ERROR: Buffer overrun.  adc_capture_array_1[-1] ({:+8}) does not match initialised magic value ({:+8}) at index={:8} !!".format(value, magic_value, index))
                    adc_capture_array_1[index] = magic_value
                    buffer_errors += 1

                print("Capture Buffer Errors = {}".format(buffer_errors))
                self.buffer_errors_total += buffer_errors
                print("Total Capture Buffer Errors = {}".format(self.buffer_errors_total))

            ##
            ## Peak Detection Test
            ##
            if self.config.peak_detect:
                peak_errors = self.peak_detect()
                self.peak_errors_total += peak_errors

                if self.config.peak_detect_debug:
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

            print("\nTotal Capture Trigger Count = {}".format(self.capture_trigger_count))

            ##
            ## Show ADC Clock Count Per PPS.
            ##
            if 1:
                self.adc_clock_count_now = adc_clock_count_per_pps
                ## Check if in valid range.
                if self.adc_clock_count_valid_min <= self.adc_clock_count_now <= self.adc_clock_count_valid_max:
                    if self.adc_clock_count_now < self.adc_clock_count_min:
                        self.adc_clock_count_min = self.adc_clock_count_now
                    if self.adc_clock_count_now > self.adc_clock_count_max:
                        self.adc_clock_count_max = self.adc_clock_count_now

                print
                delta = self.adc_clock_count_now - self.config.sample_frequency
                print("DEBUG: adc_clock_count_per_pps_now = {:10}, delta = {:7}".format(self.adc_clock_count_now, delta))
                delta = self.adc_clock_count_min - self.config.sample_frequency
                print("DEBUG: adc_clock_count_per_pps_min = {:10}, delta = {:7}".format(self.adc_clock_count_min, delta))
                delta = self.adc_clock_count_max - self.config.sample_frequency
                print("DEBUG: adc_clock_count_per_pps_max = {:10}, delta = {:7}".format(self.adc_clock_count_max, delta))

            ## FIXME: DEBUG: exit after one cycle.
            #break

##############################################################################


def argh_main():

    config = Config()

    #! override defaults with settings in user settings file.
    config.read_settings_file()

    #!
    #! override config defaults for test_fpga app.
    #!

    config.capture_mode             = 'manual'

    config.show_capture_debug       = True

    config.peak_detect_numpy_capture_count_limit = 1*1000*1000
    config.peak_detect_numpy        = True
    config.peak_detect_numpy_debug  = False

    config.peak_detect_fpga         = True
    config.peak_detect_fpga_debug   = False

    config.peak_detect              = True
    config.peak_detect_debug        = False

    config.peak_detect_normal       = True
    config.peak_detect_squared      = True

    #config.show_capture_buffers = True

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
                 test_mode              = config.test_mode.name.lower(),
                 debug                  = False,
                 ):
        """Main entry if running this module directly."""

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

        if test_mode != config.test_mode.name.lower():
            config.set_test_mode(test_mode)

        if debug:
            config.peak_detect_numpy_debug  = True
            config.peak_detect_fpga_debug   = True
            config.peak_detect_debug        = True

        config.show_all()

        #!--------------------------------------------------------------------

        app = Read_Capture_Buffers_App(config=config)
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

    #!------------------------------------------------------------------------

    argh.dispatch_command(app_main)

##============================================================================

if __name__ == "__main__":
    argh_main()
