"""IND Driver Module."""

## Set to the FPGA register mapping variant.
## Should only need original API version, once IND2 FPGA is made
## to conform with the original IND1 API.
IND_FPGA_API = 1
#IND_FPGA_API = 2

from enum import IntEnum

import ioctl
import ctypes
import fcntl
import mmap
import time
import array
import struct
#from collections import namedtuple

#!
#! Defaults.
#!
dev_name = '/dev/IND'

max_channels = 3
max_capture_count = 10 * 1024 * 1024
#! 2 bytes per sample.  2 buffers for ping-pong acquisition.
max_capture_size = max_capture_count * max_channels * 2 * 2
mmap_memory_size = 128 * 1024 * 1024
#print("DEBUG: max_capture_size={}".format(max_capture_size))
#print("DEBUG: mmap_memory_size={}".format(mmap_memory_size))
assert(max_capture_size <= mmap_memory_size)

#!
#! FIXME: could refactor this module into separate modules as an ind package.
#! FIXME: eg. ind.leds, ind.modem, ind.adc, ...
#!

#!===========================================================================
#!  Interfaces to IND driver below.
#!  Should the driver interface be a separate module?
#!===========================================================================

#=============================================================================
#!
#! Config Constants/Defaults.
#!
#=============================================================================
class Config(IntEnum):
    PPS_Generate            = 1 << 0
    Debug_DMA_Start         = 1 << 1
    DMA_Halt                = 1 << 2
    DMA_Reset               = 1 << 3
    FPGA_Reset              = 1 << 4
    ADC_Test_Data           = 1 << 5
    PPS_Debug_Mode          = 1 << 6
    DMA_Debug_Mode          = 1 << 7
    Debug_Select_Ch_0       = 0
    Debug_Select_Ch_1       = 1 << 8
    Debug_Select_Ch_2       = 2 << 8
    Debug_Select_Ch_Off     = 3 << 8
    Debug_Select_Active     = 1 << 11
    Unsigned_Data           = 0
    Signed_Data             = 1 << 12

    All                     = PPS_Generate \
                            | Debug_DMA_Start | DMA_Halt | DMA_Reset \
                            | FPGA_Reset | ADC_Test_Data \
                            | PPS_Debug_Mode | DMA_Debug_Mode \
                            | Debug_Select_Ch_0 | Debug_Select_Ch_1 \
                            | Debug_Select_Ch_2 | Debug_Select_Ch_Off \
                            | Debug_Select_Active \
                            | Unsigned_Data | Signed_Data

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

    Mode_Start_Unsigned     = Mode_Normal | Unsigned_Data
    Mode_Start_Signed       = Mode_Normal | Signed_Data
    Mode_Manual_Unsigned    = Mode_PPS_Trigger | Unsigned_Data
    Mode_Manual_Signed      = Mode_PPS_Trigger | Signed_Data
    Mode_Manual_Trigger     = Mode_PPS_Trigger
    Mode_Stop               = Mode_System_Halt

    Peak_Start_Disable      = 0x00FFFFFF                #! default
    Peak_Stop_Disable       = 0x00FFFFFF                #! default

    ADC_Offset              = 0                         #! default


#=============================================================================
#!
#! Cmd Interrupt Constants
#!
#=============================================================================
class Interrupt(IntEnum):
    Disable     = 0
    Enable      = 1 << 0

#=============================================================================
#!
#! Status Register Constants
#!
#=============================================================================

class Status_1(IntEnum):
    SPI_Busy                = 1 << 0
    S2MM_Error              = 1 << 1
    MM2S_Read_Complete      = 1 << 2        #! What is this ??
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
    Not_Restart_Request     = 1 << 14       ## PM MCU has requested a restart
    Not_Shutdown_Request    = 1 << 15       ## PM MCU has requested a shutdown

    All                     = SPI_Busy | S2MM_Error | MM2S_Read_Complete | MM2S_Error   \
                            | SPI_Error | Interrupt_Active | FPGA_Reset | ADC_Test      \
                            | PPS_Debug | DMA_Reset | DMA_Debug | Interrupt_Enable      \
                            | Battery_Low | AC_Power                                    \
                            | Not_Restart_Request | Not_Shutdown_Request

