import logging
import functools

import sockio.sio


OUT_OF_RANGE = '_______'
OUT_OF_LIMIT = '.......'
DISABLED = ''
UNITS = ('K', 'C', 'F', 'S')
NAK = 'NAK'

#Delta read back tolerance
DELTA_RB = 0.0000001 #6 decimals precision
#setpoints seem to have some kind of preset values when not in K or S units
DELTA_RB_SETPT = 0.0001

TYPES = ['OFF', 'PID', 'MAN', 'TABLE', 'RAMPP', 'RAMPT']
RANGES = ['HI', 'MID', 'LOW']


def to_float(text):
    if text in (OUT_OF_LIMIT, OUT_OF_RANGE):
        return None
    return float(text)


def to_float_unit(text):
    return to_float(text[:-1])


def to_on_off(text):
    return text.upper() == 'ON'


def from_name(text):
    return '"{}"'.format(text)


class CryoConError(Exception):
    pass


class _Property:

    def __init__(self, prefix, name, fget=lambda x: x, fset=lambda x: x):
        self.cmd = ':{} {{}}:{}'.format(prefix.upper(), name.upper())
        self.fget = fget
        self.fset = fset

    def __get__(self, obj, owner=None):
        if self.fget is None:
            raise AttributeError("can't set attribute")
        cmd = self.cmd.format(obj.id) + '?'
        return obj.ctrl._query(cmd, self.fget)

    def __set__(self, obj, value):
        if self.fset is None:
            raise AttributeError("can't set attribute")
        cmd = '{} {}'.format(self.cmd.format(obj.id), self.fset(value))
        reply = obj.ctrl._command(cmd)


channel_property = functools.partial(_Property, 'INPUT')
loop_property = functools.partial(_Property, 'LOOP')


class Channel:

    name = channel_property('nam', fset=from_name)
    temperature = channel_property('temp', to_float)
    unit = channel_property('unit')
    variance = channel_property('vari', to_float)
    slope = channel_property('slop', to_float)
    alarm = channel_property('alar')

    def __init__(self, channel, ctrl):
        self.id = channel
        self.ctrl = ctrl


class Loop:

    source = loop_property('source')
    type = loop_property('typ')
    rate = loop_property('rate', to_float)
    set_point = loop_property('setpt', to_float_unit)

    def __init__(self, nb, ctrl):
        self.id = nb
        self.ctrl = ctrl

    def _query(self, cmd, func=lambda x: x):
        cmd = ':LOOP {}:{}?'.format(self.id, cmd)
        return self.ctrl._query(cmd, func)

    def _command(self, cmd, value):
        cmd = ':LOOP {}:{} {}'.format(self.id, cmd, value)
        self.ctrl._command(cmd)

    @property
    def output_power(self):
        return self._query('OUTPWR', to_float)

    @output_power.setter
    def output_power(self, power):
        if self.type != 'MAN':
            raise CryoConError('Loop must be in manual mode to set output power')
        self._query('OUTPWR {}'.format(power))
        rb = self.output_power
        if abs(rb - power) > DELTA_RB:
            raise CryoConError(
                'Written power {!r} differs from the one read back from '
                'instrument {!r}'.format(power, rb))

    @property
    def range(self):
        return self._query('RANGE')

    @range.setter
    def range(self, rng):
        if self.id != 1:
            raise IndexError('Can only set range for loop 1')
        if rng.upper() not in RANGES:
            raise ValueError('Invalid loop range {!r}. Valid ranges are: {}'.
                             format(rng, ','.join(RANGES)))
        self._query('RANGE {}'.format(rng))


class CryoCon:

    class Group:

        def __init__(self, ctrl):
            self.ctrl = ctrl
            self.cmds = []
            self.funcs = []

        def append(self, cmd, func):
            self.cmds.append(cmd)
            self.funcs.append(func)

        def query(self):
            request = ';'.join(self.cmds)
            reply = self.ctrl._ask(request)
            replies = (msg.strip() for msg in reply.split(';'))
            replies = [func(text) for func, text in zip(self.funcs, replies)]
            self.replies = replies

    def __init__(self, host, port=5000, channels='ABCD', loops=(1,2,3,4)):
        self._conn = sockio.sio.TCP(host, port)
        self.channels = {channel:Channel(channel, self) for channel in channels}
        self.loops = {loop:Loop(loop, self) for loop in loops}
        self.group = None

    def __getitem__(self, key):
        try:
            return self.channels[key]
        except KeyError:
            return self.loops[key]

    def __enter__(self):
        self.group = self.Group(self)
        return self.group

    def __exit__(self, exc_type, exc_value, traceback):
        self.group.query()
        self.group = None

    def _ask(self, cmd):
        cmd += '\n'
        logging.info('REQ: %r', cmd)
        reply = self._conn.write_readline(cmd.encode()).strip().decode()
        logging.info('REP: %r', reply)
        return reply

    def _query(self, cmd, func=lambda x: x):
        if self.group is None:
            return func(self._ask(cmd))
        else:
            self.group.append(cmd, func)

    def _command(self, cmd):
        reply = self._ask(cmd)
        assert not reply

    @property
    def idn(self):
        return self._query(':*IDN?')

    @property
    def name(self):
        return self._query(':SYSTEM:NAME?')

    @property
    def hw_revision(self):
        return self._query(':SYSTEM:HWR?')

    @property
    def fw_revision(self):
        return self._query(':SYSTEM:FWR?')

    @property
    def control(self):
        return self._query(':CONTROL?', to_on_off)

    @control.setter
    def control(self, onoff):
        cmd = 'CONTROL' if onoff in (True, 'on', 'ON') else 'STOP'
        self._command(cmd)

    @property
    def lockout(self):
        return self._query(':SYSTEM:LOCKOUT?', to_on_off)

    @lockout.setter
    def lockout(self, onoff):
        value = 'ON' if onoff in (True, 'on', 'ON') else 'OFF'
        self._command(':SYSTEM:LOCKOUT {}'.format(value))

    @property
    def led(self):
        return self._query(':SYSTEM:REMLED?', to_on_off)

    @led.setter
    def led(self, onoff):
        value = 'ON' if onoff in (True, 'on', 'ON') else 'OFF'
        self._command(':SYSTEM:REMLED {}'.format(value))

    @property
    def display_filter_time(self):
        return self._query(':SYSTEM:DISTC?', to_float)

    @display_filter_time.setter
    def display_filter_time(self, value):
        assert value in (0.5, 1, 2, 4, 8, 16, 32 or 64)
        self._command(':SYSTEM:DISTC {}'.format(value))
