import time
import asyncio
import logging
import datetime
import functools
import contextlib


OUT_OF_RANGE = '_______'
OUT_OF_LIMIT = '.......'
NA = 'N/A'
DISABLED = ''
UNITS = ('K', 'C', 'F', 'S')
NACK = 'NACK'

# Delta read back tolerance
DELTA_RB = 0.0000001  # 6 decimals precision
# setpoints seem to have some kind of preset values when not in K or S units
DELTA_RB_SETPT = 0.0001

TYPES = ['OFF', 'PID', 'MAN', 'TABLE', 'RAMPP', 'RAMPT']
RANGES = ['HI', 'MID', 'LOW']


def to_int(text):
    if text in (OUT_OF_LIMIT, OUT_OF_RANGE, NA):
        return None
    return int(text)


def to_float(text):
    if text in (OUT_OF_LIMIT, OUT_OF_RANGE, NA):
        return None
    return float(text)


def to_float_unit(text):
    return to_float(text[:-1])


def to_on_off(text):
    return text.upper() == 'ON'


def from_on_off(b):
    if b in {True, 'on', 'ON'}:
        return 'ON'
    elif b in {False, 'off', 'OFF'}:
        return 'OFF'
    raise ValueError('Invalid ON/OFF value {!r}'.format(b))


def to_name(text):
    return text.strip('"')


def from_name(text):
    return '"{}"'.format(text)


def to_date(text):
    month, day, year = [int(i) for i in text.strip('"').split('/')]
    return datetime.date(year, month, day)


def from_date(date):
    if isinstance(date, str):
        if not date.startswith('"'):
            date = '"{}"'.format(date)
        return date
    return date.strftime('"%m/%d/%Y"')


def to_time(text):
    hh, mm, ss = [int(i) for i in text.strip('"').split(':')]
    return datetime.time(hh, mm, ss)


def from_time(time):
    if isinstance(time, str):
        if not time.startswith('"'):
            time = '"{}"'.format(time)
        return time
    return time.strftime('"%H:%M:%S"')


def handle_reply(reply):
    if reply is None:
        return
    reply = reply.decode().strip()
    if reply is NACK:
        raise CryoConError('Command not acknowledged')
    return reply


class CryoConError(Exception):
    pass


def sub_member(prefix, name, fget=lambda x: x, fset=None):
    assert not (fget is None and fset is None)
    cmd = ':{} {{}}:{}'.format(prefix.upper(), name.upper())

    def get_set(obj, value=None):
        command = cmd.format(obj.id)
        if value is None:
            if fget is None:
                raise ValueError('{} is not readable'.format(command))
            command += '?'
        elif fset is None:
            raise ValueError('{} is not writable'.format(command))
        else:
            set_command = '{} {}'.format(command, fset(value))
            if fget is None:
                return obj.ctrl._command(set_command)
            command = '{};{}?'.format(set_command, command)
        return obj.ctrl._query(command, fget)

    return get_set


channel_member = functools.partial(sub_member, 'INPUT')
loop_member = functools.partial(sub_member, 'LOOP')


class Channel:

    name = channel_member('nam', to_name, from_name)
    temperature = channel_member('temp', to_float)
    unit = channel_member('unit')
    minimum = channel_member('min', to_float)
    maximum = channel_member('max', to_float)
    variance = channel_member('vari', to_float)
    slope = channel_member('slop', to_float)
    offset = channel_member('offs', to_float)
    alarm = channel_member('alar')

    def __init__(self, channel, ctrl):
        self.id = channel
        self.ctrl = ctrl

    def clear_alarm(self):
        self.ctrl._command(':INPUT A:ALAR:CLE')


class Loop:

    source = loop_member('source', fset=str)
    set_point = loop_member('setpt', to_float_unit)
    error = loop_member('err')
    type = loop_member('typ', fset=str)
    range = loop_member('rang', fset=str)
    ramp = loop_member('ramp', to_on_off)
    rate = loop_member('rate', to_float, str)
    proportional_gain = loop_member('pga', to_float, str)
    integrator_gain = loop_member('iga', to_float, str)
    differentiator_gain = loop_member('dga', to_float, str)
    manual_output_power = loop_member('pman', to_float, str)  # percentage
    output_power = loop_member('outp', to_float)  # percentage
    load = loop_member('load', to_int, str)
    max_output_power = loop_member('maxp', to_float, str)  # percentage
    max_set_point = loop_member('maxs', to_float_unit)
    output_voltage = loop_member('vsen', to_float_unit)  # in V
    output_current = loop_member('isen', to_float_unit)  # in A
    output_load_resistance = loop_member('lsen', to_float, None)
    temperature = loop_member('htrh', to_float_unit, None)  # in degC
    autotune_status = loop_member('aut:stat', str, None)

    def __init__(self, nb, ctrl):
        self.id = nb
        self.ctrl = ctrl

    def _query(self, cmd, func=lambda x: x):
        cmd = ':LOOP {}:{}?'.format(self.id, cmd)
        return self.ctrl._query(cmd, func)

    def _command(self, cmd, value):
        cmd = ':LOOP {}:{} {}'.format(self.id, cmd, value)
        self.ctrl._command(cmd)


