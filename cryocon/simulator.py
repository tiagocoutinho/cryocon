# -*- coding: utf-8 -*-
#
# This file is part of the instrument simulator project
#
# Copyright (c) 2019 Tiago Coutinho
# Distributed under the MIT. See LICENSE for more info.

"""
.. code-block:: yaml

    devices:
    - class: CryoCon
      package: cryocon.simulator
      transports:
      - type: tcp
        url: :5000

A simple *nc* client can be used to connect to the instrument:

    $ nc 0 5000
    *IDN?
    Cryo-con,24C,204683,1.01A

Complex configuration with default values on simulator startup:

- class: CryoCon
  package: cryocon.simulator
  transports:
  - type: tcp
    url: :5001
  channels:
  - id: A
    unit: K
  - id: B
    unit: K
  loops:
  - id: 1
    source: A
    type: MAN
  distc: 4
  lockout: OFF
  remled: ON
  control: OFF
"""

import time
import random

import scpi
import gevent

from sinstruments.simulator import BaseDevice


DEFAULT_CHANNEL = {
    'unit': 'K',
    'alarm': '--',
    'alarm_highest': '105',
    'alarm_lowest': '5',
    'alarm_deadband': '0.1',
    'alarm_high_enabled': 'NO',
    'alarm_low_enabled': 'NO',
    'alarm_latch_enabled': 'NO',
    'alarm_audio': 'NO',
    'minimum': '3.4',
    'maximum': '304.12',
    'variance': '0.1',
    'slope': '0.5',
    'offset': '5.5',
}


def Channel(**data):
    id = data['id']
    data.setdefault('name', 'Channel' + id)
    channel = dict(DEFAULT_CHANNEL, **data)
    return channel


TEMPS = ['11.456', '12.456', '13.456', '14.456', '.......']

DEFAULT_LOOP = {
    'source': 'A',
    'type': 'MAN',
    'output power': '40.3',
    'setpoint': '0.0',
    'rate': '10.0',
    'range': 'MID'
}


def Loop(**data):
    return dict(DEFAULT_LOOP, **data)


DEFAULT = {
    '*idn': 'Cryo-con,24C,204683,1.01A',
    'name': 'Cryocon simulator',
    'lockout': 'OFF',
    'distc': 1,
    'remled': 'OFF',
    'control': 'OFF',
    'hardware_revision': '12A4FE',
    'firmware_revision': '78C90A',
    'channels': {name: Channel(id=name) for name in 'ABCD'},
    'loops': {str(loop): Loop(id=loop) for loop in range(2)}
}


