#!/usr/bin/env python2

"""IND Driver Module."""

from enum import IntEnum

from efd_config import TestMode
from efd_config import PhaseMode

import ioctl
import ctypes
import fcntl
import mmap
import time
import array
import struct

import logging

#!
#! Defaults.
#!
dev_name = '/dev/IND'

BANK_COUNT = 2

max_channels = 3

SAMPLE_SIZE = ctypes.sizeof(ctypes.c_uint16)

max_capture_count = 10 * 1024 * 1024

#! 2 bytes per sample.  2 buffers for ping-pong acquisition.
max_capture_size = max_capture_count * SAMPLE_SIZE * max_channels * BANK_COUNT

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
#! TODO: Rename this class to Config_Register_Bits
#!       Make enum symbols all upper case
#!
#! Config Constants/Defaults.
#!
#=============================================================================
class Config( IntEnum ):
    PPS_Generate            = 1 << 0
    Debug_DMA_Start         = 1 << 1
    DMA_Halt                = 1 << 2
    DMA_Reset               = 1 << 3

    FPGA_Reset              = 1 << 4
    ADC_Test_Data_Post_Fifo = 1 << 5
    PPS_Debug_Mode          = 1 << 6
    DMA_Debug_Mode          = 1 << 7

    Debug_Select_Ch_0       = 0
    Debug_Select_Ch_1       = 1 << 8
    Debug_Select_Ch_2       = 2 << 8
    Debug_Select_Ch_Off     = 3 << 8
    Debug_Select_Active     = 1 << 11

    Unsigned_Data           = 0
    Signed_Data             = 1 << 12

    ADC_Test_Data_Pre_Fifo  = 1 << 13

    PHASE_MODE_POLY         = 0
    PHASE_MODE_CH_0         = 1 << 14
    PHASE_MODE_CH_1         = 2 << 14
    PHASE_MODE_CH_2         = 3 << 14
    PHASE_MODE_DEFAULT      = PHASE_MODE_POLY

    All                     = PPS_Generate                              \
                            | Debug_DMA_Start | DMA_Halt | DMA_Reset    \
                            | FPGA_Reset | ADC_Test_Data_Post_Fifo      \
                            | PPS_Debug_Mode | DMA_Debug_Mode           \
                            | Debug_Select_Ch_0 | Debug_Select_Ch_1     \
                            | Debug_Select_Ch_2 | Debug_Select_Ch_Off   \
                            | Debug_Select_Active                       \
                            | Unsigned_Data | Signed_Data               \
                            | ADC_Test_Data_Pre_Fifo                    \
                            | PHASE_MODE_POLY | PHASE_MODE_CH_0         \
                            | PHASE_MODE_CH_1 | PHASE_MODE_CH_2         \

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

#     Mode_Start_Unsigned     = Mode_Normal | Unsigned_Data
#     Mode_Start_Signed       = Mode_Normal | Signed_Data
#     Mode_Manual_Unsigned    = Mode_PPS_Trigger | Unsigned_Data
#     Mode_Manual_Signed      = Mode_PPS_Trigger | Signed_Data
    Mode_Auto_Trigger       = Mode_Normal
    Mode_Manual_Trigger     = Mode_PPS_Trigger
    Mode_Stop               = Mode_System_Halt


#=============================================================================
#! Default values
#=============================================================================

phase_mode_to_config_register_mask = \
{
    PhaseMode.POLY  : Config.PHASE_MODE_POLY,
    PhaseMode.RED   : Config.PHASE_MODE_CH_0,
    PhaseMode.WHITE : Config.PHASE_MODE_CH_1,
    PhaseMode.BLUE  : Config.PHASE_MODE_CH_2,
}

#=============================================================================
#! Default values
#=============================================================================

CAPTURE_COUNT_DEFAULT       = 0
DELAY_COUNT_DEFAULT         = 0

PEAK_START_DISABLE_DEFAULT  = 0x00FFFFFF
PEAK_STOP_DISABLE_DEFAULT   = 0x00FFFFFF

ADC_OFFSET_DEFAULT          = 0


