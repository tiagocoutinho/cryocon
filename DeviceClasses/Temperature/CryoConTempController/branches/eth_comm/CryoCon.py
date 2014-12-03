#!/usr/bin/env python

###############################################################################
##
## file :        CryoConTempController.py
##
## description : Python source defining common functions of all CryoCon devices
##               family. This class is aimed to be subclassed by any CryoCon
##               device server, which may be a temp monitor or a temp controller 
##               Some functions are only available for temperature controllers,
##               so simply don't use in case of a handling a temp monitor
##
## project :     TANGO Device Server
##
## $Author:  $
##
## $Revision:  $
##
## $Log:  $
##
## copyleft : CELLS - ALBA
##            Carretera BP 1413, de Cerdanyola del Valles a Sant Cugat del Valles, Km. 3,3
##            08290 Cerdanyola del Valles, Barcelona, SPAIN
##
##            Fax: +34 93 592 43 01
##            Tel: +34 93 592 43 00
##            <http://www.cells.es>
##
###############################################################################
##
## This file is part of Tango-ds.
##
## This is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 3 of the License, or
## (at your option) any later version.
##
## This software is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, see <http://www.gnu.org/licenses/>.
###############################################################################

#Alba imports
import PyTango

#standard python imports
import time
import math
import traceback
import socket



#==================================================================
#   Auxiliary classes
#
# Utility auxiliary classes
#
#==================================================================

class Channel(object):

    def __init__(self):
        object.__init__(self)
        self.value = None
        self.unit = None
        self.display_unit = None


class Loop(object):

    def __init__(self):
        object.__init__(self)
        self.rate = None
        self.set_point = None
        self.type = None
        self.source = None
        self.power_manual = None
        self.output = None
        self.range = None


class CryoCon(object):

    #channels constants
    CHANNELS = ['A', 'B', 'C', 'D']
    LOOPS = ['1', '2', '3', '4']
    VALID_UNITS = ['K', 'C', 'F', 'S'] #Kelvin, Celsius, Fahrenheit, Sensor depending
    #@todo: when setting units to S (sensor depending) and the unit is Ohmns (not Volts),
    #the read back from the instrument is '\xea' in the case of the M14, '\x07' in the
    #case of M24C and '\xf4' for the M32. Reported to the manufacturer but got no answer
    VALID_UNITS_SENSOR = {'\x07' : 'Ohmns', 'V' : 'V'} #ohms, volts
    CH_OUT_OF_RANGE = '_______'
    CH_OUT_OF_LIMIT = '.......'
    CH_DISABLED = ''

    #Loops constants
    LOOPS_TYPES = ['OFF', 'PID', 'MAN', 'TABLE', 'RAMPP', 'RAMPT']
    LOOP1_RANGES = ['HI', 'MID', 'LOW']

    #Commands
    CMD_CH_UNIT = 'INPUT %s:UNITS %s;'
    CMD_CH_UNIT_QUERY = 'INPUT %s:UNITS?;'
    CMD_CH_TEMP_QUERY = 'INPUT? %s;'
    CMD_LOOP_OUTPUT_QUERY = 'LOOP %s:OUTPWR?;'
    CMD_LOOP_PMAN = 'LOOP %s:PMANUAL %s;'
    CMD_LOOP_PMAN_QUERY = 'LOOP %s:PMANUAL?;'
    CMD_LOOP_RANGE = 'LOOP %s:RANGE %s;'
    CMD_LOOP_RANGE_QUERY = 'LOOP %s:RANGE?;'
    CMD_LOOP_RATE = 'LOOP %s:RATE %s;'
    CMD_LOOP_RATE_QUERY = 'LOOP %s:RATE?;'
    CMD_LOOP_SETPT = 'LOOP %s:SETPT %s;'
    CMD_LOOP_SETPT_QUERY = 'LOOP %s:SETPT?;'
    CMD_LOOP_SOURCE = 'LOOP %s:SOURCE %s;'
    CMD_LOOP_SOURCE_QUERY = 'LOOP %s:SOURCE?;'
    CMD_LOOP_TYPE = 'LOOP %s:TYPE %s;'
    CMD_LOOP_TYPE_QUERY = 'LOOP %s:TYPE?;'
    CMD_SYS_DISPLAY_TC = 'SYSTEM:DISTC %s;'
    CMD_SYS_DISPLAY_TC_QUERY = 'SYSTEM:DISTC?;'
    CMD_SYS_LOCKOUT = 'SYSTEM:LOCKOUT %s;'
    CMD_SYS_LOCKOUT_QUERY = 'SYSTEM:LOCKOUT?;'
    CMD_SYS_REMOTE_LED = 'SYSTEM:REMLED %s;'
    CMD_SYS_REMOTE_LED_QUERY = 'SYSTEM:REMLED?;'
    CMD_CONTROL = 'CONTROL;'
    CMD_CONTROL_QUERY = 'CONTROL?;'
    CMD_STOP = 'STOP;'
    CMD_SEPARATOR = ':'
    RESULT_SEPARATOR = ';'

    #Delta read back tolerance
    DELTA_RB = 0.0000001 #6 decimals precision
    DELTA_RB_SETPT = 0.0001 #setpoints seem to have some kind of preset values when not in K or S units

    #known serial device classes
    KNOWN_SERIAL_CLASSES = ['Serial', 'PySerial']

    #Package buffer
    MAX_BUFF_SIZE = 1024
    
    def __init__(self):
        object.__init__(self)


