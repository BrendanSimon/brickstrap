#!/usr/bin/env python2

##############################################################################
##
##  Author:     Successful Endeavours Pty Ltd
##
##############################################################################

'''
This module retrieves weather parameters from a weather station.
Support weather stations are:
    * Vaisala Weather Transmitter WXT520
'''

import ind

## =========================================
## Weather Station Output - composite output
## =========================================
##
## 0R0,Ta=24.9C,Ua=38.1P,Ri=0.0M
## 0R0,Ta=24.9C,Ua=38.1P,Ri=0.0M
## 0R0,Ta=24.9C,Ua=38.1P,Ri=0.0M
## 0R0,Ta=24.9C,Ua=38.1P,Ri=0.0M
##
## =======================================
## Weather Station Output - default output
## =======================================
##
## 0TX,Start-up
## 0R5,Th=25.4C,Vh=0.0#,Vs=14.3V,Vr=3.491V
## 0R2,Ta=25.0C,Ua=38.4P,Pa=1008.1H
## 0TX,Start-up
## 0R5,Th=25.4C,Vh=0.0#,Vs=14.3V,Vr=3.491V
## 0R2,Ta=25.0C,Ua=39.9P,Pa=1008.2H
## 0R1,Dn=000#,Dm=000#,Dx=000#,Sn=0.0#,Sm=0.0#,Sx=0.0#
## 0R1,Dn=000#,Dm=000#,Dx=000#,Sn=0.0#,Sm=0.0#,Sx=0.0#
## 0R3,Rc=0.00M,Rd=10s,Ri=0.1M,Hc=0.0M,Hd=0s,Hi=0.0M
## 0R1,Dn=000#,Dm=000#,Dx=000#,Sn=0.0#,Sm=0.0#,Sx=0.0#
## 0R5,Th=25.0C,Vh=0.0#,Vs=14.4V,Vr=3.480V
## 0R1,Dn=000#,Dm=000#,Dx=000#,Sn=0.0#,Sm=0.0#,Sx=0.0#
## 0R3,Rc=0.00M,Rd=10s,Ri=0.1M,Hc=0.0M,Hd=0s,Hi=0.0M
## 0R1,Dn=000#,Dm=000#,Dx=000#,Sn=0.0#,Sm=0.0#,Sx=0.0#
## 0R1,Dn=000#,Dm=000#,Dx=000#,Sn=0.0#,Sm=0.0#,Sx=0.0#Z
## 0R3,Rc=0.00M,Rd=10s,Ri=0.1M,Hc=0.0M,Hd=0s,Hi=0.0M
## 0R5,Th=25.2C,Vh=0.0#,Vs=14.4V,Vr=3.480V
##
## =======================================


import sys
#import os.path
import time
import select
import serial
#from collections import namedtuple
import threading
import re


## Serial port implemented in Zynq FPGA, registered as /dev/ttyS0.
DEV_NAME = '/dev/ttyS0'
BAUD_RATE = 19200

##============================================================================

class Weather_Station_Thread(threading.Thread):

    ##------------------------------------------------------------------------

    def __init__(self):
        threading.Thread.__init__(self)

        self.weather_station = Weather_Station() #starting the stream of info
        self.running = True #setting the thread running to true

    ##------------------------------------------------------------------------

    def run(self):
        self.weather_station.configure()

        while self.running:
            self.weather_station.wait_and_process() #this will continue to loop, wait for data, and process it.

        self.weather_station.cleanup()

    ##------------------------------------------------------------------------

    def cleanup(self):
        print('INFO: Weather_Thread: Cleaning up ...')
        self.running = False
        self.join()
        print('INFO: Weather_Thread: Done.')

##============================================================================

## regular expression to match 'Ta=' + non-whitespace-chars + (comma or whitespace-char or eol).
temperature_regex = re.compile(r'Ta=(?P<temperature>\S*?)(?:,|\s|$)')

## regular expression to match 'Ua=' + non-whitespace-chars + (comma or whitespace-char or eol).
humidity_regex = re.compile(r'Ua=(?P<humidity>\S*?)(?:,|\s|$)')

## regular expression to match 'Ri=' + non-whitespace-chars + (comma or whitespace-char or eol).
rain_intensity_regex = re.compile(r'Ri=(?P<rain_intensity>\S*?)(?:,|\s|$)')