class Status_2(IntEnum):
    SPI_Busy                = 1 << 0
    S2MM_Error              = 1 << 1
    MM2S_Read_Complete      = 1 << 2        #! What is this ??
    MM2S_Error              = 1 << 3
    SPI_Error               = 1 << 4
    Interrupt_Active        = 1 << 5
    FPGA_Reset              = 1 << 6
    ADC_Test                = 1 << 7
    PPS_Debug               = 1 << 8
    DMA_Reset               = 1 << 9
    DMA_Debug               = 1 << 10
    Interrupt_Enable        = 1 << 11

## IND2 Kutu assignments
## FIXME: these are probably wrong !!
    Modem_OK                = 1 << 12
    Weather_Station_OK      = 1 << 13
    Battery_OK              = 1 << 14
    Power_OK                = 1 << 15
    PPS_OK                  = 1 << 16

    Not_Restart_Request     = 1 << 17
    Not_Shutdown_Request    = 1 << 18

    Battery_Low             = 1 << 19       ## FIXME: not sure if this is correct !!
    AC_Power                = 1 << 20       ## FIXME: not sure if this is correct !!

    All                     = SPI_Busy | S2MM_Error | MM2S_Read_Complete | MM2S_Error   \
                            | SPI_Error | Interrupt_Active | FPGA_Reset | ADC_Test      \
                            | PPS_Debug | DMA_Reset | DMA_Debug | Interrupt_Enable      \
                            | Modem_OK | Weather_Station_OK                             \
                            | Battery_OK | Power_OK                                     \
                            | PPS_OK                                                    \
                            | Not_Restart_Request | Not_Shutdown_Request

#=============================================================================
#!
#! Control Register Constants
#!
#=============================================================================

class Control_1(IntEnum):
    Modem_Reset             = 1 << 0
    Modem_Power             = 1 << 1
    EN_Select               = 1 << 2        #! What is this ??

    Not_OS_Running          = 1 << 3        ## output low to indicate to PM MCU that we are up and running ok
    Not_Spare_MCU           = 1 << 4        ## a spare signal to PM MCU (could be input or output)?

    All                     = Modem_Reset | Modem_Power | EN_Select     \
                            | Not_OS_Running | Not_Spare_MCU

class Control_2(IntEnum):
    Modem_Reset             = 1 << 0
    Modem_Power             = 1 << 1
    EN_Select               = 1 << 2        #! What is this ??

    Not_OS_Running          = 1 << 3        ## output low to indicate to PM MCU that we are up and running ok
    Not_Spare_MCU           = 1 << 4        ## a spare signal to PM MCU (could be input or output)?

    All                     = Modem_Reset | Modem_Power | EN_Select     \
                            | Not_OS_Running | Not_Spare_MCU

## IND2 Kutu assignments (FIXME) !!
    Running                 = 1 << 3
    Alert                   = 1 << 4
    Not_OS_Running          = 1 << 5        ## output low to indicate to PM MCU that we are up and running ok

    All                     = Modem_Reset | Modem_Power | EN_Select     \
                            | Running | Alert                           \
                            | Not_OS_Running | Not_Spare_MCU

#=============================================================================
#!
#! IOCTL LED Constants
#!
#=============================================================================

class LED_1(IntEnum):
## IND1 assignments
    Running                 = 1 << 0
    Alert                   = 1 << 1
    Spare_3G                = 1 << 2        ## IND1 Spare LED on 3G board.
    PPS_OK                  = 1 << 3
    Modem_OK                = 1 << 4
    Weather_Station_OK      = 1 << 5
    Power_OK                = 1 << 6
    Battery_OK              = 1 << 7

    Spare1_3G               = 1 << 8
    Spare2_3G               = 1 << 9        ## IND2 Spare LED on 3G board.
    Spare3_3G               = 1 << 10
    Spare4_3G               = 1 << 11
    Spare1_RF               = 1 << 12
    Spare2_RF               = 1 << 13
    Spare3_RF               = 1 << 14
    Spare4_RF               = 1 << 15

    Debug0                  = 1 << 28
    Debug1                  = 1 << 29
    Debug2                  = 1 << 30
    Debug3                  = 1 << 30   ## FIXME !!

    All                     = Running | Alert | Spare_3G | PPS_OK           \
                            | Modem_OK | Weather_Station_OK                 \
                            | Battery_OK | Power_OK                         \
                            | Spare1_3G | Spare2_3G | Spare3_3G | Spare4_3G \
                            | Spare1_RF | Spare2_RF | Spare3_RF | Spare4_RF \
                            | Debug0 | Debug1 | Debug2 | Debug3             \

    Spare                   = Spare_3G | Spare2_3G     ## Use both bits so works with IND1 and IND2 boards.