#------------------------------------------------------------------
#------------------------------------------------------------------
# Internal functions shared by all CryoCon devices (both monitor
# and controller types)
#------------------------------------------------------------------
#------------------------------------------------------------------

#------------------------------------------------------------------
# serial communications functions. Serial and PySerial supported
#------------------------------------------------------------------

    def _init_comms(self):
        serial_class = self.serial.info().dev_class
        if not serial_class in self.KNOWN_SERIAL_CLASSES:
            msg = 'Unknown serial class %s. Valid ones are: %s' % (serial_class, self.KNOWN_SERIAL_CLASSES)
            self.error_stream(msg)
            PyTango.Except.throw_exception('Unknown serial class', msg, '%s::_init_comms()' % self.get_name())

        if serial_class == 'Serial':
            self.serial.command_inout('DevSerFlush',2)
            self._communicate_raw = self._communicate_raw_Serial
        elif serial_class == 'PySerial':
            if self.serial.State() != PyTango.DevState.ON:
                self.serial.command_inout('Open')
            self.serial.command_inout('FlushInput')
            self.serial.command_inout('FlushOutput')
            self._communicate_raw = self._communicate_raw_PySerial
        else: #should be impossible, but you never know
            msg = 'Unsupported serial device class: %s. Valid ones are: %s' % (serial_class, str(self.KNOWN_SERIAL_CLASSES))
            self.error_stream(msg)
            PyTango.Except.throw_exception('Communication init error', msg, '%s::_init_comms()' % self.get_name())

    
    def _communicate_raw_Serial(self, cmd, output_expected=False, strip_string=True):
        self.lock.acquire()
        try:
            self.debug_stream('In %s::_communicate_raw_Serial() command input: %s' % (self.get_name(), cmd) )
            self.serial.command_inout('DevSerWriteString', cmd+'\r')
            if output_expected:
                read_ = self.serial.command_inout('DevSerReadLine')
                if strip_string:
                    output = read_.strip()
                else:
                    output = filter(lambda x: x not in ('\r','\n'), read_) #preserve all characters except \n and \r
                self.debug_stream('In %s::_communicate_raw_Serial(). Command output: %r Return value: %r' % (self.get_name(), read_, output))
                return output
        except Exception, e:
            self.error_stream('In %s::_communicate_raw_Serial() unexpected exception: %s' % (self.get_name(), traceback.format_exc()) )
            raise
        finally:
            self.lock.release()


    def _communicate_raw_PySerial(self, cmd, output_expected=False, strip_string=True):
        self.lock.acquire()
        try:
            self.debug_stream('In %s::_communicate_raw_PySerial() command input: %s' % (self.get_name(), cmd) )
            self.serial.command_inout('Write', bytearray(cmd))
            if output_expected:
                read_ = self.serial.command_inout('ReadLine')
                if read_ .size == 0:
                    msg = 'Got empty return value from PySerial device. This is probably a communication error. Please check'
                    self.error_stream(msg)
                    PyTango.Except.throw_exception('Communication error', msg, '%s::_communicate_raw_PySerial()' % self.get_name())
                read_ = read_.tostring()
                if strip_string:
                    output = read_.strip()
                else:
                    output = filter(lambda x: x not in ('\r','\n'), read_) #preserve all characters except \n and \r
                self.debug_stream('In %s::_communicate_raw_PySerial(). Command output: %r Return value: %r' % (self.get_name(), read_, output))
                return output
        except Exception, e:
            self.error_stream('In %s::_communicate_raw_PySerial() unexpected exception: %s' % (self.get_name(), traceback.format_exc()))
            raise
        finally:
            self.lock.release()
 
    def _init_eth_comms(self, ip, port, timeout=3):
        self.socket_conf = (ip, int(port))
        self.crycon_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.crycon_socket.connect(self.socket_conf)
        self.buff = self.MAX_BUFF_SIZE
        self._communicate_raw = self._communicate_raw_Eth
        
    def _communicate_raw_Eth(self, cmd, output_expected=False, 
                             strip_string=True):
        with self.lock:
            try:
                msg = ('In %s::_communicate_raw_Eth() command input: %s' 
                       % (self.get_name(), cmd) )
                self.debug_stream(msg)
                self.crycon_socket.send(cmd+'\r\n')
                if output_expected:
                    result = self.crycon_socket.recv(self.buff)
                    if len(result) == 0:
                        msg = ('Got empty return value from the socket. This is'
                               ' probably a communication error. Please check')
                        self.error_stream(msg)
                        method_name = ('%s::_communicate_raw_Eth()' 
                                       % self.get_name()) 
                        PyTango.Except.throw_exception('Communication error', 
                                                       msg, method_name)
                    read_ = result
                    if strip_string:
                        output = read_.strip()
                    else:
                        #preserve all characters except \n and \r
                        output = filter(lambda x: x not in ('\r','\n'), read_) 
                    
                    msg = ('In %s::_communicate_raw_Eth(). Command output: %r'
                           ' Return value: %r' % (self.get_name(), read_, 
                                                  output))    
                    self.debug_stream(msg)
                    return output

                
            except Exception, e:
                msg = ('In %s::_communicate_raw_Eth() unexpected '
                       'exception: %s' % (self.get_name(), 
                                          traceback.format_exc()))
                self.error_stream(msg)
                raise

            
