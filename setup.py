# -*- coding: utf-8 -*-

"""The setup script."""

import sys
from setuptools import setup, find_packages

requirements = ['sockio', 'PyTango']


setup(
    name='cryocon',
    author="Jairo Moldes",
    author_email='jmoldes@cells.es',
    version='1.0.0',
    description="CryCon library",
    long_description="CryoCon library",
    entry_points={
        'console_scripts': [
            'CryoConTempController = cryocon.tango:main',
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
