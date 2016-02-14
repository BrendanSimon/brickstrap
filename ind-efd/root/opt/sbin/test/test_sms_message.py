#!/usr/bin/env python2

##
## Unit test generation of sms messages.
##

import sys
import os.path

##
## set python path so we can import or application modules.
##
#print("{!r}".format(sys.path))
opt_sbin_path = os.path.abspath('..')
sys.path.append(opt_sbin_path)
#print("{!r}".format(sys.path))

import efd_app

##
## CSV file data.
##
## 2016-02-12 10:18:23+00:00,2016-02-12 20:18:23+10:00,0.00179290771484375,-0.00362396240234375,0.020268864,5.709579606068797e-09,247306851330008.41,0.0023651123046875,-0.00396728515625,0.065328772,5.6858421728936815e-09,121063638433340.83,0.0014495849609375,-0.0029754638671875,0.104449696,5.6962919002124462e-09,142273351310783.03,20.2C,73.2P,0.0M
##


test_measurements = {
    'datetime_utc'          : '2016-02-12 10:18:23+00:00',
    'datetime_local'        : '2016-02-12 20:18:23+10:00',
    'max_volt_red'          : 0.00179290771484375,
    'min_volt_red'          : 0,
    'max_time_offset_red'   : 0.00362396240234375,
    'min_time_offset_red'   : 0.020268864,
    't2_red'                : 5.709579606068797e-09,
    'w2_red'                : 247306851330008.41,
    'max_volt_wht'          : 0.0023651123046875,
    'min_volt_wht'          : -0.0023651123046875,
    'max_time_offset_wht'   : 0.00396728515625,
    'min_time_offset_wht'   : 0.065328772,
    't2_wht'                : 5.6858421728936815e-09,
    'w2_wht'                : 121063638433340.83,
    'max_volt_blu'          : 0.0014495849609375,
    'min_volt_blu'          : -0.0014495849609375,
    'max_time_offset_blu'   : 0.0029754638671875,
    'min_time_offset_blu'   : 0.104449696,
    't2_blu'                : 5.6962919002124462e-09,
    'w2_blu'                : 142273351310783.03,
    'temperature'           : '20.2C',
    'humidity'              : '73.2P',
    'rain_intensity'        : '0.0M',
    }

test_results = '''\
EFD PD Event
Unit: 0
Site: Unit-Test
Time (L): 2016-02-12 20:18:23+10:00
RED: Vmax=+0.0018, Vmin=+0.0000, T2=+5.7e-09, W2=+2.5e+14
WHT: Vmax=+0.0024, Vmin=-0.0024, T2=+5.7e-09, W2=+1.2e+14
BLU: Vmax=+0.0014, Vmin=-0.0014, T2=+5.7e-09, W2=+1.4e+14
Temp: 20.2C
Humidity: 73.2P
Rain-Int: 0.0M\
'''

def test_generate_sms_message():
    app.measurements = test_measurements
    message = app.generate_sms_message()
    print("TEST OUTPUT: message length = {}".format(len(message)))
    print("TEST OUTPUT: message = ...")
    print(message)
    status = message == test_results
    print("TEST RESULT: {}".format("PASS" if status else "FAIL"))

def test_main():
    global config
    config = efd_app.config
    global app
    app = efd_app.EFD_App(config=config)
    #app.init()

    test_generate_sms_message()

if __name__ == '__main__':
    test_main()