#------------------------------------------------------------------
# standard_attribute_state_machine
#------------------------------------------------------------------
    def _standard_attr_state_machine(self, req_type = None):
        #always allow reading
        if req_type == PyTango.AttReqType.READ_REQ:
            return True

        state = self.get_state()
        if state in [PyTango.DevState.ON, PyTango.DevState.ALARM, PyTango.DevState.OFF]:
            return True
        elif state in [PyTango.DevState.UNKNOWN, PyTango.DevState.FAULT]:
            return False
        else:
            self.error_stream('In %s::_standard_attr_state_machine(): reached unexpected condition %s' % (self.get_name(), str(state)) )
            return False


#------------------------------------------------------------------
# get_channel_unit
#------------------------------------------------------------------
    def _get_channel_unit(self, channel):
        cmd = self.CMD_CH_UNIT_QUERY % channel
        unit = self._communicate_raw(cmd, output_expected=True, strip_string=False)
        return unit


#------------------------------------------------------------------
#   Set state
#------------------------------------------------------------------
    def _set_state(self, new_state, new_status=None):
        #preserve FAULT state if set
        if self.get_state() == PyTango.DevState.FAULT:
            return
        self.set_state(new_state)
        if new_status != None:
            self.set_status(new_status)


#------------------------------------------------------------------
#   _update_channels_info
#------------------------------------------------------------------
    def _update_channels_info(self):
        attr_list = self.get_device_attr()
        for channel in self.channels_keys:
            unit = self._get_channel_unit(channel)
            attr_name = 'Channel%s' % channel
            self.channels[channel].unit = unit
            attr = attr_list.get_attr_by_name(attr_name)
            attr_properties = attr.get_properties()
            if unit in self.valid_units_sensor:
                unit = self.valid_units_sensor[unit]
            self.channels[channel].display_unit = unit
            attr_properties.unit = unit
            attr.set_properties(attr_properties, self)
            self.push_att_conf_event(attr)