#=============================================================================
#!
#! TODO: Rename this class ??
#!       Make enum symbols all upper case
#!
#! Cmd Interrupt Constants
#!
#=============================================================================
class Interrupt( IntEnum ):
    Disable     = 0
    Enable      = 1 << 0

#=============================================================================
#!
#! TODO: Rename this class to Status_Register_Bits
#!       Make enum symbols all upper case
#!
#! Status Register Constants
#!
#=============================================================================

class Status( IntEnum ):
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
    Not_Restart_Request     = 1 << 14       #! PM MCU has requested a restart
    Not_Shutdown_Request    = 1 << 15       #! PM MCU has requested a shutdown

    ADC_Test_Data_Pre_Fifo  = 1 << 16

    PHASE_MODE_POLY         = 0
    PHASE_MODE_CH_0         = 1 << 17
    PHASE_MODE_CH_1         = 2 << 17
    PHASE_MODE_CH_2         = 3 << 17
    PHASE_MODE_DEFAULT      = PHASE_MODE_POLY


    All                     = SPI_Busy | S2MM_Error | MM2S_Read_Complete | MM2S_Error   \
                            | SPI_Error | Interrupt_Active | FPGA_Reset | ADC_Test      \
                            | PPS_Debug | DMA_Reset | DMA_Debug | Interrupt_Enable      \
                            | Battery_Low | AC_Power                                    \
                            | Not_Restart_Request | Not_Shutdown_Request                \
                            | ADC_Test_Data_Pre_Fifo                                    \
                            | PHASE_MODE_POLY | PHASE_MODE_CH_0                         \
                            | PHASE_MODE_CH_1 | PHASE_MODE_CH_2                         \

#=============================================================================
#!
#! TODO: Rename this class to Control_Register_Bits
#!       Make enum symbols all upper case
#!
#! Control Register Constants
#!
#=============================================================================

class Control( IntEnum ):
    Modem_Reset             = 1 << 0
    Modem_Power             = 1 << 1
    EN_Select               = 1 << 2        #! What is this ??

    Not_OS_Running          = 1 << 3        #! output low to indicate to PM MCU that we are up and running ok
    Not_Spare_MCU           = 1 << 4        #! a spare signal to PM MCU (could be input or output)?

    All                     = Modem_Reset | Modem_Power | EN_Select     \
                            | Not_OS_Running | Not_Spare_MCU

#=============================================================================
#!
#! TODO: Rename this class to LED_Register_Bits
#!       Make enum symbols all upper case
#!
#! IOCTL LED Constants
#!
#=============================================================================

class LED( IntEnum ):
#! IND1 assignments
    Running                 = 1 << 0
    Alert                   = 1 << 1
    Spare_3G                = 1 << 2        #! IND1 Spare LED on 3G board.
    PPS_OK                  = 1 << 3
    Modem_OK                = 1 << 4
    Weather_Station_OK      = 1 << 5
    Power_OK                = 1 << 6
    Battery_OK              = 1 << 7

    Spare1_3G               = 1 << 8
    Spare2_3G               = 1 << 9        #! IND2 Spare LED on 3G board.
    Spare3_3G               = 1 << 10
    Spare4_3G               = 1 << 11
    Spare1_RF               = 1 << 12
    Spare2_RF               = 1 << 13
    Spare3_RF               = 1 << 14
    Spare4_RF               = 1 << 15

    Debug0                  = 1 << 28
    Debug1                  = 1 << 29
    Debug2                  = 1 << 30
    Debug3                  = 1 << 30   #! FIXME !!

    All                     = Running | Alert | Spare_3G | PPS_OK           \
                            | Modem_OK | Weather_Station_OK                 \
                            | Battery_OK | Power_OK                         \
                            | Spare1_3G | Spare2_3G | Spare3_3G | Spare4_3G \
                            | Spare1_RF | Spare2_RF | Spare3_RF | Spare4_RF \
                            | Debug0 | Debug1 | Debug2 | Debug3             \

    Spare                   = Spare_3G | Spare2_3G     #! Use both bits so works with IND1 and IND2 boards.

