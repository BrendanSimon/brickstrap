"""IND Driver Module."""

from enum import IntEnum

import ioctl
import ctypes
import fcntl
import mmap
import time
import array
import struct
#from collections import namedtuple

##
## Defaults.
##
dev_name = '/dev/IND'

max_channels = 3
max_capture_count = 10 * 1024 * 1024
## 2 bytes per sample.  2 buffers for ping-pong acquisition.
max_capture_size = max_capture_count * max_channels * 2 * 2
mmap_memory_size = 128 * 1024 * 1024
#print("DEBUG: max_capture_size={}".format(max_capture_size))
#print("DEBUG: mmap_memory_size={}".format(mmap_memory_size))
assert(max_capture_size <= mmap_memory_size)

##
## FIXME: could refactor this module into separate modules as an ind package.
## FIXME: eg. ind.leds, ind.modem, ind.adc, ...
##

##===========================================================================
##  Interfaces to IND driver below.
##  Should the driver interface be a separate module?
##===========================================================================

##
## Config Constants
##
class Config(IntEnum):
    PPS_Generate            = 1 << 0
    Debug_DMA_Start         = 1 << 1
    DMA_Halt                = 1 << 2
    DMA_Reset               = 1 << 3
    FPGA_Reset              = 1 << 4
    ADC_Test_Data           = 1 << 5
    PPS_Debug_Mode          = 1 << 6
    DMA_Debug_Mode          = 1 << 7
    Debug_Select_Active     = 1 << 11
    Debug_Select_Ch_0       = 0
    Debug_Select_Ch_1       = 1 << 8
    Debug_Select_Ch_2       = 1 << 9
    Debug_Select_Ch_Off     = 1 << 10
    Signed_Data             = 1 << 12

    Mode_Normal             = 0
    Mode_DMA_Debug          = DMA_Debug_Mode
    Mode_DMA_Trigger        = DMA_Debug_Mode | Debug_DMA_Start
    Mode_PPS_Debug          = PPS_Debug_Mode
    Mode_PPS_Trigger        = PPS_Debug_Mode | PPS_Generate
    Mode_System_Halt        = PPS_Debug_Mode

    Mode_Ch_Auto            = 0
    Mode_Ch_Auto_Invert     = ~(Debug_Select_Active | Debug_Select_Ch_Off)
    Mode_Ch_0               = Debug_Select_Active | Debug_Select_Ch_0
    Mode_Ch_1               = Debug_Select_Active | Debug_Select_Ch_1
    Mode_Ch_2               = Debug_Select_Active | Debug_Select_Ch_2
    Mode_Ch_Off             = Debug_Select_Active | Debug_Select_Ch_Off

    Mode_Signed             = Signed_Data

    Mode_Start_Unsigned     = Mode_Normal
    Mode_Start_Signed       = Mode_Normal | Mode_Signed
    Mode_Stop               = Mode_System_Halt

    Peak_Start_Disable      = 0x00FFFFFF
    Peak_Stop_Disable       = 0x00FFFFFF

##
## Cmd Interrupt Constants
##
class Interrupt(IntEnum):
    Disable     = 0
    Enable      = 1 << 0


##
## Status Register Constants
##
class Status(IntEnum):
    SPI_Busy                = 1 << 0
    S2MM_Error              = 1 << 1
    MM2S_Read_Complete      = 1 << 2        ## What is this ??
    MM2S_Error              = 1 << 3
    SPI_Error               = 1 << 4
    Interrupt_Active        = 1 << 5
    FPGA_Reset              = 1 << 6
    ADC_Test                = 1 << 7
    PPS_Debug               = 1 << 8
    DMA_Reset               = 1 << 9
    DMA_Debug               = 1 << 10
    Interrupt_Enable        = 1 << 11
    Battery_Low             = 1 << 12
    AC_Power                = 1 << 13


##
## Control Register Constants
##
class Control(IntEnum):
    Modem_Reset             = 1 << 0
    Modem_Power             = 1 << 1
    EN_Select               = 1 << 2        ## What is this ??

    All                     = Modem_Reset | Modem_Power | EN_Select