class LED_2(IntEnum):
## IND2 Kutu assignments
#     Running                 = 0             ##FIXME: currently in Control reg !!
#     Alert                   = 0             ##FIXME: currently in Control reg !!

    Debug0                  = 1 << 0
    Debug1                  = 1 << 1
    Debug2                  = 1 << 2
    Debug3                  = 1 << 3

    Spare1_3G               = 1 << 4
#     Spare2_3G               = 1 << 2        ## set to bit 2 for backward compatibility with IND1 system.
    Spare2_3G               = 1 << 5        ## FIXME: remove when FPGA is remapped !!
    Spare3_3G               = 1 << 6
    Spare4_3G               = 1 << 7
    Spare1_RF               = 1 << 8
    Spare2_RF               = 1 << 9
    Spare3_RF               = 1 << 10
    Spare4_RF               = 1 << 11

    Modem_OK                = 1 << 12
    Weather_Station_OK      = 1 << 13
    Battery_OK              = 1 << 14
    Power_OK                = 1 << 15
    PPS_OK                  = 1 << 16

    All                     = Debug0 | Debug1 | Debug2 | Debug3             \
                            | Spare1_3G | Spare2_3G | Spare3_3G | Spare4_3G \
                            | Spare1_RF | Spare2_RF | Spare3_RF | Spare4_RF \
                            | Modem_OK | Weather_Station_OK                 \
                            | Battery_OK | Power_OK                         \
                            | PPS_OK

    Spare                   = Spare2_3G


#=============================================================================
#! Map classes based on selected version of FPGA.
#! There may be a way of doing this dynamically by reading the FPGA version register.
#=============================================================================

if IND_FPGA_API == 1:
    Status = Status_1
    Control = Control_1
    LED = LED_1
elif IND_FPGA_API == 2:
    Status = Status_2
    Control = Control_2
    LED = LED_2
else:
    raise Exception("Invalid value for `IND_FPGA_API`")

#=============================================================================

class maxmin_struct(ctypes.Structure):
    _fields_ = [
        ('max_ch0_data',    ctypes.c_int16),        #! __i16 max_ch0_data
        ('_unused_1_',      ctypes.c_int16),        #! __i16 max_ch2_data
        ('max_ch0_addr',    ctypes.c_uint32),       #! __u32 max_ch0_addr
        ('min_ch0_data',    ctypes.c_int16),        #! __i16 min_ch0_data
        ('_unused_2_',      ctypes.c_int16),        #! __i16 max_ch2_data
        ('min_ch0_addr',    ctypes.c_uint32),       #! __u32 min_ch0_addr

        ('max_ch1_data',    ctypes.c_int16),        #! __i16 max_ch1_data
        ('_unused_3_',      ctypes.c_int16),        #! __i16 max_ch2_data
        ('max_ch1_addr',    ctypes.c_uint32),       #! __u32 max_ch1_addr
        ('min_ch1_data',    ctypes.c_int16),        #! __i16 min_ch1_data
        ('_unused_4_',      ctypes.c_int16),        #! __i16 max_ch2_data
        ('min_ch1_addr',    ctypes.c_uint32),       #! __u32 min_ch1_addr

        ('max_ch2_data',    ctypes.c_int16),        #! __i16 max_ch2_data
        ('_unused_5_',      ctypes.c_int16),        #! __i16 max_ch2_data
        ('max_ch2_addr',    ctypes.c_uint32),       #! __u32 max_ch2_addr
        ('min_ch2_data',    ctypes.c_int16),        #! __i16 min_ch2_data
        ('_unused_6_',      ctypes.c_int16),        #! __i16 min_ch2_data
        ('min_ch2_addr',    ctypes.c_uint32),       #! __u32 min_ch2_addr
    ]

class FPGA_Version(ctypes.Structure):
    _fields_ = [
        ('_unused_0_',      ctypes.c_uint16),       #! __u16 unused
        ('major',           ctypes.c_uint8),        #! __u8 major version number
        ('minor',           ctypes.c_uint8),        #! __u8 minor version number
    ]

class bit_flag_struct(ctypes.Structure):
    _fields_ = [
        ('set',             ctypes.c_uint32),       #! __u32 set
        ('clear',           ctypes.c_uint32),       #! __u32 clear
        ('toggle',          ctypes.c_uint32),       #! __u32 clear
    ]