#=============================================================================

class Struct_Base(ctypes.Structure):

    def __repr__(self):
        s = ', '.join("{}={}".format(t[0],getattr(self,t[0])) for t in self._fields_)
        return "{}: ( {} )".format(self.__class__.__name__, s)

#=============================================================================

class MaxMin(Struct_Base):
    _fields_ = [
        #! version 1 : peak values and indices.
        ('max_ch0_data',    ctypes.c_int16),        #! __i16 max_ch0_data
        ('_unused_1_',      ctypes.c_int16),        #! __i16 (unused)
        ('max_ch0_addr',    ctypes.c_uint32),       #! __u32 max_ch0_addr
        ('min_ch0_data',    ctypes.c_int16),        #! __i16 min_ch0_data
        ('_unused_2_',      ctypes.c_int16),        #! __i16 (unused)
        ('min_ch0_addr',    ctypes.c_uint32),       #! __u32 min_ch0_addr

        ('max_ch1_data',    ctypes.c_int16),        #! __i16 max_ch1_data
        ('_unused_3_',      ctypes.c_int16),        #! __i16 (unused)
        ('max_ch1_addr',    ctypes.c_uint32),       #! __u32 max_ch1_addr
        ('min_ch1_data',    ctypes.c_int16),        #! __i16 min_ch1_data
        ('_unused_4_',      ctypes.c_int16),        #! __i16 (unused)
        ('min_ch1_addr',    ctypes.c_uint32),       #! __u32 min_ch1_addr

        ('max_ch2_data',    ctypes.c_int16),        #! __i16 max_ch2_data
        ('_unused_5_',      ctypes.c_int16),        #! __i16 (unused)
        ('max_ch2_addr',    ctypes.c_uint32),       #! __u32 max_ch2_addr
        ('min_ch2_data',    ctypes.c_int16),        #! __i16 min_ch2_data
        ('_unused_6_',      ctypes.c_int16),        #! __i16 (unused)
        ('min_ch2_addr',    ctypes.c_uint32),       #! __u32 min_ch2_addr

        #! version 2 : add peak counts.
        ('max_ch0_count',   ctypes.c_uint32),       #! __u32 max_ch0_count
        ('min_ch0_count',   ctypes.c_uint32),       #! __u32 min_ch0_count

        ('max_ch1_count',   ctypes.c_uint32),       #! __u32 max_ch1_count
        ('min_ch1_count',   ctypes.c_uint32),       #! __u32 min_ch1_count

        ('max_ch2_count',   ctypes.c_uint32),       #! __u32 max_ch2_count
        ('min_ch2_count',   ctypes.c_uint32),       #! __u32 min_ch2_count
    ]

#=============================================================================

class MaxMin2(Struct_Base):
    _fields_ = [
        #! version 1 : peak values and indices.
        ('max_ch0_data',    ctypes.c_int32),        #! __i16 max_ch0_data
        ('max_ch0_addr',    ctypes.c_uint32),       #! __u32 max_ch0_addr
        ('min_ch0_data',    ctypes.c_int32),        #! __i16 min_ch0_data
        ('min_ch0_addr',    ctypes.c_uint32),       #! __u32 min_ch0_addr

        ('max_ch1_data',    ctypes.c_int32),        #! __i16 max_ch1_data
        ('max_ch1_addr',    ctypes.c_uint32),       #! __u32 max_ch1_addr
        ('min_ch1_data',    ctypes.c_int32),        #! __i16 min_ch1_data
        ('min_ch1_addr',    ctypes.c_uint32),       #! __u32 min_ch1_addr

        ('max_ch2_data',    ctypes.c_int32),        #! __i16 max_ch2_data
        ('max_ch2_addr',    ctypes.c_uint32),       #! __u32 max_ch2_addr
        ('min_ch2_data',    ctypes.c_int32),        #! __i16 min_ch2_data
        ('min_ch2_addr',    ctypes.c_uint32),       #! __u32 min_ch2_addr

        #! version 2 : add peak counts.
        ('max_ch0_count',   ctypes.c_uint32),       #! __u32 max_ch0_count
        ('min_ch0_count',   ctypes.c_uint32),       #! __u32 min_ch0_count

        ('max_ch1_count',   ctypes.c_uint32),       #! __u32 max_ch1_count
        ('min_ch1_count',   ctypes.c_uint32),       #! __u32 min_ch1_count

        ('max_ch2_count',   ctypes.c_uint32),       #! __u32 max_ch2_count
        ('min_ch2_count',   ctypes.c_uint32),       #! __u32 min_ch2_count
    ]

