#!/usr/bin/env python

###############################################################################
##
## file :        CryoConTempController.py
##
## description : Python source for the CryoConTempController and its commands. 
##                The class is derived from Device. It represents the
##                CORBA servant object which will be accessed from the
##                network. All commands which can be executed on the
##                CryoConTempController are implemented in this file.
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

#import common functions class for subclassing
import CryoCon

#Alba imports
import PyTango

#standard python imports
import sys
import time
import threading


#==================================================================
#   CryoConTempController Class Description:
#
# This device reads the temperature channels from a CryoCon
# temperature controller and controls its loops outputs. It does so by
# communicating with the hardware via a serial device, which must be
# correctly configured and setup.
#
#==================================================================

class CryoConTempController(PyTango.Device_4Impl, CryoCon.CryoCon):

#--------- Add you global variables here --------------------------


#------------------------------------------------------------------
# setup_standard_attributes
#------------------------------------------------------------------
    def _setup_standard_attributes(self):
        for attr in CryoConTempControllerClass.attr_list:
            method = 'is_' + attr + '_allowed'
            if not hasattr(CryoConTempController, method): #respect method if already defined
                setattr(CryoConTempController, method, CryoConTempController._standard_attr_state_machine)


#------------------------------------------------------------------
#    Device constructor
#------------------------------------------------------------------
    def __init__(self,cl, name):
        PyTango.Device_4Impl.__init__(self,cl,name)
        CryoCon.CryoCon.__init__(self)
        self._setup_standard_attributes()
        CryoConTempController.init_device(self)


#------------------------------------------------------------------
#    Device destructor
#------------------------------------------------------------------
    def delete_device(self):
        self.info_stream('[Device delete_device method] for device %s' % self.get_name())
        try:
            #let's unlock front panel and set the remote LED off.
            cmd = self.CMD_SYS_REMOTE_LED % 'OFF'
            self._communicate_raw(cmd)
            cmd = self.CMD_SYS_LOCKOUT % 'OFF'
            self._communicate_raw(cmd)
            #@todo: if the delete_device() is followed by an init_device() for unknow reasons
            #the first command issued in init_device gets no answer from the device if this
            #sleep is not done. This only happens with model M32. It has been reported to the
            #manufacturer but got no answer, so we have to live with this by now.
            time.sleep(0.1)
        except Exception, e:
            msg = 'Error while trying to %s::delete_device(): %s' % (self.get_name(), str(e))
            self.error_stream(msg)