class spi_cmd_struct(ctypes.Structure):
    _fields_ = [
        ('port_devices',    ctypes.c_uint32 * 16),  #! __u32 port_device[16]
        ('port_addr',       ctypes.c_uint32 * 16),  #! __u32 port_addr[16]
        ('port_data',       ctypes.c_uint32 * 16),  #! __u32 port_data[16]
        ('num_spi_writes',  ctypes.c_uint32)        #! __u32 num_spi_writes
    ]

class debug_struct(ctypes.Structure):
    _fields_ = [
        ('cmd',     ctypes.c_uint32),               #! __u32 cmd
        ('reg',     ctypes.c_uint32),               #! __u32 reg
        ('data',    ctypes.c_uint32),               #! __u32 data
    ]

class cmd_struct(ctypes.Structure):
    _fields_ = [
        ('config',                  ctypes.c_uint32),   #! __u32 config
        ('interrupt',               ctypes.c_uint32),   #! __u32 interrupt
        ('address',                 ctypes.c_uint32),   #! __u32 address
        ('capture_count',           ctypes.c_uint32),   #! __u32 capture_count
        ('delay_count',             ctypes.c_uint32),   #! __u32 delay_count
        ('peak_detect_start_count', ctypes.c_uint32),   #! __u32 delay_count
        ('peak_detect_stop_count',  ctypes.c_uint32),   #! __u32 delay_count
        ('adc_offset',              ctypes.c_int32),    #! __s32 adc_offset
    ]


#=============================================================================
#!
#! IOCTL Command Constants
#!
#=============================================================================

IOCTL_BASE = ord('t')

IOCTL_ID_BASE = 0x80

def _IOW(id, structure):
    val = ioctl._IOW(IOCTL_BASE, (IOCTL_ID_BASE + id), ctypes.sizeof(structure))
    return val

def _IOR(id, structure):
    val = ioctl._IOR(IOCTL_BASE, (IOCTL_ID_BASE + id), ctypes.sizeof(structure))
    return val

def _IOWR(id, structure):
    val = ioctl._IOWR(IOCTL_BASE, (IOCTL_ID_BASE + id), ctypes.sizeof(structure))
    return val

# Can't use enum with Python2, if value has top bit set.
#class IOCTL(IntEnum):
class IOCTL:
    #! FIXME: not all operations are IOWR !!
    #! FIXME: change cmd_struct to appropriate struct for operation.
    IND_USER_RESET                      = _IOWR(0x00, structure=cmd_struct)
    IND_USER_DMA_RESET                  = _IOWR(0x01, structure=cmd_struct)
    IND_USER_SET_MODE                   = _IOWR(0x02, structure=cmd_struct)
    IND_USER_SET_ADDRESS                = _IOWR(0x03, structure=cmd_struct)
    IND_USER_DMA_TEST                   = _IOWR(0x04, structure=cmd_struct)
    IND_USER_TRIG_PPS                   = _IOWR(0x05, structure=cmd_struct)
    IND_USER_SPI_WRITE                  = _IOWR(0x06, structure=cmd_struct)
    IND_USER_STATUS                     = _IOWR(0x07, structure=cmd_struct)
    IND_USER_SET_LEDS                   = _IOWR(0x08, structure=cmd_struct)
    IND_USER_CLEAR_LEDS                 = _IOWR(0x09, structure=cmd_struct)
    IND_USER_SET_CTRL                   = _IOWR(0x0A, structure=cmd_struct)
    IND_USER_CLEAR_CTRL                 = _IOWR(0x0B, structure=cmd_struct)
    IND_USER_SET_INTERRUPT              = _IOWR(0x0C, structure=cmd_struct)
    IND_USER_GET_SEM                    = _IOWR(0x0D, structure=cmd_struct)
    IND_USER_SET_SEM                    = _IOWR(0x0E, structure=cmd_struct)
    IND_USER_REG_DEBUG                  = _IOWR(0x0F, structure=cmd_struct)
    IND_USER_MODIFY_LEDS                = _IOWR(0x10, structure=bit_flag_struct)
    IND_USER_MODIFY_CTRL                = _IOWR(0x11, structure=bit_flag_struct)
    IND_USER_READ_MAXMIN                = _IOWR(0x12, structure=maxmin_struct)
    IND_USER_FPGA_VERSION               = _IOWR(0x13, structure=FPGA_Version)
    IND_USER_ADC_CLOCK_COUNT_PER_PPS    = _IOWR(0x14, structure=ctypes.c_uint)
    IND_USER_ADC_OFFSET_SET             = _IOW( 0x15, structure=ctypes.c_int)
    IND_USER_ADC_OFFSET_GET             = _IOR( 0x16, structure=ctypes.c_int)

