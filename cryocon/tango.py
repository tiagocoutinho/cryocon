import time

from tango import DevState, AttrQuality
from tango.server import Device, attribute, command, device_property

from .cryocon import CryoCon


def create_device(address, channels, loops):
    if address.startswith('tcp://'):
        address = address[6:]
        pars = address.split(':')
        host = pars[0]
        if len(pars) > 1:
            port = int(pars[1])
        else:
            port = 5000
        return CryoCon(host, port, channels=channels, loops=loops)
    else:
        raise NotImplementedError(
            'address {!r} not supported'.format(address))


def float_attr(value):
    if value is None:
        return float('nan'), time.time(), AttrQuality.ATTR_INVALID
    return value


ATTR_MAP = {
    'channela': lambda cryo: cryo['A'].temperature,
    'channelb': lambda cryo: cryo['B'].temperature,
    'channelc': lambda cryo: cryo['C'].temperature,
    'channeld': lambda cryo: cryo['D'].temperature,
    'loop1output': lambda cryo: cryo[1].output_power,
    'loop2output': lambda cryo: cryo[2].output_power,
    'loop3output': lambda cryo: cryo[3].output_power,
    'loop4output': lambda cryo: cryo[4].output_power,
    'loop1range': lambda cryo: cryo[1].range,
    'loop1rate': lambda cryo: cryo[1].rate,
    'loop2rate': lambda cryo: cryo[2].rate,
    'loop3rate': lambda cryo: cryo[3].rate,
    'loop4rate': lambda cryo: cryo[4].rate,
    'loop1setpoint': lambda cryo: cryo[1].set_point,
    'loop2setpoint': lambda cryo: cryo[2].set_point,
    'loop3setpoint': lambda cryo: cryo[3].set_point,
    'loop4setpoint': lambda cryo: cryo[4].set_point,
}


class CryoConTempController(Device):

    address = device_property(str)
    UsedChannels = device_property([str], default_value='ABCD')
    UsedLoops = device_property([int], default_value=[1, 2, 3, 4])
    ReadValidityPeriod = device_property(float, default_value=0.1)
    AutoLockFrontPanel = device_property(bool, default_value=False)

    def init_device(self):
        super().init_device()
        self.last_read_time = 0
        self._temperatures = None
        channels = ''.join(self.UsedChannels)
        loops = self.UsedLoops

        self.cryocon = create_device(self.address, channels, loops)
        self.last_values = {}

    def delete_device(self):
        super().delete_device()
        self.cryocon._conn.close()

    def read_attr_hardware(self, indexes):
        multi_attr = self.get_device_attr()
        names = []
        with self.cryocon as group:
            for index in indexes:
                attr = multi_attr.get_attr_by_ind(index)
                attr_name = attr.get_name().lower()
                func = ATTR_MAP[attr_name]
                func(self.cryocon)
                names.append(attr_name)

        self.last_values = dict(zip(names, group.replies))

    def dev_state(self):
        try:
            return DevState.ON if self.cryocon.control else DevState.OFF
        except:
            return DevState.FAULT

    def dev_status(self):
        try:
            return 'Connected. Control is {}'.format(
                'On' if self.cryocon.control else 'Off')
        except Exception as err:
            return 'Error: {!r}'.format(err)

    @attribute
    def channelA(self):
        return float_attr(self.last_values['channela'])

    @attribute
    def channelB(self):
        return float_attr(self.last_values['channelb'])

    @attribute
    def channelC(self):
        return float_attr(self.last_values['channelc'])

    @attribute
    def channelD(self):
        return float_attr(self.last_values['channeld'])

    @attribute
    def loop1output(self):
        return float_attr(self.last_values['loop1output'])

    @loop1output.setter
    def loop1output(self, power):
        self.cryocon[1].output_power = power

    @attribute(unit='%')
    def loop2output(self):
        return float_attr(self.last_values['loop2output'])

    @loop2output.setter
    def loop2output(self, power):
        self.cryocon[2].output_power = power

    @attribute(unit='%')
    def loop3output(self):
        return float_attr(self.last_values['loop3output'])

    @loop3output.setter
    def loop3output(self, power):
        self.cryocon[3].output_power = power

    @attribute(unit='%')
    def loop4output(self):
        return float_attr(self.last_values['loop4output'])

    @loop4output.setter
    def loop4output(self, power):
        self.cryocon[4].output_power = power

    @attribute(dtype=str)
    def loop1range(self):
        return self.last_values['loop1range']

    @loop1range.setter
    def loop1range(self, range):
        self.cryocon[1].range = range

    @attribute
    def loop1rate(self):
        return float_attr(self.last_values['loop1rate'])

    @loop1rate.setter
    def loop1rate(self, rate):
        self.cryocon[1].rate = rate

    @attribute
    def loop2rate(self):
        return float_attr(self.last_values['loop2rate'])

    @loop2rate.setter
    def loop2rate(self, rate):
        self.cryocon[2].rate = rate

    @attribute
    def loop3rate(self):
        return float_attr(self.last_values['loop3rate'])

    @loop3rate.setter
    def loop3rate(self, rate):
        self.cryocon[3].rate = rate

    @attribute
    def loop4rate(self):
        return float_attr(self.last_values['loop4rate'])

    @loop4rate.setter
    def loop4rate(self, rate):
        self.cryocon[4].rate = rate

    @attribute
    def loop1setpoint(self):
        return float_attr(self.last_values['loop1setpoint'])

    @loop1setpoint.setter
    def loop1setpoint(self, set_point):
        self.cryocon[1].set_point = set_point

    @attribute
    def loop2setpoint(self):
        return float_attr(self.last_values['loop2setpoint'])

    @loop2setpoint.setter
    def loop2setpoint(self, set_point):
        self.cryocon[2].set_point = set_point

    @attribute
    def loop3setpoint(self):
        return float_attr(self.last_values['loop3setpoint'])

    @loop3setpoint.setter
    def loop3setpoint(self, set_point):
        self.cryocon[3].set_point = set_point

    @attribute
    def loop4setpoint(self):
        return float_attr(self.last_values['loop4setpoint'])

    @loop4setpoint.setter
    def loop4setpoint(self, set_point):
        self.cryocon[4].set_point = set_point

    @command
    def on(self):
        self.cryocon.control = True

    @command
    def off(self):
        self.cryocon.control = False

    @command(dtype_in=str, dtype_out=str)
    def run(self, cmd):
        return self.cryocon._ask(cmd)

    @command(dtype_in=[str])
    def setchannelunit(self, unit):
        raise NotImplementedError


def main():
    CryoConTempController.run_server()


if __name__ == '__main__':
    main()