#=============================================================================

#! see https://stackoverflow.com/questions/24307022/how-to-compare-two-ctypes-objects-for-equality
#! for more generalise comparison operator functions which can be used in a base class.

class TimeSpec(Struct_Base):
    _fields_ = [
        ('tv_sec',    ctypes.c_long),
        ('tv_nsec',   ctypes.c_long),
    ]

    #! simple efficient comparison function.
    #! assumes `other` is a TimeSpec class.
    def __eq__(self, other):
        return self.tv_sec == other.tv_sec and self.tv_nsec == other.tv_nsec

    #! simple efficient comparison function.
    #! assumes `other` is a TimeSpec class.
    def __ne__(self, other):
        return self.tv_sec != other.tv_sec or self.tv_nsec != other.tv_nsec

    #! convert to floating point
    def __float__(self):
        f = float(self.tv_sec) + (float(self.tv_nsec) / 1000000000.0)
        return f

#=============================================================================

class CaptureInfo(Struct_Base):
    _fields_ = [
        ('irq_time',                TimeSpec),          #! struct timespec irq_time
        ('int_status',              ctypes.c_uint32),   #! __u32 status
        ('irq_count',               ctypes.c_uint32),   #! __u32 irq_count
        ('semaphore',               ctypes.c_int32),    #! __u32 semaphore
        ('adc_clock_count_per_pps', ctypes.c_uint32),   #! __u32 adc_clock_count_per_pps
        ('bank',                    ctypes.c_int32),    #! __u32 bank
        ('maxmin_normal',           MaxMin),            #! IND_maxmin_struct maxmin_normal
        ('maxmin_squared',          MaxMin2),           #! IND_maxmin_struct maxmin_squared
    ]

class CaptureInfoList(Struct_Base):
    _fields_ = [
        ('ci',    CaptureInfo * BANK_COUNT),
    ]

    def __len__(self):
        return BANK_COUNT

    def __getitem__(self, key):
        return self.ci[key]

    def __iter__(self): #! return an iterator
        return iter(self.ci)

#     def __iter__(self): #! initialise the iterator
#         self._it = 0
#         return self
#
#     def next(self): #! __next__(self) for python 3 !!
#         if self._it >= BANK_COUNT:
#             raise StopIteration
#
#         ci = self.ci[self._it]
#         self._it += 1
#
#         return ci

#=============================================================================

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
    IND_USER_READ_MAXMIN_NORMAL         = _IOR( 0x12, structure=MaxMin)
    IND_USER_FPGA_VERSION               = _IOWR(0x13, structure=FPGA_Version)
    IND_USER_ADC_CLOCK_COUNT_PER_PPS    = _IOWR(0x14, structure=ctypes.c_uint32)
    IND_USER_ADC_OFFSET_SET             = _IOW( 0x15, structure=ctypes.c_int32)
    IND_USER_ADC_OFFSET_GET             = _IOR( 0x16, structure=ctypes.c_int32)
    IND_USER_READ_MAXMIN_SQUARED        = _IOR( 0x17, structure=MaxMin2)
    IND_USER_CAPTURE_INFO_0_GET         = _IOR( 0x18, structure=CaptureInfo)
    IND_USER_CAPTURE_INFO_1_GET         = _IOR( 0x19, structure=CaptureInfo)
    IND_USER_CAPTURE_INFO_LIST_GET      = _IOR( 0x1A, structure=CaptureInfoList)
    IND_USER_DMA_MEM_SYNC_ALL           = _IOW( 0x1B, structure=ctypes.c_uint32)
    IND_USER_DMA_MEM_SYNC_BANK          = _IOW( 0x1B, structure=ctypes.c_uint32)

