#!/usr/bin/env python2

##############################################################################
#!
#!  Author:     Successful Endeavours Pty Ltd
#!
##############################################################################

'''
This module contains a class to manage measurement logs.
'''

import argh
import time

import sensors          #! python interface to lmsensors via ctypes.

#!============================================================================

class Sensor(object):
    '''Manage an idividual sensor'''

    def __init__(self, sensor, scale=1.0):
        self.init(sensor, scale)

    def init(self, sensor, scale=1.0):
        '''Runtime intialisation method.'''
        self.sensor = sensor
        self.scale = scale
        
    def read(self):
        return self.sensor.get_value() * self.scale
        
#!============================================================================

class Sensors(object):
    '''Manage EFD sensors (via lmsensors).'''

    def __init__(self):
        #self.batt_scale = (100.0 + 18.0) / 18.0
        self.batt_scale = (680.0 + 110.0) / 110.0
        self.supp_scale = (680.0 + 110.0) / 110.0
        self.init()

    def cleanup(self):
        sensors.cleanup()
        
    def init(self):
        '''Runtime intialisation method.'''
        self.box_temperature_sensor = None
        self.battery_sensor = None
        self.supply_sensor = None
        
        self.cleanup()
        sensors.init()
        
        #! Search for EFD sensors
        for chip in sensors.iter_detected_chips():
            #print("DEBUG: chip = {!r}".format(chip))
            for feature in chip:
                #print("DEBUG: feature = {!r}".format(feature))
                chip_str = str(chip)
                if chip_str.startswith("lm75") and chip.addr == 0x48 and feature.name == "temp1":
                    self.box_temperature_sensor = Sensor(feature)
                elif chip_str.startswith("mcp3021") and chip.addr == 0x4d and feature.name == "in0":
                    self.battery_sensor = Sensor(feature, scale=self.batt_scale)
                elif chip_str.startswith("mcp3021") and chip.addr == 0x4e and feature.name == "in0":
                    self.supply_sensor = Sensor(feature, scale=self.supp_scale)
        
    def battery_voltage(self):
        return self.battery_sensor.read()
        
    def supply_voltage(self):
        return self.supply_sensor.read()

    ## note: the solar variant has it's voltage terminals accross the
    ## note: battery.  i.e. it's the same value as the battery voltage.
    def solar_voltage(self):
        return self.battery_voltage()
        
    def box_temperature(self):
        return self.box_temperature_sensor.read()
        
#!============================================================================

def app_main():
    """Main entry if running this module directly."""

    print(__name__)
    sensors = Sensors()
    #sensors.init()
    
    for i in range(100):
        time.sleep(1)
        temp  = sensors.box_temperature()
        batt  = sensors.battery_voltage()
        supp  = sensors.supply_voltage()
        solar = sensors.solar_voltage()
        print("temp = {:3.1f} batt = {:4.2f} supp = {:4.2f} solar = {:4.2f}".format(temp, batt, supp, solar))

    sensors.cleanup()
        
#!============================================================================

def argh_main():

    argh.dispatch_command(app_main)

#!============================================================================

if __name__ == "__main__":
    argh_main()