##
## IOCTL LED Constants
##
class LED(IntEnum):
    Running                 = 1 << 0
    Alert                   = 1 << 1
    Spare                   = 1 << 2
    PPS_OK                  = 1 << 3
    Modem_OK                = 1 << 4
    Weather_Station_OK      = 1 << 5
    #AC_Power_OK             = 1 << 6
    #Battery_OK              = 1 << 7

    All                     = Running | Alert | Spare | PPS_OK | Modem_OK | Weather_Station_OK

class cmd_struct(ctypes.Structure):
    _fields_ = [
        ('config',                  ctypes.c_uint32),   ## __u32 config
        ('interrupt',               ctypes.c_uint32),   ## __u32 interrupt
        ('address',                 ctypes.c_uint32),   ## __u32 address
        ('capture_count',           ctypes.c_uint32),   ## __u32 capture_count
        ('delay_count',             ctypes.c_uint32),   ## __u32 delay_count
        ('peak_detect_start_count', ctypes.c_uint32),   ## __u32 delay_count
        ('peak_detect_stop_count',  ctypes.c_uint32),   ## __u32 delay_count
    ]

class maxmin_struct(ctypes.Structure):
    _fields_ = [
        ('max_ch0_data',    ctypes.c_int16),        ## __u32 max_ch0_data
        ('_unused_1_',      ctypes.c_int16),        ## __u32 max_ch2_data
        ('max_ch0_addr',    ctypes.c_uint32),       ## __u32 max_ch0_addr
        ('min_ch0_data',    ctypes.c_int16),        ## __u32 min_ch0_data
        ('_unused_2_',      ctypes.c_int16),        ## __u32 max_ch2_data
        ('min_ch0_addr',    ctypes.c_uint32),       ## __u32 min_ch0_addr

        ('max_ch1_data',    ctypes.c_int16),        ## __u32 max_ch1_data
        ('_unused_3_',      ctypes.c_int16),        ## __u32 max_ch2_data
        ('max_ch1_addr',    ctypes.c_uint32),       ## __u32 max_ch1_addr
        ('min_ch1_data',    ctypes.c_int16),        ## __u32 min_ch1_data
        ('_unused_4_',      ctypes.c_int16),        ## __u32 max_ch2_data
        ('min_ch1_addr',    ctypes.c_uint32),       ## __u32 min_ch1_addr

        ('max_ch2_data',    ctypes.c_int16),        ## __u32 max_ch2_data
        ('_unused_5_',      ctypes.c_int16),        ## __u32 max_ch2_data
        ('max_ch2_addr',    ctypes.c_uint32),       ## __u32 max_ch2_addr
        ('min_ch2_data',    ctypes.c_int16),        ## __u32 min_ch2_data
        ('_unused_6_',      ctypes.c_int16),        ## __u32 min_ch2_data
        ('min_ch2_addr',    ctypes.c_uint32),       ## __u32 min_ch2_addr
    ]

class bit_flag_struct(ctypes.Structure):
    _fields_ = [
        ('set',             ctypes.c_uint),         ## __u32 set
        ('clear',           ctypes.c_uint),         ## __u32 clear
        ('toggle',          ctypes.c_uint),         ## __u32 clear
    ]

class spi_cmd_struct(ctypes.Structure):
    _fields_ = [
        ('port_devices',    ctypes.c_uint * 16),    ## __u32 port_device[16]
        ('port_addr',       ctypes.c_uint * 16),    ## __u32 port_addr[16]
        ('port_data',       ctypes.c_uint * 16),    ## __u32 port_data[16]
        ('num_spi_writes',  ctypes.c_uint)          ## __u32 num_spi_writes
    ]

class debug_struct(ctypes.Structure):
    _fields_ = [
        ('cmd',     ctypes.c_uint),                 ## __u32 cmd
        ('reg',     ctypes.c_uint),                 ## __u32 reg
        ('data',    ctypes.c_uint),                 ## __u32 data
    ]


##
## IOCTL Command Constants
##

IOCTL_BASE = ord('t')

def _IOWR(id, structure):
    val = ioctl._IOWR(IOCTL_BASE, (0x80 + id), ctypes.sizeof(structure))
    #val = ioctl._IOWR(IOCTL_BASE, (0x80 + id), 16)
    #print("DEBUG: _IOWR: val = 0x{:0X}".format(val))
    return val

