# Copyright JSN, 2026 <jsn-usb2serial@pebble.plus.com>

from .DeviceBase import DeviceBase
import time
import re

class DeviceA(DeviceBase):
	"""
	Supported device(s):
	
	.. EC Buying
	"""
	def __init__(self, port):
		super().__init__(port)
		self._count = None

	# @property
	# def relay_count(self) -> int:
	# 	if self._count == None:
	# 		lines = self.query_relay_status()
	# 		self._count = len(lines)
	# 	return self._count
	# TODO: moved to base class. Cleanup.


	def invert(self, id, verify=False):
		# EC Buying's module lacks native support for this command.
		if self._relay_state[id] == 0:
			self.open(id, verify)
		else:
			self.close(id, verify)
		return self.check(id)

	def check(self, id: int):
		time.sleep(self._delay)
		self.query_status()
		return self._relay_state[id]

	def query_status(self) -> list[int]:
		self._port.reset_input_buffer() # The receiving buffer, I guess.
		self._port.write([0xFF])  # query status
		self._port.flush()
		time.sleep(self._delay) # Doesn't work without this small delay.

		if True:
			# TODO: update DeviceB to use the same approach if needed.
			self._relay_state = [0] * len(self._relay_state) # Reset our internal array.

		line_count = 0
		while True:
			line = self._port.readline().decode('ascii')
			if(len(line) == 0): break # No more lines to read
			self._update_internal_array(line)
			line_count += 1
		self._count = line_count
		return self._relay_state[:self._count]


	# TODO: deprecate this function, don't delete it
	def query_relay_status(self):
		"""
		Query the status of relays on the device, and update our internal
		channel array.

		Note the device natively uses base 1 for its channel numbering,
		whereas our channel array is using base 0.

		Returns the device's native response as a list of byte arrays.
		"""
		self._port.write([0xFF,0x0D,0x0A])  # query status
		time.sleep(self._delay) # Doesn't work without this small delay.
		lines = []
		while True:
			bytes = self._port.readline()
			if(len(bytes) == 0): break # No more lines to read
			lines.append(bytes.strip())
			line = bytes.decode('ascii')
			self._update_internal_array(line)
		return lines

	def _update_internal_array(self, line: str) -> None:
		# This function is specific to ECBuyer device.
		# Compile a pattern to match the 'CH1: OFF' format
		pattern1 = re.compile(r'\s*ch([0-9]+):\s*(on|off)', re.IGNORECASE)

		# Update internal array...
		match_obj = pattern1.match(line)
		if match_obj == None:
			raise Exception('Status returned by device was not recognized.')
		groups = match_obj.groups()
		i = int(groups[0]) - 1
		v = 1 if groups[1].upper() == 'ON' else 0
		self._relay_state[i] = v	# Update our internal array.

