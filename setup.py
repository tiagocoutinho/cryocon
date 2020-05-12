# -*- coding: utf-8 -*-

"""The setup script."""

import sys
from setuptools import setup, find_packages

requirements = ['sockio>=0.8']


setup(
    name='cryocon',
    author="Jairo Moldes",
    author_email='jmoldes@cells.es',
    version='1.1.0',
    description="CryCon library",
    long_description="CryoCon library",
    extras_require={
        'tango-ds': ['PyTango'],
        'simulator': ['sinstruments', 'scpi-protocol>=0.2']
    },
    entry_points={
        'console_scripts': [
            'CryoConTempController = cryocon.tango:main [tango-ds]',
        ]
    },
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7'
    ],
    install_requires=requirements,
    license="LGPLv3",
    include_package_data=True,
    keywords='cryocon, library, tango',
    packages=find_packages(include=['cryocon']),
    url='https://github.com/ALBA-Synchrotron/cryocon')