# Can't use enum with Python2, if value has top bit set.
#class IOCTL(IntEnum):
class IOCTL:
    ## FIXME: not all operations are IOWR !!
    ## FIXME: change cmd_struct to appropriate struct for operation.
    IND_USER_RESET          = _IOWR(0x00, structure=cmd_struct)
    IND_USER_DMA_RESET      = _IOWR(0x01, structure=cmd_struct)
    IND_USER_SET_MODE       = _IOWR(0x02, structure=cmd_struct)
    IND_USER_SET_ADDRESS    = _IOWR(0x03, structure=cmd_struct)
    IND_USER_DMA_TEST       = _IOWR(0x04, structure=cmd_struct)
    IND_USER_TRIG_PPS       = _IOWR(0x05, structure=cmd_struct)
    IND_USER_SPI_WRITE      = _IOWR(0x06, structure=cmd_struct)
    IND_USER_STATUS         = _IOWR(0x07, structure=cmd_struct)
    IND_USER_SET_LEDS       = _IOWR(0x08, structure=cmd_struct)
    IND_USER_CLEAR_LEDS     = _IOWR(0x09, structure=cmd_struct)
    IND_USER_SET_CTRL       = _IOWR(0x0A, structure=cmd_struct)
    IND_USER_CLEAR_CTRL     = _IOWR(0x0B, structure=cmd_struct)
    IND_USER_SET_INTERRUPT  = _IOWR(0x0C, structure=cmd_struct)
    IND_USER_GET_SEM        = _IOWR(0x0D, structure=cmd_struct)
    IND_USER_SET_SEM        = _IOWR(0x0E, structure=cmd_struct)
    IND_USER_REG_DEBUG      = _IOWR(0x0F, structure=cmd_struct)
    IND_USER_MODIFY_LEDS    = _IOWR(0x10, structure=bit_flag_struct)
    IND_USER_MODIFY_CTRL    = _IOWR(0x11, structure=bit_flag_struct)
    IND_USER_READ_MAXMIN    = _IOWR(0x12, structure=maxmin_struct)


##===========================================================================
##  Library functions.
##===========================================================================

def get_device_handle():
    try:
        #print("DEBUG: opening device name '{}'".format(dev_name))
        #dev_hand = open(dev_name, 'rw')
        dev_hand = open(dev_name, 'r+b')
        #print("DEBUG: dev_hand={!r}".format(dev_hand))
    except:
        print("EXCEPTION: opening device name '{}'".format(dev_name))
        raise
    return dev_hand

def fpga_reset(dev_hand=None):
    '''Reset the FPGA.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_RESET, 0)
    except:
        print("EXCEPTION: resetting ADC DMA engine.")
        raise

def leds_modify(on=0, off=0, toggle=0, dev_hand=None):
    '''Modify LEDs by setting bits (on) and clearing bits (off).'''

    bits = bit_flag_struct()

    #print("DEBUG: leds_modify: on={}, off={}, toggle={}".format(on, off, toggle))

    bits.set = on & LED.All
    bits.clear = off & LED.All
    bits.toggle = toggle & LED.All

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        #print("DEBUG: modifying LEDS '{!r}'".format(bits))
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_MODIFY_LEDS, bits)
    except:
        print("EXCEPTION: modifying LEDS '{!r}'".format(bits))
        raise

def ctrl_modify(set, clear, dev_hand=None):
    '''Modify control register by setting and clearing bits.'''

    bits = bit_flag_struct()
    bits.set = set & LED.All
    bits.clear = clear & LED.All

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        #print("DEBUG: modifying LEDS '{!r}'".format(bits))
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_MODIFY_CTRL, bits)
    except:
        print("EXCEPTION: modifying CTRL '{!r}'".format(bits))
        raise

def modem_power_pulse(duration, dev_hand=None):
    '''Assert power key signal for some duration then deassert.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    ## Assert power key signal.
    #on = Control.Modem_Reset | Control.Modem_Power
    on = Control.Modem_Power
    off = 0
    ctrl_modify(set=on, clear=off, dev_hand=dev_hand)

    ## duration = 100-600ms => turn on.
    ## duration >= 600ms => turn off.  NB: seems to toggle power state.
    time.sleep(duration)

    ## Deassert power key signal.
    on = 0
    off = Control.Modem_Power | Control.Modem_Reset
    ctrl_modify(set=on, clear=off, dev_hand=dev_hand)

