import pytest
import serial
from lcus_usb_relay_module_controller import DeviceB
from device_tests import DeviceTests

DEVICE = DeviceB

RELAY_COUNT = 2

SERIAL_PORT_CONFIG = {
	'port': 'COM3',
	'baudrate': 9600,
	'bytesize': 8,
	'timeout': 0.2,
	'stopbits': serial.STOPBITS_ONE,
	'parity': serial.PARITY_NONE,
}

@pytest.mark.usefixtures("device")
class TestDeviceB(DeviceTests):

	# Example of how to skip or xfail a test from the base class.
	@pytest.mark.xfail(reason="Demonstration only")
	def test_not_a_test(self):
		super().test_not_a_test()