#!===========================================================================
#!  Library functions.
#!===========================================================================

def get_device_handle():
    try:
        #print("DEBUG: opening device name '{}'".format(dev_name))
        #dev_hand = open(dev_name, 'rw')
        dev_hand = open(dev_name, 'r+b')
        #print("DEBUG: dev_hand={!r}".format(dev_hand))
    except IOError:
        print("EXCEPTION: opening device name '{}'".format(dev_name))
        raise
    return dev_hand

def fpga_reset(dev_hand=None):
    '''Reset the FPGA.'''
    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_RESET, 0)
    except IOError:
        print("IOError: resetting ADC DMA engine.")
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
    except IOError:
        print("IOError: modifying LEDS '{!r}'".format(bits))
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
    except IOError:
        print("IOError: modifying CTRL '{!r}'".format(bits))
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
    except Exception:
        print("EXCEPTION: getting ADC Memory Map.")
        raise

    return mem

def adc_dma_reset(dev_hand=None):
    '''Reset ADC DMA engine.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_DMA_RESET, 0)
    except IOError:
        print("IOError: resetting ADC DMA engine.")
        raise

def adc_capture_address(address=0, dev_hand=None):
    '''Set capture offset address.  Use for ping-pong capture.  Should be either 0 or half the buffer size.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_SET_ADDRESS, address)
    except IOError:
        print("IOError: setting capture address.")
        raise

def adc_capture_set_mode( address                   = 0,
                          mode                      = Config.Mode_PPS_Debug,
                          interrupt_enable          = False,
                          capture_count             = CAPTURE_COUNT_DEFAULT,
                          delay_count               = DELAY_COUNT_DEFAULT,
                          peak_detect_start_count   = PEAK_START_DISABLE_DEFAULT,
                          peak_detect_stop_count    = PEAK_STOP_DISABLE_DEFAULT,
                          adc_offset                = ADC_OFFSET_DEFAULT,
                          dev_hand                  = None
                        ):
    '''Setup ADC Capture parameters.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    cmd = cmd_struct()

    cmd.config = mode
    cmd.interrupt = 1 if interrupt_enable else 0
    cmd.address = address
    cmd.capture_count = capture_count
    cmd.delay_count = delay_count
    cmd.peak_detect_start_count = peak_detect_start_count
    cmd.peak_detect_stop_count = peak_detect_stop_count
    cmd.adc_offset = adc_offset

    logging.info( "adc_capture_mode_set: cmd.config                  = 0x{:08x}".format( cmd.config ) )
    logging.info( "adc_capture_mode_set: cmd.interrupt               = 0x{:08x}".format( cmd.interrupt ) )
    logging.info( "adc_capture_mode_set: cmd.address                 = 0x{:08x}".format( cmd.address ) )
    logging.info( "adc_capture_mode_set: cmd.capture_count           = 0x{:08x}".format( cmd.capture_count ) )
    logging.info( "adc_capture_mode_set: cmd.delay_count             = 0x{:08x}".format( cmd.delay_count ) )
    logging.info( "adc_capture_mode_set: cmd.peak_detect_start_count = 0x{:08x}".format( cmd.peak_detect_start_count ) )
    logging.info( "adc_capture_mode_set: cmd.peak_detect_stop_count  = 0x{:08x}".format( cmd.peak_detect_stop_count ) )
    logging.info( "adc_capture_mode_set: cmd.adc_offset              = {}".format( cmd.adc_offset ) )

    #status = status_get(dev_hand=dev_hand)

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_SET_MODE, cmd)
    except IOError:
        print("IOError: ADC Capture Setup.")
        raise

    #status = status_get(dev_hand=dev_hand)

def adc_capture_start( address,
                       capture_count,
                       delay_count,
                       capture_mode             = 'auto',
                       signed                   = True,
                       peak_detect_start_count  = PEAK_START_DISABLE_DEFAULT,
                       peak_detect_stop_count   = PEAK_STOP_DISABLE_DEFAULT,
                       adc_offset               = ADC_OFFSET_DEFAULT,
                       test_mode                = TestMode.NORMAL,
                       phase_mode               = Config.PHASE_MODE_DEFAULT,
                       dev_hand                 = None
                    ):
    '''Start ADC Capture.'''

    logging.info( "adc_capture_start: capture_mode={!r}".format( capture_mode ) )
    logging.info( "adc_capture_start: test_mode={!r}".format( test_mode ) )
    logging.info( "adc_capture_start: phase_mode={!r}".format( phase_mode ) )

    if capture_mode not in [ 'auto', 'manual' ]:
        msg = "capture_mode should be 'auto' or 'manual', not {!r}".format(capture_mode)
        raise ValueError(msg)

    mode_start = 0

    mode_start |= Config.Mode_Manual_Trigger if capture_mode == 'manual' else 0
    mode_start |= Config.Mode_Auto_Trigger   if capture_mode == 'auto'   else 0

    mode_start |= Config.Signed_Data if signed else Config.Unsigned_Data

    mode_start |= Config.ADC_Test_Data_Post_Fifo if test_mode == TestMode.ADC_POST_FIFO else 0
    mode_start |= Config.ADC_Test_Data_Pre_Fifo  if test_mode == TestMode.ADC_PRE_FIFO  else 0

    phase_mode_mask = phase_mode_to_config_register_mask.get( phase_mode, Config.PHASE_MODE_DEFAULT )

    mode_start |= phase_mode_mask

    logging.info( "adc_capture_start: mode_start=0x{:08x}".format( mode_start ) )

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
    except IOError:
        print("IOError: ADC Trigger.")
        raise

def adc_capture_maxmin_normal_get(dev_hand=None):
    '''Get the maximum and minimum normal sample values and indices of each channel.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    maxmin = MaxMin()
    try:
        #! set mutable flag to true to place data in maxmin object.
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_READ_MAXMIN_NORMAL, maxmin, True)
    except IOError:
        print("IOError: ADC Capture MaxMin Normal Get.")
        raise

    return maxmin