def member(name, fget=lambda x: x, fset=None):
    assert not (fget is None and fset is None)
    cmd = ':{}'.format(name.upper())

    def get_set(obj, value=None):
        command = cmd
        if value is None:
            if fget is None:
                raise ValueError('{} is not readable'.format(command))
            command += '?'
        elif fset is None:
            raise ValueError('{} is not writable'.format(command))
        else:
            set_command = '{} {}'.format(command, fset(value))
            if fget is None:
                return obj._command(set_command)
            command = '{};{}?'.format(set_command, command)
        return obj._query(command, fget)

    return get_set


class CryoCon:

    comm_error_retry_period = 3

    class Group:

        def __init__(self, ctrl):
            self.ctrl = ctrl
            self.cmds = ['']
            self.funcs = []

        def append(self, cmd, func):
            cmds = self.cmds[-1]
            # maximum of 255 characters per command
            if len(cmds) + len(cmd) > 250:
                cmds = ''
                self.cmds.append(cmds)
            cmds += cmd
            self.cmds[-1] = cmds
            self.funcs.append(func)

        def _store(self, replies):
            replies = ''.join(replies)
            replies = (msg.strip() for msg in replies.split(';'))
            replies = [func(text) for func, text in zip(self.funcs, replies)]
            self.replies = replies

        async def _async_store(self, replies):
            self._store([await reply for reply in replies])

        def query(self):
            replies = [self.ctrl._ask(request) for request in self.cmds]
            is_async = replies and asyncio.iscoroutine(replies[0])
            store = self._async_store if is_async else self._store
            return store(replies)

    def __init__(self, conn, channels='ABCD', loops=(1, 2, 3, 4)):
        self._conn = conn
        self._is_async = asyncio.iscoroutinefunction(conn.write_readline)
        self._log = logging.getLogger("CryoCon({}:{})".format(conn.host, conn.port))
        self._last_comm_error = None, 0  # (error, timestamp)
        self.channels = {channel: Channel(channel, self) for channel in channels}
        self.loops = {loop: Loop(loop, self) for loop in loops}
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
        group = self.group
        self.group = None
        group.query()

    async def __aenter__(self):
        self.group = self.Group(self)
        return self.group

    async def __aexit__(self, exc_type, exc_value, traceback):
        group = self.group
        self.group = None
        await group.query()

    @contextlib.contextmanager
    def _guard_io(self):
        self._last_comm_error = None, 0
        try:
            yield
        except OSError as comm_error:
            self._last_comm_error = comm_error, time.time()
            raise

    async def _async_io(self, func, request):
        self._log.debug("REQ: %r", request)
        with self._guard_io():
            reply = handle_reply(await func(request))
        self._log.debug("REP: %r", reply)
        return reply

    def _sync_io(self, func, request):
        self._log.debug("REQ: %r", request)
        with self._guard_io():
            reply = handle_reply(func(request))
        self._log.debug("REP: %r", reply)
        return reply

    def _ask(self, cmd):
        now = time.time()
        last_err, last_ts = self._last_comm_error
        if now < (last_ts + self.comm_error_retry_period):
            raise last_err
        query = '?;' in cmd
        raw_cmd = cmd.encode() + b'\n'
        io = self._conn.write_readline if query else self._conn.write
        handle = self._async_io if asyncio.iscoroutinefunction(io) else self._sync_io
        return handle(io, raw_cmd)

    def _query(self, cmd, func=lambda x: x):
        cmd = cmd + ';'
        if self.group is None:
            reply = self._ask(cmd)
            if asyncio.iscoroutine(reply):
                async def async_func(reply):
                    return func(await reply)
                reply = async_func(reply)
            else:
                reply = func(reply)
            return reply
        else:
            self.group.append(cmd, func)

    def _command(self, cmd):
        return self._ask(cmd)

    idn = member('*IDN')
    name = member('SYSTEM:NAME', to_name, from_name)
    hw_revision = member('SYSTEM:HWR')
    fw_revision = member('SYSTEM:FWR')
    lockout = member('SYSTEM:LOCKOUT', to_on_off, from_on_off)
    led = member('SYSTEM:REMLED', to_on_off, from_on_off)
    display_filter_time = member('SYSTEM:DISTC', to_float, str)
    date = member('SYSTEM:DATE', to_date, from_date)
    time = member('SYSTEM:TIME', to_time, from_time)

    def control(self, value=None):
        cmd = ':CONTROL?'
        if value is not None:
            set_cmd = ':CONTROL' if value in (True, 'on', 'ON') else ':STOP'
            cmd = '{};{}'.format(set_cmd, cmd)
        return self._query(cmd, to_on_off)

    def __repr__(self):
        if self._is_async:
            data = '(asynchonous)'
        else:
            items = 'idn', 'name', 'control', 'hw_revision', 'fw_revision'
            try:
                with self as group:
                    for item in items:
                        getattr(self, item)()
                data = '\n'.join('{}: {}'.format(key.upper(), value)
                                 for key, value in zip(items, group.replies))
            except OSError:
                data = '(disconnected)'

        return 'CrycoCon({}:{})\n{}'.format(self._conn.host, self._conn.port, data)