#------------------------------------------------------------------
# Device initialization
#------------------------------------------------------------------
    def init_device(self):
        self.info_stream('In %s::init_device()' % self.get_name())

        #get device properties
        self.get_device_properties(self.get_device_class())

        #retrieve allowed transient property if present and reset transient_errors
        self.transient_errors = 0
        if (self.AllowedTransientErrors == []) or (type(self.AllowedTransientErrors) != int):
            msg = 'In %s::init_device() AllowedTransientErrors not specified or invalid, assuming 0' % self.get_name()
            self.warn_stream(msg)
            self.AllowedTransientErrors = 0

        #lock for avoiding simultaneous serial port access
        self.lock = threading.Lock()

        #try to initialize communications (set FAULT state and return if goes wrong)
        try:
            if self.CommType == 'serial':
                self.serial = PyTango.DeviceProxy(self.SerialDevice)
                self._init_comms()
            elif self.CommType == 'eth':
                self._init_eth_comms(self.IP, self.Eth_Port)
        except Exception, e:
            msg = 'In %s::init_device() error while initializing communication: %s' % (self.get_name(), repr(e))
            self.error_stream(msg)
            self._set_state(PyTango.DevState.FAULT, msg)
            return

        #at least we have access to the serial, so try to go on
        try:
            #initialize channels keys
            self.UsedChannels = list(self.UsedChannels)
            if not self.UsedChannels in ([],['']):
                if (not (set(self.UsedChannels).issubset(set(self.CHANNELS)))):
                    PyTango.Except.throw_exception('Bad parameter', 'Invalid UsedChannels: %s' % self.UsedChannels, '%s::init_device()' % self.get_name())
                self.channels_keys = self.UsedChannels
            else:
                self.channels_keys = CHANNELS

            #initialize loops keys
            self.UsedLoops = list(self.UsedLoops)
            if not self.UsedLoops in ([],['']):
                if (not (set(self.UsedLoops).issubset(set(self.LOOPS)))):
                    PyTango.Except.throw_exception('Bad parameter', 'Invalid UsedLoops: %s' % self.UsedLoops, '%s::init_device()' % self.get_name())
                self.loops_keys = self.UsedLoops
            else:
                self.loops_keys = LOOPS

           #channels initialization
            self.valid_units = self.VALID_UNITS
            self.valid_units_sensor = self.VALID_UNITS_SENSOR
            self.channels = {}
            for channel in self.channels_keys:
                self.channels[channel] = CryoCon.Channel()
            #update channels info
            self._update_channels_info()

            #loops initialization
            self.loops = {}
            for loop in self.loops_keys:
                self.loops[loop] = CryoCon.Loop()
            self.loops_types = self.LOOPS_TYPES

            #update loops info and units
            self._update_loops_info()

            #prepare composed commands
            self.read_temp_cmd = self.CMD_CH_TEMP_QUERY % (','.join(self.channels_keys))
            self.read_loops_outputs_cmd = self.CMD_SEPARATOR.join([self.CMD_LOOP_OUTPUT_QUERY % i for i in self.loops_keys])
            self.read_loops_rates_cmd = self.CMD_SEPARATOR.join([self.CMD_LOOP_RATE_QUERY % i for i in self.loops_keys])
            self.read_loops_setpoints_read_cmd = self.CMD_SEPARATOR.join([self.CMD_LOOP_SETPT_QUERY % i for i in self.loops_keys])
            self.read_loops_types_read_cmd = self.CMD_SEPARATOR.join([self.CMD_LOOP_TYPE_QUERY % i for i in self.loops_keys])
            #let's try to avoid unnecessary accesses to the hardware
            if self.ReadValidityPeriod == []:
                self.ch_read_validity = 1 #1 second default timeout
                cmd = self.CMD_SYS_DISPLAY_TC_QUERY
                display_tc = self._communicate_raw(cmd, output_expected=True)
                self.ch_read_validity = float(display_tc)
            else:
                self.ch_read_validity = self.ReadValidityPeriod
            self.loops_rates_read_validity = self.ch_read_validity
            self.loops_outputs_read_validity = self.ch_read_validity
            self.loops_ranges_read_validity = self.ch_read_validity
            self.last_ch_read_time = 0
            self.last_loops_rates_read_time = 0
            self.last_loops_outputs_read_time = 0
            self.last_loops_ranges_read_time = 0

            #query control on/off
            cmd = self.CMD_CONTROL_QUERY
            state = self._communicate_raw(cmd, output_expected=True)
            if state == 'ON':
                self.set_state(PyTango.DevState.ON)
                self.set_status('Loop control ON')
                self.control_enabled = True
            else:
                self.set_state(PyTango.DevState.OFF)
                self.set_status('Loop control OFF')
                self.control_enabled = False

            #if autolock is on then try to lock front panel
            if (self.AutoLockFrontPanel != []) and (self.AutoLockFrontPanel):
                self.auto_lock = True
                cmd = (self.CMD_SYS_LOCKOUT % 'ON') + self.CMD_SEPARATOR + self.CMD_SYS_LOCKOUT_QUERY
                lockout = self._communicate_raw(cmd, output_expected=True)
                if lockout != 'ON':
                    msg = 'Error while trying to lock front panel'
                    self._set_state(PyTango.DevState.FAULT, msg)
            else:
                self.auto_lock = False

            #even if not locking front panel, let's set the remote LED on.
            cmd = (self.CMD_SYS_REMOTE_LED % 'ON') + self.CMD_SEPARATOR + self.CMD_SYS_REMOTE_LED_QUERY
            led = self._communicate_raw(cmd, output_expected=True)
            if led != 'ON':
                msg = 'Error while trying to set remote LED ON'
                self._set_state(PyTango.DevState.FAULT, msg)

        except Exception, e:
            msg = 'In %s::init_device() unexpected exception: %s' % (self.get_name(), repr(e))
            self.error_stream(msg)
            self._set_state(PyTango.DevState.FAULT, msg)
            raise


