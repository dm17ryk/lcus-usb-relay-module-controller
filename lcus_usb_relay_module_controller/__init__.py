# Copyright JSN, 2024 <jsn-usb2serial@pebble.plus.com>
#
# Overview:
# =========
#
# This module allows you to control a USB relay board.
#
# It was developed and with an LCUS-4 board, which has a USB to serial port 
# chip ('CH340T') manufactured by Nanjing Qinheng Microelectronics Co., Ltd.
# (https://www.wch-ic.com/). The board itself is possibly made by 'EC Buying'.
#
# It should also work with other similar boards, such as the LCUS-1, LCUS-2 and
# LCUS-8.  If you find others that work, please drop me an email.
#
# Instructions for installing and using the module can be found here on GitHub:
# https://github.com/Pebble94464/lcus-usb-relay-module-controller

from .DeviceA import DeviceA
from .DeviceB import DeviceB
from .LegacyDevice import Device as LegacyDevice

Device = DeviceA  # Default to the new implementation.

# To select the orignal or different implmentation in your code, simply use...
# from lcus_usb_relay_module_controller import LegacyDevice as Device
# TODO: move to documentation.

__all__ = ['Device', 'DeviceA', 'DeviceB', 'LegacyDevice']
