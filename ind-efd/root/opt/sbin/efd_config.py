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
import enum

import logging

#!============================================================================

def get_logging_level_names():
    '''Helper to retrieve dict of logging names and levels.'''

    #! find logging's internal dictionary for level names.
    #! the internal dict name changed in python 3.4.
    try:
        level_to_name = logging._levelToName
        level_vals = level_to_name.keys()
    except AttributeError:
        level_to_name = logging._levelNames
        level_vals = [ key for key in level_to_name.keys() if isinstance(key,int) ]

    level_vals = sorted(level_vals)
    level_names = [ level_to_name[val] for val in level_vals ]
    return level_names

#!============================================================================

class CaptureMode( enum.Enum ):
    AUTO        = 1
    MANUAL      = 2

#!============================================================================

class PeakDetectMode( enum.Enum ):
    SQUARED     = 1
    NORMAL      = 2
#     ABSOLUTE    = 3

#!============================================================================

class TestMode( enum.Enum ):
    NORMAL          = 1
    ADC_POST_FIFO   = 2
    ADC_PRE_FIFO    = 3

#!============================================================================

class ADC_Polarity( enum.Enum ):
    SIGNED      = 1
    UNSIGNED    = 2

#!============================================================================

class Phase_Mode( enum.Enum ):
    POLY         = 0
    RED          = 1
    WHITE        = 2
    BLUE         = 3

    #! aliases -
    #DEFAULT      = POLY

#! aliases
#!
#! NOTE: Python 2 will display name of DEFAULT as "DEFAULT" for Enum
#!                                            and "POLY"    for IntEnum
#!       Python 3 will display name of DEFAULT as "POLY"    for Enum and IntEnum
#!
#!       Therefore use an object external to the Enum class
#!
PHASE_MODE_DEFAULT  = Phase_Mode.POLY

#!============================================================================

class ConfigDefault( object ):
    """
    Default Configuration Settings.

    This should be used as read-only a singleton
    (i.e. don't read settings file or overwrite attributes, etc)
    This should be enforced by some mechanism (__slots__ perhaps?).
    Applications can instantiate their own Config objects and modify.
    """

    #!
    #! Default values.  Can be overridden by settings file or command line.
    #!

    version_str = '0.12.2-dev1'

    serial_number = '0'

    site_name = 'Site {sn}'.format(sn=serial_number)

    pd_event_reporting_interval = 5 * 60            #! report PD events every 5 minutes (minimum interval)
    reporting_sms_phone_numbers = []                #! empty list of phone numbers.

    efd_ping_servers = ['http://portal.efdweb.com']
    efd_ping_api = 'api/Ping'

    web_server = 'http://portal.efdweb.com'
    web_server_measurements_log = '{ws}/api/AddEFDLog/{sn}/'.format(ws=web_server, sn=serial_number)

    bank_count = 2

    channel_count = 3

    #! 16-bits
    sample_bits = 16

    #! Sample Frequency 250 MS/s
    sample_frequency = 250 * 1000 * 1000

    adc_polarity = ADC_Polarity.SIGNED
    #! 0x8000 if using offset-binary, 0 if using signed-binary.
    sample_offset = 0 if adc_polarity == ADC_Polarity.SIGNED else 0x8000

    #! ADC offset applied to compensate for DC offset in the system.
    #! Signed value (in sample units).
    #! Written to FPGA register and applied by the FPGA as samples are streamed from the ADC.
    adc_offset = 0;

    voltage_range_pp = 2.5

    pd_event_trigger_voltage = 0.10

    #! Capture Mode
    #! 'auto'   : PPS triggered.
    #! 'manual' : oneshot software triggered.
    capture_mode = 'auto'

    #! delay between captures in in manual mode (fake pps).
    pps_delay = 1.0

    capture_count = 10*1000*1000

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

    fft_size = 256
    fft_size_half = fft_size // 2

    show_phase_arrays               = False
    show_phase_arrays_on_pd_event   = False
    show_capture_buffers            = False

    #peak_detect_mode                = PeakDetectMode.SQUARED
    peak_detect_mode                = PeakDetectMode.NORMAL

    peak_detect_normal              = True
    peak_detect_squared             = True

    peak_detect_numpy_capture_count_limit = 1*1000*1000
    peak_detect_numpy               = False
    peak_detect_numpy_debug         = False

    peak_detect_fpga                = True
    peak_detect_fpga_debug          = False

    peak_detect_fpga_fix            = False
    peak_detect_fpga_fix_debug      = False

    peak_detect                     = True
    peak_detect_debug               = False

    tf_mapping                      = True
    tf_mapping_debug                = False

    show_measurements               = False
    show_measurements_post          = False

    page_size = 64

    page_width = 16

    data_dir = os.path.join('/mnt', 'data')

    state_filename = os.path.join(data_dir, 'efd_app.state')

    #! set via function call during intialisation.
    measurements_log_field_names = []

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

    save_capture_data = False

    test_mode = TestMode.NORMAL

    phase_mode = PHASE_MODE_DEFAULT

    logging_level = logging.getLevelName(logging.WARNING)

    #!========================================================================

    def __init__(self):