#------------------------------------------------------------------
#    Always executed hook method
#------------------------------------------------------------------
    def always_executed_hook(self):
        self.info_stream('In %s::always_excuted_hook()' % self.get_name())


#------------------------------------------------------------------
#    Device state
#------------------------------------------------------------------
    def dev_state(self):
        self.info_stream('In %s::dev_state()' % self.get_name())

        try:
            #if state is FAULT, don't waste your time
            current_state = self.get_state()
            if current_state == PyTango.DevState.FAULT:
                return current_state

            #query control on/off and front panel lockout
            cmd = self.CMD_CONTROL_QUERY + self.CMD_SEPARATOR + self.CMD_SYS_LOCKOUT_QUERY
            result = self._communicate_raw(cmd, output_expected=True, strip_string=True)

            #check if communication was correct and reset transient_errors if so
            if result.find('NACK') >= 0:
                self.transient_errors += 1
                error_now = True
            else:
                self.transient_errors = 0
                error_now = False
            if self.transient_errors > self.AllowedTransientErrors:
                msg = 'Max transient errors exceeded. It looks like a real comm problem. Please check!'
                self.error_stream(msg)
                self._set_state(PyTango.DevState.FAULT, msg)
                return self.get_state()
            #if this was simply a transient error, return current state
            if error_now:
                return self.get_state()

            #now it should be safe to try to parse result
            control, lockout = [res.strip() for res in result.split(self.RESULT_SEPARATOR)]

            #check control on/off has not been modified
            if control == 'ON':
                control_now = True
                state_ = PyTango.DevState.ON
            else:
                control_now = False
                state_ = PyTango.DevState.OFF
            if self.control_enabled != control_now:
                #only complain if auto_lock front panel is enabled
                if self.auto_lock:
                    msg = 'Control was supposed to be %s but it is %s. Please check!!!' % (self.control_enabled, control_now)
                    self.error_stream(msg)
                    self._set_state(PyTango.DevState.ALARM,msg)
                else:
                    self._set_state(state_, 'Loops control %s' % str(state_))
                self.control_enabled = control_now

            #if necessary, check that front panel has not been disabled
            if self.auto_lock and lockout != 'ON':
                msg = 'Front panel has been unlocked! Please check why and then call init_device()'
                self.error_stream(msg)
                self._set_state(PyTango.DevState.FAULT, msg)
        except Exception, e:
            msg = 'Unable to update device state: %s' % str(e)
            self.error_stream(msg)
            self._set_state(PyTango.DevState.FAULT, msg)

        return self.get_state()


#==================================================================
#
#    CryoConTempController read/write attribute methods
#
#==================================================================
#------------------------------------------------------------------
#    Read Attribute Hardware
#------------------------------------------------------------------
    def read_attr_hardware(self,data):
        self.info_stream('In %s::read_attr_hardware()' % self.get_name())


#------------------------------------------------------------------
#    Read TransientErrors attribute
#------------------------------------------------------------------
    def read_TransientErrors(self, attr):
        self.info_stream('In %s::read_TransientErrors()' % self.get_name())
        attr.set_value(self.transient_errors)


#------------------------------------------------------------------
#    Read ChannelA attribute
#------------------------------------------------------------------
    def read_ChannelA(self, attr):
        self.info_stream('In %s::read_ChannelA()' % self.get_name())
        self.read_Channels(attr)