def adc_capture_maxmin_squared_get(dev_hand=None):
    '''Get the maximum and minimum squared sample values and indices of each channel.'''

    if not dev_hand:
        dev_hand = get_device_handle()

#     maxmin = MaxMin()
    maxmin = MaxMin2()
    try:
        #! set mutable flag to true to place data in maxmin object.
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_READ_MAXMIN_SQUARED, maxmin, True)
    except IOError:
        print("IOError: ADC Capture MaxMin Squared Get.")
        raise

    return maxmin

def adc_capture_info_get(bank, dev_hand=None):
    '''Get the capture info from the kernel driver.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    ioctl_id = IOCTL.IND_USER_CAPTURE_INFO_0_GET if bank == 0 else IOCTL.IND_USER_CAPTURE_INFO_1_GET

    capture_info = CaptureInfo()
    try:
        #! set mutable flag to true to place data in our object.
        fcntl.ioctl(dev_hand, ioctl_id, capture_info, True)
    except IOError:
        print("IOError: ADC Capture Info Get.")
        raise

    return capture_info

def adc_capture_info_list_get(dev_hand=None):
    '''Get the capture info list from the kernel driver.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    ioctl_id = IOCTL.IND_USER_CAPTURE_INFO_LIST_GET

    ci_list = CaptureInfoList()
    try:
        #! set mutable flag to true to place data in our object.
        fcntl.ioctl(dev_hand, ioctl_id, ci_list, True)
    except IOError:
        print("IOError: ADC Capture Info List Get.")
        raise

    return ci_list

def dma_mem_sync_all(dev_hand=None):
    '''Synchronise all DMA memory by invalidating the memory cache.'''

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_DMA_MEM_SYNC_ALL)
#         fcntl.ioctl(dev_hand, IOCTL.DMA_MEM_SYNC_ALL, 0)
    except IOError:
        print("IOError: DMA Memory Sync All.")
        raise

