import time
import inspect
import logging
import urllib.parse

from connio import connection_for_url

from tango import DevState, AttrQuality, GreenMode
from tango.server import Device, attribute, command, device_property

import cryocon


def attr(**kwargs):
    name = kwargs['name'].lower()
    func = ATTR_MAP[name]
    dtype = kwargs.setdefault('dtype', float)

    def get(self):
        value = self.last_values[name]
        if isinstance(value, Exception):
            raise value
        value = self.last_values[name]
        if value is None:
            value = float('nan') if dtype == float else ''
            return value, time.time(), AttrQuality.ATTR_INVALID
        return value

    attr = attribute(get, **kwargs)

    sig = inspect.signature(func)
    if len(sig.parameters) > 1:
        @attr.setter
        def fset(self, value):
            func(self.cryocon, value)
        fset.__name__ = 'write_' + name
        kwargs['fset'] = fset

    return attr


ATTR_MAP = {
    'idn': lambda cryo: cryo.idn(),
    'control': lambda cryo, v=None: cryo.control(v),
    'channela': lambda cryo: cryo['A'].temperature(),
    'channelb': lambda cryo: cryo['B'].temperature(),
    'channelc': lambda cryo: cryo['C'].temperature(),
    'channeld': lambda cryo: cryo['D'].temperature(),
    'loop1output': lambda cryo, v=None: cryo[1].output_power(v),
    'loop2output': lambda cryo, v=None: cryo[2].output_power(v),
    'loop3output': lambda cryo, v=None: cryo[3].output_power(v),
    'loop4output': lambda cryo, v=None: cryo[4].output_power(v),
    'loop1range': lambda cryo, v=None: cryo[1].range(v),
    'loop1rate': lambda cryo, v=None: cryo[1].rate(v),
    'loop2rate': lambda cryo, v=None: cryo[2].rate(v),
    'loop3rate': lambda cryo, v=None: cryo[3].rate(v),
    'loop4rate': lambda cryo, v=None: cryo[4].rate(v),
    'loop1ramp': lambda cryo, v=None: cryo[1].ramp(v),
    'loop2ramp': lambda cryo, v=None: cryo[2].ramp(v),
    'loop3ramp': lambda cryo, v=None: cryo[3].ramp(v),
    'loop4ramp': lambda cryo, v=None: cryo[4].ramp(v),
    'loop1type': lambda cryo, v=None: cryo[1].type(v),
    'loop2type': lambda cryo, v=None: cryo[2].type(v),
    'loop3type': lambda cryo, v=None: cryo[3].type(v),
    'loop4type': lambda cryo, v=None: cryo[4].type(v),
    'loop1setpoint': lambda cryo, v=None: cryo[1].set_point(v),
    'loop2setpoint': lambda cryo, v=None: cryo[2].set_point(v),
    'loop3setpoint': lambda cryo, v=None: cryo[3].set_point(v),
    'loop4setpoint': lambda cryo, v=None: cryo[4].set_point(v),
    'loop1pgain': lambda cryo: cryo[1].proportional_gain(),
    'loop2pgain': lambda cryo: cryo[2].proportional_gain(),
    'loop3pgain': lambda cryo: cryo[3].proportional_gain(),
    'loop4pgain': lambda cryo: cryo[4].proportional_gain(),
    'loop1igain': lambda cryo: cryo[1].integrator_gain(),
    'loop2igain': lambda cryo: cryo[2].integrator_gain(),
    'loop3igain': lambda cryo: cryo[3].integrator_gain(),
    'loop4igain': lambda cryo: cryo[4].integrator_gain(),
    'loop1dgain': lambda cryo: cryo[1].differentiator_gain(),
    'loop2dgain': lambda cryo: cryo[2].differentiator_gain(),
    'loop3dgain': lambda cryo: cryo[3].differentiator_gain(),
    'loop4dgain': lambda cryo: cryo[4].differentiator_gain(),
}