#------------------------------------------------------------------
#    Read ChannelB attribute
#------------------------------------------------------------------
    def read_ChannelB(self, attr):
        self.info_stream('In %s::read_ChannelB()' % self.get_name())
        self.read_Channels(attr)


#------------------------------------------------------------------
#    Read ChannelC attribute
#------------------------------------------------------------------
    def read_ChannelC(self, attr):
        self.info_stream('In %s::read_ChannelC()' % self.get_name())
        self.read_Channels(attr)


#------------------------------------------------------------------
#    Read ChannelD attribute
#------------------------------------------------------------------
    def read_ChannelD(self, attr):
        self.info_stream('In %s::read_ChannelD()' % self.get_name())
        self.read_Channels(attr)


#------------------------------------------------------------------
#    Read Loop1Output attribute
#------------------------------------------------------------------
    def read_Loop1Output(self, attr):
        self.info_stream('In %s::read_Loop1Output()' % self.get_name())
        self.read_LoopsOutputs(attr)


#------------------------------------------------------------------
#    Read Loop2Output attribute
#------------------------------------------------------------------
    def read_Loop2Output(self, attr):
        self.info_stream('In %s::read_Loop2Output()' % self.get_name())
        self.read_LoopsOutputs(attr)


#------------------------------------------------------------------
#    Read Loop3Output attribute
#------------------------------------------------------------------
    def read_Loop3Output(self, attr):
        self.info_stream('In %s::read_Loop3Output()' % self.get_name())
        self.read_LoopsOutputs(attr)


#------------------------------------------------------------------
#    Read Loop4Output attribute
#------------------------------------------------------------------
    def read_Loop4Output(self, attr):
        self.info_stream('In %s::read_Loop4Output()' % self.get_name())
        self.read_LoopsOutputs(attr)


#------------------------------------------------------------------
#    Write Loop1Output attribute
#------------------------------------------------------------------
    def write_Loop1Output(self, attr):
        self.info_stream('In %s::write_Loop1Output()' % self.get_name())
        self.write_LoopPowerManual(attr)


#------------------------------------------------------------------
#    Write Loop2Output attribute
#------------------------------------------------------------------
    def write_Loop2Output(self, attr):
        self.info_stream('In %s::write_Loop2Output()' % self.get_name())
        self.write_LoopPowerManual(attr)


#------------------------------------------------------------------
#    Write Loop3Output attribute
#------------------------------------------------------------------
    def write_Loop3Output(self, attr):
        self.info_stream('In %s::write_Loop3Output()' % self.get_name())
        self.write_LoopPowerManual(attr)


#------------------------------------------------------------------
#    Write Loop4Output attribute
#------------------------------------------------------------------
    def write_Loop4Output(self, attr):
        self.info_stream('In %s::write_Loop4Output()' % self.get_name())
        self.write_LoopPowerManual(attr)


#------------------------------------------------------------------
#    Read Loop1Range attribute
#------------------------------------------------------------------
    def read_Loop1Range(self, attr):
        self.info_stream('In %s::read_Loop1Range()' % self.get_name())
        self.read_Loop1Range_(attr)


#------------------------------------------------------------------
#    Read Loop1Rate attribute
#------------------------------------------------------------------
    def read_Loop1Rate(self, attr):
        self.info_stream('In %s::read_Loop1Rate()' % self.get_name())
        self.read_LoopsRates(attr)


#------------------------------------------------------------------
#    Read Loop2Rate attribute
#------------------------------------------------------------------
    def read_Loop2Rate(self, attr):
        self.info_stream('In %s::read_Loop2Rate()' % self.get_name())
        self.read_LoopsRates(attr)


#------------------------------------------------------------------
#    Read Loop3Rate attribute
#------------------------------------------------------------------
    def read_Loop3Rate(self, attr):
        self.info_stream('In %s::read_Loop3Rate()' % self.get_name())
        self.read_LoopsRates(attr)


