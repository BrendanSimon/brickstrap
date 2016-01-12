#!/usr/bin/env python2

"""IND Driver Module."""

from enum import IntEnum

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
class Status(IntEnum):
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
    PPS_Debug               = 1 << 9
    DMA_Reset               = 1 << 10
    DMA_Reset               = 1 << 11
    DMA_Debug               = 1 << 12
    Interrupt_En            = 1 << 13
    Battery_Low             = 1 << 14
    AC_Power                = 1 << 15


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
    SPARE                   = 1 << 2
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

if __name__ == "__main__":
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
    print("LED.Running              =", LED.Running)
    print("LED.Running              =", int(LED.Running))
    print("LED.Alert                =", LED.Alert)
    print("LED.Alert                =", int(LED.Alert))
    print("LED.Weather_Station_OK   =", LED.Weather_Station_OK)
    print("LED.Weather_Station_OK   =", int(LED.Weather_Station_OK))

    try:
        devname = '/dev/IND'
        print("DEBUG: opening device name '{}'".format(devname))
        devhand = open(devname, 'rw')
    except:
        print("EXCEPTION: opening device name '{}'".format(devname))
        raise

    leds = LED.Running

    #led_seq = [ LED.Battery_OK, LED.AC_Power_OK, LED.PPS_OK, LED.Running,
    #led_seq = [ LED.PPS_OK, LED.Running, LED.Modem_OK, LED.Alert, LED.Weather_Station_OK, LED.SPARE ]
    led_seq = [ LED.PPS_OK, LED.Running, LED.Modem_OK, LED.Alert, LED.Weather_Station_OK ]
    led_mask = sum(led_seq)
    led_seq += led_seq[::-1][1:-1]
    #for count in range(10):
    while True:
        for count, led in enumerate(led_seq):
            leds_on = led
            leds_off = ~leds_on & led_mask
            try:
                #print("DEBUG: setting LEDS '{!r}'".format(leds_on))
                fcntl.ioctl(devhand, IOCTL.IND_USER_SET_LEDS, leds_on)
            except:
                print("EXCEPTION: setting LEDS '{!r}'".format(leds_on))
                raise

            try:
                #print("DEBUG: clearing LEDS '{!r}'".format(leds_off))
                fcntl.ioctl(devhand, IOCTL.IND_USER_CLEAR_LEDS, leds_off)
            except:
                print("EXCEPTION: clearing LEDS '{!r}'".format(leds_off))
                raise

            on = 0
            c = count >> 2
            if (c & 1): on |= Control.Modem_Reset
            if (c & 2): on |= Control.Modem_Power
            off = ~on & (Control.Modem_Reset | Control.Modem_Power)
            if DEBUG:
                print("DEBUG: count = {}".format(count))
                print("DEBUG: on    = 0x{:0X}".format(on))
                print("DEBUG: off   = 0x{:0X}".format(off))

            try:
                #print("DEBUG: setting CTRL '{!r}'".format(leds_on))
                fcntl.ioctl(devhand, IOCTL.IND_USER_SET_CTRL, on)
            except:
                print("EXCEPTION: setting CTRL '{!r}'".format(on))
                raise

            try:
                #print("DEBUG: clearing CTRL '{!r}'".format(leds_off))
                fcntl.ioctl(devhand, IOCTL.IND_USER_CLEAR_CTRL, off)
            except:
                print("EXCEPTION: clearing CTRL '{!r}'".format(off))
                raise

            time.sleep(0.1)

    devhand.close()