class CryoCon(Device):

    green_mode = GreenMode.Asyncio

    url = device_property(str)
    baudrate = device_property(dtype=int, default_value=9600)
    bytesize = device_property(dtype=int, default_value=8)
    parity = device_property(dtype=str, default_value='N')

    UsedChannels = device_property([str], default_value='ABCD')
    UsedLoops = device_property([int], default_value=[1, 2, 3, 4])
    ReadValidityPeriod = device_property(float, default_value=0.1)
    AutoLockFrontPanel = device_property(bool, default_value=False)

    def url_to_connection_args(self):
        url = self.url
        res = urllib.parse.urlparse(url)
        kwargs = dict(concurrency="async")
        if res.scheme in {"serial", "rfc2217"}:
            kwargs.update(dict(baudrate=self.baudrate, bytesize=self.bytesize,
                               parity=self.parity))
        elif res.scheme == "tcp":
            if res.port is None:
                url += ":5000"
            kwargs["timeout"] = 0.5
            kwargs["connection_timeout"] = 1
        return url, kwargs

    async def init_device(self):
        await super().init_device()
        channels = ''.join(self.UsedChannels)
        loops = self.UsedLoops

        url, kwargs = self.url_to_connection_args()
        conn = connection_for_url(url, **kwargs)
        self.cryocon = cryocon.CryoCon(conn, channels=channels, loops=loops)
        self.last_values = {}
        self.last_state_ts = 0

    async def delete_device(self):
        super().delete_device()
        try:
            await self.cryocon._conn.close()
        except Exception:
            logging.exception('Error closing cryocon')

    async def read_attr_hardware(self, indexes):
        multi = self.get_device_attr()
        names = [
            multi.get_attr_by_ind(index).get_name().lower()
            for index in sorted(indexes)
        ]
        funcs = [ATTR_MAP[name] for name in names]
        async with self.cryocon as group:
            names.insert(0, "control")
            self.cryocon.control()
            for func in funcs:
                func(self.cryocon)
        values = group.replies
        self.last_values = dict(zip(names, values))
        await self._update_state_status(self.last_values['control'])

    async def _update_state_status(self, value=None):
        if value is None:
            ts = time.time()
            if ts < (self.last_state_ts + 1):
                return self.get_state(), self.get_status()
            try:
                value = await self.cryocon.control()
            except Exception as error:
                value = error
        ts = time.time()
        if isinstance(value, Exception):
            state, status = DevState.FAULT, 'Error: {!r}'.format(value)
        else:
            state = DevState.ON if value else DevState.OFF
            status = 'Control is {}'.format('On' if value else 'Off')
        self.set_state(state)
        self.set_status(status)
        self.last_state_ts = ts
        self.__local_status = status  # prevent deallocation by keeping reference
        return state, status

    async def dev_state(self):
        state, status = await self._update_state_status()
        return state

    async def dev_status(self):
        state, status = await self._update_state_status()
        return status

    idn = attr(name='idn', label='ID', dtype=str)
    channelA = attr(name='channelA', label='Channel A', unit='K')
    channelB = attr(name='channelB', label='Channel B', unit='K')
    channelC = attr(name='channelC', label='Channel C', unit='K')
    channelD = attr(name='channelD', label='Channel D', unit='K')
    loop1output = attr(name='loop1output', label='Loop 1 Output', unit='%')
    loop2output = attr(name='loop2output', label='Loop 2 Output', unit='%')
    loop3output = attr(name='loop3output', label='Loop 3 Output', unit='%')
    loop4output = attr(name='loop4output', label='Loop 4 Output', unit='%')
    loop1range = attr(name='loop1range', label='Loop 1 Range', dtype='str')
    loop1rate = attr(name='loop1rate', label='Loop 1 Rate', unit='K/min', min_value=0, max_value=100)
    loop2rate = attr(name='loop2rate', label='Loop 2 Rate', unit='K/min', min_value=0, max_value=100)
    loop3rate = attr(name='loop3rate', label='Loop 3 Rate', unit='K/min', min_value=0, max_value=100)
    loop4rate = attr(name='loop4rate', label='Loop 4 Rate', unit='K/min', min_value=0, max_value=100)
    loop1ramp = attr(name='loop1ramp', label='Loop 1 Ramp', dtype=bool)
    loop2ramp = attr(name='loop2ramp', label='Loop 2 Ramp', dtype=bool)
    loop3ramp = attr(name='loop3ramp', label='Loop 3 Ramp', dtype=bool)
    loop4ramp = attr(name='loop4ramp', label='Loop 4 Ramp', dtype=bool)
    loop1type = attr(name='loop1type', label='Loop 1 Type', dtype=str)
    loop2type = attr(name='loop2type', label='Loop 2 Type', dtype=str)
    loop3type = attr(name='loop3type', label='Loop 3 Type', dtype=str)
    loop4type = attr(name='loop4type', label='Loop 4 Type', dtype=str)
    loop1setpoint = attr(name='loop1setpoint', label='Loop 1 SetPoint', unit='K')
    loop2setpoint = attr(name='loop2setpoint', label='Loop 1 SetPoint', unit='K')
    loop3setpoint = attr(name='loop3setpoint', label='Loop 1 SetPoint', unit='K')
    loop4setpoint = attr(name='loop4setpoint', label='Loop 1 SetPoint', unit='K')
    loop1pgain = attr(name='loop1pgain', label='Loop 1 P gain')
    loop2pgain = attr(name='loop2pgain', label='Loop 2 P gain')
    loop3pgain = attr(name='loop3pgain', label='Loop 3 P gain')
    loop4pgain = attr(name='loop4pgain', label='Loop 4 P gain')
    loop1igain = attr(name='loop1igain', label='Loop 1 I gain', unit='s')
    loop2igain = attr(name='loop2igain', label='Loop 2 I gain', unit='s')
    loop3igain = attr(name='loop3igain', label='Loop 3 I gain', unit='s')
    loop4igain = attr(name='loop4igain', label='Loop 4 I gain', unit='s')
    loop1dgain = attr(name='loop1dgain', label='Loop 1 D gain', unit='Hz')
    loop2dgain = attr(name='loop2dgain', label='Loop 2 D gain', unit='Hz')
    loop3dgain = attr(name='loop3dgain', label='Loop 3 D gain', unit='Hz')
    loop4dgain = attr(name='loop4dgain', label='Loop 4 D gain', unit='Hz')

    @command
    def on(self):
        return self.cryocon.control(True)

    @command
    def off(self):
        return self.cryocon.control(False)

    @command(dtype_in=str, dtype_out=str)
    def run(self, cmd):
        return self.cryocon._ask(cmd)

    @command(dtype_in=[str])
    def setchannelunit(self, unit):
        raise NotImplementedError


def main():
    import logging
    fmt = '%(asctime)s %(levelname)s %(threadName)s %(message)s'
    logging.basicConfig(level=logging.WARNING, format=fmt)
    CryoCon.run_server()


if __name__ == '__main__':
    main()