#------------------------------------------------------------------
#    Read Loop4Rate attribute
#------------------------------------------------------------------
    def read_Loop4Rate(self, attr):
        self.info_stream('In %s::read_Loop4Rate()' % self.get_name())
        self.read_LoopsRates(attr)


#------------------------------------------------------------------
#    Write Loop1Range attribute
#------------------------------------------------------------------
    def write_Loop1Range(self, attr):
        self.info_stream('In %s::write_Loop1Range()' % self.get_name())
        self.write_Loop1Range_(attr)


#------------------------------------------------------------------
#    Write Loop1Rate attribute
#------------------------------------------------------------------
    def write_Loop1Rate(self, attr):
        self.info_stream('In %s::write_Loop1Rate()' % self.get_name())
        self.write_LoopRate(attr)

#------------------------------------------------------------------
#    Write Loop2Rate attribute
#------------------------------------------------------------------
    def write_Loop2Rate(self, attr):
        self.info_stream('In %s::write_Loop2Rate()' % self.get_name())
        self.write_LoopRate(attr)


#------------------------------------------------------------------
#    Write Loop3Rate attribute
#------------------------------------------------------------------
    def write_Loop3Rate(self, attr):
        self.info_stream('In %s::write_Loop3Rate()' % self.get_name())
        self.write_LoopRate(attr)


#------------------------------------------------------------------
#    Write Loop4Rate attribute
#------------------------------------------------------------------
    def write_Loop4Rate(self, attr):
        self.info_stream('In %s::write_Loop4Rate()' % self.get_name())
        self.write_LoopRate(attr)


#------------------------------------------------------------------
#    Read read_Loop1SetPoint attribute
#------------------------------------------------------------------
    def read_Loop1SetPoint(self, attr):
        self.info_stream('In %s::read_Loop1SetPoint()' % self.get_name())
        self.read_LoopsSetPoints(attr)


#------------------------------------------------------------------
#    Read read_Loop2SetPoint attribute
#------------------------------------------------------------------
    def read_Loop2SetPoint(self, attr):
        self.info_stream('In %s::read_Loop2SetPoint()' % self.get_name())
        self.read_LoopsSetPoints(attr)


#------------------------------------------------------------------
#    Read read_Loop3SetPoint attribute
#------------------------------------------------------------------
    def read_Loop3SetPoint(self, attr):
        self.info_stream('In %s::read_Loop3SetPoint()' % self.get_name())
        self.read_LoopsSetPoints(attr)


#------------------------------------------------------------------
#    Read read_Loop4SetPoint attribute
#------------------------------------------------------------------
    def read_Loop4SetPoint(self, attr):
        self.info_stream('In %s::read_Loop4SetPoint()' % self.get_name())
        self.read_LoopsSetPoints(attr)


#------------------------------------------------------------------
#    Write Loop1SetPoint attribute
#------------------------------------------------------------------
    def write_Loop1SetPoint(self, attr):
        self.info_stream('In %s::write_Loop1SetPoint()' % self.get_name())
        self.write_LoopSetPoint(attr)


#------------------------------------------------------------------
#    Write Loop2SetPoint attribute
#------------------------------------------------------------------
    def write_Loop2SetPoint(self, attr):
        self.info_stream('In %s::write_Loop2SetPoint()' % self.get_name())
        self.write_LoopSetPoint(attr)


#------------------------------------------------------------------
#    Write Loop3SetPoint attribute
#------------------------------------------------------------------
    def write_Loop3SetPoint(self, attr):
        self.info_stream('In %s::write_Loop3SetPoint()' % self.get_name())
        self.write_LoopSetPoint(attr)


#------------------------------------------------------------------
#    Write Loop4SetPoint attribute
#------------------------------------------------------------------
    def write_Loop4SetPoint(self, attr):
        self.info_stream('In %s::write_Loop4SetPoint()' % self.get_name())
        self.write_LoopSetPoint(attr)


