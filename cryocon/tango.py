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


ATTR_MAP = {
    'channela': lambda ctrl: ctrl['A'].temperature,
    'channelb': lambda ctrl: ctrl['B'].temperature,
    'channelc': lambda ctrl: ctrl['C'].temperature,
    'channeld': lambda ctrl: ctrl['D'].temperature,
    'loop1output': lambda ctrl: ctrl[1].output_power,
    'loop2output': lambda ctrl: ctrl[2].output_power,
    'loop3output': lambda ctrl: ctrl[3].output_power,
    'loop4output': lambda ctrl: ctrl[4].output_power,
    'loop1range': lambda ctrl: ctrl[1].range,
    'loop1rate': lambda ctrl: ctrl[1].rate,
    'loop2rate': lambda ctrl: ctrl[2].rate,
    'loop3rate': lambda ctrl: ctrl[3].rate,
    'loop4rate': lambda ctrl: ctrl[4].rate,
    'loop1setpoint': lambda ctrl: ctrl[1].set_point,
    'loop2setpoint': lambda ctrl: ctrl[2].set_point,
    'loop3setpoint': lambda ctrl: ctrl[3].set_point,
    'loop4setpoint': lambda ctrl: ctrl[4].set_point,
}


class CryoConTempController(Device):

    address = device_property(str)
    UsedChannels = device_property([str], default_value='ABCD')
    UsedLoops = device_property([int], default_value=[1, 2])
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

    def read_attr_hardware(self, indexes):
        multi_attr = self.get_device_attr()
        names = []
        import time
        with self.cryocon as group:
            for index in indexes:
                attr = multi_attr.get_attr_by_ind(index)
                attr_name = attr.get_name().lower()
                ATTR_MAP[attr_name](self.cryocon)
                names.append(attr_name)
        self.last_values = dict(zip(names, group.replies))

    @attribute
    def channelA(self):
        return self.last_values['channela']

    @attribute
    def channelB(self):
        return self.last_values['channelb']

    @attribute
    def channelC(self):
        return self.last_values['channelc']

    @attribute
    def channelD(self):
        return self.last_values['channeld']

    @attribute
    def loop1output(self):
        return self.last_values['loop1output']

    @attribute(unit='%')
    def loop2output(self):
        return self.last_values['loop2output']

    @attribute(unit='%')
    def loop3output(self):
        return self.last_values['loop3output']

    @attribute(unit='%')
    def loop4output(self):
        return self.last_values['loop4output']

    @attribute(dtype=str)
    def loop1range(self):
        return self.last_values['loop1range']

    @attribute
    def loop1rate(self):
        return self.last_values['loop1rate']

    @attribute
    def loop2rate(self):
        return self.last_values['loop2rate']

    @attribute
    def loop3rate(self):
        return self.last_values['loop3rate']

    @attribute
    def loop4rate(self):
        return self.last_values['loop4rate']

    @attribute
    def loop1setpoint(self):
        return self.last_values['loop1setpoint']

    @attribute
    def loop2setpoint(self):
        return self.last_values['loop2setpoint']

    @attribute
    def loop3setpoint(self):
        return self.last_values['loop3setpoint']

    @attribute
    def loop4setpoint(self):
        return self.last_values['loop4setpoint']

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