#------------------------------------------------------------------
#   _update_loops_info
#------------------------------------------------------------------
    def _update_loops_info(self):
        attr_list = self.get_device_attr()
        for loop in self.loops_keys:
            cmd = self.CMD_LOOP_SOURCE_QUERY % loop
            source = self._communicate_raw(cmd, output_expected=True)
            source = source[-1]
            cmd = self.CMD_LOOP_TYPE_QUERY % loop
            type_ = self._communicate_raw(cmd, output_expected=True)
            #special case: a loop may not have a source channel, but ONLY if in manual mode
            if not source in self.channels_keys:
                if not (type_.upper() in ('MAN', 'OFF')):
                    msg = 'Loop %s is configured to be using channel %s, but the later is not being managed' % (loop, source)
                    self.error_stream(msg)
                    self._set_state(PyTango.DevState.FAULT, msg)
                    PyTango.Except.throw_exception('Inconsistent configuration', msg, '%s::init_device()' % self.get_name())
                else:
                    continue #don't try to go on, since this has no sense
            self.loops[loop].source = source
            unit = self.channels[source].display_unit
            attr_name = 'Loop%sSetPoint' % loop
            attr = attr_list.get_attr_by_name(attr_name)
            attr_properties = attr.get_properties()
            attr_properties.unit = unit
            attr.set_properties(attr_properties, self)
            self.push_att_conf_event(attr)
            attr_name = 'Loop%sRate' % loop
            attr = attr_list.get_attr_by_name(attr_name)
            attr_properties = attr.get_properties()
            attr_properties.unit = '%s/min' % unit
            attr.set_properties(attr_properties, self)
            self.push_att_conf_event(attr)


#------------------------------------------------------------------
#    Read Channels
#------------------------------------------------------------------
    def read_Channels(self, attr):
        self.info_stream('In %s::read_Channels()' % self.get_name())

        channel_name = attr.get_name()
        channel = channel_name[-1]

        if channel not in self.channels_keys:
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)
            return

        #read from hardware all the channels (only if timed out)
        now = time.time()
        if (now - self.last_ch_read_time) > self.ch_read_validity:
            try:
                self.last_ch_read_time = now
                results = self._read_channels()
            except Exception, e:
                msg = 'In %s::read_Channels() error reading temperatures: %s' % (self.get_name(), traceback.format_exc())
                self.error_stream(msg)
                PyTango.Except.throw_exception('Communication error', msg, '%s::read_Channels()' % self.get_name())

            #update values
            for idx, ch in enumerate(self.channels_keys):
                try:
                    read_temp = results[idx]
                    value = float(read_temp)
                except ValueError:
                    value = float('NaN')
                    if read_temp == self.CH_OUT_OF_RANGE:
                        msg = 'Channel %s voltage out of range. Check sensor connections' % (ch)
                    elif read_temp == self.CH_OUT_OF_LIMIT:
                        msg = 'Channel %s voltage in range, but measurement outside limits. Check sensor connections' % (ch)
                    elif read_temp == self.CH_DISABLED:
                        msg = 'Channel %s seems to be disabled while it was not expected to be.' % (ch)
                    else:
                        msg = 'Unexpected value returned from controller for %s: %s' % (channel_name, read_temp)
                    self.error_stream(msg)
                    self._set_state(PyTango.DevState.ALARM, msg)
                finally:
                    self.channels[ch].value = value

        #return the requested channel
        value_ = self.channels[channel].value
        attr.set_value(value_)
        if math.isnan(value_):
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)


#------------------------------------------------------------------
#    Read LoopsOutputs
#------------------------------------------------------------------
    def read_LoopsOutputs(self, attr):
        self.info_stream('In %s::read_LoopsOutputs()' % self.get_name())

        attr_name = attr.get_name()
        loop = filter(lambda x: x.isdigit(), attr_name)

        if loop not in self.loops_keys:
            msg = 'Invalid loop %s in %s::read_LoopsOutputs()' % (loop, self.get_name())
            self.error_stream(msg)
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)
            return

        #let's be optimistic
        valid = PyTango.AttrQuality.ATTR_VALID

        #read from hardware (only if timed out)
        now = time.time()
        if (now - self.last_loops_outputs_read_time) > self.loops_outputs_read_validity:
            #read from hardware all the channels
            try:
                self.last_loops_outputs_read_time = now
                results = self._read_loops_outputs()
            except Exception, e:
                msg = 'In %s::read_LoopsOutputs() error reading outputs: %s' % (self.get_name(), traceback.format_exc())
                self.error_stream(msg)
                PyTango.Except.throw_exception('Communication error', msg, '%s::read_LoopsOutputs()' % self.get_name())

            for idx, loop_ in enumerate(self.loops_keys):
                try:
                    read_output = results[idx]
                    value = float(read_output)
                except ValueError:
                    if loop == loop_:
                        valid = PyTango.AttrQuality.ATTR_INVALID
                    value = float('NaN')
                    msg = 'Error reading loop %s output Output' % (loop_)
                    self.error_stream(msg)
                finally:
                    self.loops[loop_].output = value

        #return the requested loop
        attr.set_value(self.loops[loop].output)
        attr.set_quality(valid)