#------------------------------------------------------------------
#    Read Loop1Type attribute
#------------------------------------------------------------------
    def read_Loop1Type(self, attr):
        self.info_stream('In %s::read_Loop1Type()' % self.get_name())
        self.read_LoopsTypes(attr)


#------------------------------------------------------------------
#    Read Loop2Type attribute
#------------------------------------------------------------------
    def read_Loop2Type(self, attr):
        self.info_stream('In %s::read_Loop2Type()' % self.get_name())
        self.read_LoopsTypes(attr)


#------------------------------------------------------------------
#    Read Loop3Type attribute
#------------------------------------------------------------------
    def read_Loop3Type(self, attr):
        self.info_stream('In %s::read_Loop3Type()' % self.get_name())
        self.read_LoopsTypes(attr)


#------------------------------------------------------------------
#    Read Loop4Type attribute
#------------------------------------------------------------------
    def read_Loop4Type(self, attr):
        self.info_stream('In %s::read_Loop4Type()' % self.get_name())
        self.read_LoopsTypes(attr)



#------------------------------------------------------------------
#    Write Loop1Type attribute
#------------------------------------------------------------------
    def write_Loop1Type(self, attr):
        self.info_stream('In %s::write_Loop1Type()' % self.get_name())
        self.write_LoopType(attr)


#------------------------------------------------------------------
#    Write Loop2Type attribute
#------------------------------------------------------------------
    def write_Loop2Type(self, attr):
        self.info_stream('In %s::write_Loop2Type()' % self.get_name())
        self.write_LoopType(attr)


#------------------------------------------------------------------
#    Write Loop3Type attribute
#------------------------------------------------------------------
    def write_Loop3Type(self, attr):
        self.info_stream('In %s::write_Loop3Type()' % self.get_name())
        self.write_LoopType(attr)


#------------------------------------------------------------------
#    Write Loop4Type attribute
#------------------------------------------------------------------
    def write_Loop4Type(self, attr):
        self.info_stream('In %s::write_Loop4Type()' % self.get_name())
        self.write_LoopType(attr)



#==================================================================
#
# CryoConTempController command methods
#
#==================================================================

#------------------------------------------------------------------
#    On command:
#------------------------------------------------------------------
    def On(self):
        self.info_stream('In %s::On()' % self.get_name())
        #command set on an readback state
        cmd = self.CMD_CONTROL + self.CMD_SEPARATOR + self.CMD_CONTROL_QUERY
        control = self._communicate_raw(cmd, True)
        #If read back state is not on then raise exception (something happened)
        if control != 'ON':
            msg = 'Read back state is not ON after trying to set it on. Readback is: %s. Please check instrument!' % control
            self._set_state(PyTango.DevState.FAULT, msg)
            PyTango.Except.throw_exception('Instrument error', msg, '%s::On()' % self.get_name())

        self.control_enabled = True
        self._set_state(PyTango.DevState.ON, 'Loops control ON')


#------------------------------------------------------------------
#    Off command:
#------------------------------------------------------------------
    def Off(self):
        self.info_stream('In %s::Off()' % self.get_name())
        #command set off an readback state
        cmd = self.CMD_STOP + self.CMD_SEPARATOR + self.CMD_CONTROL_QUERY
        control = self._communicate_raw(cmd, True)
        #If read back state is not OFF then raise exception (something happened)
        if control != 'OFF':
            msg = 'Read back state is not OFF after trying to set it off. Readback is: %s. Please check instrument!' % control
            self._set_state(PyTango.DevState.FAULT, msg)
            PyTango.Except.throw_exception('Instrument error', msg, '%s::Off()' % self.get_name())

        self.control_enabled = False
        self._set_state(PyTango.DevState.OFF, 'Loops control OFF')