#!===========================================================================
#!  Library functions.
#!===========================================================================

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

    #print("DEBUG: leds_modify: on=0x{:08X}, off=0x{:08X}, toggle=0x{:08X}".format(on, off, toggle))

    if (on & off):
        raise ValueError("'on' and 'off' arguments have conflicting bit(s) set (on=0x{:08X} off=0x{:08X} bits=0x{:08X})".format(on, off, (on & off)))
    elif (on & toggle):
        raise ValueError("'on' and 'toggle' arguments have conflicting bit(s) set (on=0x{:08X} toggle=0x{:08X} bits=0x{:08X})".format(on, toggle, (on & toggle)))
    elif (off & toggle):
        raise ValueError("'off' and 'toggle' arguments have conflicting bit(s) set (off=0x{:08X} toggle=0x{:08X} bits=0x{:08X})".format(off, toggle, (off & toggle)))

    bits = bit_flag_struct()
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

def ctrl_modify(set=0, clear=0, toggle=0, dev_hand=None):
    '''Modify control register by setting and clearing bits.'''

    if (set & clear):
        raise ValueError("'set' and 'clear' arguments have conflicting bit(s) set (set=0x{:08X} clear=0x{:08X} bits=0x{:08X})".format(set, clear, (set & clear)))
    elif (set & toggle):
        raise ValueError("'set' and 'toggle' arguments have conflicting bit(s) set (set=0x{:08X} toggle=0x{:08X} bits=0x{:08X})".format(set, toggle, (set & toggle)))
    elif (clear & toggle):
        raise ValueError("'clear' and 'toggle' arguments have conflicting bit(s) set (clear=0x{:08X} toggle=0x{:08X} bits=0x{:08X})".format(clear, toggle, (clear & toggle)))

    bits = bit_flag_struct()
    bits.set = set & Control.All
    bits.clear = clear & Control.All
    bits.toggle = toggle & Control.All

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

    #! Assert power key signal.
    on = Control.Modem_Power
    ctrl_modify(set=on, dev_hand=dev_hand)

    #! duration = 100-600ms => turn on.
    #! duration >= 600ms => turn off.  NB: seems to toggle power state.
    time.sleep(duration)

    #! Deassert power key signal.
    off = Control.Modem_Power | Control.Modem_Reset
    ctrl_modify(clear=off, dev_hand=dev_hand)

def modem_power_off(dev_hand=None):
    '''Turn off modem - assert power key signal for 600ms.'''
    '''NOTE: this seems to toggle the power state of the modem,'''
    '''rather than turn it off.'''

    #! duration = 100-600ms => turn on modem.
    #! duration >= 600ms => turn off modem.  NB. seems to toggle power state.
    duration = 0.7
    modem_power_pulse(duration=duration, dev_hand=dev_hand)

def modem_power_on(dev_hand=None):
    '''Turn on modem - asserts power key signal for 100ms.'''

    #! duration = 100-600ms => turn on modem.
    #! duration >= 600ms => turn off modem.  NB. seems to toggle power state.
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

