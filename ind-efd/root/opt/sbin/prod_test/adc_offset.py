#!/usr/bin/env python2

#!============================================================================
#!
#!  Author:     Successful Endeavours Pty Ltd
#!
#!============================================================================

'''
This script is used to verify/set the DC offset compensation for the ADC.
'''

import argh
from argh import arg

import sys
import os.path
import time
import arrow
import subprocess
import copy
import logging
import traceback

import colorama
from colorama import Fore as FG, Back as BG, Style as ST

import numpy as np
import math

#sys.path.insert(1, '/opt/sbin')
#sys.path.insert(1, '/mnt/data/etc')
#sys.path.append('.')
sys.path.append('..')
#sys.path.append('/opt/sbin')
#sys.path.append('/mnt/data/etc')

import ind
from efd_config import Config

#!============================================================================

class Phases( object ):
    """Each capture buffer has storage for red, white and blue phases."""

    red = None
    blu = None
    wht = None

    def __init__( self, red, wht, blu ):
        self.red = red
        self.wht = wht
        self.blu = blu

    def __repr__( self ):
        s = "{}(red={!r},wht={!r},blu={!r})".format( self.__class__.__name__, self.red, self.wht, self.blu )
        return s

    @classmethod
    def from_offset_and_size( cls, array, offset, size ):
        beg = offset
        end = beg + size
        red = array[ beg : end ]

        beg += size
        end = beg + size
        wht = array[ beg : end ]

        beg += size
        end = beg + size
        blu = array[ beg : end ]

        inst = cls( red, wht, blu )
        return inst

#!============================================================================