#------------------------------------------------------------------
#    Run command:
#
#    Description: directly runs a command by writting it to the hardware
#    argin:  DevString    Command to run
#    argout: DevString    Result (if any) or ''
#------------------------------------------------------------------
    def Run(self, argin):
        self.info_stream('In %s::Run()' % self.get_name())
        return self._communicate_raw(argin, True)


#------------------------------------------------------------------
#    SetChannelUnits command:
#
#    Description: set the unit of a channel and updates the
#                 corresponding tango attributes units
#    argin:  DevVarStringArray    Channel and unit to be set
#------------------------------------------------------------------
    def SetChannelUnit(self, argin):
        #check parameters
        channel, unit = argin
        channel = channel.upper()
        unit = unit.upper()
        msg = ''
        if not (channel in self.channels_keys):
            msg += 'Invalid channel: %s.Valid channels are: %s' % (channel, str(self.channels_keys))
        if not (unit in self.valid_units):
            msg += 'Invalid unit: %s.Valid units are: %s' % (unit, str(self.valid_units))
        if msg !='':
            self.error_stream(msg)
            PyTango.Except.throw_exception('Bad parameter', msg, '%s::SetChannelUnit()' % self.get_name())

        #set and read back requested value and check it really changed (if not raise exception)
        cmd = self.CMD_CH_UNIT % (channel, unit) + self.CMD_SEPARATOR + self.CMD_CH_UNIT_QUERY % (channel)
        unit_rb = self._communicate_raw(cmd, output_expected=True, strip_string=False)
        #sensor units need a special treatment
        if unit_rb in self.valid_units_sensor.keys():
            unit_rb_translated = 'S'
        else:
            unit_rb_translated = unit_rb
        if unit != unit_rb_translated:
            msg = 'read back unit (%s) is different than the one set (%s).' % (unit_rb, unit)
            PyTango.Except.throw_exception('Error', msg, '%s::SetChannelUnit()' % self.get_name())
            msg+=' Please check units consistency.'
            self._set_state(PyTango.DevState.FAULT, msg)

        #update channels info
        self._update_channels_info()

        #update loops info
        self._update_loops_info()


