This device server is used to control basic features of a CryoCon temperature
controller.

It has been tested with M32 and M24C models, but should work with other models.

The SCPI syntax for controlling the instrument is very similar to that for
controlling a temperature monitor, and hence these functions have been shared
with the CryoConTempMonitor project. These common functions are in CryoCon.py
file (this file should be exactly the same in both projects CryoConTempMonitor
and CryoConTempController). Of course the temperature controller has many
functions that the monitor doesn't contain, but simply these functions are not
used in the temperature monitor code.
