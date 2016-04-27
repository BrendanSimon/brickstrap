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
import numpy as np
import math
import time
import arrow
import select

from collections import namedtuple

from efd_config import Config

import ind

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

class Read_Capture_Buffers_App(object):
    '''The IND Early Fault Detection application class.'''

    def __init__(self, config):
        '''Initialise Read_Capture_Buffers_App class.'''
        print(self.__doc__)

        self.config = config

        self.app_state = None
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
        if 1:
            print("set_phases(): adc_capture_buffer_offset={:08X}:".format(self.adc_capture_buffer_offset))
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
            self.adc_capture_array.fill(self.config.initialise_capture_memory_magic_value)

        if self.config.show_intialised_capture_buffers:
            self.show_all_capture_buffers()

        self.init_phase_arrays()
        if self.config.show_intialised_phase_arrays:
            self.show_phase_arrays()

    def cleanup(self):
        '''Cleanup application before exit.'''

        print("Stopping ADC.")
        self.adc_stop()

    def adc_numpy_array(self):
        mem = ind.adc_memory_map(dev_hand=self.dev_hand)
        print("ADC Memory: {!r}".format(mem))
        print("ADC Memory: {}".format(mem))
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

    def fpga_version_get(self):
        print("DEBUG: FPGA Version Get()")
        fpga_version = ind.fpga_version_get(dev_hand=self.dev_hand)
        return fpga_version

    def adc_dma_reset(self):
        print("DEBUG: ADC DMA Resetting ...")
        ind.adc_dma_reset(dev_hand=self.dev_hand)
        print("DEBUG: ADC DMA Reset.")

    def adc_capture_buffer_next(self):
        '''Set next capture bufer for next dma acquisition -- use for ping-pong buffering.'''
        curr_offset = self.adc_capture_buffer_offset

        self.set_phases()

        next_offset = self.adc_capture_buffer_offset_half if curr_offset == 0 else 0
        print("DEBUG: next_capture_buffer: curr_offset={:X}, next_offset={:X}".format(curr_offset, next_offset))
        self.adc_capture_buffer_offset = next_offset

        ind.adc_capture_address(address=next_offset, dev_hand=self.dev_hand)

    def adc_stop(self):
        print("ADC Stop")
        ind.adc_capture_stop(dev_hand=self.dev_hand)

    def adc_start(self):
        print("ADC Start")

        signed = self.config.capture_data_polarity_is_signed()
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

        cfg = self.config
        ind.adc_capture_start(address=0, capture_count=cfg.capture_count, delay_count=cfg.delay_count, capture_mode=cfg.capture_mode, signed=signed, peak_detect_start_count=peak_detect_start_count, peak_detect_stop_count=peak_detect_stop_count, dev_hand=self.dev_hand)

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

    def adc_trigger(self):
        print("ADC Manual Trigger")
        ind.adc_trigger(dev_hand=self.dev_hand)

    def adc_data_ready_wait(self):
        #print("ADC Data Ready Wait")
        if self.config.capture_mode == 'manual':
            self.adc_trigger()
            self.adc_semaphore_wait()
        else:
            self.adc_select_wait()

    def get_mmap_sample_data(self):
        '''Get sample data from memory mapped buffer.'''
        self.adc_semaphore_set(0)
        self.adc_data_ready_wait()

    def get_sample_data(self):
        '''Get sample data from memory mapped buffer or capture files.'''
        '''FIXME: capture files not implemented !!'''
        self.get_mmap_sample_data()

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

    ##------------------------------------------------------------------------

    def peak_convert_numpy(self, index, data, index_offset):
        '''Convert peak index and value to Peak object, converting to time and voltage.'''
        toff = float(index + index_offset) / self.config.sample_frequency
        #toff = float(index + index_offset) * self.time_resolution
        value = data[index] - self.config.sample_offset
        volt = value * self.voltage_factor
        peak = Peak(index=index, value=value, time_offset=toff, voltage=volt)
        return peak

    ##------------------------------------------------------------------------

    def peak_min(self, data, index_offset):
        '''Search numpy data array for minimum value and the index.'''
        '''Value is converted from sample level to volts.'''

        peak_data = data[self.peak_detect_start_count:self.peak_detect_stop_count]
        idx = np.argmin(peak_data) + self.peak_detect_start_count
        peak = self.peak_convert_numpy(index=idx, data=data, index_offset=index_offset)
        return peak

    ##------------------------------------------------------------------------

    def peak_max(self, data, index_offset):
        '''Search numpy data array for maximum value and the index.'''
        '''Value is converted from sample level to volts.'''

        peak_data = data[self.peak_detect_start_count:self.peak_detect_stop_count]
        idx = np.argmax(peak_data) + self.peak_detect_start_count
        peak = self.peak_convert_numpy(index=idx, data=data, index_offset=index_offset)
        return peak

    ##------------------------------------------------------------------------

    def peak_detection_numpy(self):
        '''Perform peak detection on current phases using numpy.'''

        phase = self.red_phase
        offset = self.config.capture_index_offset_red
        t1 = time.time()
        peak_max_red = self.peak_max(phase, index_offset=offset)
        t2 = time.time()
        peak_min_red = self.peak_min(phase, index_offset=offset)
        t3 = time.time()
        red_time_delta_1 = t2 - t1
        red_time_delta_2 = t3 - t2
        if 1:
            print("DEBUG: RED: time_delta_1={}".format(red_time_delta_1))
            print("DEBUG: RED: time_delta_2={}".format(red_time_delta_2))

        phase = self.wht_phase
        offset = self.config.capture_index_offset_wht
        peak_max_wht = self.peak_max(phase, index_offset=offset)
        peak_min_wht = self.peak_min(phase, index_offset=offset)

        phase = self.blu_phase
        offset = self.config.capture_index_offset_blu
        peak_max_blu = self.peak_max(phase, index_offset=offset)
        peak_min_blu = self.peak_min(phase, index_offset=offset)

        self.peak_max_red = peak_max_red
        self.peak_min_red = peak_min_red
        self.peak_max_wht = peak_max_wht
        self.peak_min_wht = peak_min_wht
        self.peak_max_blu = peak_max_blu
        self.peak_min_blu = peak_min_blu

    ##------------------------------------------------------------------------

    def peak_convert_fpga(self, index, value, index_offset):
        '''Convert peak index and value to Peak object, converting to time and voltage.'''
        toff = float(index + index_offset) / self.config.sample_frequency
        #toff = float(index + index_offset) * self.time_resolution
        value -= self.config.sample_offset
        volt = value * self.voltage_factor
        peak = Peak(index=index, value=value, time_offset=toff, voltage=volt)
        return peak

    ##------------------------------------------------------------------------

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

        ##
        ## Fix FPGA peak-detection errors.
        ##
        if config.peak_detect_fpga_fix:
            self.peak_detection_fpga_fix(maxmin=maxmin)

    ##------------------------------------------------------------------------

    def peak_detection_fpga_fix(self, maxmin):
        '''Fix peak detection errors from FPGA.'''

        ## FIXME: forget this for now -- higher priority issues !!
        return

        ##
        ## Fix FPGA peak-detection errors.
        ##
        t1 = time.time()

        ## Red
        tmp_phase = self.phase_array_around_index(phase=self.red_phase, index=self.peak_max_red.index, size_half=8)
        print("DEBUG: tmp_phase = {!r}".format(tmp_phase))
        print("DEBUG: tmp_phase = {}".format(tmp_phase))

        peak_max_red = self.peak_convert_fpga(index=maxmin.max_ch0_addr, value=maxmin.max_ch0_data, index_offset=self.config.capture_index_offset_red)
        peak_min_red = self.peak_convert_fpga(index=maxmin.min_ch0_addr, value=maxmin.min_ch0_data, index_offset=self.config.capture_index_offset_red)

        return

    ##------------------------------------------------------------------------

    def peak_detection(self):
        '''Perform peak detection on current phases.'''

        ## Do FPGA first, as minmax registers are not double buffered.
        if self.config.peak_detect_fpga:
            ret = self.peak_detection_fpga()

            ## Maintain reference to FPGA peak values.
            fpga_peak_max_red = self.peak_max_red
            fpga_peak_min_red = self.peak_min_red
            fpga_peak_max_wht = self.peak_max_wht
            fpga_peak_min_wht = self.peak_min_wht
            fpga_peak_max_blu = self.peak_max_blu
            fpga_peak_min_blu = self.peak_min_blu

            if self.config.peak_detect_fpga_debug:
                print("DEBUG: Peak Detect FPGA")
                print("DEBUG: peak_max_red = {}".format(fpga_peak_max_red))
                print("DEBUG: peak_min_red = {}".format(fpga_peak_min_red))
                print("DEBUG: peak_max_wht = {}".format(fpga_peak_max_wht))
                print("DEBUG: peak_min_wht = {}".format(fpga_peak_min_wht))
                print("DEBUG: peak_max_blu = {}".format(fpga_peak_max_blu))
                print("DEBUG: peak_min_blu = {}".format(fpga_peak_min_blu))

        if self.config.peak_detect_numpy:
            ret = self.peak_detection_numpy()

            ## Maintain reference to numpy peak values.
            numpy_peak_max_red = self.peak_max_red
            numpy_peak_min_red = self.peak_min_red
            numpy_peak_max_wht = self.peak_max_wht
            numpy_peak_min_wht = self.peak_min_wht
            numpy_peak_max_blu = self.peak_max_blu
            numpy_peak_min_blu = self.peak_min_blu

            if self.config.peak_detect_numpy_debug:
                print("DEBUG: Peak Detect NUMPY")
                print("DEBUG: peak_max_red = {}".format(numpy_peak_max_red))
                print("DEBUG: peak_min_red = {}".format(numpy_peak_min_red))
                print("DEBUG: peak_max_wht = {}".format(numpy_peak_max_wht))
                print("DEBUG: peak_min_wht = {}".format(numpy_peak_min_wht))
                print("DEBUG: peak_max_blu = {}".format(numpy_peak_max_blu))
                print("DEBUG: peak_min_blu = {}".format(numpy_peak_min_blu))

            if fpga_peak_max_red is numpy_peak_max_red:
                print("ERROR: SAME OBJECT: fpga_peak_max_red is numpy_peak_max_red !!")

        if self.config.peak_detect_numpy and self.config.peak_detect_fpga:
            print("DEBUG: Peak Detect Check FPGA v Numpy")

            ## Red Max
            if fpga_peak_max_red.value != numpy_peak_max_red.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_max_red.value={} numpy_peak_max_red.value={}".format(fpga_peak_max_red.value, numpy_peak_max_red.value))
            if fpga_peak_max_red.index != numpy_peak_max_red.index:
                print(" INFO: INDEX NOT EQUAL: fpga_peak_max_red.index={} numpy_peak_max_red.index={}".format(fpga_peak_max_red.index, numpy_peak_max_red.index))
            if fpga_peak_max_red.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:  fpga_peak_max_red.index={} peak_detect_start_count={}".format(fpga_peak_max_red.index, self.peak_detect_start_count))
            if fpga_peak_max_red.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH: fpga_peak_max_red.index={} peak_detect_stop_count={}".format(fpga_peak_max_red.index, self.peak_detect_stop_count))

            ## Red Min
            if fpga_peak_min_red.value != numpy_peak_min_red.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_min_red.value={} numpy_peak_min_red.value={}".format(fpga_peak_min_red.value, numpy_peak_min_red.value))
            if fpga_peak_min_red.index != numpy_peak_min_red.index:
                print(" INFO: INDEX NOT EQUAL: fpga_peak_min_red.index={} numpy_peak_min_red.index={}".format(fpga_peak_min_red.index, numpy_peak_min_red.index))
            if fpga_peak_min_red.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:  fpga_peak_min_red.index={} peak_detect_start_count={}".format(fpga_peak_min_red.index, self.peak_detect_start_count))
            if fpga_peak_min_red.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH: fpga_peak_min_red.index={} peak_detect_stop_count={}".format(fpga_peak_min_red.index, self.peak_detect_stop_count))

            ## White Max
            if fpga_peak_max_wht.value != numpy_peak_max_wht.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_max_wht.value={} numpy_peak_max_wht.value={}".format(fpga_peak_max_wht.value, numpy_peak_max_wht.value))
            if fpga_peak_max_wht.index != numpy_peak_max_wht.index:
                print(" INFO: INDEX NOT EQUAL: fpga_peak_max_wht.index={} numpy_peak_max_wht.index={}".format(fpga_peak_max_wht.index, numpy_peak_max_wht.index))
            if fpga_peak_max_wht.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:  fpga_peak_max_wht.index={} peak_detect_start_count={}".format(fpga_peak_max_wht.index, self.peak_detect_start_count))
            if fpga_peak_max_wht.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH: fpga_peak_max_wht.index={} peak_detect_stop_count={}".format(fpga_peak_max_wht.index, self.peak_detect_stop_count))

            ## White Min
            if fpga_peak_min_wht.value != numpy_peak_min_wht.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_min_wht.value={} numpy_peak_min_wht.value={}".format(fpga_peak_min_wht.value, numpy_peak_min_wht.value))
            if fpga_peak_min_wht.index != numpy_peak_min_wht.index:
                print(" INFO: INDEX NOT EQUAL: fpga_peak_min_wht.index={} numpy_peak_min_wht.index={}".format(fpga_peak_min_wht.index, numpy_peak_min_wht.index))
            if fpga_peak_min_wht.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:  fpga_peak_min_wht.index={} peak_detect_start_count={}".format(fpga_peak_min_wht.index, self.peak_detect_start_count))
            if fpga_peak_min_wht.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH: fpga_peak_min_wht.index={} peak_detect_stop_count={}".format(fpga_peak_min_wht.index, self.peak_detect_stop_count))

            ## Blue Max
            if fpga_peak_max_blu.value != numpy_peak_max_blu.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_max_blu.value={} numpy_peak_max_blu.value={}".format(fpga_peak_max_blu.value, numpy_peak_max_blu.value))
            if fpga_peak_max_blu.index != numpy_peak_max_blu.index:
                print(" INFO: INDEX NOT EQUAL: fpga_peak_max_blu.index={} numpy_peak_max_blu.index={}".format(fpga_peak_max_blu.index, numpy_peak_max_blu.index))
            if fpga_peak_max_blu.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:  fpga_peak_max_blu.index={} peak_detect_start_count={}".format(fpga_peak_max_blu.index, self.peak_detect_start_count))
            if fpga_peak_max_blu.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH: fpga_peak_max_blu.index={} peak_detect_stop_count={}".format(fpga_peak_max_blu.index, self.peak_detect_stop_count))

            ## Blue Min
            if fpga_peak_min_blu.value != numpy_peak_min_blu.value:
                print("ERROR: VALUE NOT EQUAL: fpga_peak_min_blu.value={} numpy_peak_min_blu.value={}".format(fpga_peak_min_blu.value, numpy_peak_min_blu.value))
            if fpga_peak_min_blu.index != numpy_peak_min_blu.index:
                print(" INFO: INDEX NOT EQUAL: fpga_peak_min_blu.index={} numpy_peak_min_blu.index={}".format(fpga_peak_min_blu.index, numpy_peak_min_blu.index))
            if fpga_peak_min_blu.index < self.peak_detect_start_count:
                print("ERROR: INDEX TOO LOW:  fpga_peak_min_blu.index={} peak_detect_start_count={}".format(fpga_peak_min_blu.index, self.peak_detect_start_count))
            if fpga_peak_min_blu.index >= self.peak_detect_stop_count:
                print("ERROR: INDEX TOO HIGH: fpga_peak_min_blu.index={} peak_detect_stop_count={}".format(fpga_peak_min_blu.index, self.peak_detect_stop_count))

        return ret

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
            print("DEBUG: phase_array_around_index: index={}".format(index))
            print("DEBUG: phase_array_around_index: size_half={}".format(size_half))
            print("DEBUG: phase_array_around_index: beg={}".format(beg))
            print("DEBUG: phase_array_around_index: end={}".format(end))

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

        print("adc_capture_array_len = {}".format(adc_capture_array_len))
        print("adc_capture_array_0_len = {}".format(adc_capture_array_0_len))

        assert(adc_capture_array_0_len == len(adc_capture_array_0))
        assert(adc_capture_array_0_len == len(adc_capture_array_1))

        ## Start the analog acquisition.
        if self.config.capture_mode == 'manual':
            print("Starting Analog Data Acquisition -- Manual Trigger")
            self.adc_start()
        else:
            print("Starting Analog Data Acquisition -- Auto PPS Trigger")
            self.adc_start()

        capture_count = self.config.capture_count
        errors = 0

        while True:
            sys.stdout.flush()

            #self.running_led_off()

            self.get_sample_data()          ## wait for data to be available.

            #self.running_led_on()
            self.running_led_toggle()

            ## NOTE: stdout ends up in /var/log/syslog when app run via systemd !!
            if 1:
                print("\n========================================")

            ## Clear terminal screen by sending special chars (ansi sequence?).
            #print("\033c")

            if config.show_capture_debug:
                print("DEBUG: Data Captured - Processing ...")

            #self.adc_capture_buffer_next()  ## use next capture buffer for ping-pong

            self.spare_led_on()

            ##
            ## Read capture memory
            ## NOTE: with non-cache memory, CANNOT copy/memcpy large arrays (within PPS one second period)
            ##
            if 0:
                print("Copying adc_capture_array_0 to tmp_array_0")
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
                    print("Checking adc_capture_array_0 and tmp_array_0 at index={}".format(index))
                    value = adc_capture_array_0[index]
                    temp = tmp_array_0[index]
                    if value != temp:
                        print("ERROR: adc_capture_array_0 ({}) does not match tmp_array_0 ({}) at index={} !!".format(value, temp, index))
                        errors += 1

            ##
            ## Check for buffer overrun in initialise_capture_memory config is set.
            ##
            if self.config.initialise_capture_memory:
                magic_value = self.config.initialise_capture_memory_magic_value

                print("Checking adc_capture_array for magic number")

                index = (capture_count * 3) - 1
                #print("DEBUG: adc_capture_array_0[CC] index={}".format(index))
                value = adc_capture_array_0[index]
                if value == magic_value:
                    print("ERROR: Buffer underrun.  adc_capture_array_0[CC-1] ({}) matches initialised magic value ({}) at index={} !!".format(value, magic_value, index))
                    adc_capture_array_0[index] = magic_value
                    errors += 1
                    while True:
                        index += 1
                        if index >= adc_capture_array_0_len:
                            print("ERROR: Reached end of adc_capture_array_0 !!")
                            break
                        value = adc_capture_array_0[index]
                        if value == magic_value:
                            print("DEBUG: adc_capture_array_0 magic ok at index={}".format(index))
                            break

                index = capture_count * 3
                #print("DEBUG: adc_capture_array_0[CC] index={}".format(index))
                value = adc_capture_array_0[index]
                if value != magic_value:
                    print("ERROR: Buffer overrun.  adc_capture_array_0[CC] ({}) does not match initialised magic value ({}) at index={} !!".format(value, magic_value, index))
                    adc_capture_array_0[index] = magic_value
                    errors += 1
                    while True:
                        index += 1
                        if index >= adc_capture_array_0_len:
                            print("ERROR: Reached end of adc_capture_array_0 !!")
                            break
                        value = adc_capture_array_0[index]
                        if value == magic_value:
                            print("DEBUG: adc_capture_array_0 magic ok at index={}".format(index))
                            break

                index = -1
                value = adc_capture_array_0[index]
                if value != magic_value:
                    print("ERROR: Buffer overrun.  adc_capture_array_0[-1] ({}) does not match initialised magic value ({}) at index={} !!".format(value, magic_value, index))
                    adc_capture_array_0[index] = magic_value
                    errors += 1

                index = capture_count * 3
                value = adc_capture_array_1[index]
                if value != magic_value:
                    print("ERROR: Buffer overrun.  adc_capture_array_1[CC] ({}) does not match initialised magic value ({}) at index={} !!".format(value, magic_value, index))
                    adc_capture_array_1[index] = magic_value
                    errors += 1

                index = -1
                value = adc_capture_array_1[index]
                if value != magic_value:
                    print("ERROR: Buffer overrun.  adc_capture_array_1[-1] ({}) does not match initialised magic value ({}) at index={} !!".format(value, magic_value, index))
                    adc_capture_array_1[index] = magic_value
                    errors += 1

                print("Errors = {}".format(errors))

            ##
            ## Peak Detection Test
            ##
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

##############################################################################

## Make config object global.
config = Config()

##
## set config defaults for test_fpga app.
##
config.peak_detect_numpy_capture_count_limit = 1*1000*1000
config.peak_detect_numpy = True
config.peak_detect_numpy_debug = False

config.peak_detect_fpga = True
config.peak_detect_fpga_debug = False

config.peak_detect_fpga_fix = False
config.peak_detect_fpga_fix_debug = False

config.peak_detection = True
config.peak_detection_debug = False

##############################################################################

def app_main(capture_count=0, pps_mode=True):
    """Main entry if running this module directly."""

    if capture_count:
        config.set_capture_count(capture_count)
        print("INFO: capture_count set to {}".format(config.capture_count))

    if not pps_mode:
        config.set_capture_mode('manual')
        print("INFO: capture_mode set to {}".format(config.capture_mode))

    config.show_all()

    app = Read_Capture_Buffers_App(config=config)
    app.init()
    try:
        app.main_loop()
    except (KeyboardInterrupt):
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

def argh_main():

    argh.dispatch_command(app_main)

##============================================================================

if __name__ == "__main__":
    argh_main()