class CryoCon(BaseDevice):

    MIN_TIME = 0.1

    def __init__(self, name, **opts):
        kwargs = {}
        if 'newline' in opts:
            kwargs['newline'] = opts.pop('newline')
        self._config = dict(DEFAULT, **opts)
        self._config['channels'] = {channel['id'].upper(): Channel(**channel)
                                    for channel in self._config['channels'].values()}
        self._config['loops'] = {str(loop['id']): Loop(**loop)
                                 for loop in self._config['loops'].values()}
        super().__init__(name, **kwargs)
        self._last_request = 0
        self._cmds = scpi.Commands({
            '*IDN': scpi.Cmd(get=lambda req: self._config['*idn']),
            'SYSTem:LOCKout': scpi.Cmd(get=self.lockout, set=self.lockout),
            'SYSTem:REMLed': scpi.Cmd(get=self.remled, set=self.remled),
            'SYSTem:NAMe': scpi.Cmd(get=self.sys_name, set=self.sys_name),
            'SYSTem:DATe': scpi.Cmd(get=self.sys_date, set=self.sys_date),
            'SYSTem:TIMe': scpi.Cmd(get=self.sys_time, set=self.sys_time),
            'SYSTem:HWRev': scpi.Cmd(get=self.hw_revision),
            'SYSTem:FWRev': scpi.Cmd(get=self.fw_revision),
            'CONTrol': scpi.Cmd(get=self.control, set=self.control),
            'STOP': scpi.Cmd(set=self.stop),
            'INPut': scpi.Cmd(get=self.get_input, set=self.set_input),
            'LOOP': scpi.Cmd(get=self.get_loop, set=self.set_loop),
        })

    def handle_line(self, line):
        self._log.debug('request %r', line)
        curr_time = time.time()
        dt = self.MIN_TIME - (curr_time - self._last_request)
        self._last_request = curr_time
        if dt > 0:
            self._log.debug('too short requests. waiting %.3f ms', dt*1000)
            gevent.sleep(dt)
        line = line.decode()
        requests = scpi.split_line(line)
        results = (self.handle_request(request) for request in requests)
        results = (result for result in results if result is not None)
        reply = ';'.join(results).encode()
        if reply:
            reply += b'\n'
            self._log.debug('reply %r', reply)
            return reply

    def handle_request(self, request):
        cmd = self._cmds.get(request.name)
        if cmd is None:
            return 'NACK'
        if request.query:
            getter = cmd.get('get')
            if getter is None:
                return 'NACK'
            return cmd['get'](request)
        else:
            setter = cmd.get('set')
            if setter is None:
                return 'NACK'
            return cmd['set'](request)

    def lockout(self, request):
        if request.query:
            return 'ON' if self._config['lockout'] in ('ON', True) else 'OFF'
        args = request.args.upper()
        if args in ('ON', 'OFF'):
            self._config['lockout'] = args

    def remled(self, request):
        if request.query:
            return 'ON' if self._config['remled'] in ('ON', True) else 'OFF'
        args = request.args.upper()
        if args in ('ON', 'OFF'):
            self._config['remled'] = args

    def control(self, request):
        if request.query:
            return 'ON' if self._config['control'] in ('ON', True) else 'OFF'
        self._config['control'] = 'ON'

    def stop(self, request):
        self._config['control'] = 'OFF'

    def sys_name(self, request):
        if request.query:
            return self._config['name']
        self._config['name'] = request.args.replace('"', '')

    def sys_date(self, request):
        if request.query:
            return time.strftime('"%m/%d/%Y"')
        # cannot change machine date!

    def sys_time(self, request):
        if request.query:
            return time.strftime('"%H:%M:%S"')
        # cannot change machine time!

    def hw_revision(self, request):
        return self._config['hardware_revision']

    def fw_revision(self, request):
        return self._config['firmware_revision']

    def get_input(self, request):
        if ':' in request.args:
            channels, variable = request.args.split(':', 1)
            variable = variable.upper()
        else:
            channels, variable = request.args, 'TEMP'
        channels = [ch.upper() for ch in channels.split(',')]
        if variable.startswith('TEMP'):
            values = [random.choice(TEMPS) for channel in channels]
            return ';'.join(values)
        elif variable.startswith('UNIT'):
            ch = self._config['channels']
            values = [ch[channel]['unit'] for channel in channels]
            return ';'.join(values)
        elif variable.startswith('NAM'):
            ch = self._config['channels']
            values = [ch[channel]['name'] for channel in channels]
            return ';'.join(values)
        elif variable.startswith('SLOP'):
            ch = self._config['channels']
            values = [ch[channel]['slope'] for channel in channels]
            return ';'.join(values)
        elif variable.startswith('VARI'):
            ch = self._config['channels']
            values = [ch[channel]['variance'] for channel in channels]
            return ';'.join(values)
        elif variable.startswith('MIN'):
            ch = self._config['channels']
            values = [ch[channel]['minimum'] for channel in channels]
            return ';'.join(values)
        elif variable.startswith('MAX'):
            ch = self._config['channels']
            values = [ch[channel]['maximum'] for channel in channels]
            return ';'.join(values)
        elif variable.startswith('ALAR'):
            ch = self._config['channels']
            values = [ch[channel]['alarm'] for channel in channels]
            return ';'.join(values)
        else:
            return 'NACK'

    def set_input(self, request):
        arg, value = request.args.split(' ', 1)
        channel, variable = arg.split(':', 1)
        variable = variable.upper()
        channels = self._config['channels']
        channel = channels[channel.upper()]
        if variable.startswith('UNIT'):
            channel['unit'] = value
        elif variable.startswith('NAM'):
            channel['name'] = value
        else:
            return 'NACK'

    def get_loop(self, request):
        channel, variable = request.args.split(':', 1)
        variable = variable.upper()
        loop = self._config['loops']
        channel = loop[channel]
        if variable.startswith('SOUR'):
            return channel['source']
        elif variable.startswith('SETP'):
            return channel['setpoint']
        elif variable.startswith('TYP'):
            return channel['type']
        elif variable.startswith('OUTP'):
            return channel['output power']
        elif variable.startswith('RAT'):
            return channel['rate']
        elif variable.startswith('RANG'):
            return channel['range']
        else:
            return 'NACK'

    def set_loop(self, request):
        arg, value = request.args.split(' ', 1)
        channel, variable = arg.split(':', 1)
        variable = variable.upper()
        loop = self._config['loops']
        channel = loop[channel]
        if variable.startswith('SOUR'):
            channel['source'] = value
        elif variable.startswith('SETP'):
            channel['setpoint'] = value
        elif variable.startswith('TYP'):
            channel['type'] = value
        elif variable.startswith('OUTP'):
            channel['output power'] = value
        elif variable.startswith('RAT'):
            channel['rate'] = value
        elif variable.startswith('RANG'):
            channel['range'] = value
        else:
            return 'NACK'
