#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''
This script is used to test production boards off the assembly line.
It assumes that it has been powered up and all voltage rails tested.
'''

import argh
from argh import arg

import sys
import os.path
import time
import arrow
import subprocess
import logging
import traceback

import colorama
from colorama import Fore as FG, Back as BG, Style as ST

import re
from tee import StdoutTee, StderrTee

#import numpy as np
#import math

#sys.path.insert(1, '/opt/sbin')
#sys.path.insert(1, '/mnt/data/etc')
#sys.path.append('.')
#sys.path.append('..')
sys.path.append('/opt/sbin')
#sys.path.append('/mnt/data/etc')

import ind
from settings import SERIAL_NUMBER
from efd_config import Config

#!============================================================================
#! Filter function to remove control characters (ansi colours) from a string
#! Used when redirecting stdout to a file using Tee.StdoutTee
#!============================================================================
def _remove_control_chars( message ):
    """Remove control characters (ansi colours) from a string."""

    msg = re.sub( r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]', "", message )
    return msg



class MyStdoutTee( StdoutTee ):
    """Override StdoutTee to support no file logging if filename is ''.
    i.e. output to stdout only
    """

    def __init__( self, *args , **kwargs ):
        #! default to remove control chars from file output
        ff = kwargs.get( 'file_filters', [ _remove_control_chars ] )
        kwargs[ 'file_filters' ] = ff

        StdoutTee.__init__( self, *args, **kwargs )

    def write( self, message ):
        try:
            StdoutTee.write( self, message )
        except AttributeError:
            pass

    def __enter__( self ):
        try:
            StdoutTee.__enter__( self )
        except IOError:
            pass

##============================================================================

class Production_Test_App(object):

    error_count = 0
    pass_count  = 0

    ##------------------------------------------------------------------------

    def __init__( self, config ):
        self.config = config

    ##------------------------------------------------------------------------

    ## TODO: could put in base class IND_App ??
    def init( self ):
        """Initialise the app"""

        #colorama.init()
        colorama.init( autoreset=True )
        #colorama.init( autoreset=True, wrap=False )
        #colorama.init( wrap=False )

        self.banner_start()
        self.superuser_test()
        self.services_stop()

    ##------------------------------------------------------------------------

    ## TODO: could put in base class IND_App ??
    def cleanup( self ):
        """Cleanup the app on exit"""

        #self.services_start()
        self.banner_end()

    ##------------------------------------------------------------------------

    def error(self, msg):
        print(FG.RED + "ERROR: " + msg + "\n")
        self.error_count += 1

    def passed(self, msg):
        print(FG.GREEN + "PASS: " + msg + "\n")
        self.pass_count += 1

    ##------------------------------------------------------------------------

    def shell_command(self, cmd):
        """Return output of an executable, which is executed in a shell."""

        ret = None
        try:
            ret = subprocess.check_output(cmd, shell=True)
        except Exception as ex:
            self.error(ex.message)
            raise

        return ret

    ##------------------------------------------------------------------------

    def banner_start(self):

        timestamp = arrow.now()
        self.start_timestamp = timestamp
        self.start_timestamp_str = timestamp.format("YYYY-MM-DD hh:mm:ss")

        banner = "\n\n\n" + FG.YELLOW \
                + "======================================================\n" \
                + "IND EFD Production Test\n" \
                + "started: {}\n".format(self.start_timestamp_str) \
                + "serial number: {}\n".format(SERIAL_NUMBER) \
                + "======================================================\n"

        print( ST.RESET_ALL )
        print( banner )
        print( ST.RESET_ALL )

    ##------------------------------------------------------------------------

    def banner_end(self):

        timestamp = arrow.now()
        self.end_timestamp = timestamp
        self.end_timestamp_str = timestamp.format("YYYY-MM-DD hh:mm:ss")

        color = FG.YELLOW
        err_color = FG.GREEN if self.error_count == 0 else FG.RED

        banner = color \
                + "======================================================\n" \
                + "IND EFD Production Test\n" \
                + "started: {}\n".format(self.start_timestamp_str) \
                + "ended:   {}\n".format(self.end_timestamp_str) \
                + "serial number: {}\n".format(SERIAL_NUMBER) \
                + err_color \
                + "Errors: {}\n".format(self.error_count) \
                + color \
                + "======================================================\n"

        print( ST.RESET_ALL )
        print( banner )
        print( ST.RESET_ALL )

    ##------------------------------------------------------------------------

    def superuser_test(self):

        filename = '/root/prod_test_was_here.txt'
        try:
            self.shell_command('touch ' + filename)
            self.shell_command('rm ' + filename)
        except Exception as ex:
            self.error("superuser test failed !!")
            sys.exit(-1)

    ##------------------------------------------------------------------------

    def services_stop(self):

        #print("Stopping services...")

        ## Stop the ntp service.
        #print("Stopping chrony service...")
        try:
            self.shell_command('systemctl stop chrony')
        except Exception as ex:
            self.error("stopping chrony service failed !!")

        ## Stop modem being power cycled if no network connectivity.
        #print("Stopping sepl-modem service...")
        try:
            self.shell_command('systemctl stop sepl-modem')
        except Exception as ex:
            self.error("stopping sepl-modem service failed !!")

        ## Stop the efd sampling, measurement, logging, posting.
        #print("Stopping efd service...")
        try:
            self.shell_command('systemctl stop efd')
        except Exception as ex:
            self.error("stopping efd service failed !!")

    ##------------------------------------------------------------------------

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

    ##------------------------------------------------------------------------

    def disk_usage_test(self):

        out = self.shell_command('df -h')
        lines = out.split('\n')
        for l in lines[1:]:
            if not l:
                continue
            #print(FG.CYAN +"l = {!r}".format(l))
            items = l.split()
            #print("DEBUG: items={!r}".format(items))
            mnt = items[5]
            size = items[1]
            unit = size[-1]
            mag = float(size[:-1])
            #print("DEBUG: mnt={!r}, size={!r}, mag={!r}, unit={!r}".format(mnt, size, mag, unit))
            if mnt == '/':
                #print("DEBUG: found {!r} in {!r}".format(mnt, l))
                if unit != 'M' or mag < 970 or mag > 980:
                    self.error("{!r} size not valid ({})".format(mnt, size))
            elif mnt == '/boot/flash':
                #print("DEBUG: found {!r} in {!r}".format(mnt, l))
                if unit != 'M' or mag < 62 or mag > 64:
                    self.error("{!r} size not valid ({})".format(mnt, size))
            elif mnt == '/mnt/data':
                #print("DEBUG: found {!r} in {!r}".format(mnt, l))
                if unit != 'G' or mag < 27 or mag > 29:
                    self.error("{!r} size not valid ({})".format(mnt, size))

    ##------------------------------------------------------------------------

    def memory_usage_test(self):

        out = self.shell_command('free -h')
        lines = out.split('\n')
        #print(FG.CYAN +"l = {!r}".format(l))
        items = lines[1].split()
        #print("DEBUG: items={!r}".format(items))
        mem_type, size = items[0:2]
        #print("DEBUG: mem_type={!r}, size={!r}".format(mem_type, size))
        if ( mem_type != 'Mem:' ) or ( '1.0G' not in size ):
            self.error("memory not valid: mem_type={!r}, size={!r}".format(mem_type, size))

    ##------------------------------------------------------------------------

    def usb_test(self):

        out = self.shell_command('lsusb')
        if 'Linux Foundation 2.0 root hub' not in out:
            self.error("USB root hub not found")

    ##------------------------------------------------------------------------

    def i2c_0_test( self ):

        exp = \
            "     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f\n"   \
            "00:          -- -- -- -- -- -- -- -- -- -- -- -- -- \n"  \
            "10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- \n"  \
            "20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- \n"  \
            "30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- \n"  \
            "40: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- \n"  \
            "50: -- UU -- -- UU UU UU UU -- -- -- -- -- -- -- -- \n"  \
            "60: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- \n"  \
            "70: -- -- -- -- -- -- -- --                         \n"                           \

        out = self.shell_command( 'i2cdetect -y -r 0' )

        #print( "DEBUG: out={!r}".format( out ) )
        #print( "DEBUG: exp={!r}".format( exp ) )

        if out != exp:
            self.error( "i2c-0 device probe mismatch" )

    ##------------------------------------------------------------------------

    def rtc_test(self):

        try:
            out = self.shell_command('hwclock')
            #print("DEBUG: out={!r}".format(out))
        except Exception as ex:
            self.error("hwclock command failed")

    ##------------------------------------------------------------------------

    def fpga_test(self):

        self.dev_hand = ind.get_device_handle()

        ## NOTE: resetting causes first maxmin values to be all zero for some reason !!
        #ind.fpga_reset(dev_hand=self.dev_hand)

        fpga_ver = ind.fpga_version_get(dev_hand=self.dev_hand)
        if fpga_ver.major != 2:
            self.error("Wrong FPGA version")

    ##------------------------------------------------------------------------

    def adc_test(self):

        #! confirm signal generated is connected and setup correctly.
        while True:
            msg = FG.CYAN + "Setup signal generator => 5Vpp, 5V offset, 1MHz sine input"
            #msg = FG.CYAN + "Setup signal generator => 10Vpp 1MHz sine input"
            #msg = FG.CYAN + "Setup signal generator => 5V 25Hz 1% duty pulse input"
            print( msg )
            print( FG.CYAN + "Is signal generator setup correctly? (y/n)" )
            ans = sys.stdin.readline().strip().upper()
            if ans == 'Y':
                break
            elif ans == 'N':
                self.error( "signal generator not setup correctly !!" )
                return

        cfg = self.config

        cfg.set_capture_mode('manual')

        self.dev_hand = ind.get_device_handle()

        ## NOTE: resetting causes first maxmin values to be all zero for some reason !!
        #ind.fpga_reset( dev_hand=self.dev_hand )

        #ind.adc_capture_stop( dev_hand=self.dev_hand )

        self.prev_bank  = 1
        self.bank       = 0

        capture_mode            = 'manual'
        signed                  = cfg.adc_polarity_is_signed()
        peak_detect_start_count = 0
        peak_detect_stop_count  = cfg.capture_count - 1

        ind.adc_capture_start( address                  = 0,
                               capture_count            = cfg.capture_count,
                               delay_count              = cfg.delay_count,
                               capture_mode             = capture_mode,
                               signed                   = signed,
                               peak_detect_start_count  = peak_detect_start_count,
                               peak_detect_stop_count   = peak_detect_stop_count,
                               adc_offset               = cfg.adc_offset,
                               phase_mode               = cfg.phase_mode,
                               dev_hand                 = self.dev_hand
                            )

        #! TODO: make this a config setting
        repetitions = 1
        #repetitions = 3
        #repetitions = 11
        #repetitions = 111

        sem = 0

        for i in xrange( repetitions ):

            logging.info( "Trigger ADC capture" )
            ind.adc_semaphore_set( 0, dev_hand=self.dev_hand )
            ind.adc_trigger( dev_hand=self.dev_hand )

            timeout = time.time() + 1
            while True:
                sem = ind.adc_semaphore_get( dev_hand=self.dev_hand )
                if sem:
                    #print( "OK: waiting for adc semaphore" )
                    break
                if time.time() > timeout:
                    self.error( "TIMEOUT: waiting for adc semaphore" )
                    break
                time.sleep( 0 )

        if not sem:
            return

        #!
        #! Retrieve info from driver.
        #!
        #maxmin_normal = ind.adc_capture_maxmin_normal_get( dev_hand=self.dev_hand )
        capture_info_lst = ind.adc_capture_info_list_get( dev_hand=self.dev_hand )

        #!
        #! Synchronise DMA capture memory.
        #!
        logging.info( "Synchronising capture memory..." )
        ind.dma_mem_sync_bank( self.bank, dev_hand=self.dev_hand )

        capture_info_prev = capture_info_lst[ self.prev_bank ]
        capture_info      = capture_info_lst[ self.bank ]
        logging.debug( "" )
        logging.debug( "capture_info_prev = {!r}\n".format( capture_info_prev ) )
        logging.debug( "capture_info      = {!r}\n".format( capture_info ) )

        maxmin_normal   = capture_info.maxmin_normal
        maxmin_squared  = capture_info.maxmin_squared
        #adc_clock_count_per_pps = capture_info.adc_clock_count_per_pps

        peak_max_red = maxmin_normal.max_ch0_data
        peak_min_red = maxmin_normal.min_ch0_data
        peak_max_wht = maxmin_normal.max_ch1_data
        peak_min_wht = maxmin_normal.min_ch1_data
        peak_max_blu = maxmin_normal.max_ch2_data
        peak_min_blu = maxmin_normal.min_ch2_data

        logging.info( "peak_max_red = {!r}".format( peak_max_red ) )
        logging.info( "peak_min_red = {!r}".format( peak_min_red ) )
        logging.info( "peak_max_wht = {!r}".format( peak_max_wht ) )
        logging.info( "peak_min_wht = {!r}".format( peak_min_wht ) )
        logging.info( "peak_max_blu = {!r}".format( peak_max_blu ) )
        logging.info( "peak_min_blu = {!r}".format( peak_min_blu ) )

        #! Signals applied at RF board inputs
        #!--------------------------------------------------------------------
        #! Digilent Analog Discovery 2:
        #!   10Vpp 1MHz sine input              => max is ~ +18000, min is ~ -14000
        #!   5V 25Hz 1% duty pulse input        => max is ~ +17700, min is ~ -15900
        #! RIGOL DG1022 Signal Generator:
        #!    5Vpp, 0V offset, 1MHz sine input  => max is ~ +12430, min is ~ -9760
        #!    5Vpp, 5V offset, 1MHz sine input  => max is ~ +13490, min is ~ -13470
        #!   5V 25Hz 1% duty pulse input        => max is ~ +19200, min is ~ -18800
        #!--------------------------------------------------------------------
        exp_max =  13490
        exp_min = -13470
        tolerance = int( exp_max * 0.05 )

        exp_max_lo = exp_max - tolerance
        exp_max_hi = exp_max + tolerance
        exp_min_lo = exp_min - tolerance
        exp_min_hi = exp_min + tolerance

        if not (exp_max_lo < peak_max_red < exp_max_hi):
            self.error( "ADC peak max red failed ({!r} <= {!r} <= {!r})".format( exp_max_lo, peak_max_red, exp_max_hi ) )

        if not (exp_max_lo < peak_max_wht < exp_max_hi):
            self.error( "ADC peak max wht failed ({!r} <= {!r} <= {!r})".format( exp_max_lo, peak_max_wht, exp_max_hi ) )

        if not (exp_max_lo < peak_max_blu < exp_max_hi):
            self.error( "ADC peak max blu failed ({!r} <= {!r} <= {!r})".format( exp_max_lo, peak_max_blu, exp_max_hi ) )

        if not (exp_min_lo < peak_min_red < exp_min_hi):
            self.error( "ADC peak min red failed ({!r} <= {!r} <= {!r})".format( exp_min_lo, peak_min_red, exp_min_hi ) )

        if not (exp_min_lo < peak_min_wht < exp_min_hi):
            self.error( "ADC peak min wht failed ({!r} <= {!r} <= {!r})".format( exp_min_lo, peak_min_wht, exp_min_hi ) )

        if not (exp_min_lo < peak_min_blu < exp_min_hi):
            self.error( "ADC peak min blu failed ({!r} <= {!r} <= {!r})".format( exp_min_lo, peak_min_blu, exp_min_hi ) )

        ind.adc_capture_stop( dev_hand=self.dev_hand )

    ##------------------------------------------------------------------------

    def blinky_test(self):

        while True:
            print(FG.CYAN + "Please check all LEDs are working...")
            time.sleep(1)
            ind.blinky(count=2, delay=0.2)
            print(FG.CYAN + "Did all LEDs illuminate? (y/n)")
            ans = sys.stdin.readline().strip().upper()
            if ans == 'Y':
                break
            elif ans == 'N':
                self.error("Blinky failed")
                break

    ##------------------------------------------------------------------------

    def ttyS1_test(self):

        delay = 0.5
        while True:
            print(FG.CYAN + "Connect XBee serial adapter...")
            print(FG.CYAN + "Press enter and check for login prompt...")
            print(FG.CYAN + "Did the login prompt respond? (y/n)")
            ans = sys.stdin.readline().strip().upper()
            if ans == 'Y':
                break
            elif ans == 'N':
                self.error("ttyS1 test failed")
                break

    ##------------------------------------------------------------------------

    def adc_offset_test( self ):
        """Set ADC offset ii import and run the adc_offset app."""

        from adc_offset import ADC_Offset_App

        app = ADC_Offset_App( config=self.config )

        try:
            #app.init()
            #app.main()
            app.adc_offset_test_set()
        finally:
            #app.cleanup()
            pass

    ##------------------------------------------------------------------------

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

    ##------------------------------------------------------------------------

    def test_all( self ):
        """Run all test functions."""

        test_functions = \
        [
            self.disk_usage_test,
            self.memory_usage_test,
            self.usb_test,
            self.i2c_0_test,
            self.rtc_test,
            self.fpga_test,
            self.adc_offset_test,
            self.adc_test,
            self.blinky_test,
            self.ttyS1_test,
        ]

        for test_num, func in enumerate( test_functions, start=1 ):
            self.test_func( test_num, func )

    ##------------------------------------------------------------------------

    def main(self):
        """Main entry for running the production tests."""

        self.test_all()


##############################################################################


def argh_main():
    """Main entry if running this module directly."""

    config = Config()

    #! override defaults with settings in user settings file.
    config.read_settings_file()

    #!
    #! override config defaults this app.
    #!

    config.capture_mode             = 'manual'

    config.show_capture_debug       = True

    #!
    #! additional config items for this app only !!
    #!

    #!------------------------------------------------------------------------

    @arg( '--capture_mode',             choices=['auto','manual'] )
    @arg( '--adc_polarity',             choices=['signed','unsigned'] )
    @arg( '-a', '--adc_offset', help='use this adc offset value' )
    @arg( '-p', '--phase_mode',         choices=['poly','red','white','blue'] )
    @arg( '-d', '--debug' )
    @arg( '-l', '--logging_level',      choices=['error','warning','info','debug'] )
    #! app specific config settings
    @arg( '-o', '--output_filename', help="append stdout to this file" )
    def argh_main2( capture_count           = config.capture_count,
                    capture_mode            = config.capture_mode,
                    pps_delay               = config.pps_delay,
                    adc_polarity            = config.adc_polarity.name.lower(),
                    adc_offset              = config.adc_offset,
                    show_measurements       = config.show_measurements,
                    show_capture_buffers    = config.show_capture_buffers,
                    show_capture_debug      = config.show_capture_debug,
                    phase_mode              = config.phase_mode.name.lower(),
                    debug                   = False,
                    logging_level           = config.logging_level,
                    #! app specific config settings
                    output_filename         = '',
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

        #!--------------------------------------------------------------------
        #! run the app
        #!--------------------------------------------------------------------

        #! redirect stdout to a file (as well as to stdout)
        #stdout_tee = MyStdoutTee( output_filename, file_filters=[ _remove_control_chars ] )
        stdout_tee = MyStdoutTee( output_filename )

        with stdout_tee:
            app = Production_Test_App( config=config )
            try:
                app.init()
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
                logging.info( "Exception: {}".format( exc.message ) )
                app.error( "Unhandled Exception -- exiting..." )
            finally:
                logging.info( "Cleaning up." )
                app.cleanup()
                logging.info( "Done." )

    #!------------------------------------------------------------------------

    argh.dispatch_command( argh_main2 )

##============================================================================

if __name__ == "__main__":
    argh_main()

