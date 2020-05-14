# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

requirements = ['sockio>=0.8']

with open("README.md") as f:
    description = f.read()


setup(
    name='cryocon',
    author="Jairo Moldes",
    author_email='jmoldes@cells.es',
    version='2.1.0',
    description="CryCon library",
    long_description=description,
    long_description_content_type="text/markdown",
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
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8'
    ],
    install_requires=requirements,
    license="LGPLv3",
    include_package_data=True,
    keywords='cryocon, library, tango, simulator',
    packages=find_packages(),
    python_requires=">=3.5",
    url='https://github.com/ALBA-Synchrotron/cryocon')