def adc_capture_address(address=0, dev_hand=None):
    '''Set capture offset address.  Use for ping-pong capture.  Should be either 0 or half the buffer size.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_SET_ADDRESS, address)
    except:
        print("EXCEPTION: setting capture address.")
        raise

def adc_capture_set_mode(address=0,
                         mode=Config.Mode_PPS_Debug,
                         interrupt_enable=False,
                         capture_count=0,
                         delay_count=0,
                         peak_detect_start_count=Config.Peak_Start_Disable,
                         peak_detect_stop_count=Config.Peak_Stop_Disable,
                         adc_offset=Config.ADC_Offset,
                         dev_hand=None):
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
    cmd.adc_offset = adc_offset

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

def adc_capture_start(address,
                      capture_count,
                      delay_count,
                      capture_mode='auto',
                      signed=True,
                      peak_detect_start_count=Config.Peak_Start_Disable,
                      peak_detect_stop_count=Config.Peak_Stop_Disable,
                      adc_offset=Config.ADC_Offset,
                      dev_hand=None):
    '''Start ADC Capture.'''

    if capture_mode == 'manual':
        mode_start = Config.Mode_Manual_Signed if signed else Config.Mode_Manual_Unsigned
    elif capture_mode == 'auto':
        mode_start = Config.Mode_Start_Signed if signed else Config.Mode_Start_Unsigned
    else:
        msg = "capture_mode should be 'auto' or 'manual', not {!r}".format(capture_mode)
        raise ValueError(msg)

    adc_capture_set_mode(address=address,
                         mode=mode_start,
                         interrupt_enable=True,
                         capture_count=capture_count,
                         delay_count=delay_count,
                         peak_detect_start_count=peak_detect_start_count,
                         peak_detect_stop_count=peak_detect_stop_count,
                         adc_offset=adc_offset,
                         dev_hand=dev_hand)

def adc_capture_stop(dev_hand=None):
    '''Stop ADC Capture.'''

    adc_capture_set_mode(address=0,
                         mode=Config.Mode_Stop,
                         interrupt_enable=False,
                         dev_hand=dev_hand)

def adc_trigger(dev_hand=None):
    '''Manually Trigger ADC Capture.'''

    arg = Config.Mode_Manual_Trigger
    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_TRIG_PPS, arg)
    except:
        print("EXCEPTION: ADC Trigger.")
        raise

def adc_capture_maxmin_get(dev_hand=None):
    '''Get the maximum and minimum sample values and indices of each channel.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    maxmin = maxmin_struct()
    try:
        #! set mutable flag to true to place data in maxmin object.
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_READ_MAXMIN, maxmin, True)
    except:
        print("EXCEPTION: ADC Capture MaxMin Get.")
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

    #print("DEBUG: status_get: status = 0x{:08x}".format(value))
    return value

def adc_semaphore_get(dev_hand=None):
    '''Get ADC Semaphore.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    try:
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
    spi_cmd.port_addr[0] = 0x14         #! output mode register.
    spi_cmd.port_data[0] = 0x08 | 0x01  #! default, two's complement.
    spi_cmd.num_spi_writes = 1

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_SPI_WRITE, spi_cmd)
    except:
        print("EXCEPTION: ADC Set Semaphore.")
        raise

#!===========================================================================

def fpga_version_get(dev_hand=None):
    '''Get the FPGA Version information.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    fpga_version = FPGA_Version()
    try:
        ## set mutable flag to true to place data in the object.
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_FPGA_VERSION, fpga_version, True)
    except:
        print("EXCEPTION: FPGA Version Get.")
        raise

    return fpga_version

##----------------------------------------------------------------------------

def adc_clock_count_per_pps_get(dev_hand=None):
    """Get the ADC Clock Count Per PPS reading."""

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        a = fcntl.ioctl(dev_hand, IOCTL.IND_USER_ADC_CLOCK_COUNT_PER_PPS, "1234")
        value = struct.unpack('l', a)[0]
    except:
        print("EXCEPTION: Get ADC Clock Counter Per PPS.")
        raise

    return value

##----------------------------------------------------------------------------

def adc_offset_set(adc_offset, dev_hand=None):
    """Set the ADC Offset to be applied to ADC sample stream."""

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_ADC_OFFSET_SET, adc_offset)
    except:
        print("EXCEPTION: Set ADC Offset.")
        raise

##----------------------------------------------------------------------------

def adc_offset_get(dev_hand=None):
    """Set the ADC DC Offset to be applied to ADC sample stream."""

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        a = fcntl.ioctl(dev_hand, IOCTL.IND_USER_ADC_OFFSET_GET, "1234")
        value = struct.unpack('l', a)[0]
    except:
        print("EXCEPTION: Get ADC Offset.")
        raise

    return value

##----------------------------------------------------------------------------

def power_restart_requested(status=None, dev_hand=None):
    """
    Check if Restart Request is asserted from Power Management MCU.
    status [IN] -- is a raw status value.  If None, status will be fetched.
    Check Shutdown Request is not asserted (allows main board to run with out PMU board attached, as both signals may be floating depending on FPGA config)
    """
    if status == None:
        status = status_get(dev_hand)

    shutdown = (status & Status.Not_Shutdown_Request) == 0
    restart  = (status & Status.Not_Restart_Request) == 0
    result   = restart and not shutdown
    return result

def power_shutdown_requested(status=None, dev_hand=None):
    """
    Check if Shutdown Request is asserted from Power Management MCU.
    status [IN] -- is a raw status value.  If None, status will be fetched.
    Check Restart Request is not asserted (allows main board to run with out PMU board attached, as both signals may be floating depending on FPGA config)
    """
    if status == None:
        status = status_get(dev_hand)

    shutdown = (status & Status.Not_Shutdown_Request) == 0
    restart  = (status & Status.Not_Restart_Request) == 0
    result   = shutdown and not restart
    return result

