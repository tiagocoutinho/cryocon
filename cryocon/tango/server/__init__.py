from .cryocon import CryoCon


def main():
    import sys
    import logging
    import tango.server
    args = ['CryoCon'] + sys.argv[1:]
    fmt = '%(asctime)s %(threadName)s %(levelname)s %(name)s %(message)s'
    logging.basicConfig(level=logging.INFO, format=fmt)
    tango.server.run((CryoCon,), args=args, green_mode=tango.GreenMode.Asyncio)