##----------------------------------------------------------------------------

def extract_temperature(s):
    '''return temperature field from input string, or null string.'''
    m = temperature_regex.search(s)
    if m:
        #print("DEBUG: found regex match, group() = {!r}".format(m.group()))
        temperature = m.group('temperature')
        #print("DEBUG: temperature = {!r}".format(temperature))
    else:
        temperature = ''

    return temperature

##----------------------------------------------------------------------------

def extract_humidity(s):
    '''return humidity field from input string, or null string.'''
    m = humidity_regex.search(s)
    if m:
        #print("DEBUG: found regex match, group() = {!r}".format(m.group()))
        humidity = m.group('humidity')
        #print("DEBUG: humidity = {!r}".format(humidity))
    else:
        humidity = ''

    return humidity

##----------------------------------------------------------------------------

def extract_rain_intensity(s):
    '''return rain_intensity field from input string, or null string.'''
    m = rain_intensity_regex.search(s)
    if m:
        #print("DEBUG: found regex match, group() = {!r}".format(m.group()))
        rain_intensity = m.group('rain_intensity')
        #print("DEBUG: rain_intensity = {!r}".format(rain_intensity))
    else:
        rain_intensity = ''

    return rain_intensity

##============================================================================

class Weather_Station(object):

    select_timeout = 1

    serial_timeout = 0.1

    ##------------------------------------------------------------------------

    def __init__(self, ser_dev_name=DEV_NAME, baudrate=BAUD_RATE):

        self.ser_dev_name = None
        self.ser_dev_hand = None

        self.ind_dev_hand = None

        self.init(ser_dev_name=ser_dev_name)

    ##------------------------------------------------------------------------

    def init(self, ser_dev_name=DEV_NAME, baudrate=BAUD_RATE):

        self.cleanup()

        self.ser_dev_name = ser_dev_name
        #self.ser_dev_hand = open(ser_dev_name, 'r+b')
        self.ser_dev_hand = serial.Serial(port=ser_dev_name, baudrate=baudrate,
                                      #parity=serial.PARITY_ODD,
                                      #stopbits=serial.STOPBITS_TWO,
                                      #bytesize=serial.SEVENBITS,
                                      timeout=self.serial_timeout
                                     )

        self.ind_dev_hand = ind.get_device_handle()

        ## Measurement data.
        self.temperature = '0'
        self.humidity = '0'
        self.rain_intensity = '0'

    ##------------------------------------------------------------------------

    def cleanup(self):

        if self.ind_dev_hand:
            self.ind_dev_hand.close()
            self.ind_dev_hand = None

        if self.ser_dev_hand:
            self.ser_dev_hand.close()
            self.ser_dev_hand = None

    ##------------------------------------------------------------------------

    def configure(self):
        '''Configure the weather station to report only what we need.'''
        '''  - temperature, humidity, rain intensity, every one second.'''

        ## List of commands to run to configure the weather station.
        config_commands = [

            ##
            ## Temperature, Humidity, Pressure settings.
            ##
            #'0TU,R=0000000001010000,I=1,P=H,T=C,N=T\r\n',
            ## Set temperature and humidity read interval to 1.
            '0TU,R=0000000001010000,I=1,P=H,T=C\r\n',

            ##
            ## Wind settings.
            ##
            #'0WU,R=0000000000000000,I=3600,A=3,G=1,U=M,D=O,N=W,F=4\r\n',
            ## Disable wind reporting.
            '0WU,R=0000000000000000,I=3600\r\n',

            ##
            ## Precipitation settings.
            ##
            #'0RU,R=0000000000100000,I=1,U=M,S=M,M=R,Z=M,X=10000,Y=100\r\n',
            ## Set Rain Intensity read interval to 1.
            '0RU,R=0000000000100000,I=1,M=T\r\n',

            ##
            ## Supervisory settings.
            ##
            #'0SU,R=0000000000000000,I=3600,S=Y,H=N\r\n',
            ## Disable supervisory reporting.
            '0SU,R=0000000000000000,I=3600\r\n',

            ##
            ## Communications settings.
            ##
            #'0XU,A=0,M=A,T=0,C=2,I=1,B=19200,D=8,P=N,S=1,L=25,N=WXT520\r\n',
            ## Set composite data inverval to 1 second.
            '0XU,I=1\r\n',

            ## Reset unit.
            '0XZ\r\n',
            ]

        for cmd in config_commands:
            #print("INFO: Weather Station command = {!r}".format(cmd))
            self.ser_dev_hand.write(cmd)
            time.sleep(0.1)

    ##------------------------------------------------------------------------

    def weather_led_off(self):
        ind.weather_led_off(dev_hand=self.ind_dev_hand)

    def weather_led_on(self):
        ind.weather_led_on(dev_hand=self.ind_dev_hand)

    def weather_led_toggle(self):
        ind.weather_led_toggle(dev_hand=self.ind_dev_hand)

    ##------------------------------------------------------------------------

    def wait_and_process(self):
        '''wait for data and process it.'''

        #self.weather_led_off()

        r = select.select([self.ser_dev_hand], [], [], self.select_timeout)
        #print("DEBUG: r = {!r}".format(r))
        if not r[0]:
            #print("DEBUG: TIMEOUT: wait_and_process")
            return

        #self.weather_led_on()
        self.weather_led_toggle()

        ## Composite data output format.
        ## 0R0,Ta=24.9C,Ua=38.1P,Ri=0.0M
        ## Default data output format.
        ## 0R2,Ta=25.0C,Ua=39.9P,Pa=1008.2H
        ## 0R3,Rc=0.00M,Rd=10s,Ri=0.1M,Hc=0.0M,Hd=0s,Hi=0.0M

        #print
        #print("DEBUG: Weather Data Captured")
        #print("----------------------------")

        for s in self.ser_dev_hand.readlines():
            #print("INFO: Weather Station Received: {}".format(s))

            temperature = extract_temperature(s)
            if temperature:
                self.temperature = temperature

            humidity = extract_humidity(s)
            if humidity:
                self.humidity = humidity

            rain_int = extract_rain_intensity(s)
            if rain_int:
                self.rain_intensity = rain_int

