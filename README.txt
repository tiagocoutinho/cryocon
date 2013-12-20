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

A possible bug was detected on model M24C, and a mail was sent to CryoCon, but
unfortunately I got not answer from them. To face this possible bug I had to
modify the device server to allow transient error answer from the instument
This is the mail I sent:
*******************************************************************************
Hi,

My name is Jairo Moldes. I'm working as a software engineer at Alba 
synchrotron in Spain. One of the end stations of the beamline I'm working on 
contains a CryoCon M24C temperature Controller.

We have developed our own software which uses the serial for communicating 
with the instrument. I have detected that sometime the answer to the command 
'CONTROL?;:SYSTEM:LOCKOUT?;' is incorrect (I didn't check if this happens with 
other commands). The answer sometimes contains a 'NACK', like for example: 
'NACK\r\n' or 'ON ;NACK\r\n'

The problem can be reproduced with the attached python code (you probably need 
to customize it). When I run it, after a random number of loops (it may take 
very long) it finally fails. Note that the baud rate is set to 19200.

Have you detected this problem? If so, which is the solution? If not, can you 
reproduce it?

Thanks in advance. Regards,
*******************************************************************************
An this is the m24.py test script:
#!/usr/bin/env python

import time
import serial

if __name__ == '__main__':
    ser = serial.Serial('/dev/ttyS0', 19200, 8, 'N', 1, timeout=1)
    cmd = 'CONTROL?;:SYSTEM:LOCKOUT?;'
    answer = 'ON ;ON'
    while True:
        try:
            ser.write(cmd+'\n')
            time.sleep(0.5)
            line = ser.readline()
            print '%r' % line
            if line.strip() != answer:
                print time.ctime()
                ser.close()
                break
        except Exception, e:
            print e
            ser.close()
*******************************************************************************