#         pass
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

        if web_server != None:
            self.web_server = web_server
            self.set_web_uris()
            print("INFO: `web_server` set to {}".format(self.web_server))
            print("INFO: `web_server_measurements_log` set to {}".format(self.web_server_measurements_log))

    #!========================================================================

    def set_capture_count(self, capture_count=None):
        if capture_count != None:
            self.capture_count = capture_count
            self.delay_count = self.total_count - self.capture_count

            print("INFO: capture_count set to {}".format(self.capture_count))
            print("INFO: delay_count set to {}".format(self.delay_count))
            #print("INFO: total_count is {}".format(self.total_count))

        if self.capture_count < self.fft_size:
            print("WARN: fft_size lowered")
            self.set_fft_size(self.capture_count)

    #!========================================================================

#     def set_fft_size(self, fft_size=None):
    def set_fft_size(self, fft_size):
#         if fft_size != None:
        if fft_size != self.fft_size:
            self.fft_size = fft_size
            print("INFO: fft_size set to {}".format(self.fft_size))

        fft_size_half = self.fft_size // 2
        if fft_size_half != self.fft_size_half:
            self.fft_size_half = fft_size_half
            print("INFO: fft_size_half set to {}".format(self.fft_size_half))

    #!========================================================================

    def set_capture_mode(self, capture_mode='auto'):
        if capture_mode not in ['auto', 'manual']:
            msg = "capture_mode should be 'auto' or 'manual', not {!r}".format(capture_mode)
            raise KeyError(msg)

        self.capture_mode = capture_mode
        print("INFO: `capture_mode` set to {}".format(self.capture_mode))

        if capture_mode == 'manual':
            self.peak_detect_numpy_capture_count_limit = self.capture_count
        else:
            peak_detect_numpy_capture_count_limit = 1*1000*1000
        #print("INFO: peak_detect_numpy_capture_count_limit set to {}".format(self.peak_detect_numpy_capture_count_limit))

        if self.capture_count > self.peak_detect_numpy_capture_count_limit:
            self.peak_detect_numpy = False
            print("INFO: skipping numpy peak detection as capture_count ({}) too high (> {})".format(self.capture_count, self.peak_detect_numpy_capture_count_limit))

    #!========================================================================

    def set_pps_delay(self, pps_delay=None):
        if pps_delay != None:
            self.pps_delay = pps_delay
            print("INFO: `pps_delay` set to {}".format(self.pps_delay))

    #!========================================================================

    def set_show_capture_debug(self, show_capture_debug=None):
        if show_capture_debug != None:
            self.show_capture_debug = show_capture_debug
            print("INFO: `show_capture_debug` set to {}".format(self.show_capture_debug))

    #!========================================================================

    def set_show_capture_buffers(self, show_capture_buffers=None):
        if show_capture_buffers != None:
            self.show_capture_buffers = show_capture_buffers
            print("INFO: `show_capture_buffers` set to {}".format(self.show_capture_buffers))

    #!========================================================================

    def set_adc_polarity(self, adc_polarity=None):
        if adc_polarity != None:
            try:
                value = adc_polarity.upper()
                self.adc_polarity = ADC_Polarity[value]
                print("INFO: `adc_polarity` set to {}".format(self.adc_polarity))
            except KeyError as ex:
                print("ERROR: invalid `adc_polarity`: {!r}".format(adc_polarity))
            except Exception as ex:
                print(ex.message)
            else:
                #self.sample_offset = 0 if self.adc_polarity == ADC_Polarity.SIGNED else 0x8000
                print("INFO: `sample_offset` set to 0x{:X}".format(self.sample_offset))

    #!========================================================================

    def adc_polarity_is_signed(self):
        #return self.sample_offset == 0
        return self.adc_polarity == ADC_Polarity.SIGNED

    #!========================================================================

    def set_adc_offset(self, adc_offset=None):
        if adc_offset != None:
            self.adc_offset = adc_offset
            print("INFO: `adc_offset` set to {}".format(self.adc_offset))

    #!========================================================================

    def set_peak_detect_mode(self, peak_detect_mode=None):
        if peak_detect_mode != None:
            try:
                value = peak_detect_mode.upper()
                self.peak_detect_mode = PeakDetectMode[value]
                print("INFO: `peak_detect_mode` set to {}".format(self.peak_detect_mode))
            except KeyError as ex:
                print("ERROR: invalid `peak_detect_mode`: {!r}".format(peak_detect_mode))
            except Exception as ex:
                print(ex.message)

    #!========================================================================

    def set_peak_detect_normal(self, peak_detect_normal=None):
        if peak_detect_normal != None:
            self.peak_detect_normal = peak_detect_normal
            print("INFO: `peak_detect_normal` set to {}".format(self.peak_detect_normal))

    #!========================================================================

    def set_peak_detect_squared(self, peak_detect_squared=None):
        if peak_detect_squared != None:
            self.peak_detect_squared = peak_detect_squared
            print("INFO: `peak_detect_squared` set to {}".format(self.peak_detect_squared))

    #!========================================================================

    def set_append_gps_data(self, append_gps_data=None):
        if append_gps_data != None:
            self.append_gps_data_to_measurements_log = bool(append_gps_data)
            print("INFO: `append_gps_data_to_measurements_log` set to {}".format(self.append_gps_data_to_measurements_log))

    #!========================================================================

    def set_save_capture_data(self, save_capture_data=None):
        if save_capture_data != None:
            self.save_capture_data = bool(save_capture_data)
            print("INFO: `save_capture_data` set to {}".format(self.save_capture_data))

    #!========================================================================

    def set_show_measurements(self, show_measurements=None):
        if show_measurements != None:
            self.show_measurements = bool(show_measurements)
            print("INFO: `show_measurements` set to {}".format(self.show_measurements))

    #!========================================================================

    def set_measurements_log_field_names(self):

        self.measurements_log_field_names = [
            'datetime_utc', 'datetime_local',
            'max_volt_red', 'min_volt_red', 'max_time_offset_red', 't2_red', 'w2_red',
            'max_volt_wht', 'min_volt_wht', 'max_time_offset_wht', 't2_wht', 'w2_wht',
            'max_volt_blu', 'min_volt_blu', 'max_time_offset_blu', 't2_blu', 'w2_blu',
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

        self.measurements_log_field_names += [
            'max_count_sq_red', 'max_count_sq_wht', 'max_count_sq_blu',
            'max_volt_sq_red', 'max_volt_sq_wht', 'max_volt_sq_blu',
            'max_time_offset_sq_red', 'max_time_offset_sq_wht', 'max_time_offset_sq_blu',

            #!
            #! Fields to potentially add later if IND request them (in no particular order)
            #!
            #'min_count_sq_red', 'min_count_sq_wht', 'min_count_sq_blu',
            #'min_volt_sq_red', 'min_volt_sq_wht', 'min_volt_sq_blu',
            #'min_time_offset_sq_red', 'min_time_offset_sq_wht', 'min_time_offset_sq_blu',
            #'min_count_red', 'min_count_wht', 'min_count_blu',
            #'min_time_offset_red', 'min_time_offset_wht', 'min_time_offset_blu',
            #'max_count_red', 'max_count_wht', 'max_count_blu',
            ]

    #!========================================================================

    def set_test_mode(self, test_mode=None):
        if test_mode != None:
            try:
                value = test_mode.upper()
                self.test_mode = TestMode[value]
                print("INFO: `test_mode` set to {}".format(self.test_mode))
            except KeyError as ex:
                print("ERROR: invalid `test_mode`: {!r}".format(test_mode))
            except Exception as ex:
                print(ex.message)

    #!========================================================================

    def set_phase_mode( self, phase_mode=None ):
        if phase_mode != None:
            try:
                value = phase_mode.upper()
                self.phase_mode = Phase_Mode[ value ]
                print( "INFO: `phase_mode` set to {}".format( self.phase_mode ) )
            except KeyError as ex:
                print( "ERROR: invalid `phase_mode`: {!r}".format( phase_mode ) )
            except Exception as ex:
                print( ex.message )

    #!========================================================================

    def set_logging_level(self, logging_level=None):
        if logging_level != None:
            level_names = get_logging_level_names()
            logging_level = logging_level.upper()
            if logging_level in level_names:
                self.logging_level = logging_level
            print("INFO: `logging_level` set to {}".format(self.logging_level))

    #!========================================================================

    def show_all(self):
        print("-------------------------------------------------------------")

        print("version_str = {}".format(self.version_str))

        print("serial_number = {}".format(self.serial_number))
        print("site_name = {}".format(self.site_name))

        print("efd_ping_servers = {}".format(self.efd_ping_servers))
        print("efd_ping_uris = {}".format(self.efd_ping_uris))

        print("web_server = {}".format(self.web_server))
        print("web_server_measurements_log = {}".format(self.web_server_measurements_log))

        print("bank_count = {}".format(self.bank_count))
        print("channel_count = {}".format(self.channel_count))

        print("sample_bits = {}".format(self.sample_bits))

        print("sample_frequency = {}".format(self.sample_frequency))

        print("adc_polarity = {}".format(self.adc_polarity))
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

        print("peak_detect_mode = {}".format(self.peak_detect_mode))

        print("peak_detect_normal = {}".format(self.peak_detect_normal))
        print("peak_detect_squared = {}".format(self.peak_detect_squared))

        print("peak_detect_numpy_capture_count_limit = {}".format(self.peak_detect_numpy_capture_count_limit))
        print("peak_detect_numpy = {}".format(self.peak_detect_numpy))
        print("peak_detect_numpy_debug = {}".format(self.peak_detect_numpy_debug))

        print("peak_detect_fpga = {}".format(self.peak_detect_fpga))
        print("peak_detect_fpga_debug = {}".format(self.peak_detect_fpga_debug))

        print("peak_detect_fpga_fix = {}".format(self.peak_detect_fpga_fix))
        print("peak_detect_fpga_fix_debug = {}".format(self.peak_detect_fpga_fix_debug))

        print("peak_detect = {}".format(self.peak_detect))
        print("peak_detect_debug = {}".format(self.peak_detect_debug))

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

        print("save_capture_data = {}".format(self.save_capture_data))

        print("test_mode = {}".format(self.test_mode))

        print("phase_mode = {}".format( self.phase_mode ))

        print("logging_level = {}".format(self.logging_level))

        print("-------------------------------------------------------------")

#!============================================================================

class Config( ConfigDefault ):

    #!
    #! Default values.  Can be overridden by settings file or command line.
    #!

    #!========================================================================

    def __init__(self):
        super(Config, self).__init__()

    ##========================================================================

    def read_settings_file( self ):
        #! Using 'import' is QUICK-AND-DIRTY method to read/write settings from/to a file.
        #! It relies on settings.py being available in the python path to load the 'module'
        #! Currently a symlink is used from settings.py in app directory to the settings file.
        try:
            reload( settings )
        except NameError:
            import settings

        self.serial_number                       =            getattr( settings, 'SERIAL_NUMBER',                       self.serial_number )
        self.site_name                           =            getattr( settings, 'SITE_NAME',                           self.site_name )
        self.reporting_sms_phone_numbers         = list(      getattr( settings, 'REPORTING_SMS_PHONE_NUMBERS',         self.reporting_sms_phone_numbers ) )
        self.pd_event_trigger_voltage            = float(     getattr( settings, 'PD_EVENT_TRIGGER_VOLTAGE',            self.pd_event_trigger_voltage ) )
        self.pd_event_reporting_interval         = int(       getattr( settings, 'PD_EVENT_REPORTING_INTERVAL',         self.pd_event_reporting_interval ) )
        self.efd_ping_servers                    = list(      getattr( settings, 'EFD_PING_SERVERS',                    self.efd_ping_servers ) )
        self.web_server                          =            getattr( settings, 'WEB_SERVER',                          self.web_server )
        self.timezone                            =            getattr( settings, 'TIMEZONE',                            self.timezone )
        self.append_gps_data_to_measurements_log = bool( int( getattr( settings, 'APPEND_GPS_DATA_TO_MEASUREMENTS_LOG', self.append_gps_data_to_measurements_log ) ) )
        self.save_capture_data                   = bool( int( getattr( settings, 'SAVE_CAPTURE_DATA',                   ConfigDefault.save_capture_data ) ) )
        fft_size                                 = int(       getattr( settings, 'FFT_SIZE',                            ConfigDefault.fft_size ) )
        self.adc_offset                          = int(       getattr( settings, 'ADC_OFFSET',                          self.adc_offset ) )
        phase_mode                               =            getattr( settings, 'PHASE_MODE',                          None )
        peak_detect_mode                         =            getattr( settings, 'PEAK_DETECT_MODE',                    None )
        capture_count                            =            getattr( settings, 'CAPTURE_COUNT',                       None )
        logging_level                            =            getattr( settings, 'LOGGING_LEVEL',                       None )

        self.set_capture_count( capture_count )
        #self.set_serial_number()
        self.set_fft_size( fft_size )
        self.set_efd_ping_uris()
        self.set_web_uris()
        self.set_measurements_log_field_names()
        self.set_phase_mode( phase_mode )
        self.set_peak_detect_mode( peak_detect_mode )
        self.set_logging_level( logging_level )

    ##========================================================================

    def settings_file_set( self, key, value ):
        #! Using 'import' is QUICK-AND-DIRTY method to read/write settings from/to a file.
        #! It relies on settings.py being available in the python path to load the 'module'
        #! Currently a symlink is used from settings.py in app directory to the settings file.
        try:
            reload( settings )
        except NameError:
            import settings

        filename = settings.__file__.replace( '.pyc', '.py' )

        new_line = "{}={}\n".format( key, repr( value ) )

        #! read original contents of file into memory
        with open( filename, 'r' ) as f:
            lines= f.readlines()

        #! search for existing setting and replace it
        set = False
        for i, line in enumerate( lines ):
            if line.startswith( key ):
                lines[ i ] = new_line
                set = True

        #! write lines back to file
        with open( filename, 'w' ) as f:
            f.writelines( lines )

            #! append setting if it was not replaced above
            if not set:
                with open( filename, 'a' ) as f:
                    f.write( '\n' + new_line + '\n' )

##############################################################################

def argh_main():
    """Main entry if running this module directly."""

    config = Config()

    print("\n")
    print("Config settings (default)")
    config.show_all()

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
                 phase_mode             = config.phase_mode.name.lower(),
                 logging_level          = config.logging_level.lower(),
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

        if phase_mode != config.phase_mode.name.lower():
            config.set_phase_mode( phase_mode )

        if logging_level != config.logging_level.lower():
            config.set_logging_level( logging_level )

        logging.basicConfig( level=config.logging_level )

        effective_log_level = logging.getLogger().getEffectiveLevel()
        if effective_log_level <= logging.INFO:
            config.show_all()

    #!------------------------------------------------------------------------

    argh.dispatch_command(app_main)

#!============================================================================

if __name__ == "__main__":
    argh_main()
