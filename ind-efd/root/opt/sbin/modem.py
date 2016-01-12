#!/usr/bin/env python2

"""IND Driver Module."""

from enum import IntEnum

import sys
import ioctl
import ctypes
#import linuxdvb
import fcntl
import time

## could make this a runtime option.
DEBUG = False

##
## Config Constants
##
class Config(IntEnum):
    PPS_Generate            = 1 << 0
    Debug_DMA_Start         = 1 << 1
    DMA_Halt                = 1 << 2        ## What is this ??
    DMA_Reset               = 1 << 3
    FPGA_Reset              = 1 << 4
    ADC_Test_Data           = 1 << 5
    PPS_Debug_Mode          = 1 << 6
    DMA_Debug_Mode          = 1 << 7

    Mode_Normal             = 0
    Mode_DMA_Debug          = DMA_Debug_Mode
    Mode_DMA_Trigger        = DMA_Debug_Mode | Debug_DMA_Start
    Mode_PPS_Debug          = PPS_Debug_Mode
    Mode_PPS_Trigger        = PPS_Debug_Mode | PPS_Generate


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


##
## IOCTL LED Constants
##
class LED(IntEnum):
    Running                 = 1 << 0
    Alert                   = 1 << 1
    _spare                  = 1 << 2
    PPS_OK                  = 1 << 3
    Modem_OK                = 1 << 4
    Weather_Station_OK      = 1 << 5
    #AC_Power_OK             = 1 << 6
    #Battery_OK              = 1 << 7

class cmd_struct(ctypes.Structure):
    _fields_ = [
        ('config',          ctypes.c_uint), ## __32 config
        ('interrupt',       ctypes.c_uint), ## __32 address
        ('address',         ctypes.c_uint), ## __32 address
        ('capture_count',   ctypes.c_uint), ## __32 capture_count
        ('delay_count',     ctypes.c_uint)  ## __32 delay_count
    ]

class spi_cmd_struct(ctypes.Structure):
    _fields_ = [
        ('port_devices',    ctypes.c_uint), ## __32 port_device[16]
        ## FIXME: how to define an array ??
        ('port_addr',       ctypes.c_uint), ## __32 port_addr[16]
        ## FIXME: how to define an array ??
        ('port_data',       ctypes.c_uint), ## __32 port_data[16]
        ('num_spi_writes',  ctypes.c_uint)  ## __32 num_spi_writes
    ]

class debug_struct(ctypes.Structure):
    _fields_ = [
        ('cmd',     ctypes.c_uint), ## __32 cmd
        ('reg',     ctypes.c_uint), ## __32 reg
        ('data',    ctypes.c_uint), ## __32 data
    ]


##
## IOCTL Command Constants
##

IOCTL_BASE = ord('t')

def _IOWR(id):
    #return ioctl._IOWR(IOCTL_BASE, (0x80 + id), ctypes.sizeof(cmd_struct))
    val = ioctl._IOWR(IOCTL_BASE, (0x80 + id), ctypes.sizeof(cmd_struct))
    #val = ioctl._IOWR(IOCTL_BASE, (0x80 + id), 16)
    print("DEBUG: _IOWR: val = 0x{:0X}".format(val))
    return val

# Can't use enum with Python2, if value has top bit set.
#class IOCTL(IntEnum):
class IOCTL:
    IND_USER_RESET          = _IOWR(0)
    IND_USER_DMA_RESET      = _IOWR(1)
    IND_USER_SET_MODE       = _IOWR(2)
    IND_USER_SET_ADDRESS    = _IOWR(3)
    IND_USER_DMA_TEST       = _IOWR(4)
    IND_USER_TRIG_PPS       = _IOWR(5)
    IND_USER_SPI_WRITE      = _IOWR(6)
    IND_USER_STATUS         = _IOWR(7)
    IND_USER_SET_LEDS       = _IOWR(8)
    IND_USER_CLEAR_LEDS     = _IOWR(9)
    IND_USER_SET_CTRL       = _IOWR(10)
    IND_USER_CLEAR_CTRL     = _IOWR(11)
    IND_USER_GET_SEM        = _IOWR(12)
    IND_USER_SET_SEM        = _IOWR(13)
    IND_USER_REG_DEBUG      = _IOWR(14)


#Args = operation_args()
#Args.field1 = data1;
#Args.field2 = data2;
#
#devicehandle = open('/dev/my_usb', 'rw')
#
## try:
#fcntl.ioctl(devicehandle, operation, Args)
## exception block to check error

def set_control_reg(devhand, on, off):
    """Set and clear control register bits."""

    ## Clear control register bits.
    try:
        print("DEBUG: clearing CTRL '{!r}'".format(off))
        fcntl.ioctl(devhand, IOCTL.IND_USER_CLEAR_CTRL, off)
    except:
        print("EXCEPTION: clearing CTRL '{!r}'".format(off))
        raise

    ## Set control register bits.
    try:
        print("DEBUG: setting CTRL '{!r}'".format(on))
        fcntl.ioctl(devhand, IOCTL.IND_USER_SET_CTRL, on)
    except:
        print("EXCEPTION: setting CTRL '{!r}'".format(on))
        raise


if __name__ == "__main__":
    try:
        delay = float(sys.argv[1])
    except:
        raise Exception("must specify delay as first parameter")

    try:
        devname = '/dev/IND'
        print("DEBUG: opening device name '{}'".format(devname))
        devhand = open(devname, 'rw')
    except:
        print("EXCEPTION: opening device name '{}'".format(devname))
        raise

    mask = Control.Modem_Reset | Control.Modem_Power

    while True:
        ##
        ## Pulse power key to turn it on.
        ##

        ## Assert power key signal.
        on = 0
        #on |= Control.Modem_Reset
        on |= Control.Modem_Power
        off = ~on & mask
        if DEBUG:
            print("DEBUG: on    = 0x{:0X}".format(on))
            print("DEBUG: off   = 0x{:0X}".format(off))
        set_control_reg(devhand, on, off)

        ## 100-600ms delay.
        time.sleep(delay)

        ## Dessert power key signal.
        on = 0
        off = ~on & (Control.Modem_Reset | Control.Modem_Power)
        if DEBUG:
            print("DEBUG: on    = 0x{:0X}".format(on))
            print("DEBUG: off   = 0x{:0X}".format(off))

        set_control_reg(devhand, on, off)

        break

    devhand.close()