#------------------------------------------------------------------
#    Read Loop1Range
#------------------------------------------------------------------
    def read_Loop1Range_(self, attr):
        self.info_stream('In %s::read_Loop1Range()' % self.get_name())

        attr_name = attr.get_name()
        loop = filter(lambda x: x.isdigit(), attr_name)
        loop = str(loop)

        if (loop != '1'):
            msg = 'Invalid loop %s in %s::read_Loop1Range()' % (loop, self.get_name())
            self.error_stream(msg)
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)
            return

        #let's be optimistic
        valid = PyTango.AttrQuality.ATTR_VALID

        #read from hardware (only if timed out)
        now = time.time()
        if (now - self.last_loops_ranges_read_time) > self.loops_ranges_read_validity:
            #read from hardware
            try:
                self.last_loops_ranges_read_time = now
                cmd = self.CMD_LOOP_RANGE_QUERY % loop
                read_range = self._communicate_raw(cmd, output_expected=True)
            except Exception, e:
                self.loops[loop].range = 'Unknown'
                msg = 'In %s::read_Loop1Range_() error reading range: %s' % (self.get_name(), traceback.format_exc())
                self.error_stream(msg)
                PyTango.Except.throw_exception('Communication error', msg, '%s::read_Loop1Range_()' % self.get_name())

            #if everything went ok
            self.loops[loop].range = read_range.upper()

        #return the requested range
        if self.loops[loop].range not in self.LOOP1_RANGES:
            msg = 'Unknown range type for loop'
            self.error_stream(msg)
            valid = PyTango.AttrQuality.ATTR_INVALID

        attr.set_value(self.loops[loop].range)
        attr.set_quality(valid)


#------------------------------------------------------------------
#    Read LoopsRates
#------------------------------------------------------------------
    def read_LoopsRates(self, attr):
        self.info_stream('In %s::read_LoopsRates()' % self.get_name())

        attr_name = attr.get_name()
        loop = filter(lambda x: x.isdigit(), attr_name)

        if (loop not in self.loops_keys) or not (self.loops[loop].source in self.channels_keys):
            msg = 'Invalid loop %s in %s::read_LoopsRates()' % (loop, self.get_name())
            self.error_stream(msg)
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)
            return

        #let's be optimistic
        valid = PyTango.AttrQuality.ATTR_VALID

        #read from hardware (only if timed out)
        now = time.time()
        if (now - self.last_loops_rates_read_time) > self.loops_rates_read_validity:
            #read from hardware all the channels
            try:
                self.last_loops_rates_read_time = now
                results = self._read_loops_rates()
            except Exception, e:
                msg = 'In %s::read_LoopsRates() error reading ramping rates: %s' % (self.get_name(), traceback.format_exc())
                self.error_stream(msg)
                PyTango.Except.throw_exception('Communication error', msg, '%s::read_LoopsRates()' % self.get_name())

            for idx, loop_ in enumerate(self.loops_keys):
                try:
                    read_rate = results[idx]
                    value = float(read_rate)
                except ValueError:
                    value = float('NaN')
                    if loop == loop_:
                        valid = PyTango.AttrQuality.ATTR_INVALID
                    msg = 'Error reading loop %s ramp rate' % (loop_)
                    self.error_stream(msg)
                finally:
                    self.loops[loop_].rate = value

        #return the requested rate
        attr.set_value(self.loops[loop].rate)
        attr.set_quality(valid)