#==================================================================
#
#    CryoConTempControllerClass class definition
#
#==================================================================
class CryoConTempControllerClass(PyTango.DeviceClass):

    #Class Properties
    class_property_list = {
    }


    #    Device Properties
    device_property_list = {
        'AllowedTransientErrors':
            [PyTango.DevUShort,
            'Some models (at least the M24C used at alba BL29) randomly answer NACK to valid command requests. The manufacturer was contacted '
            'but I got no answer so far. The only solution to avoid continuously going to FAULT is simply ignore these transient errors.',
            [] ],
        'CommType':
            [PyTango.DevString,
            'eth or serial.',
            [] ],
        'IP':
            [PyTango.DevString,
            'IP of the instrument.',
            [] ],
        'Eth_Port':
            [PyTango.DevString,
            'Ethernet port of the instrument.',
            [] ],
        'SerialDevice':
            [PyTango.DevString,
            'The serial device to connect to the instrument.',
            [] ],
        'ReadValidityPeriod':
            [PyTango.DevDouble,
            'Time in seconds (may include decimals or be 0) while the last read values from the hardware are consider to be valid. '
            'This is done to try to minimize the accesses to the hardware. '
            'If not specified, the display time constant of the instrument will be used.',
            [] ],
        'AutoLockFrontPanel':
            [PyTango.DevBoolean,
            'Front panel lock at init. '
            'If not specified False is assumed.',
            [] ],
        'UsedChannels':
            [PyTango.DevVarStringArray,
            'The channels we really want to read and manage (ignore the others). Channels may be discontinued (i.e if I want A and D but not B or C). '
            'This is also useful to be able to control different CryoCon models which may have different number of channels but the same interface. '
            'If not specified, all channels will be used',
            [] ],
        'UsedLoops':
            [PyTango.DevVarStringArray,
            'The loops we really want to read and manage (ignore the others). Loops may be discontinued (i.e 1 and 4 but not 2 or 3), but'
            'the channel that a given loops is using as source must be in UsedChannels. '
            'This is also useful to be able to control different CryoCon models which may have different number of loops but the same interface. '
            'If not specified, all loops will be used',
            [] ],
    }


    #Command definitions
    cmd_list = {
        'SetChannelUnit':
            [[PyTango.DevVarStringArray, 'channel and unit to set'],
             [PyTango.DevVoid, '']],
        'On':
            [[PyTango.DevVoid, ''],
             [PyTango.DevVoid, '']],
        'Off':
            [[PyTango.DevVoid, ''],
             [PyTango.DevVoid, '']],
        'Run':
            [[PyTango.DevString, 'Command to run'],
             [PyTango.DevString, 'Results']],
    }


    #Attribute definitions
    attr_list = {
        'ChannelA':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ],
            { 'format': '%6.6f'
            }],
        'ChannelB':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ],
            { 'format': '%6.6f'
            }],
        'ChannelC':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ],
            { 'format': '%6.6f'
            }],
        'ChannelD':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ],
            { 'format': '%6.6f'
            }],
        'Loop1Output':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'description':'Output power', 'unit': '%', 'format': '%6.6f'
            }],
        'Loop2Output':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'description':'Output power', 'unit': '%', 'format': '%6.6f'
            }],
        'Loop3Output':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'description':'Output power', 'unit': '%', 'format': '%6.6f'
            }],
        'Loop4Output':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'description':'Output power', 'unit': '%', 'format': '%6.6f'
            }],
        'Loop1Range':
            [[PyTango.DevString,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'description': 'Loop 1 range (HI, MID, LOW)'
            }],
        'Loop1Rate':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'format': '%6.6f'
            }],
        'Loop2Rate':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'format': '%6.6f'
            }],
        'Loop3Rate':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'format': '%6.6f'
            }],
        'Loop4Rate':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'format': '%6.6f'
            }],
        'Loop1SetPoint':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'format': '%6.6f'
            }],
        'Loop2SetPoint':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'format': '%6.6f'
            }],
        'Loop3SetPoint':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'format': '%6.6f'
            }],
        'Loop4SetPoint':
            [[PyTango.DevDouble,
            PyTango.SCALAR,
            PyTango.READ_WRITE],
            { 'format': '%6.6f'
            }],
        'Loop1Type':
            [[PyTango.DevString,
            PyTango.SCALAR,
            PyTango.READ_WRITE]],
        'Loop2Type':
            [[PyTango.DevString,
            PyTango.SCALAR,
            PyTango.READ_WRITE]],
        'Loop3Type':
            [[PyTango.DevString,
            PyTango.SCALAR,
            PyTango.READ_WRITE]],
        'Loop4Type':
            [[PyTango.DevString,
            PyTango.SCALAR,
            PyTango.READ_WRITE]],
        'TransientErrors':
            [[PyTango.DevLong,
            PyTango.SCALAR,
            PyTango.READ],
            {
            }],
    }


#------------------------------------------------------------------
#    CryoConTempControllerClass Constructor
#------------------------------------------------------------------
    def __init__(self, name):
        PyTango.DeviceClass.__init__(self, name)
#        CryoCon.__init__()
        self.set_type(name)
        print 'In CryoConTempControllerClass  constructor'

#==================================================================
#
#    CryoConTempController class main method
#
#==================================================================
def main(*args):
    try:
        py = PyTango.Util(*args)
        py.add_class(CryoConTempControllerClass,CryoConTempController)

        U = PyTango.Util.instance()
        U.server_init()
        U.server_run()

    except PyTango.DevFailed,e:
        print '-------> Received a DevFailed exception:',e
    except Exception,e:
        print '-------> An unforeseen exception occurred....',e
        raise


#==================================================================
#
#    CryoConTempController class main invocation
#
#==================================================================
if __name__ == '__main__':
    main(sys.argv)
