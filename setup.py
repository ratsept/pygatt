#!/usr/bin/env python

from setuptools import setup


setup(
    name='pygatt',
    version='0.11',
    description='Python Bluetooth 4.0 bluez gatttool wrapper',
    author='David Gelvin',
    author_email='david.gelvin@gmail.com',
    url='https://github.com/Sonopro/pygatt',
    packages=['pygatt'],
    install_requires= [
        'sh>=1.09'
    ]
)