#!/usr/bin/env python

from distutils.core import setup

setup(
    name="rts2www",
    version="0.1",
    packages=["rts2www"],
    package_data = {'':["templates/*", "uploads/*", "static/*"]}

        )
