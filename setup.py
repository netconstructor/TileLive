#!/usr/bin/env python

from distutils.core import setup

# this version only updates the last number
version = '0.1.3.0'
app = 'tilelive'
description = 'Lightweight WSGI tile-server, written in Python, using Mapnik rendering and designed to serve tiles in the OSM/Google scheme.'
readme = file('README.markdown','rb').read()

setup(name='%s' % app,
      version = version,
      description = description,
      # long_description=readme,
      author = 'Dane Springmeyer, Tom MacWright',
      author_email = 'dbsgeo@gmail.com, macwright@gmail.com',
      requires = ['Mapnik'],
      keywords = 'mapnik,gis,geospatial,openstreetmap,tiles,cache',
      license = 'BSD',
      url = 'http://github.com/tmcw/TileLiteLive',
      download_url = "http://github.com/tmcw/TileLiteLive/zipball/v0.1.3.0#egg=tilelive-0.1.3.0",
      packages = ['tilelive'],
      scripts = ['liveserv.py', 'tileseed.py'],
      classifiers=[
            'Development Status :: 4 - Beta',
            'Environment :: Web Environment',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: BSD License',
            'Intended Audience :: Science/Research',
            'Operating System :: OS Independent',
            'Programming Language :: Python',
            'Topic :: Scientific/Engineering :: GIS',
            'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
            'Topic :: Utilities'],
      )