#------------------------------------------------------------------
#    Read LoopsSetPoints
#------------------------------------------------------------------
    def read_LoopsSetPoints(self, attr):
        self.info_stream('In %s::read_LoopsSetPoints()' % self.get_name())

        attr_name = attr.get_name()
        loop = filter(lambda x: x.isdigit(), attr_name)
        loop = str(loop)

        if (loop not in self.loops_keys) or not (self.loops[loop].source in self.channels_keys):
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)
            return

        #read from hardware
        try:
            results = self._read_loops_setpoints()
        except Exception, e:
            msg = 'In %s::read_LoopsSetPoints() error reading setpoints: %s' % (self.get_name(), traceback.format_exc())
            self.error_stream(msg)
            PyTango.Except.throw_exception('Communication error', msg, '%s::read_LoopsSetPoints()' % self.get_name())

        for idx, loop_ in enumerate(self.loops_keys):
            try:
                if not (self.loops[loop_].source in self.channels_keys):
                    continue
                read_setpoint = results[idx]
                expected_unit = self.channels[self.loops[loop_].source].unit
                read_setpoint = read_setpoint.strip(expected_unit) #remove unit character
                value = float(read_setpoint)
            except ValueError:
                value = float('NaN')
                msg = 'In %s::read_LoopsSetPoints() Error reading loop %s set point: %s' % (self.get_name(), loop_, read_setpoint)
                self.error_stream(msg)
            except Exception, e:
                value = float('NaN')
                msg = 'In %s::read_LoopsSetPoints() unexpected exception: %s' % (self.get_name(), traceback.format_exc())
                self.error_stream(msg)
            finally:
                self.loops[loop_].set_point = value

        #return the requested loop setpoing
        value_ = self.loops[loop].set_point
        attr.set_value(value_)
        if math.isnan(value_):
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)


#------------------------------------------------------------------
#    Read read_LoopsTypes
#------------------------------------------------------------------
    def read_LoopsTypes(self, attr):
        self.info_stream('In %s::read_LoopsTypes()' % self.get_name())

        attr_name = attr.get_name()
        loop = filter(lambda x: x.isdigit(), attr_name)
        loop = str(loop)

        if loop not in self.loops_keys:
            attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)
            return

        #read from hardware
        try:
            results = self._read_loops_types()
        except Exception, e:
            msg = 'In %s::read_LoopsTypes() error reading loops types: %s' % (self.get_name(), traceback.format_exc())
            self.error_stream(msg)
            PyTango.Except.throw_exception('Communication error', msg, '%s::read_LoopsTypes()' % self.get_name())
        for idx, loop_ in enumerate(self.loops_keys):
            try:
                read_type = results[idx]
            except ValueError:
                attr.set_quality(PyTango.AttrQuality.ATTR_INVALID)
                msg = 'Error reading loop %s type' % (loop_)
                self.error_stream(msg)
                return
            finally:
                self.loops[loop_].type = read_type

        #return the requested loop
        attr.set_value(self.loops[loop].type)


#------------------------------------------------------------------
#    write_LoopPowerManual
#------------------------------------------------------------------
    def write_LoopPowerManual(self, attr):
        self.info_stream('In %s::write_LoopPowerManual()' % self.get_name())
        attr_name = attr.get_name()
        loop = filter(lambda x: x.isdigit(), attr_name)
        loop = int(loop)
        power = attr.get_write_value()
        self._write_loop_power_manual(loop, power)


#------------------------------------------------------------------
#    write_Loop1Range
#------------------------------------------------------------------
    def write_Loop1Range_(self, attr):
        self.info_stream('In %s::write_Loop1Range()' % self.get_name())
        attr_name = attr.get_name()
        loop = filter(lambda x: x.isdigit(), attr_name)
        loop = int(loop)
        range_ = attr.get_write_value()
        self._write_loop_range(loop, range_)


#------------------------------------------------------------------
#    write_LoopRate
#------------------------------------------------------------------
    def write_LoopRate(self, attr):
        self.info_stream('In %s::write_LoopRate()' % self.get_name())
        attr_name = attr.get_name()
        loop = filter(lambda x: x.isdigit(), attr_name)
        loop = int(loop)
        rate = attr.get_write_value()
        self._write_loop_rate(loop, rate)


#------------------------------------------------------------------
#    write_LoopSetPoint
#------------------------------------------------------------------
    def write_LoopSetPoint(self, attr):
        self.info_stream('In %s::write_LoopSetPoint()' % self.get_name())
        attr_name = attr.get_name()
        loop = filter(lambda x: x.isdigit(), attr_name)
        loop = int(loop)
        set_point = attr.get_write_value()
        self._write_loop_set_point(loop, set_point)


#------------------------------------------------------------------
#    write_LoopType
#------------------------------------------------------------------
    def write_LoopType(self, attr):
        self.info_stream('In %s::write_LoopType()' % self.get_name())
        attr_name = attr.get_name()
        loop = filter(lambda x: x.isdigit(), attr_name)
        loop = int(loop)
        type_ = attr.get_write_value()
        self._write_loop_type(loop, type_)