def dma_mem_sync_bank(bank, dev_hand=None):
    '''Synchronise a capture bank of DMA memory by invalidating the memory cache.'''

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_DMA_MEM_SYNC_BANK, bank)
    except IOError:
        print("IOError: DMA Memory Sync Bank (bank={!r}).".format(bank))
        raise

def status_get(dev_hand=None):
    '''Get FPGA Status.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        a = fcntl.ioctl(dev_hand, IOCTL.IND_USER_STATUS, "1234")
        value = struct.unpack('L', a)[0]
    except IOError:
        print("IOError: Get Status.")
        raise

    #print("DEBUG: status_get: status = 0x{:08x}".format(value))
    return value

def adc_semaphore_get(dev_hand=None):
    '''Get ADC Semaphore.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        a = fcntl.ioctl(dev_hand, IOCTL.IND_USER_GET_SEM, "1234")
        value = struct.unpack('L', a)[0]
    except IOError:
        print("IOError: ADC Get Semaphore.")
        raise

    return value

def adc_semaphore_set(value=0, dev_hand=None):
    '''Set ADC Semaphore.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_SET_SEM, value)
    except IOError:
        print("IOError: ADC Set Semaphore.")
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
    except IOError:
        print("IOError: ADC Set Semaphore.")
        raise

#!===========================================================================

def fpga_version_get(dev_hand=None):
    '''Get the FPGA Version information.'''

    if not dev_hand:
        dev_hand = get_device_handle()

    fpga_version = FPGA_Version()
    try:
        #! set mutable flag to true to place data in the object.
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_FPGA_VERSION, fpga_version, True)
    except IOError:
        print("IOError: FPGA Version Get.")
        raise

    return fpga_version

#!----------------------------------------------------------------------------

def adc_clock_count_per_pps_get(dev_hand=None):
    """Get the ADC Clock Count Per PPS reading."""

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        a = fcntl.ioctl(dev_hand, IOCTL.IND_USER_ADC_CLOCK_COUNT_PER_PPS, "1234")
        value = struct.unpack('L', a)[0]
    except IOError:
        print("IOError: Get ADC Clock Counter Per PPS.")
        raise

    return value

#!----------------------------------------------------------------------------

def adc_offset_set(adc_offset, dev_hand=None):
    """Set the ADC Offset to be applied to ADC sample stream."""

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        fcntl.ioctl(dev_hand, IOCTL.IND_USER_ADC_OFFSET_SET, adc_offset)
    except IOError:
        print("IOError: Set ADC Offset.")
        raise

#!----------------------------------------------------------------------------

def adc_offset_get(dev_hand=None):
    """Set the ADC DC Offset to be applied to ADC sample stream."""

    if not dev_hand:
        dev_hand = get_device_handle()

    try:
        a = fcntl.ioctl(dev_hand, IOCTL.IND_USER_ADC_OFFSET_GET, "1234")
        value = struct.unpack('l', a)[0]
    except IOError:
        print("IOError: Get ADC Offset.")
        raise

    return value

#!----------------------------------------------------------------------------

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

#!----------------------------------------------------------------------------

def running_led_off(dev_hand=None):

    led = LED.Running
    leds_modify(off=led, dev_hand=dev_hand)

def running_led_on(dev_hand=None):

    led = LED.Running
    leds_modify(on=led, dev_hand=dev_hand)

def running_led_toggle(dev_hand=None):

    led = LED.Running
    leds_modify(toggle=led, dev_hand=dev_hand)

#!----------------------------------------------------------------------------

def alert_led_off(dev_hand=None):

    led = LED.Alert
    leds_modify(off=led, dev_hand=dev_hand)

def alert_led_on(dev_hand=None):

    led = LED.Alert
    leds_modify(on=led, dev_hand=dev_hand)

def alert_led_toggle(dev_hand=None):

    led = LED.Alert
    leds_modify(toggle=led, dev_hand=dev_hand)

#!----------------------------------------------------------------------------

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

#! IND1:
#     led = LED.Power_OK
#! IND2:
    led = LED.Power_OK
    leds_modify(off=led, dev_hand=dev_hand)

def power_led_on(dev_hand=None):

#! IND1:
#     led = LED.Power_OK
#! IND2:
    led = LED.Power_OK
    leds_modify(on=led, dev_hand=dev_hand)

def power_led_toggle(dev_hand=None):

#! IND1:
#     led = LED.Power_OK
#! IND2:
    led = LED.Power_OK
    leds_modify(toggle=led, dev_hand=dev_hand)

#!----------------------------------------------------------------------------

def battery_led_off(dev_hand=None):

#! IND1:
#     led = LED.Battery_OK
#! IND2:
    led = LED.Battery_OK
    leds_modify(off=led, dev_hand=dev_hand)

def battery_led_on(dev_hand=None):

#! IND1:
#     led = LED.Battery_OK
#! IND2:
    led = LED.Battery_OK
    leds_modify(on=led, dev_hand=dev_hand)

def battery_led_toggle(dev_hand=None):

#! IND1:
#     led = LED.Battery_OK
#! IND2:
    led = LED.Battery_OK
    leds_modify(toggle=led, dev_hand=dev_hand)

#!----------------------------------------------------------------------------

def spare_led_off(dev_hand=None):

    led = LED.Spare
    leds_modify(off=led, dev_hand=dev_hand)

def spare_led_on(dev_hand=None):

    led = LED.Spare
    leds_modify(on=led, dev_hand=dev_hand)

def spare_led_toggle(dev_hand=None):

    led = LED.Spare
    leds_modify(toggle=led, dev_hand=dev_hand)

#!----------------------------------------------------------------------------

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

#!----------------------------------------------------------------------------

def blinky(count=0, delay=0.1, dev_hand=None):
    """Cycle through all the LEDs."""

    if not dev_hand:
        dev_hand = get_device_handle()

    led_seq = [ LED.Battery_OK, LED.Power_OK, LED.PPS_OK,
                LED.Running, LED.Modem_OK, LED.Alert,
                LED.Weather_Station_OK, LED.Spare ]

    #! append leds in reverse order, omitting end LEDs.
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

    capture_info = CaptureInfo()
    print("\ncapture_info = {!r}".format(capture_info))

    ci_list = CaptureInfoList()
    print("\nci_list      = {!r}".format(ci_list))

    list_ci_list = list(ci_list)
    print("\nlist_ci_list = {!r}".format(list_ci_list))

    print("\nci_list.ci[0] = {!r}".format(ci_list.ci[0]))
    print("\nci_list.ci[1] = {!r}".format(ci_list.ci[1]))

    print("\nci_list[0]    = {!r}".format(ci_list[0]))
    print("\nci_list[1]    = {!r}".format(ci_list[1]))

    for i, ci in enumerate(ci_list):
        print("\nci[i={}]  = {!r}".format(i, ci))

    try:
        print("DEBUG: opening device name '{}'".format(dev_name))
        #dev_hand = open(dev_name, 'rw')
        dev_hand = open(dev_name, 'r+b')
        print("DEBUG: dev_hand={!r}".format(dev_hand))
    except IOError:
        print("IOError: opening device name '{}'".format(dev_name))
        raise

    #led_seq = [ LED.Battery_OK, LED.Power_OK, LED.PPS_OK, LED.Running,
    led_seq = [ LED.PPS_OK, LED.Running, LED.Modem_OK, LED.Alert, LED.Weather_Station_OK, LED.Spare ]
    led_seq += led_seq[1:-1][::-1]
    for count, led in enumerate(led_seq * 10):
        #!
        #! Cycle LEDs.
        #!
        on = led & LED.All
        off = ~on & LED.All
        if 0:
            print("DEBUG: count = {}".format(count))
            print("DEBUG: on    = 0x{:0X}".format(on))
            print("DEBUG: off   = 0x{:0X}".format(off))

        leds_modify(on, off, dev_hand=dev_hand)

        #!
        #! Cycle Modem control.
        #!
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