##============================================================================

def main():
    """Main entry if running this module directly."""

    ws_thread = Weather_Station_Thread()
    ws_info = ws_thread.weather_station

    #ws_thread.init()
    ws_thread.start()
    delay = 3
    try:
        while True:
            print('Sleeping for {} seconds'.format(delay))
            time.sleep(delay)

            print
            print('----------------------------------------')
            print('temperature    : {}'.format(ws_info.temperature))
            print('humidity       : {}'.format(ws_info.humidity))
            print('rain intensity : {}'.format(ws_info.rain_intensity))
            print('----------------------------------------')

    except (KeyboardInterrupt, SystemExit):
        ## ctrl+c key press or sys.exit() called.
        print("EXCEPTION: KeyboardInterrupt or SystemExit")
    finally:
        print("Nearly done ...")
        ws_thread.cleanup()

    print "Done.\nExiting."

##============================================================================

def test_case():

    ## Composite data output format.
    ## 0R0,Ta=24.9C,Ua=38.1P,Ri=0.0M
    ## Default data output format.
    ## 0R2,Ta=25.0C,Ua=39.9P,Pa=1008.2H
    ## 0R3,Rc=0.00M,Rd=10s,Ri=0.1M,Hc=0.0M,Hd=0s,Hi=0.0M

    print
    print("DEBUG: Weather Data Captured")
    print("----------------------------")

    lines = [
        '0R0,Ta=24.9C,Ua=38.1P,Ri=0.0M',
        '0R0,Ta=24.9C,Ua=38.1P,Ri=0.0M\r\n',
        '0R2,Ta=25.0C,Ua=39.9P,Pa=1008.2H',
        '0R3,Rc=0.00M,Rd=10s,Ri=0.1M,Hc=0.0M,Hd=0s,Hi=0.0M',
        'XXX,Ta=33.0C',
        'Ta=44.0C',
        'Ta=55.0C,XXX',
        ]

    for s in lines:
        print("line: {!r}".format(s))
        temperature = extract_temperature(s)
        humidity = extract_humidity(s)
        rain_int = extract_rain_intensity(s)

        if temperature:
            print("DEBUG: temperature = {!r}".format(temperature))

        if humidity:
            print("DEBUG: humidity = {!r}".format(humidity))

        if rain_int:
            print("DEBUG: rain_intensity = {!r}".format(rain_int))

        print

    #sys.exit(0)

##============================================================================

if __name__ == "__main__":
    test_case()
    main()

