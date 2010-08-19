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

define('port', default=8888, 
    help='run on the given port', type=int)
define('buffer_size', default=128, 
    help='mapnik buffer size', type=int)
define('tilesize', default=256, 
    help='the size of generated tiles', type=int)
define('inspect', default=False, 
    help='open inspection endpoints for data', type=bool)
define('geojson', default=False, 
    help='allow output of GeoJSON', type=bool)
define('tile_cache', default=True, 
    help='enable development tile cache', type=bool)
define('point_query', default=True, 
    help='enable point query', type=bool)

class TileLive:
    def rle_encode(self, l):
        from itertools import groupby
        return ["%d:%s" % (len(list(group)), name) for name, group in groupby(l)]
      
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
        # TODO: run tile getter to generate geojson
        z, x, y = map(int, [z, x, y])
        if options.tile_cache and self.application._tile_cache.contains(mapfile, 
            "%d/%d/%d.%s" % (z, x, y, filetype)):
            self.set_header('Content-Type', 'application/javascript')
            self.jsonp(self.application._tile_cache.get(mapfile, 
                "%d/%d/%d.%s" % (z, x, y, filetype)),
                self.get_argument('jsoncallback', None))
            self.finish()
            return
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
            # TODO: this makes dangerous assumptions about the content of the file string
            mapnik_map.set_metawriter_property('tile_dir', 
                self.application._tile_cache.local_dir(self.mapfile, ''))
            mapnik_map.set_metawriter_property('z', str(self.z))
            mapnik_map.set_metawriter_property('x', str(self.x))
            mapnik_map.set_metawriter_property('y', str(self.y))
            url = "%d/%d/%d.%s" % (self.z, self.x, self.y, 'png')
            self.application._tile_cache.prepare_dir(self.mapfile, url)
            mapnik.render_to_file(mapnik_map, 
                self.application._tile_cache.local_url(self.mapfile, url))
            json_url = "%d/%d/%d.%s" % (self.z, self.x, self.y, 'json')
            if not os.path.isfile(self.application._tile_cache.local_url(self.mapfile, json_url)):
                o = open(self.application._tile_cache.local_url(self.mapfile, json_url), 'w')
                o.writelines("""
                { "type": "FeatureCollection",
                  "features": [
                """)
                o.close()

            self.set_header('Content-Type', 'application/javascript')
            self.jsonp(self.application._tile_cache.get(self.mapfile, 
                "%d/%d/%d.%s" % (self.z, self.x, self.y, self.filetype)),
                self.get_argument('jsoncallback', None))
            self.finish()
        except RuntimeError:
            logging.error('Map for %s failed to render, cache reset', self.mapfile)
            self.application._map_cache.remove(self.mapfile)
            # Retry exactly once to re-render this tile.
            if not hasattr(self, 'retry'):
                self.retry = True
                self.get(self.mapfile, self.z, self.x, self.y, self.filetype)





class GridTileHandler(tornado.web.RequestHandler, TileLive):
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
            # TODO: RLE
            fg = [] # feature grid
            for y in range(0, 256, 4):
                for x in range(0, 256, 4):
                    featureset = mapnik_map.query_map_point(0,x,y)
                    added = False
                    for feature in featureset.features:
                        fg.append(feature.properties['CODE2'])
                        added = True
                    if not added:
                        fg.append('')

            self.jsonp({'features': str('|'.join(self.rle_encode(fg)))}, self.get_argument('callback', None))
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
        if options.tile_cache and self.application._tile_cache.contains(mapfile, 
            "%d/%d/%d.%s" % (z, x, y, filetype)):
            self.set_header('Content-Type', 'image/png')
            self.write(self.application._tile_cache.get(mapfile, 
                "%d/%d/%d.%s" % (z, x, y, filetype)))
            self.finish()
            return
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
            im_data = self.application._im.tostring('png')
            self.write(im_data)
            self.finish()
            if options.tile_cache:
                # TODO: this makes dangerous assumptions about the content of the file string
                mapnik_map.set_metawriter_property('tile_dir', 
                    self.application._tile_cache.local_dir(self.mapfile, ''))
                mapnik_map.set_metawriter_property('z', str(self.z))
                mapnik_map.set_metawriter_property('x', str(self.x))
                mapnik_map.set_metawriter_property('y', str(self.y))
                url = "%d/%d/%d.%s" % (self.z, self.x, self.y, self.filetype)
                self.application._tile_cache.prepare_dir(self.mapfile, url)
                mapnik.render_to_file(mapnik_map, 
                    self.application._tile_cache.local_url(self.mapfile, url))
            return
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
        ]

        if options.inspect:
            import inspect
            handlers.extend(inspect.handlers)

        if options.point_query:
            import point_query
            handlers.extend(point_query.handlers)

        if options.tile_cache:
            self._tile_cache = cache.TileCache(directory='tiles')
            # handlers.extend([(r"/tile/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.(json)", DataTileHandler)])
            handlers.extend([(r"/tile/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.(json)", DataTileHandler)])
            handlers.extend([(r"/tile/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.grid\.(json)", GridTileHandler)])

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