#!===========================================================================

def power_os_running_off(dev_hand=None):
    """Deassert `not_os_running` (high) signal."""

    mask = Control.Not_OS_Running
    ctrl_modify(set=mask, dev_hand=dev_hand)

def power_os_running_on(dev_hand=None):
    """Assert `not_os_running` (low) signal."""

    mask = Control.Not_OS_Running
    ctrl_modify(clear=mask, dev_hand=dev_hand)

def power_os_running_toggle(dev_hand=None):
    """Toggle `not_os_running` signal."""

    mask = Control.Not_OS_Running
    ctrl_modify(toggle=mask, dev_hand=dev_hand)

def power_os_running_set(value=None, dev_hand=None):
    """
    Assert or Deassert `not_os_running` signal.
    """

    if value == True:
        power_os_running_on(dev_hand=dev_hand)
    elif value == False:
        power_os_running_off(dev_hand=dev_hand)

##----------------------------------------------------------------------------

def running_led_off(dev_hand=None):

    if IND_FPGA_API == 1:
        led = LED.Running
        leds_modify(off=led, dev_hand=dev_hand)
    elif IND_FPGA_API == 2:
        led = Control.Running
        ctrl_modify(clear=led, dev_hand=dev_hand)

def running_led_on(dev_hand=None):

    if IND_FPGA_API == 1:
        led = LED.Running
        leds_modify(on=led, dev_hand=dev_hand)
    elif IND_FPGA_API == 2:
        led = Control.Running
        ctrl_modify(set=led, dev_hand=dev_hand)

def running_led_toggle(dev_hand=None):

    if IND_FPGA_API == 1:
        led = LED.Running
        leds_modify(toggle=led, dev_hand=dev_hand)
    elif IND_FPGA_API == 2:
        led = Control.Running
        ctrl_modify(toggle=led, dev_hand=dev_hand)

##----------------------------------------------------------------------------

def alert_led_off(dev_hand=None):

    if IND_FPGA_API == 1:
        led = LED.Alert
        leds_modify(off=led, dev_hand=dev_hand)
    if IND_FPGA_API == 2:
        led = Control.Alert
        ctrl_modify(clear=led, dev_hand=dev_hand)

def alert_led_on(dev_hand=None):

    if IND_FPGA_API == 1:
        led = LED.Alert
        leds_modify(on=led, dev_hand=dev_hand)
    if IND_FPGA_API == 2:
        led = Control.Alert
        ctrl_modify(set=led, dev_hand=dev_hand)

def alert_led_toggle(dev_hand=None):

    if IND_FPGA_API == 1:
        led = LED.Alert
        leds_modify(toggle=led, dev_hand=dev_hand)
    if IND_FPGA_API == 2:
        led = Control.Alert
        ctrl_modify(toggle=led, dev_hand=dev_hand)

##----------------------------------------------------------------------------

def pps_ok_led_off(dev_hand=None):

    led = LED.PPS_OK
    leds_modify(off=led, dev_hand=dev_hand)

def pps_ok_led_on(dev_hand=None):

    led = LED.PPS_OK
    leds_modify(on=led, dev_hand=dev_hand)

def pps_ok_led_toggle(dev_hand=None):

    led = LED.PPS_OK
    leds_modify(toggle=led, dev_hand=dev_hand)

#!===========================================================================

def modem_led_off(dev_hand=None):

    led = LED.Modem_OK
    leds_modify(off=led, dev_hand=dev_hand)

def modem_led_on(dev_hand=None):

    led = LED.Modem_OK
    leds_modify(on=led, dev_hand=dev_hand)

def modem_led_toggle(dev_hand=None):

    led = LED.Modem_OK
    leds_modify(toggle=led, dev_hand=dev_hand)

#!===========================================================================

def weather_led_off(dev_hand=None):

    led = LED.Weather_Station_OK
    leds_modify(off=led, dev_hand=dev_hand)

def weather_led_on(dev_hand=None):

    led = LED.Weather_Station_OK
    leds_modify(on=led, dev_hand=dev_hand)

def weather_led_toggle(dev_hand=None):

    led = LED.Weather_Station_OK
    leds_modify(toggle=led, dev_hand=dev_hand)

#!===========================================================================

