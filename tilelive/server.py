#!/usr/bin/env python

__author__ = 'Dane Springmeyer (dbsgeo [ -a- ] gmail.com)'
__copyright__ = 'Copyright 2009, Dane Springmeyer'
__version__ = '0.1.3'
__license__ = 'BSD'

import os, sys, base64, logging, tempfile
import tornado.httpclient
import tornado.httpserver
import tornado.ioloop
import tornado.web
from tornado.escape import json_encode
from tornado.options import define, options
import cache, sphericalmercator
from sphericalmercator import SphericalMercator
from exceptions import KeyError
from osgeo import ogr

try:
    import mapnik2 as mapnik
except ImportError:
    import mapnik

if not hasattr(mapnik,'Envelope'):
    mapnik.Envelope = mapnik.Box2d

define('port', default=8888, help='run on the given port', type=int)
define('buffer_size', default=128, help='mapnik buffer size', type=int)
define('tilesize', default=256, help='the size of generated tiles', type=int)
define('inspect', default=False, help='open inspection endpoints for data', type=bool)
define('geojson', default=False, help='allow output of GeoJSON', type=bool)

class TileLive:
    def layer_by_id(self, mapnik_map, layer_id):
        """
        find a layer in a map, given a map id that a user puts as a param
        """
        try:
            layer = filter(
                lambda l:
                    l.datasource.params().as_dict().get('id', False) == 
                    layer_id,
                mapnik_map.layers)[0]
            return layer
        except KeyError:
            raise Exception('Layer not found')

    def jsonp(self, json, jsoncallback):
        """ serve a page with an optional jsonp callback """
        if jsoncallback:
            json = "%s(%s)" % (jsoncallback, json)
            self.set_header('Content-Type', 'text/javascript')
        else:
            self.set_header('Content-Type', 'application/json')
        self.write(json)

class DataTileHandler(tornado.web.RequestHandler, TileLive):
    """ handle all tile requests """
    @tornado.web.asynchronous
    def get(self, mapfile, z, x, y, filetype):
        z, x, y = map(int, [z, x, y])
        self.z = z
        self.x = x
        self.y = y
        self.filetype = filetype
        self.mapfile = mapfile
        self.application._map_cache.get(mapfile, self, self.async_callback(self.async_get))

    def async_get(self, mapnik_map):
        envelope = self.application._merc.xyz_to_envelope(self.x, self.y, self.z)
        mapnik_map.zoom_to_box(envelope)
        mapnik_map.buffer_size = options.buffer_size
        try:
            mapnik.render(mapnik_map, self.application._im)
            self.finish()
        except RuntimeError:
            logging.error('Map for %s failed to render, cache reset', self.mapfile)
            self.application._map_cache.remove(self.mapfile)
            # Retry exactly once to re-render this tile.
            if not hasattr(self, 'retry'):
                self.retry = True
                self.get(self.mapfile, self.z, self.x, self.y, self.filetype)

class TileHandler(tornado.web.RequestHandler):
    """ handle all tile requests """
    @tornado.web.asynchronous
    def get(self, mapfile, z, x, y, filetype):
        z, x, y = map(int, [z, x, y])
        self.z = z
        self.x = x
        self.y = y
        self.filetype = filetype
        self.mapfile = mapfile
        self.application._map_cache.get(mapfile, self, self.async_callback(self.async_get))

    def async_get(self, mapnik_map):
        envelope = self.application._merc.xyz_to_envelope(self.x, self.y, self.z)
        mapnik_map.zoom_to_box(envelope)
        mapnik_map.buffer_size = options.buffer_size
        try:
            mapnik.render(mapnik_map, self.application._im)
            self.set_header('Content-Type', 'image/png')
            self.write(self.application._im.tostring('png'))
            self.finish()
        except RuntimeError:
            logging.error('Map for %s failed to render, cache reset', self.mapfile)
            self.application._map_cache.remove(self.mapfile)
            # Retry exactly once to re-render this tile.
            if not hasattr(self, 'retry'):
                self.retry = True
                self.get(self.mapfile, self.z, self.x, self.y, self.filetype)

class MainHandler(tornado.web.RequestHandler):
    """ home page, of little consequence """
    def get(self):
        self.render('home.html')

class Application(tornado.web.Application):
    """ routers and settings for TileLite """
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/tile/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.(png|jpg|gif)", TileHandler),
            (r"/tile/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.(json)", DataTileHandler),
            (r"/features/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.(json)", FeatureTileHandler),
        ]
        if options.inspect:
            import inspect
            handlers.extend(inspect.handlers)

        if options.geojson:
            handlers.extend(
                [(r"/([^/]+)/([^/]+)/([^/]+)/geo.json", InspectGeoJSONHandler)])
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), 'templates'),
            static_path=os.path.join(os.path.dirname(__file__), 'static'),
        )
        tornado.web.Application.__init__(self, handlers, **settings)
        self._merc = SphericalMercator(levels=23, size=256)
        self._mercator = mapnik.Projection("+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +no_defs +over")
        self._im = mapnik.Image(options.tilesize, options.tilesize)
        self._map_cache = cache.MapCache(directory='mapfiles')

def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == '__main__':
    main()