def modem_power_off(dev_hand=None):
    '''Turn off modem - assert power key signal for 600ms.'''
    '''NOTE: this seems to toggle the power state of the modem,'''
    '''rather than turn it off.'''

    ## duration = 100-600ms => turn on modem.
    ## duration >= 600ms => turn off modem.  NB. seems to toggle power state.
    duration = 0.7
    modem_power_pulse(duration=duration, dev_hand=dev_hand)

def modem_power_on(dev_hand=None):
    '''Turn on modem - asserts power key signal for 100ms.'''

    ## duration = 100-600ms => turn on modem.
    ## duration >= 600ms => turn off modem.  NB. seems to toggle power state.
    duration = 0.2
    modem_power_pulse(duration=duration, dev_hand=dev_hand)

def adc_memory_map(size=0, dev_hand=None):
    '''Get ADC Memory Map.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    if not size:
        size = mmap_memory_size

    try:
        #mem = mmap.mmap(dev_hand.fileno(), length=size, access=mmap.ACCESS_READ, offset=0)
        mem = mmap.mmap(dev_hand.fileno(), length=size, offset=0)
    except:
        print("EXCEPTION: getting ADC Memory Map.")
        raise

    return mem

def adc_dma_reset(dev_hand=None):
    '''Reset ADC DMA engine.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_DMA_RESET, 0)
    except:
        print("EXCEPTION: resetting ADC DMA engine.")
        raise

def adc_capture_address(dev_hand=None, address=0):
    '''Set capture offset address.  Use for ping-pong capture.  Should be either 0 or half the buffer size.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_SET_ADDRESS, address)
    except:
        print("EXCEPTION: setting capture address.")
        raise

def adc_capture_set_mode(address=0, mode=Config.Mode_PPS_Debug, interrupt_enable=False, capture_count=0, delay_count=0, peak_detect_start_count=Config.Peak_Start_Disable, peak_detect_stop_count=Config.Peak_Stop_Disable, dev_hand=None):
    '''Setup ADC Capture parameters.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    cmd = cmd_struct()

    #cmd.config = Config.Mode_Normal
    #cmd.config = Config.Mode_DMA_Debug
    #cmd.config = Config.Mode_DMA_Trigger
    #cmd.config = Config.Mode_PPS_Debug
    #cmd.config = Config.Mode_PPS_Trigger
    cmd.config = mode

    cmd.interrupt = 1 if interrupt_enable else 0
    cmd.address = address
    cmd.capture_count = capture_count
    cmd.delay_count = delay_count
    cmd.peak_detect_start_count = peak_detect_start_count
    cmd.peak_detect_stop_count = peak_detect_stop_count

    if 0:
        print("DEBUG: adc_capture_mode_set: cmd.config=0x{:08x}".format(cmd.config))
        print("DEBUG: adc_capture_mode_set: cmd.interrupt=0x{:08x}".format(cmd.interrupt))
        print("DEBUG: adc_capture_mode_set: cmd.address=0x{:08x}".format(cmd.address))
        print("DEBUG: adc_capture_mode_set: cmd.capture_count=0x{:08x}".format(cmd.capture_count))
        print("DEBUG: adc_capture_mode_set: cmd.delay_count=0x{:08x}".format(cmd.delay_count))
        print("DEBUG: adc_capture_mode_set: cmd.peak_detect_start_count=0x{:08x}".format(cmd.peak_detect_start_count))
        print("DEBUG: adc_capture_mode_set: cmd.peak_detect_stop_count=0x{:08x}".format(cmd.peak_detect_stop_count))

    status = status_get(dev_hand=dev_hand)

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_SET_MODE, cmd)
    except:
        print("EXCEPTION: ADC Capture Setup.")
        raise

    #status = status_get(dev_hand=dev_hand)

def adc_capture_start(address, capture_count, delay_count, signed=True, peak_detect_start_count=Config.Peak_Start_Disable, peak_detect_stop_count=Config.Peak_Stop_Disable, dev_hand=None):
    '''Start ADC Capture.'''

    mode_start = Config.Mode_Start_Signed if signed else Config.Mode_Start_Unsigned

    adc_capture_set_mode(address=address, mode=mode_start, interrupt_enable=True, capture_count=capture_count, delay_count=delay_count, peak_detect_start_count=peak_detect_start_count, peak_detect_stop_count=peak_detect_stop_count, dev_hand=dev_hand)