#------------------------------------------------------------------
#    _read_channels
#------------------------------------------------------------------
    def _read_channels(self):
        result = self._communicate_raw(self.read_temp_cmd, output_expected=True)
        results = result.split(self.RESULT_SEPARATOR)
        return results


#------------------------------------------------------------------
#    _read_loops_outputs
#------------------------------------------------------------------
    def _read_loops_outputs(self):
        result = self._communicate_raw(self.read_loops_outputs_cmd, output_expected=True)
        results = result.split(self.RESULT_SEPARATOR)
        return results


#------------------------------------------------------------------
#    _read_loops_rates
#------------------------------------------------------------------
    def _read_loops_rates(self):
        result = self._communicate_raw(self.read_loops_rates_cmd, output_expected=True)
        results = result.split(self.RESULT_SEPARATOR)
        return results


#------------------------------------------------------------------
#    _read_loops_setpoints
#------------------------------------------------------------------
    def _read_loops_setpoints(self):
        result = self._communicate_raw(self.read_loops_setpoints_read_cmd, output_expected=True, strip_string=False)
        results = result.split(self.RESULT_SEPARATOR)
        return results


#------------------------------------------------------------------
#    _read_loops_types
#------------------------------------------------------------------
    def _read_loops_types(self):
        result = self._communicate_raw(self.read_loops_types_read_cmd, output_expected=True)
        results = result.split(self.RESULT_SEPARATOR)
        results_strip = [res.strip() for res in results]
        return results_strip


#------------------------------------------------------------------
#    _write_loop_power_manual
#------------------------------------------------------------------
    def _write_loop_power_manual(self, loop, power):
        msg = ''
        loop = str(loop)
        if loop not in self.loops_keys:
            msg += 'Invalid loop: %s. Valid loops are: %s' % (loop, str(self.loops_keys))
        if msg !='':
            self.error_stream(msg)
            PyTango.Except.throw_exception('Bad parameter', msg, '%s::_write_loop_power_manual()' % self.get_name())

        #check we are in manual mode
        types = self._read_loops_types()
        idx = self.loops_keys.index(loop)
        type_ = types[idx]
        if type_.upper() != 'MAN':
            msg = 'Loop must be in manual mode in order to set this value, not in %s mode' % type_
            self.error_stream(msg)
            PyTango.Except.throw_exception('Bad parameter', msg, '%s::_write_loop_power_manual()' % self.get_name())

        #request command, including read_back
        cmd = self.CMD_LOOP_PMAN % (loop, str(power)) + self.CMD_SEPARATOR + self.CMD_LOOP_PMAN_QUERY % loop
        power_rb = self._communicate_raw(cmd, output_expected=True)
        power_rb = float(power_rb)
        if abs(power - power_rb) > self.DELTA_RB:
            msg = 'Written power %s differs from the one read back from instrument %s' % (str(power), str(power_rb))
            self.error_stream(msg)
            PyTango.Except.throw_exception('Instrument error', msg, '%s::_write_loop_power_manual()' % self.get_name())
        self.loops[loop].power_manual = power


#------------------------------------------------------------------
#    _write_loop_range
#------------------------------------------------------------------
    def _write_loop_range(self, loop, range_):
        msg = ''
        loop = str(loop)
        if loop not in ('1'):
            msg += 'Invalid loop: %r. Valid loops are: %s' % (loop, '1')
        if range_.upper() not in self.LOOP1_RANGES:
            msg += 'Invalid loop range: %r. Valid ranges are: %s' % (range_, str(self.LOOP1_RANGES))
        if msg != '':
            self.error_stream(msg)
            PyTango.Except.throw_exception('Bad parameter', msg, '%s::_write_loop_range()' % self.get_name())

        #request command
        cmd = self.CMD_LOOP_RANGE % (loop, range_.upper()) + self.CMD_SEPARATOR + self.CMD_LOOP_RANGE_QUERY % loop
        range_rb = self._communicate_raw(cmd, output_expected=True)

        if range_.upper() != range_rb.upper():
            msg = 'Written loop range %s differs from the read back from instrument %s' % (str(range_), str(range_rb))
            self.error_stream(msg)
            PyTango.Except.throw_exception('Instrument error', msg, '%s::_write_loop_type()' % self.get_name())
        self.loops[loop].range = range_


