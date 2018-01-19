#!/usr/bin/env python2

##############################################################################
#!
#!  Author:     Successful Endeavours Pty Ltd
#!
##############################################################################

'''
This module handles configuration information for EFD applications.
'''

import argh
import os.path

#!============================================================================

class Config(object):

    #!
    #! Default values.  Can be overridden by settings file or command line.
    #!

    version_str = '0.10.3-dev'

    serial_number = '0'

    site_name = 'Site {sn}'.format(sn=serial_number)

    pd_event_reporting_interval = 5 * 60            #! report PD events every 5 minutes (minimum interval)
    reporting_sms_phone_numbers = []                #! empty list of phone numbers.

    efd_ping_servers = ['http://portal.efdweb.com']
    efd_ping_api = 'api/Ping'

    web_server = 'http://portal.efdweb.com'
    web_server_measurements_log = '{ws}/api/AddEFDLog/{sn}/'.format(ws=web_server, sn=serial_number)

    num_channels = 3

    #! 16-bits
    sample_bits = 16

    #! Sample Frequency 250 MS/s
    sample_frequency = 250 * 1000 * 1000

    #! 0x8000 if using offset-binary, 0 if using signed-binary.
    sample_offset = 0

    #! ADC offset applied to compensate for DC offset in the system.
    #! Signed value (in sample units).
    #! Written to FPGA register and applied by the FPGA as samples are streamed from the ADC.
    adc_offset = 0;

    voltage_range_pp = 2.5

    pd_event_trigger_voltage = 0.10

    capture_count = 10*1000*1000

    #! Capture Mode
    #! 'auto'   : PPS triggered.
    #! 'manual' : oneshot software triggered.
    capture_mode = 'auto'

    total_count = sample_frequency * 50 // 1000         #! total of 50ms between start of channel sampling.

    delay_count = total_count - capture_count

    initialise_capture_memory               = True
    initialise_capture_memory_magic_value   = 0x6141
    show_intialised_capture_buffers         = False
    show_intialised_phase_arrays            = False

    show_capture_debug                      = False

    capture_index_offset_red = 0
    capture_index_offset_wht = total_count
    capture_index_offset_blu = total_count * 2

    fft_size = 1 << 8      #! 256 bins.  Was 1 << 16 (65,536)
    fft_size_half = fft_size >> 1

    show_phase_arrays               = False
    show_phase_arrays_on_pd_event   = False
    show_capture_buffers            = False

    peak_detect_numpy_capture_count_limit = 1*1000*1000
    peak_detect_numpy           = False
    peak_detect_numpy_debug     = False

    peak_detect_fpga            = True
    peak_detect_fpga_debug      = False

    peak_detect_fpga_fix        = False
    peak_detect_fpga_fix_debug  = False

    peak_detection              = True
    peak_detection_debug        = False

    tf_mapping                  = True
    tf_mapping_debug            = False

    show_measurements           = False
    show_measurements_post      = False

    page_size = 64

    page_width = 16

    data_dir = os.path.join('/mnt', 'data')

    state_filename = os.path.join(data_dir, 'efd_app.state')

    measurements_log_field_names = [
        'datetime_utc', 'datetime_local',
        'max_volt_red', 'min_volt_red', 'max_time_offset_red', #'min_time_offset_red',
        't2_red', 'w2_red',
        'max_volt_wht', 'min_volt_wht', 'max_time_offset_wht', #'min_time_offset_wht',
        't2_wht', 'w2_wht',
        'max_volt_blu', 'min_volt_blu', 'max_time_offset_blu', #'min_time_offset_blu',
        't2_blu', 'w2_blu',
        'temperature', 'humidity', 'rain_intensity',
        'alert',
        'adc_clock_count_per_pps',
        ]

    #! retry time interval (minimum) between reposting EFD measurements to web portal.
    measurments_post_retry_time_interval = 10

    #! max of 60 records (1 minute) of data per post to web portal.
    max_records_per_post = 60

    #! max of 600 records (10 minutes) of data can be queued.
    max_cloud_queue_size = 600

    #! Default to UTC timezone, if not set in user settings file.
    timezone = 'utc'

    #! FIXME: this is likely to be temporary !!
    append_gps_data_to_measurements_log = False

    #!========================================================================

    def __init__(self):
        self.read_settings_file()

        self.set_efd_ping_uris()
        self.set_web_uris()

    ##========================================================================

    def read_settings_file(self):
        #! Using 'import' is quick and dirty method to read in settings from a file.
        #! It relies on settings.py being available in the python path to load the 'module'
        #! Currently a symlink is used from settings.py in app directory to the settings file.
        import settings

        self.serial_number                       =            getattr(settings, 'SERIAL_NUMBER',                       self.serial_number)
        self.site_name                           =            getattr(settings, 'SITE_NAME',                           self.site_name)
        self.reporting_sms_phone_numbers         = list(      getattr(settings, 'REPORTING_SMS_PHONE_NUMBERS',         self.reporting_sms_phone_numbers) )
        self.pd_event_trigger_voltage            = float(     getattr(settings, 'PD_EVENT_TRIGGER_VOLTAGE',            self.pd_event_trigger_voltage) )
        self.pd_event_reporting_interval         = int(       getattr(settings, 'PD_EVENT_REPORTING_INTERVAL',         self.pd_event_reporting_interval) )
        self.efd_ping_servers                    = list(      getattr(settings, 'EFD_PING_SERVERS',                    self.efd_ping_servers) )
        self.web_server                          =            getattr(settings, 'WEB_SERVER',                          self.web_server)
        self.timezone                            =            getattr(settings, 'TIMEZONE',                            self.timezone)
        self.append_gps_data_to_measurements_log = bool( int( getattr(settings, 'APPEND_GPS_DATA_TO_MEASUREMENTS_LOG', self.append_gps_data_to_measurements_log) ) )
        self.fft_size                            = int(       getattr(settings, 'FFT_SIZE',                            self.fft_size) )
        self.adc_offset                          = int(       getattr(settings, 'ADC_OFFSET',                          self.adc_offset ) )

        self.set_capture_count()
        self.set_fft_size()
        #self.set_serial_number()
        self.set_efd_ping_uris()
        self.set_web_uris()
        self.set_measurements_log_field_names()

    #!========================================================================

    def set_efd_ping_uris(self):

        self.efd_ping_uris = []
        for server in self.efd_ping_servers:
            uri = '{eps}/{epa}/{sn}/'.format(eps=server, epa=self.efd_ping_api, sn=self.serial_number)
            self.efd_ping_uris.append(uri)

    #!========================================================================

    def set_web_uris(self):

        if self.web_server:
            self.web_server_measurements_log    = '{ws}/api/AddEFDLog/{sn}/'.format(ws=self.web_server, sn=self.serial_number)

    #!========================================================================

    def set_web_server(self, web_server=None):

        if web_server:
            self.web_server = web_server
            self.set_web_uris()

    #!========================================================================

    def set_capture_count(self, capture_count=None):
        if capture_count:
            self.capture_count = capture_count

        self.delay_count = self.total_count - self.capture_count

        #print("INFO: capture_count set to {}".format(self.capture_count))
        #print("INFO: delay_count set to {}".format(self.delay_count))
        #print("INFO: total_count is {}".format(self.total_count))

        if self.capture_count < self.fft_size:
            print("WARN: fft_size lowered")
            self.set_fft_size(self.capture_count)

    #!========================================================================

    def set_fft_size(self, fft_size=None):
        if fft_size:
            self.fft_size = fft_size
            #print("INFO: fft_size set to {}".format(self.fft_size))

        self.fft_size_half = self.fft_size // 2
        #print("INFO: fft_size_half set to {}".format(self.fft_size_half))

    #!========================================================================

    def capture_data_polarity_is_signed(self):
        return self.sample_offset == 0

    #!========================================================================

    def set_capture_mode(self, capture_mode='auto'):
        if capture_mode not in ['auto', 'manual']:
            msg = "capture_mode should be 'auto' or 'manual', not {!r}".format(capture_mode)
            raise ValueError(msg)

        self.capture_mode = capture_mode
        #print("INFO: capture_mode set to {}".format(self.capture_mode))

        if capture_mode == 'manual':
            self.peak_detect_numpy_capture_count_limit = self.capture_count
        else:
            peak_detect_numpy_capture_count_limit = 1*1000*1000
        #print("INFO: peak_detect_numpy_capture_count_limit set to {}".format(self.peak_detect_numpy_capture_count_limit))

        if self.capture_count > self.peak_detect_numpy_capture_count_limit:
            self.peak_detect_numpy = False
            print("INFO: skipping numpy peak detection as capture_count ({}) too high (> {})".format(self.capture_count, self.peak_detect_numpy_capture_count_limit))

    #!========================================================================

    def set_adc_offset(self, adc_offset=None):
        if adc_offset:
            self.adc_offset = adc_offset
            #print("INFO: adc_offset set to {}".format(self.adc_offset))

    #!========================================================================

    def set_append_gps_data(self, append_gps_data=None):
        if append_gps_data:
            self.append_gps_data_to_measurements_log = bool(append_gps_data)
            print("INFO: append_gps_data_to_measurements_log set to {}".format(self.append_gps_data_to_measurements_log))

    #!========================================================================

    def set_show_measurements(self, show_measurements=None):
        if show_measurements:
            self.show_measurements = bool(show_measurements)
            print("INFO: show_measurements set to {}".format(self.show_measurements))

    #!========================================================================

    def set_measurements_log_field_names(self):

        self.measurements_log_field_names = [
            'datetime_utc', 'datetime_local',
            'max_volt_red', 'min_volt_red', 'max_time_offset_red', #'min_time_offset_red',
            't2_red', 'w2_red',
            'max_volt_wht', 'min_volt_wht', 'max_time_offset_wht', #'min_time_offset_wht',
            't2_wht', 'w2_wht',
            'max_volt_blu', 'min_volt_blu', 'max_time_offset_blu', #'min_time_offset_blu',
            't2_blu', 'w2_blu',
            'temperature', 'humidity', 'rain_intensity',
            'alert',
            ]

        if self.append_gps_data_to_measurements_log:
            self.measurements_log_field_names += [
                'gps_latitude', 'gps_longitude',
                'battery_volt', 'solar_volt',
                'box_temperature',
                ]

        #! FIXME: the above is temporary, so maybe this should go after 'alert' field !!
        self.measurements_log_field_names += [ 'adc_clock_count_per_pps' ]

    #!========================================================================

    def show_all(self):
        print("-------------------------------------------------------------")
        print("Config values")
        print("-------------")

        print("version_str = {}".format(self.version_str))

        print("serial_number = {}".format(self.serial_number))
        print("site_name = {}".format(self.site_name))

        print("efd_ping_servers = {}".format(self.efd_ping_servers))
        print("efd_ping_uris = {}".format(self.efd_ping_uris))

        print("web_server = {}".format(self.web_server))
        print("web_server_measurements_log = {}".format(self.web_server_measurements_log))

        print("num_channels = {}".format(self.num_channels))

        print("sample_bits = {}".format(self.sample_bits))

        print("sample_frequency = {}".format(self.sample_frequency))

        print("sample_offset = {}".format(self.sample_offset))
        print("adc_offset = {}".format(self.adc_offset))

        print("voltage_range_pp = {}".format(self.voltage_range_pp))

        print("pd_event_trigger_voltage = {}".format(self.pd_event_trigger_voltage))

        print("capture_count = {}".format(self.capture_count))
        print("total_count = {}".format(self.total_count))
        print("delay_count = {}".format(self.delay_count))

        print("initialise_capture_memory = {}".format(self.initialise_capture_memory))
        print("initialise_capture_memory_magic_value = {}".format(self.initialise_capture_memory_magic_value))
        print("show_intialised_capture_buffers = {}".format(self.show_intialised_capture_buffers))
        print("show_intialised_phase_arrays = {}".format(self.show_intialised_phase_arrays))

        print("show_capture_debug = {}".format(self.show_capture_debug))

        print("capture_index_offset_red = {}".format(self.capture_index_offset_red))
        print("capture_index_offset_wht = {}".format(self.capture_index_offset_wht))
        print("capture_index_offset_blu = {}".format(self.capture_index_offset_blu))

        print("fft_size = {}".format(self.fft_size))
        print("fft_size_half = {}".format(self.fft_size_half))

        print("show_phase_arrays = {}".format(self.show_phase_arrays))
        print("show_phase_arrays_on_pd_event = {}".format(self.show_phase_arrays_on_pd_event))
        print("show_capture_buffers = {}".format(self.show_capture_buffers))

        print("peak_detect_numpy_capture_count_limit = {}".format(self.peak_detect_numpy_capture_count_limit))
        print("peak_detect_numpy = {}".format(self.peak_detect_numpy))
        print("peak_detect_numpy_debug = {}".format(self.peak_detect_numpy_debug))

        print("peak_detect_fpga = {}".format(self.peak_detect_fpga))
        print("peak_detect_fpga_debug = {}".format(self.peak_detect_fpga_debug))

        print("peak_detect_fpga_fix = {}".format(self.peak_detect_fpga_fix))
        print("peak_detect_fpga_fix_debug = {}".format(self.peak_detect_fpga_fix_debug))

        print("peak_detection = {}".format(self.peak_detection))
        print("peak_detection_debug = {}".format(self.peak_detection_debug))

        print("tf_mapping = {}".format(self.tf_mapping))
        print("tf_mapping_debug = {}".format(self.tf_mapping_debug))

        print("show_measurements = {}".format(self.show_measurements))
        print("show_measurements_post = {}".format(self.show_measurements_post))

        print("reporting_sms_phone_numbers = {}".format(self.reporting_sms_phone_numbers))
        print("pd_event_reporting_interval = {}".format(self.pd_event_reporting_interval))

        print("page_size = {}".format(self.page_size))
        print("page_width = {}".format(self.page_width))

        print("data_dir = {}".format(self.data_dir))
        print("state_filename = {}".format(self.state_filename))

        print("measurements_log_field_names = {}".format(self.measurements_log_field_names))

        print("measurments_post_retry_time_interval = {}".format(self.measurments_post_retry_time_interval))
        print("max_records_per_post = {}".format(self.max_records_per_post))
        print("max_cloud_queue_size = {}".format(self.max_cloud_queue_size))

        print("timezone = {}".format(self.timezone))

        print("append_gps_data_to_measurements_log = {}".format(self.append_gps_data_to_measurements_log))

        print("-------------------------------------------------------------")

##############################################################################

def app_main(capture_count=0, pps_mode=True, web_server=None, show_measurements=False, append_gps_data=False):
    """Main entry if running this module directly."""

    print(__name__)

    config = Config()

    if capture_count:
        config.set_capture_count(capture_count)
        print("INFO: `capture_count` set to {}".format(config.capture_count))

    if not pps_mode:
        config.set_capture_mode('manual')
        print("INFO: `capture_mode` set to {}".format(config.capture_mode))

    if web_server:
        config.set_web_server(web_server)
        print("INFO: `web_server' set to {}".format(config.web_server))

    if show_measurements:
        config.set_show_measurements(show_measurements)
        print("INFO: `show_measurements' set to {}".format(config.show_measurements))

    if append_gps_data:
        config.set_append_gps_data(append_gps_data)
        print("INFO: `append_gps_data_to_measurements_log' set to {}".format(config.append_gps_data_to_measurements_log))

    config.show_all()

#!============================================================================

def argh_main():

    argh.dispatch_command(app_main)

#!============================================================================

if __name__ == "__main__":
    argh_main()