def power_led_off(dev_hand=None):

## IND1:
#     led = LED.Power_OK
## IND2:
    led = LED.Power_OK
    leds_modify(off=led, dev_hand=dev_hand)

def power_led_on(dev_hand=None):

## IND1:
#     led = LED.Power_OK
## IND2:
    led = LED.Power_OK
    leds_modify(on=led, dev_hand=dev_hand)

def power_led_toggle(dev_hand=None):

## IND1:
#     led = LED.Power_OK
## IND2:
    led = LED.Power_OK
    leds_modify(toggle=led, dev_hand=dev_hand)

##----------------------------------------------------------------------------

def battery_led_off(dev_hand=None):

## IND1:
#     led = LED.Battery_OK
## IND2:
    led = LED.Battery_OK
    leds_modify(off=led, dev_hand=dev_hand)

def battery_led_on(dev_hand=None):

## IND1:
#     led = LED.Battery_OK
## IND2:
    led = LED.Battery_OK
    leds_modify(on=led, dev_hand=dev_hand)

def battery_led_toggle(dev_hand=None):

## IND1:
#     led = LED.Battery_OK
## IND2:
    led = LED.Battery_OK
    leds_modify(toggle=led, dev_hand=dev_hand)

##----------------------------------------------------------------------------

def spare_led_off(dev_hand=None):

    led = LED.Spare
    leds_modify(off=led, dev_hand=dev_hand)

def spare_led_on(dev_hand=None):

    led = LED.Spare
    leds_modify(on=led, dev_hand=dev_hand)

def spare_led_toggle(dev_hand=None):

    led = LED.Spare
    leds_modify(toggle=led, dev_hand=dev_hand)

##----------------------------------------------------------------------------

def debug_led_off(dev_hand=None):

    led = LED.Debug1
    led = 0xFFFFFFFF
    leds_modify(off=led, dev_hand=dev_hand)

def debug_led_on(dev_hand=None):

    led = LED.Debug1
    led = 0xFFFFFFFF
    leds_modify(on=led, dev_hand=dev_hand)

def debug_led_toggle(dev_hand=None):

    led = LED.Debug1
    led = 0xFFFFFFFF
    leds_modify(toggle=led, dev_hand=dev_hand)

##----------------------------------------------------------------------------

def blinky(count=0, delay=0.1, dev_hand=None):
    """Cycle through all the LEDs."""

    if not dev_hand:
        dev_hand = get_device_handle()

    led_seq = [ LED.Battery_OK, LED.Power_OK, LED.PPS_OK,
                LED.Running, LED.Modem_OK, LED.Alert,
                LED.Weather_Station_OK, LED.Spare ]

    ## append leds in reverse order, omitting end LEDs.
    led_seq += list(reversed(led_seq[1:-1]))

    remaining = 1 if count == 0 else count
    while remaining:
        for i, led in enumerate(led_seq):
            on = led & LED.All
            off = ~led & LED.All
            leds_modify(on=on, off=off, dev_hand=dev_hand)
            time.sleep(delay)
        if count > 0:
            remaining -= 1

    led = led_seq[0]
    on = led & LED.All
    off = ~led & LED.All
    leds_modify(on=on, off=off, dev_hand=dev_hand)
    time.sleep(delay)

    leds_modify(on=0, off=LED.All, dev_hand=dev_hand)

#!===========================================================================
#!  module test.
#!===========================================================================

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

    #led_seq = [ LED.Battery_OK, LED.Power_OK, LED.PPS_OK, LED.Running,
    led_seq = [ LED.PPS_OK, LED.Running, LED.Modem_OK, LED.Alert, LED.Weather_Station_OK, LED.Spare ]
    led_seq += led_seq[1:-1][::-1]
    for count, led in enumerate(led_seq * 10):
        ##
        #! Cycle LEDs.
        ##
        on = led & LED.All
        off = ~on & LED.All
        if 0:
            print("DEBUG: count = {}".format(count))
            print("DEBUG: on    = 0x{:0X}".format(on))
            print("DEBUG: off   = 0x{:0X}".format(off))

        leds_modify(on, off, dev_hand=dev_hand)

        ##
        #! Cycle Modem control.
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

        ctrl_modify(set=on, clear=off, dev_hand=dev_hand)

        time.sleep(0.1)

    dev_hand.close()

#!===========================================================================
#!  Check if running this module, rather than importing it.
#!===========================================================================

if __name__ == "__main__":
    main()