#------------------------------------------------------------------
#    _write_loop_rate
#------------------------------------------------------------------
    def _write_loop_rate(self, loop, rate):
        loop = str(loop)
        if loop not in self.loops_keys:
            msg = 'Invalid loop: %s. Valid loops are: %s' % (loop, str(self.loops_keys))
        elif not (self.loops[loop].source in self.channels_keys):
            msg = 'Invalid loop: %s. This loop has not a ruling channel and hence can only be used in MANual mode' % loop
        else:
            msg = ''
        if msg !='':
            self.error_stream(msg)
            PyTango.Except.throw_exception('Bad parameter', msg, '%s::_write_loop_rate()' % self.get_name())

        #request command, including read_back
        cmd = self.CMD_LOOP_RATE % (loop, str(rate)) + self.CMD_SEPARATOR + self.CMD_LOOP_RATE_QUERY % loop
        rate_rb = self._communicate_raw(cmd, output_expected=True)
        rate_rb = float(rate_rb)
        if (rate != rate_rb) > self.DELTA_RB: #6 decimals precision
            msg = 'Written rate %s differs from the read back from instrument %s' % (str(rate), str(rate_rb))
            self.error_stream(msg)
            PyTango.Except.throw_exception('Instrument error', msg, '%s::_write_loop_rate()' % self.get_name())
        self.loops[str(loop)].rate = rate


#------------------------------------------------------------------
#    _write_loop_set_point
#------------------------------------------------------------------
    def _write_loop_set_point(self, loop, set_point):
        loop = str(loop)
        if loop not in self.loops_keys:
            msg = 'Invalid loop: %s. Valid loops are: %s' % (loop, str(self.loops_keys))
        elif not (self.loops[loop].source in self.channels_keys):
            msg = 'Invalid loop: %s. This loop has not a ruling channel and hence can only be used in MANual mode' % loop
        else:
            msg = ''
        if msg != '':
            self.error_stream(msg)
            PyTango.Except.throw_exception('Bad parameter', msg, '%s::_write_loop_set_point()' % self.get_name())

        #request command, including read_back
        cmd = self.CMD_LOOP_SETPT % (loop, str(set_point)) + self.CMD_SEPARATOR + self.CMD_LOOP_SETPT_QUERY % loop
        set_point_rb = self._communicate_raw(cmd, output_expected=True)
        expected_unit = self.channels[self.loops[loop].source].unit
        set_point_rb = set_point_rb.strip(expected_unit) #remove unit character
        set_point_rb = float(set_point_rb)
        if abs(set_point - set_point_rb) > self.DELTA_RB_SETPT:
            msg = 'Written setpoint %s differs from the read back from instrument %s' % (str(set_point), str(set_point_rb))
            self.error_stream(msg)
            PyTango.Except.throw_exception('Instrument error', msg, '%s::_write_loop_set_point()' % self.get_name())
        self.loops[str(loop)].set_poirnt = set_point


#------------------------------------------------------------------
#    _write_loop_type
#------------------------------------------------------------------
    def _write_loop_type(self, loop, type_):
        msg = ''
        loop = str(loop)
        if loop not in self.loops_keys:
            msg += 'Invalid loop: %r. Valid loops are: %s' % (loop, str(self.loops_keys))
        if type_.upper() not in self.loops_types:
            msg += 'Invalid loop control type: %r. Valid types are: %s' % (type_, str(self.loops_types))
        if msg != '':
            self.error_stream(msg)
            PyTango.Except.throw_exception('Bad parameter', msg, '%s::_write_loop_type()' % self.get_name())

        #do not allow change loop type to something different from manual or off if associated channel is not being managed
        if not (self.loops[loop].source in self.channels_keys) and not (type_.upper() in ('MAN','OFF')):
            msg = 'Type for this loop must be set to manual or off, since its source is not being managed by this device'
            self.error_stream(msg)
            PyTango.Except.throw_exception('Bad parameter', msg, '%s::_write_loop_type()' % self.get_name())

        #request command
        cmd = self.CMD_LOOP_TYPE % (loop, type_.upper()) + self.CMD_SEPARATOR + self.CMD_LOOP_TYPE_QUERY % loop
        type_rb = self._communicate_raw(cmd, output_expected=True)
        if type_.upper() != type_rb.upper():
            msg = 'Written loop type %s differs from the read back from instrument %s' % (str(type_), str(type_rb))
            self.error_stream(msg)
            PyTango.Except.throw_exception('Instrument error', msg, '%s::_write_loop_type()' % self.get_name())
        self.loops[str(loop)].type = type_
