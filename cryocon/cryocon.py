import sockio.sio


class Channel:

    OUT_OF_RANGE = '_______'
    OUT_OF_LIMIT = '.......'
    DISABLED = ''
    UNITS = ('K', 'C', 'F', 'S')

    def __init__(self, name, ctrl):
        self.name = name
        self.ctrl = ctrl

    @property
    def temperature(self):
        cmd = 'INPUT? {}'.format(self.name)
        return float(self.ctrl._query(cmd))

    @property
    def unit(self):
        cmd = 'INPUT {}:UNITS?'.format(self.name)
        return self.ctrl._query(cmd)


class Loop:

    TYPES = ['OFF', 'PID', 'MAN', 'TABLE', 'RAMPP', 'RAMPT']
    RANGES = ['HI', 'MID', 'LOW']

    def __init__(self, nb, ctrl):
        self.nb = nb
        self.ctrl = ctrl

    def _query(self, cmd):
        cmd = 'LOOP {}:{}?'.format(self.nb, cmd)
        return self.ctrl._query(cmd)

    def _command(self, cmd, value):
        cmd = 'LOOP {}:{} {}'.format(self.nb, cmd, value)
        self.ctrl._command(cmd, value)

    @property
    def source(self):
        return self._query('SOURCE')

    @property
    def type(self):
        return self._query('TYPE')

    @property
    def output_power(self):
        return float(self._query('OUTPWR'))

    @property
    def range(self):
        return self._query('RANGE')

    @property
    def rate(self):
        return float(self._query('RATE'))

    @property
    def set_point(self):
        return float(self._query('SETPT'))


class CryoCon:

    def __init__(self, host, port=5000, channels='ABCD', loops=(1,2)):
        self._conn = sockio.sio.TCP(host, port)
        self.channels = {channel:Channel(channel, self) for channel in channels}
        self.loops = {loop:Loop(loop, self) for loop in loops}

    def __getitem__(self, key):
        try:
            return self.channels[key]
        except KeyError:
            return self.loops[key]

    def _query(self, cmd):
        if cmd[-1] not in ('\n', '\r'):
            cmd += '\n'
        return self._conn.write_readline(cmd.encode()).strip().decode()

    def _command(self, cmd):
        if cmd[-1] not in ('\n', '\r'):
            cmd += '\n'
        self._conn.write(cmd.encode())

    @property
    def idn(self):
        return self._query('*IDN?')

    @property
    def temperatures(self):
        cnames = sorted(self.channels)
        cmd = 'INPUT? {}'.format(','.join(name for name in cnames))
        values = self._query(cmd).split(';')
        return dict(zip(cnames, map(float, values)))

    @property
    def control(self):
        return self._query('CONTROL?') in ('on', 'ON')

    @control.setter
    def control(self, onoff):
        cmd = 'CONTROL' if onoff in (True, 'on', 'ON') else 'STOP'
        self._command(cmd)

    @property
    def lockout(self):
        return self._query('SYSTEM:LOCKOUT?') in ('on', 'ON')

    @lockout.setter
    def lockout(self, onoff):
        value = 'ON' if onoff in (True, 'on', 'ON') else 'OFF'
        self._command('SYSTEM:LOCKOUT {}'.format(value))

    @property
    def led(self):
        return self._query('SYSTEM:REMLED?') in ('on', 'ON')

    @led.setter
    def led(self, onoff):
        value = 'ON' if onoff in (True, 'on', 'ON') else 'OFF'
        self._command('SYSTEM:REMLED {}\n'.format(value))

    @property
    def display_filter_time(self):
        return float(self._query('SYSTEM:DISTC?'))

    @display_filter_time.setter
    def display_filter_time(self, value):
        assert value in (0.5, 1, 2, 4, 8, 16, 32 or 64)
        self._command('SYSTEM:DISTC {}'.format(value))