def adc_capture_stop(dev_hand=None):
    '''Stop ADC Capture.'''

    adc_capture_set_mode(address=0, mode=Config.Mode_Stop, interrupt_enable=False, dev_hand=dev_hand)

def adc_capture_maxmin_get(dev_hand=None):
    '''Get the maximum and minimum sample values and indices of each channel.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    maxmin = maxmin_struct()
    try:
        ## set mutable flag to true to place data in maxmin object.
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_READ_MAXMIN, maxmin, True)
    except:
        print("EXCEPTION: ADC Capture Max Mix Get.")
        raise

    return maxmin

def status_get(dev_hand=None):
    '''Get Status.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        a = fcntl.ioctl(dev_hand, IOCTL.IND_USER_STATUS, "1234")
        value = struct.unpack('l', a)[0]
    except:
        print("EXCEPTION: Get Status.")
        raise

    print("DEBUG: status_get: status = 0x{:08x}".format(value))
    return value

def adc_semaphore_get(dev_hand=None):
    '''Get ADC Semaphore.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    #struct.unpack('h', fcntl.ioctl(0, termios.TIOCGPGRP, "  "))[0]
    #buf = array.array('l', [0])
    try:
        #fcntl.ioctl(dev_hand, IOCTL.IND_USER_GET_SEM, buf, 1)
        a = fcntl.ioctl(dev_hand, IOCTL.IND_USER_GET_SEM, "1234")
        value = struct.unpack('l', a)[0]
    except:
        print("EXCEPTION: ADC Get Semaphore.")
        raise

    return value

def adc_semaphore_set(value=0, dev_hand=None):
    '''Set ADC Semaphore.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_SET_SEM, value)
    except:
        print("EXCEPTION: ADC Set Semaphore.")
        raise

