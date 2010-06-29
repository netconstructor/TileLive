#!/usr/bin/env python

from distutils.core import setup

version = '0.1.3'
app = 'tilelite'
description = 'Lightweight WSGI tile-server, written in Python, using Mapnik rendering and designed to serve tiles in the OSM/Google scheme.'
url = 'http://bitbucket.org/springmeyer/%s/' % app
readme = file('README.txt','rb').read()

setup(name='%s' % app,
      version=version,
      description=description,
      #long_description=readme,
      author='Dane Springmeyer',
      author_email='dbsgeo@gmail.com',
      requires=['Mapnik'],
      keywords='mapnik,gis,geospatial,openstreetmap,tiles,cache',
      license='BSD',
      url=url,
      packages=['tilelite'],
      scripts = ['liteserv.py'],
      classifiers=[
            'Development Status :: 4 - Beta',
            'Environment :: Web Environment',
            'Framework :: Django',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: BSD License',
            'Intended Audience :: Science/Research',
            'Operating System :: OS Independent',
            'Programming Language :: Python',
            'Topic :: Scientific/Engineering :: GIS',
            'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
            'Topic :: Utilities'],
      )
