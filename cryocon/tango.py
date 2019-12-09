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

    @property
    def temperatures(self):
        if time.time() - self.last_read_time > self.ReadValidityPeriod:
            self._temperatures = self.cryocon.temperatures
            self.last_read_time = time.time()
        return self._temperatures

    @attribute
    def channelA(self):
        return self.temperatures['A']

    @attribute
    def channelB(self):
        return self.temperatures['B']

    @attribute
    def channelC(self):
        return self.temperatures['C']

    @attribute
    def channelD(self):
        return self.temperatures['D']

    @attribute
    def loop1output(self):
        return self.cryocon[1].output_power

    @attribute(unit='%')
    def loop2output(self):
        return self.cryocon[2].output_power

    @attribute(unit='%')
    def loop2output(self):
        return self.cryocon[3].output_power

    @attribute(unit='%')
    def loop4output(self):
        return self.cryocon[4].output_power

    @attribute(dtype=str)
    def loop1range(self):
        return self.cryocon[1].range

    @attribute
    def loop1rate(self):
        return self.cryocon[1].rate

    @attribute
    def loop2rate(self):
        return self.cryocon[2].rate

    @attribute
    def loop3rate(self):
        return self.cryocon[3].rate

    @attribute
    def loop4rate(self):
        return self.cryocon[4].rate

    @attribute
    def loop1setpoint(self):
        return self.cryocon[1].set_point

    @attribute
    def loop2setpoint(self):
        return self.cryocon[2].set_point

    @attribute
    def loop3setpoint(self):
        return self.cryocon[3].set_point

    @attribute
    def loop4setpoint(self):
        return self.cryocon[4].set_point

    @command
    def on(self):
        self.cryocon.control = True

    @command
    def off(self):
        self.cryocon.control = False

    @command(dtype_in=str, dtype_out=str)
    def run(self, cmd):
        return self.cryocon._query(cmd)

    @command(dtype_in=[str])
    def setchannelunit(self, unit):
        raise NotImplementedError


def main():
    CryoConTempController.run_server()


if __name__ == '__main__':
    main()