def adc_output_mode_twos_complement(dev_hand=None):
    '''Set ADC Semaphore.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    spi_cmd = spi_cmd_struct()
    spi_cmd.port_addr[0] = 0x14         ## output mode register.
    spi_cmd.port_data[0] = 0x08 | 0x01  ## default, two's complement.
    spi_cmd.num_spi_writes = 1

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_SPI_WRITE, spi_cmd)
    except:
        print("EXCEPTION: ADC Set Semaphore.")
        raise

##----------------------------------------------------------------------------

def running_led_off(dev_hand):

    led = LED.Running
    leds_modify(off=led, dev_hand=dev_hand)

def running_led_on(dev_hand):

    led = LED.Running
    leds_modify(on=led, dev_hand=dev_hand)

def running_led_toggle(dev_hand):

    led = LED.Running
    leds_modify(toggle=led, dev_hand=dev_hand)

##----------------------------------------------------------------------------

def pps_ok_led_off(dev_hand):

    led = LED.PPS_OK
    leds_modify(off=led, dev_hand=dev_hand)

def pps_ok_led_on(dev_hand):

    led = LED.PPS_OK
    leds_modify(on=led, dev_hand=dev_hand)

def pps_ok_led_toggle(dev_hand):

    led = LED.PPS_OK
    leds_modify(toggle=led, dev_hand=dev_hand)

##----------------------------------------------------------------------------

def modem_led_off(dev_hand):

    led = LED.Modem_OK
    leds_modify(off=led, dev_hand=dev_hand)

def modem_led_on(dev_hand):

    led = LED.Modem_OK
    leds_modify(on=led, dev_hand=dev_hand)

def modem_led_toggle(dev_hand):

    led = LED.Modem_OK
    leds_modify(toggle=led, dev_hand=dev_hand)

##----------------------------------------------------------------------------

def weather_led_off(dev_hand):

    led = LED.Weather_Station_OK
    leds_modify(off=led, dev_hand=dev_hand)

def weather_led_on(dev_hand):

    led = LED.Weather_Station_OK
    leds_modify(on=led, dev_hand=dev_hand)

def weather_led_toggle(dev_hand):

    led = LED.Weather_Station_OK
    leds_modify(toggle=led, dev_hand=dev_hand)


##===========================================================================
##  module test.
##===========================================================================

def main():
    '''Main entry if this module is executed from the command line.'''

    print("IOCTL.IND_USER_RESET     =", IOCTL.IND_USER_RESET)
    print("IOCTL.IND_USER_RESET     =", int(IOCTL.IND_USER_RESET))
    print("IOCTL.IND_USER_RESET     = {:0X}".format(IOCTL.IND_USER_RESET))
    print("IOCTL.IND_USER_SET_MODE  =", IOCTL.IND_USER_SET_MODE)
    print("IOCTL.IND_USER_SET_MODE  =", int(IOCTL.IND_USER_SET_MODE))
    print("IOCTL.IND_USER_SET_MODE  = {:0X}".format(IOCTL.IND_USER_SET_MODE))
    print("IOCTL.IND_USER_REG_DEBUG =", IOCTL.IND_USER_REG_DEBUG)
    print("IOCTL.IND_USER_REG_DEBUG =", int(IOCTL.IND_USER_REG_DEBUG))
    print("IOCTL.IND_USER_REG_DEBUG = {:0X}".format(IOCTL.IND_USER_REG_DEBUG))
    print
    print("IOCTL.IND_USER_SET_LEDS    =", IOCTL.IND_USER_SET_LEDS)
    print("IOCTL.IND_USER_SET_LEDS    = 0x{:08X}".format(IOCTL.IND_USER_SET_LEDS))
    print("IOCTL.IND_USER_CLEAR_LEDS  =", IOCTL.IND_USER_CLEAR_LEDS)
    print("IOCTL.IND_USER_MODIFY_LEDS =", IOCTL.IND_USER_MODIFY_LEDS)
    print
    print("LED.Running              =", LED.Running)
    print("LED.Running              =", int(LED.Running))
    print("LED.Alert                =", LED.Alert)
    print("LED.Alert                =", int(LED.Alert))
    print("LED.Weather_Station_OK   =", LED.Weather_Station_OK)
    print("LED.Weather_Station_OK   =", int(LED.Weather_Station_OK))

    try:
        print("DEBUG: opening device name '{}'".format(dev_name))
        #dev_hand = open(dev_name, 'rw')
        dev_hand = open(dev_name, 'r+b')
        print("DEBUG: dev_hand={!r}".format(dev_hand))
    except:
        print("EXCEPTION: opening device name '{}'".format(dev_name))
        raise

    #led_seq = [ LED.Battery_OK, LED.AC_Power_OK, LED.PPS_OK, LED.Running,
    led_seq = [ LED.PPS_OK, LED.Running, LED.Modem_OK, LED.Alert, LED.Weather_Station_OK, LED.Spare ]
    led_seq += led_seq[1:-1][::-1]
    for count, led in enumerate(led_seq * 10):
        ##
        ## Cycle LEDs.
        ##
        on = led & LED.All
        off = ~on & LED.All
        if 0:
            print("DEBUG: count = {}".format(count))
            print("DEBUG: on    = 0x{:0X}".format(on))
            print("DEBUG: off   = 0x{:0X}".format(off))

        leds_modify(on, off, dev_hand=dev_hand)

        ##
        ## Cycle Modem control.
        ##
        on = 0
        c = (count >> 2) & Control.All
        if (c & 1): on |= Control.Modem_Reset
        if (c & 2): on |= Control.Modem_Power
        off = ~on & Control.All

        if 0:
            print("DEBUG: count = {}".format(count))
            print("DEBUG: on    = 0x{:0X}".format(on))
            print("DEBUG: off   = 0x{:0X}".format(off))

        ctrl_modify(on, off, dev_hand=dev_hand)

        time.sleep(0.1)

    dev_hand.close()


##===========================================================================
##  other reference stuff.
##===========================================================================

#ctypes snippets/examples.
#Args = operation_args()
#Args.field1 = data1;
#Args.field2 = data2;
#
#devicehandle = open('/dev/my_usb', 'rw')
#
## try:
#fcntl.ioctl(devicehandle, operation, Args)
## exception block to check error


##===========================================================================
##  Check if running this module, rather than importing it.
##===========================================================================

if __name__ == "__main__":
    main()