class ADC_Offset_App( object ):

    error_count = 0
    pass_count  = 0

    #!------------------------------------------------------------------------

    def __init__( self, config ):
        self.config = config

    #!------------------------------------------------------------------------

    #! TODO: could put in base class IND_App ??
    def init( self ):
        """Initialise the app"""

        colorama.init( autoreset=True )

        self.banner_start()
        self.superuser_test()
        self.services_stop()

    ##------------------------------------------------------------------------

    ## TODO: could put in base class IND_App ??
    def cleanup( self ):
        """Cleanup the app on exit"""

        #self.services_start()
        self.banner_end()

    #!------------------------------------------------------------------------

    def info( self, msg ):
        print( FG.CYAN + "INFO: " + msg + "\n" )

    def error( self, msg ):
        print( FG.RED + "ERROR: " + msg + "\n" )
        self.error_count += 1

    def passed( self, msg ):
        print( FG.GREEN + "PASS: " + msg + "\n" )
        self.pass_count += 1

    #!------------------------------------------------------------------------

    def shell_command( self, cmd ):
        ret = None
        try:
            ret = subprocess.check_output( cmd, shell=True )
        except Exception as ex:
            self.error( ex.message )
            raise

        return ret

    #!------------------------------------------------------------------------

    def banner_start( self ):
        timestamp = arrow.now()
        self.start_timestamp = timestamp
        self.start_timestamp_str = timestamp.format( "YYYY-MM-DD hh:mm:ss" )

        banner = "\n\n\n" + FG.YELLOW \
                + "======================================================\n" \
                + "IND EFD A2D Offset\n" \
                + "started: {}\n".format( self.start_timestamp_str ) \
                + "======================================================\n"

        print( banner )

    #!------------------------------------------------------------------------

    def banner_end( self ):
        timestamp = arrow.now()
        self.end_timestamp = timestamp
        self.end_timestamp_str = timestamp.format( "YYYY-MM-DD hh:mm:ss" )
        self.duration = self.end_timestamp - self.start_timestamp

        color = FG.YELLOW
        err_color = FG.GREEN if self.error_count == 0 else FG.RED

        banner = color \
                + "======================================================\n" \
                + "IND EFD A2D Offset\n" \
                + "started:  {}\n".format( self.start_timestamp_str ) \
                + "ended:    {}\n".format( self.end_timestamp_str ) \
                + "duration: {}\n".format( self.duration ) \
                + err_color \
                + "Errors:   {}\n".format( self.error_count ) \
                + color \
                + "======================================================\n"

        print( banner )

    #!------------------------------------------------------------------------

    def superuser_test(self):
        filename = '/root/prod_test_was_here.txt'
        try:
            self.shell_command('touch ' + filename)
            self.shell_command('rm ' + filename)
        except Exception as ex:
            self.error("superuser test failed !!")
            sys.exit(-1)

    #!------------------------------------------------------------------------

    def services_stop(self):
        #print("Stopping services...")

        #! Stop the ntp service.
        #print("Stopping chrony service...")
        try:
            self.shell_command('systemctl stop chrony')
        except Exception as ex:
            self.error("stopping chrony service failed !!")

        #! Stop modem being power cycled if no network connectivity.
        #print("Stopping sepl-modem service...")
        try:
            self.shell_command('systemctl stop sepl-modem')
        except Exception as ex:
            self.error("stopping sepl-modem service failed !!")

        #! Stop the efd sampling, measurement, logging, posting.
        #print("Stopping efd service...")
        try:
            self.shell_command('systemctl stop efd')
        except Exception as ex:
            self.error("stopping efd service failed !!")

    #!------------------------------------------------------------------------

    def services_start(self):
        print("Restarting services...")

        print("Restarting efd service...")
        try:
            self.shell_command('systemctl restart efd')
        except Exception as ex:
            self.error("starting efd service failed !!")

        print("Restarting sepl-modem service...")
        try:
            self.shell_command('systemctl restart sepl-modem')
        except Exception as ex:
            self.error("starting sepl-modem service failed !!")

        print("Restarting chrony service...")
        try:
            self.shell_command('systemctl restart chrony')
        except Exception as ex:
            self.error("starting chrony service failed !!")


    #!------------------------------------------------------------------------
    #! TODO: Put in ind.py library and refactor efd_app.py
    #!------------------------------------------------------------------------

    def adc_numpy_array( self ):
        mem = ind.adc_memory_map( dev_hand=self.dev_hand )
        logging.debug("ADC Memory: {!r}".format( mem ) )

        #! Numpy array holds little-endian 16-bit integers.
        signed = self.config.adc_polarity_is_signed()

        dtype = np.dtype('<i2') if signed else np.dtype('<u2')
        dtype_size = dtype.itemsize

        mem_size = len( mem )
        length = mem_size // dtype_size
        logging.debug( "dtype_size={!r} len(mem)={!r} length={!r}".format( dtype_size, mem_size, length ) )

        shape = (length,)
        np_array = np.ndarray( shape=shape, dtype=dtype, buffer=mem )
        logging.debug( "np_array={!r}".format( np_array ) )

        #! the memory offset for each bank of the capture buffer.
        bank_size = mem_size // self.config.bank_count
        logging.debug( "bank_size={!r}".format( bank_size ) )

        self.adc_capture_buffer_offset = [ bank_size * i for i in range( self.config.bank_count ) ]
        logging.debug( "self.adc_capture_buffer_offset={!r}".format( self.adc_capture_buffer_offset ) )

        return np_array

    #!------------------------------------------------------------------------

    def adc_offset_test_run( self, mode ):

        logging.info( "" )
        logging.info( "----------------------------------------------" )
        logging.info( "{} adc offset".format( mode ) )
        logging.info( "----------------------------------------------" )

        #! error count of start of func so we can check against it later
        error_count = self.error_count

        cfg = self.config

        self.dev_hand = ind.get_device_handle()

        #! NOTE: resetting causes first maxmin values to be all zero for some reason !!
        #ind.fpga_reset(dev_hand=self.dev_hand)

        #ind.adc_capture_stop( dev_hand=self.dev_hand )

        #!
        #! initialise capture buffer objects
        #!

        #! get numpy array for total capture memory
        adc_array = self.adc_numpy_array()

        #! segment into banks
        bank_size = adc_array.size // cfg.bank_count
        capture_bank_offsets = [ bank_size * i for i in range( cfg.bank_count ) ]
        logging.debug( "capture_bank_offsets = {!r}".format( capture_bank_offsets ) )

        #! segment banks into phases
        #! create capture buffer, list of capture phases
        #! eg. self.capture_buffer[0].red
        #!     self.capture_buffer[1].wht
        #!     self.capture_buffer[bank].blu
        phase_size = cfg.capture_count
        logging.debug( "phase_size = {!r}".format( phase_size ) )


        self.capture_buffer = [
            Phases.from_offset_and_size( array=adc_array, offset=capture_bank_offsets[i], size=phase_size )
                for i in range( cfg.bank_count )
            ]

        logging.debug( "self.capture_buffer = {!r}".format( self.capture_buffer ) )

        #!
        #! Setup and start capturing
        #!

        self.prev_bank  = 1
        self.bank       = 0

        capture_mode            = 'manual'
        signed                  = cfg.adc_polarity_is_signed()
        peak_detect_start_count = 0
        peak_detect_stop_count  = cfg.capture_count - 1

        #! use configuration setting if verify mode
        adc_offset = cfg.adc_offset if mode == 'verify' else 0

        ind.adc_capture_start( address                  = 0,
                               capture_count            = cfg.capture_count,
                               delay_count              = cfg.delay_count,
                               capture_mode             = capture_mode,
                               signed                   = signed,
                               peak_detect_start_count  = peak_detect_start_count,
                               peak_detect_stop_count   = peak_detect_stop_count,
                               adc_offset               = adc_offset,
                               phase_mode               = cfg.phase_mode,
                               dev_hand                 = self.dev_hand
                            )

        #!
        #! Expected max/min peak values
        #!
        exp_max = 500
        exp_min = -exp_max
        if exp_max > 500:
            logging.warn( "Expected max/min value set too high !! ({}/{})".format( exp_max, exp_min ) )

        sum_phases = Phases( red=[], wht=[], blu=[] )

        #! TODO: make this a config setting
        repetitions = 1
        #repetitions = 3
        #repetitions = 11
        #repetitions = 111

        sem = 0

        for i in xrange( repetitions ):

            ind.adc_semaphore_set( 0, dev_hand=self.dev_hand )

            ind.adc_trigger( dev_hand=self.dev_hand )

            timeout = time.time() + 1
            while True:
                sem = ind.adc_semaphore_get( dev_hand=self.dev_hand )
                if sem:
                    #print( "OK: waiting for adc semaphore" )
                    break
                if time.time() > timeout:
                    print( "TIMEOUT: waiting for adc semaphore" )
                    break
                time.sleep( 0 )

            if sem:
                logging.info( "---------------------------------------------------" )

                #!
                #! Retrieve info from driver.
                #!
                #maxmin_normal = ind.adc_capture_maxmin_normal_get( dev_hand=self.dev_hand )
                capture_info_lst  = ind.adc_capture_info_list_get( dev_hand=self.dev_hand )

                #!
                #! Synchronise DMA capture memory.
                #!
                ind.dma_mem_sync_bank( self.bank, dev_hand=self.dev_hand )

                #!
                #! calculate and accumulate phase sums for longer period calculations
                #! note: convert to "longs" to avoid (python 2) "int" overflow,
                #! when summing sums (for total average calculations)
                #!
                logging.info( "accumulating phases..." )

                red_sum = np.sum( self.capture_buffer[ self.bank ].red ).astype( long )
                sum_phases.red.append( red_sum )

                wht_sum = np.sum( self.capture_buffer[ self.bank ].wht ).astype( long )
                sum_phases.wht.append( wht_sum )

                blu_sum = np.sum( self.capture_buffer[ self.bank ].blu ).astype( long )
                sum_phases.blu.append( blu_sum )

                if 1:
                    #!
                    #! Analyse capture buffers and capture registers
                    #!

                    capture_info_prev = capture_info_lst[ self.prev_bank ]
                    capture_info      = capture_info_lst[ self.bank ]
                    logging.debug( "" )
                    logging.debug( "capture_info_prev = {!r}\n".format( capture_info_prev ) )
                    logging.debug( "capture_info      = {!r}\n".format( capture_info ) )

                    maxmin_normal   = capture_info.maxmin_normal
                    maxmin_squared  = capture_info.maxmin_squared
                    #adc_clock_count_per_pps = capture_info.adc_clock_count_per_pps

                    #!
                    #! calculate the average of each capture buffer
                    #! np.average(a, axis, weights, returned)
                    #!
                    red_avg = float( red_sum ) / cfg.capture_count
                    wht_avg = float( wht_sum ) / cfg.capture_count
                    blu_avg = float( blu_sum ) / cfg.capture_count

                    logging.info( "red_avg = {:+}".format( red_avg ) )
                    logging.info( "wht_avg = {:+}".format( wht_avg ) )
                    logging.info( "blu_avg = {:+}".format( blu_avg ) )

                    peak_max_red = maxmin_normal.max_ch0_data
                    peak_min_red = maxmin_normal.min_ch0_data
                    peak_max_wht = maxmin_normal.max_ch1_data
                    peak_min_wht = maxmin_normal.min_ch1_data
                    peak_max_blu = maxmin_normal.max_ch2_data
                    peak_min_blu = maxmin_normal.min_ch2_data

                    logging.info( "" )
                    logging.info( "FPGA VALUES" )
                    logging.info( "peak_max_red = 0x{:04X} {:+}".format( (peak_max_red & 0xFFFF), peak_max_red ) )
                    logging.info( "peak_min_red = 0x{:04X} {:+}".format( (peak_min_red & 0xFFFF), peak_min_red ) )
                    logging.info( "peak_max_wht = 0x{:04X} {:+}".format( (peak_max_wht & 0xFFFF), peak_max_wht ) )
                    logging.info( "peak_min_wht = 0x{:04X} {:+}".format( (peak_min_wht & 0xFFFF), peak_min_wht ) )
                    logging.info( "peak_max_blu = 0x{:04X} {:+}".format( (peak_max_blu & 0xFFFF), peak_max_blu ) )
                    logging.info( "peak_min_blu = 0x{:04X} {:+}".format( (peak_min_blu & 0xFFFF), peak_min_blu ) )

                    if not ( exp_min <= peak_max_red <= exp_max ):
                        self.error( "ADC peak max red failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_max_red, exp_max ) )

                    if not ( exp_min <= peak_max_wht <= exp_max ):
                        self.error( "ADC peak max wht failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_max_wht, exp_max ) )

                    if not ( exp_min <= peak_max_blu <= exp_max ):
                        self.error( "ADC peak max blu failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_max_blu, exp_max ) )

                    if not ( exp_min < peak_min_red <= exp_max ):
                        self.error( "ADC peak min red failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_min_red, exp_max ) )

                    if not ( exp_min < peak_min_wht <= exp_max ):
                        self.error( "ADC peak min wht failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_min_wht, exp_max ) )

                    if not ( exp_min < peak_min_blu <= exp_max ):
                        self.error( "ADC peak min blu failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_min_blu, exp_max ) )

                    #!
                    #! Numpy max/min (to verify FPGA registers)
                    #!

                    peak_max_red = np.max( self.capture_buffer[ self.bank ].red )
                    peak_min_red = np.min( self.capture_buffer[ self.bank ].red )
                    peak_max_wht = np.max( self.capture_buffer[ self.bank ].wht )
                    peak_min_wht = np.min( self.capture_buffer[ self.bank ].wht )
                    peak_max_blu = np.max( self.capture_buffer[ self.bank ].blu )
                    peak_min_blu = np.min( self.capture_buffer[ self.bank ].blu )

                    logging.info( "" )
                    logging.info( "NUMPY VALUES" )
                    logging.info( "peak_max_red = 0x{:04X} {:+}".format( (peak_max_red & 0xFFFF), peak_max_red ) )
                    logging.info( "peak_min_red = 0x{:04X} {:+}".format( (peak_min_red & 0xFFFF), peak_min_red ) )
                    logging.info( "peak_max_wht = 0x{:04X} {:+}".format( (peak_max_wht & 0xFFFF), peak_max_wht ) )
                    logging.info( "peak_min_wht = 0x{:04X} {:+}".format( (peak_min_wht & 0xFFFF), peak_min_wht ) )
                    logging.info( "peak_max_blu = 0x{:04X} {:+}".format( (peak_max_blu & 0xFFFF), peak_max_blu ) )
                    logging.info( "peak_min_blu = 0x{:04X} {:+}".format( (peak_min_blu & 0xFFFF), peak_min_blu ) )

                    if not ( exp_min <= peak_max_red <= exp_max ):
                        self.error( "ADC peak max red failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_max_red, exp_max ) )

                    if not ( exp_min <= peak_max_wht <= exp_max ):
                        self.error( "ADC peak max wht failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_max_wht, exp_max ) )

                    if not ( exp_min <= peak_max_blu <= exp_max ):
                        self.error( "ADC peak max blu failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_max_blu, exp_max ) )

                    if not ( exp_min < peak_min_red <= exp_max ):
                        self.error( "ADC peak min red failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_min_red, exp_max ) )

                    if not ( exp_min < peak_min_wht <= exp_max ):
                        self.error( "ADC peak min wht failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_min_wht, exp_max ) )

                    if not ( exp_min < peak_min_blu <= exp_max ):
                        self.error( "ADC peak min blu failed ({!r} <= {!r} <= {!r})".format( exp_min, peak_min_blu, exp_max ) )

        ind.adc_capture_stop( dev_hand=self.dev_hand )


        #!
        #! calculate the average of phases, and average of averages
        #!
        logging.info( "" )
        logging.info( "----------------------------------------------" )
        logging.info( "ACCUMULATED AVERAGE VALUES" )
        logging.info( "----------------------------------------------" )

        logging.debug( "sum_phases.red = {!r}".format( sum_phases.red ) )
        red_sum = sum( sum_phases.red )
        red_len = len( sum_phases.red ) * cfg.capture_count
        red_avg = float( red_sum ) / red_len
        logging.info( "red_avg = {:+}".format( red_avg ) )
        #red_set = int( round( red_avg ) )
        #logging.info( "red_set = {:+}".format( red_set ) )

        logging.debug( "sum_phases.wht = {!r}".format( sum_phases.wht ) )
        wht_sum = sum( sum_phases.wht )
        wht_len = len( sum_phases.wht ) * cfg.capture_count
        wht_avg = float( wht_sum ) / wht_len
        logging.info( "wht_avg = {:+}".format( wht_avg ) )
        #wht_set = int( round( wht_avg ) )
        #logging.info( "wht_set = {:+}".format( wht_set ) )

        logging.debug( "sum_phases.blu = {!r}".format( sum_phases.blu ) )
        blu_sum = sum( sum_phases.blu )
        blu_len = len( sum_phases.blu ) * cfg.capture_count
        blu_avg = float( blu_sum ) / blu_len
        logging.info( "blu_avg = {:+}".format( blu_avg ) )
        #blu_set = int( round( blu_avg ) )
        #logging.info( "blu_set = {:+}".format( blu_set ) )

        all_sum = red_sum + wht_sum + blu_sum
        all_len = red_len + wht_len + blu_len
        all_avg = float( all_sum ) / all_len

        #! calculated adc offset setting value (all phases/channels)
        all_set = adc_offset - int( round( all_avg ) )

        adc_offset_diff = all_set - cfg.adc_offset

        logging.info( "" )
        logging.info( "----------------------------------------------" )
        logging.info( "ADC_OFFSET User Setting" )
        logging.info( "----------------------------------------------" )
        logging.info( "ADC_OFFSET (existing)   = {:+}".format( cfg.adc_offset ) )
        logging.info( "ADC_OFFSET (calculated) = {:+}".format( all_set ) )
        logging.info( "ADC_OFFSET (difference) = {:+}".format( adc_offset_diff ) )
        logging.info( "" )

        if mode == 'verify':
            ADC_OFFSET_DIFF_MARGIN = 2
            if abs( adc_offset_diff ) > ADC_OFFSET_DIFF_MARGIN:
                self.error( "ADC_OFFSET difference out of range ({!r} <= {!r} <= {!r})".format( -ADC_OFFSET_DIFF_MARGIN, adc_offset_diff, ADC_OFFSET_DIFF_MARGIN ) )

        #! set new adc offset setting, if in set mode and no errors
        if mode == 'set':
            if self.error_count != error_count:
                self.error( "can't set ADC_OFFSET due to previous errors !!" )
            else:
                self.adc_offset_test_write_setting( all_set )

    #!------------------------------------------------------------------------

    def adc_offset_test_write_setting( self, adc_offset ):

        cfg = self.config

        key = "ADC_OFFSET"
        value = adc_offset
        new_setting = '='.join( [ key, repr(value) ] )

        #! write adc offset setting to settings file
        logging.info( "write to settings file ({})".format( new_setting ) )
        cfg.settings_file_set( key="ADC_OFFSET", value=adc_offset )

        #! update config object
        cfg.adc_offset = adc_offset
        #cfg.read_settings_file()

    #!------------------------------------------------------------------------

    def adc_offset_test_run_mode_and_verify( self, mode ):
        """Run adc offset mode ('calculate' or 'set') and verify."""

        #! confirm 50 ohm  terminator is connected.
        while True:
            print( FG.CYAN + "Is 50 ohm terminator connected? (y/n)" )
            ans = sys.stdin.readline().strip().upper()
            if ans == 'Y':
                break
            elif ans == 'N':
                self.error( "50 ohm terminator not connected !!" )
                break

        if ans == 'Y':
            #! calculate and set adc offset setting
            self.adc_offset_test_run( mode=mode )

            #! verify adc offset setting
            self.adc_offset_test_run( mode='verify' )

    #!------------------------------------------------------------------------

    def adc_offset_test_set( self ):
        """Run adc offset calculation, update settings file, and verify.
        Import this app/function and call from other test apps.  e.g. prod_test."""

        self.adc_offset_test_run_mode_and_verify( mode='set' )

    #!------------------------------------------------------------------------

    def adc_offset_test( self ):
        """Top level adc offset test function.
        Run adc offset in 'calculate' or 'set' mode, the in 'verify' mode."""

        mode = self.config.adc_offset_mode

        if mode != 'set':
            mode = 'calculate'

        self.adc_offset_test_run_mode_and_verify( mode=mode )

    #!------------------------------------------------------------------------

    def test_func( self, test_num, func ):
        func_name = func.__name__ + "()"
        head = "test {}: {}".format( test_num, func_name )
        try:
            error_count = self.error_count
            func()
            if self.error_count != error_count:
                self.error( head + " failed !!")
            else:
                self.passed( head )
        except Exception:
            self.error( head + " failed to complete correctly !!" )
            raise

    #!------------------------------------------------------------------------

    def test_all( self ):
        """Run all test functions"""

        test_functions = \
        [
            self.adc_offset_test,
        ]

        for test_num, func in enumerate( test_functions, start=1 ):
            self.test_func( test_num, func )

    #!------------------------------------------------------------------------

    def main( self ):
        """Main entry for running the production tests."""

        self.test_all()


##############################################################################


def argh_main():
    """Main entry if running this module directly."""

    config = Config()

    #! override defaults with settings in user settings file.
    config.read_settings_file()

    #!
    #! override config defaults for this app.
    #!

    config.capture_mode = 'manual'

    config.show_capture_debug = True

    #!
    #! additional config settings for this app only !!
    #!

    #! adc_offset_mode = 'calculate', 'set', 'verify'
    config.adc_offset_mode = 'verify'

    #!------------------------------------------------------------------------

    @arg( '--capture_mode',             choices=['auto','manual'] )
    @arg( '--adc_polarity',             choices=['signed','unsigned'] )
    @arg( '-a', '--adc_offset', help='use this adc offset value' )
    @arg( '-p', '--phase_mode',         choices=['poly','red','white','blue'] )
    @arg( '-d', '--debug' )
    @arg( '-l', '--logging_level',      choices=['error','warning','info','debug'] )
    #! app specific config settings
    @arg( '--adc_offset_mode',          choices=['calculate','set'] )
    @arg( '-s', '--set', help="calculate and set adc offset" )
    def argh_main2(
                    capture_count           = config.capture_count,
                    capture_mode            = config.capture_mode,
                    pps_delay               = config.pps_delay,
                    adc_polarity            = config.adc_polarity.name.lower(),
                    adc_offset              = config.adc_offset,
                    show_measurements       = config.show_measurements,
                    show_capture_buffers    = config.show_capture_buffers,
                    show_capture_debug      = config.show_capture_debug,
                    phase_mode              = config.phase_mode.name.lower(),
                    debug                   = False,
                    logging_level           = config.logging_level.lower(),

                    #! app specific config settings
                    adc_offset_mode         = config.adc_offset_mode,
                    set                     = False,
                  ):

        #! override user settings file if command line argument differs.

        if capture_count != config.capture_count:
            config.set_capture_count( capture_count )

        if capture_mode != config.capture_mode:
            config.set_capture_mode( capture_mode )

        if pps_delay != config.pps_delay:
            config.set_pps_delay( pps_delay )

        if adc_polarity != config.adc_polarity.name.lower():
            config.set_adc_polarity( adc_polarity )

        if adc_offset != config.adc_offset:
            config.set_adc_offset( adc_offset )

        if show_measurements != config.show_measurements:
            config.set_show_measurements( show_measurements )

        if show_capture_buffers != config.show_capture_buffers:
            config.set_show_capture_buffers( show_capture_buffers )

        if show_capture_debug != config.show_capture_debug:
            config.set_show_capture_debug( show_capture_debug )

        if phase_mode != config.phase_mode.name.lower():
            config.set_phase_mode( phase_mode )

        if debug:
            config.peak_detect_numpy_debug  = True
            config.peak_detect_fpga_debug   = True
            config.peak_detect_debug        = True
            logging_level                   = 'debug'

        if logging_level != config.logging_level.lower():
            config.set_logging_level( logging_level )

        logging.basicConfig( level=config.logging_level )

        effective_log_level = logging.getLogger().getEffectiveLevel()
        if effective_log_level <= logging.INFO:
            config.show_all()


        #! app specific config settings

        if set:
            adc_offset_mode = 'set'

        adc_offset_mode = adc_offset_mode.lower()
        if adc_offset_mode != config.adc_offset_mode:
            config.adc_offset_mode = adc_offset_mode
            print( "INFO: `adc_offset_mode` set to {!r}".format( config.adc_offset_mode ) )

        #!--------------------------------------------------------------------

        app = ADC_Offset_App( config=config )
        app.init()
        try:
            app.main()
        except KeyboardInterrupt:
            #! ctrl+c key press.
            app.error( "KeyboardInterrupt -- exiting ..." )
        except SystemExit:
            #! sys.exit() called.
            logging.info( "SystemExit -- exiting ..." )
        except Exception as exc:
            #! An unhandled exception !!
            logging.debug( traceback.format_exc() )
            logging.info( "Exception: {}".format(exc.message) )
            app.error( "Unhandled Exception -- exiting..." )
        finally:
            logging.info( "Cleaning up." )
            app.cleanup()
            logging.info( "Done." )

    #!------------------------------------------------------------------------

    argh.dispatch_command( argh_main2 )

#!============================================================================

if __name__ == "__main__":
    argh_main()
