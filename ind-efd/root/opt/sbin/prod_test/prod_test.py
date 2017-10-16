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
import sys
import os.path
import time
import arrow
import subprocess
#import numpy as np
#import math
import colorama
from colorama import Fore as FG, Back as BG, Style as ST

#sys.path.insert(1, '/mnt/data/etc')
sys.path.append('..')
#sys.path.append('.')

import ind
from settings import SERIAL_NUMBER
from efd_config import Config

##============================================================================

class Production_Test_App(object):

    ##------------------------------------------------------------------------

    def error(self, msg):
        print(FG.RED + "ERROR: " + msg + "\n")

    def passed(self, msg):
        print(FG.GREEN + "PASS: " + msg + "\n")

    ##------------------------------------------------------------------------

    def shell_command(self, cmd):
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

        print(banner)

    ##------------------------------------------------------------------------

    def banner_end(self, err_count):
        timestamp = arrow.now()
        self.end_timestamp = timestamp
        self.end_timestamp_str = timestamp.format("YYYY-MM-DD hh:mm:ss")

        color = FG.YELLOW
        err_color = FG.GREEN if err_count == 0 else FG.RED

        banner = color \
                + "======================================================\n" \
                + "IND EFD Production Test\n" \
                + "started: {}\n".format(self.start_timestamp_str) \
                + "ended:   {}\n".format(self.end_timestamp_str) \
                + "serial number: {}\n".format(SERIAL_NUMBER) \
                + err_color \
                + "Errors: {}\n".format(err_count) \
                + color \
                + "======================================================\n"

        print(banner)

    ##------------------------------------------------------------------------

    def superuser_test(self):
        err_count = 0

        filename = '/root/prod_test_was_here.txt'
        try:
            self.shell_command('touch ' + filename)
            self.shell_command('rm ' + filename)
        except Exception as ex:
            self.error("superuser test failed !!")
            err_count += 1
            sys.exit(-1)

        return err_count

    ##------------------------------------------------------------------------

    def services_stop(self):
        err_count = 0
        #print("Stopping services...")

        ## Stop the ntp service.
        #print("Stopping chrony service...")
        try:
            self.shell_command('systemctl stop chrony')
        except Exception as ex:
            err_count += 1

        ## Stop modem being power cycled if no network connectivity.
        #print("Stopping sepl-modem service...")
        try:
            self.shell_command('systemctl stop sepl-modem')
        except Exception as ex:
            err_count += 1


        ## Stop the efd sampling, measurement, logging, posting.
        #print("Stopping efd service...")
        try:
            self.shell_command('systemctl stop efd')
        except Exception as ex:
            err_count += 1

        return err_count

    ##------------------------------------------------------------------------

    def services_start(self):
        err_count = 0
        print("Restarting services...")

        print("Restarting efd service...")
        try:
            self.shell_command('systemctl restart efd')
        except Exception as ex:
            err_count += 1

        print("Restarting sepl-modem service...")
        try:
            self.shell_command('systemctl restart sepl-modem')
        except Exception as ex:
            err_count += 1

        print("Restarting chrony service...")
        try:
            self.shell_command('systemctl restart chrony')
        except Exception as ex:
            err_count += 1

        return err_count

    ##------------------------------------------------------------------------

    def disk_usage_test(self):
        err_count = 0

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
                    err_count += 1
            elif mnt == '/boot/flash':
                #print("DEBUG: found {!r} in {!r}".format(mnt, l))
                if unit != 'M' or mag < 62 or mag > 64:
                    self.error("{!r} size not valid ({})".format(mnt, size))
                    err_count += 1
            elif mnt == '/mnt/data':
                #print("DEBUG: found {!r} in {!r}".format(mnt, l))
                if unit != 'G' or mag < 27 or mag > 29:
                    self.error("{!r} size not valid ({})".format(mnt, size))
                    err_count += 1

        return err_count

    ##------------------------------------------------------------------------

    def memory_usage_test(self):
        err_count = 0

        out = self.shell_command('free -h')
        lines = out.split('\n')
        #print(FG.CYAN +"l = {!r}".format(l))
        items = lines[1].split()
        #print("DEBUG: items={!r}".format(items))
        mem_type, size = items[0:2]
        #print("DEBUG: mem_type={!r}, size={!r}".format(mem_type, size))
        if mem_type != 'Mem:' or size != '1.0G':
            self.error("memory not valid: mem_type={!r}, size={!r}".format(mem_type, size))
            err_count += 1

        return err_count

    ##------------------------------------------------------------------------

    def usb_test(self):
        err_count = 0

        out = self.shell_command('lsusb')
        if 'Linux Foundation 2.0 root hub' not in out:
            self.error("USB root hub not found")
            err_count += 1

        return err_count

    ##------------------------------------------------------------------------

    def i2c_0_test(self):
        err_count = 0

        exp = """\
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- -- 
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
40: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
50: -- UU -- -- UU UU UU UU -- -- -- -- -- -- -- -- 
60: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
70: -- -- -- -- -- -- -- --\
""".strip()

        out = self.shell_command('i2cdetect -y -r 0').strip()
        #print("DEBUG: out={!r}".format(out))
        #print("DEBUG: exp={!r}".format(exp))
        if out != exp:
            self.error("i2c-0 device probe mismatch")
            err_count += 1

        return err_count

    ##------------------------------------------------------------------------

    def rtc_test(self):
        err_count = 0

        out = self.shell_command('hwclock')
        #print("DEBUG: out={!r}".format(out))

        return err_count

    ##------------------------------------------------------------------------

    def fpga_test(self):
        err_count = 0

        fpga_ver = ind.fpga_version_get()
        if fpga_ver.major != 2:
            self.error("Wrong FPGA version")
            err_count += 1

        return err_count

    ##------------------------------------------------------------------------

    def adc_test(self):
        err_count = 0

        self.config = Config()
        self.config.set_capture_mode('manual')

        self.dev_hand = ind.get_device_handle()

        ind.adc_capture_stop(dev_hand=self.dev_hand)

        signed = self.config.capture_data_polarity_is_signed()
        peak_detect_start_count = 0
        peak_detect_stop_count = self.config.capture_count - 1

        ind.adc_capture_start(address=0, capture_count=self.config.capture_count, delay_count=self.config.delay_count, signed=signed, peak_detect_start_count=peak_detect_start_count, peak_detect_stop_count=peak_detect_stop_count, dev_hand=self.dev_hand)


        for i in xrange(10):
            ind.adc_trigger(dev_hand=self.dev_hand)
            while True:
                sem = ind.adc_semaphore_get(dev_hand=self.dev_hand)
                if sem:
                    break
                time.sleep(0.01)

        ind.adc_capture_stop(dev_hand=self.dev_hand)

        maxmin = ind.adc_capture_maxmin_get(dev_hand=self.dev_hand)

        peak_max_red = maxmin.max_ch0_data
        peak_min_red = maxmin.min_ch0_data
        peak_max_wht = maxmin.max_ch1_data
        peak_min_wht = maxmin.min_ch1_data
        peak_max_blu = maxmin.max_ch2_data
        peak_min_blu = maxmin.min_ch2_data

        if 0:
            print("DEBUG: peak_max_red = {!r}".format(peak_max_red))
            print("DEBUG: peak_min_red = {!r}".format(peak_min_red))
            print("DEBUG: peak_max_wht = {!r}".format(peak_max_wht))
            print("DEBUG: peak_min_wht = {!r}".format(peak_min_wht))
            print("DEBUG: peak_max_blu = {!r}".format(peak_max_blu))
            print("DEBUG: peak_min_blu = {!r}".format(peak_min_blu))

        #if not (10000 < peak_max_red < 30000):
        if abs(peak_max_red) < 1000:
            self.error("ADC peak max red failed.")
            err_count += 1

        #if not (10000 < peak_max_wht < 30000):
        if abs(peak_max_wht) < 1000:
            self.error("ADC peak max wht failed.")
            err_count += 1

        #if not (10000 < peak_max_blu < 30000):
        if abs(peak_max_blu) < 1000:
            self.error("ADC peak max blu failed.")
            err_count += 1

        #if not (-30000 < peak_min_red < -10000):
        if abs(peak_min_red) < 1000:
            self.error("ADC peak min red failed.")
            err_count += 1

        #if not (-30000 < peak_min_wht < -10000):
        if abs(peak_min_wht) < 1000:
            self.error("ADC peak min wht failed.")
            err_count += 1

        #if not (-30000 < peak_min_blu < -10000):
        if abs(peak_min_blu) < 1000:
            self.error("ADC peak min blu failed.")
            err_count += 1

        return err_count

    ##------------------------------------------------------------------------

    def blinky_test(self):
        err_count = 0

        print(FG.CYAN + "Please check all LEDs are working...")
        ind.blinky(count=1, delay=0.5)
        print(FG.CYAN + "Did all LEDs illuminate? (y/n)")
        ans = sys.stdin.readline().strip().upper()
        if ans != 'Y':
            self.error("Blinky failed")
            err_count += 1

        return err_count

    ##------------------------------------------------------------------------

    def ttyS1_test(self):
        err_count = 0

        print(FG.CYAN + "Connect XBee serial adapter...")
        time.sleep(1)
        print(FG.CYAN + "Press enter and check for login prompt...")
        time.sleep(1)
        print(FG.CYAN + "Did the login prompt respond? (y/n)")
        ans = sys.stdin.readline().strip().upper()
        if ans != 'Y':
            self.error("ttyS1 test failed")
            err_count += 1

        return err_count

    ##------------------------------------------------------------------------

    def test_func(self, fn):
        err_count = 0

        try:
            err_count = fn()
            msg = fn.__name__ + "()"
            self.passed(msg)
        except Exception as ex:
            msg = "test function '" + fn.__name__ + "() failed !!"
            self.error(msg)
            err_count += 1

        return err_count

    ##------------------------------------------------------------------------

    def main(self):
        """Main entry for running the produciton tests."""

        err_count = 0

        colorama.init(autoreset=True)

        self.banner_start()

        err_count += self.test_func( self.superuser_test )
        err_count += self.test_func( self.services_stop )
        err_count += self.test_func( self.disk_usage_test )
        err_count += self.test_func( self.memory_usage_test )
        err_count += self.test_func( self.usb_test )
        err_count += self.test_func( self.i2c_0_test )
        err_count += self.test_func( self.rtc_test )
        err_count += self.test_func( self.fpga_test )
        err_count += self.test_func( self.adc_test )
        err_count += self.test_func( self.blinky_test )
        err_count += self.test_func( self.ttyS1_test )
        #err_count += self.test_func( self.services_start )

        self.banner_end(err_count)
        print

##============================================================================

def argh_main():
    """Main entry if running this module directly."""

    app = Production_Test_App()

    try:
        app.main()
    except (KeyboardInterrupt):
        ## ctrl+c key press.
        print("KeyboardInterrupt -- exiting ...")
    except (SystemExit):
        ## sys.exit() called.
        print("SystemExit -- exiting ...")
    finally:
        print(ST.RESET_ALL)
        print("Cleaning up.")
        print("Done.  Exiting.")

##============================================================================

if __name__ == "__main__":
    argh.dispatch_command(argh_main)

