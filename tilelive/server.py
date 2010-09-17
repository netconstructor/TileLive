#!/usr/bin/env python
import os, logging, json
from exceptions import KeyError

import tornado.httpclient
import tornado.httpserver
import tornado.ioloop
import tornado.web
from tornado.escape import json_encode, json_decode
from tornado.options import define, options

from sphericalmercator import SphericalMercator
import cache, safe64

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
define('tile_cache_dir', default='tiles', 
    help='tile cache dir', type=str)
define('map_cache_dir', default='mapfiles', 
    help='tile cache dir', type=str)
define('point_query', default=True, 
    help='enable point query', type=bool)

class TileLive(object):
    def rle_encode(self, l):
        """ encode a list of strings with run-length compression """
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
            json = "%s" % json
            self.set_header('Content-Type', 'application/json')
        self.write(json)
        return json

    def fString(self, mapfile_64, z, x, y):
        """ GridTiles now use predetermined callbacks that can be done on both sides """
        return "%s_%d_%d_%d" % (mapfile_64.replace('=', '_'), z, x, y)

class DataTileHandler(tornado.web.RequestHandler, TileLive):
    """ serve GeoJSON tiles created by metawriters """
    @tornado.web.asynchronous
    def get(self, layout, mapfile_64, z, x, y, filetype):
        self.z, self.x, self.y = map(int, [z, x, y])
        self.filetype = filetype
        self.mapfile_64 = mapfile_64
        code_string = self.fString(self.mapfile_64, self.z, self.x, self.y)
        if options.tile_cache and self.application._tile_cache.contains(self.mapfile_64, 
            "%d/%d/%d.%s" % (self.z, self.x, self.y, self.filetype)):
            self.set_header('Content-Type', 'text/javascript')
            self.write(self.application._tile_cache.get(self.mapfile_64, 
                "%d/%d/%d.%s" % (self.z, self.x, self.y, self.filetype)))
            self.finish()
            return
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
            code_string = self.fString(self.mapfile_64, self.z, self.x, self.y)

            mapnik.render_to_file(mapnik_map, 
                self.application._tile_cache.local_url(self.mapfile, url))

            self.set_header('Content-Type', 'text/javascript')
            code_string = self.fString(self.mapfile, self.z, self.x, self.y)
            jsonp_str = "%s(%s)" % (code_string, json_encode({
              'features': json_decode(str(self.application._tile_cache.get(self.mapfile, 
                "%d/%d/%d.%s" % (self.z, self.x, self.y, 'json')))),
              'code_string': code_string}))
            self.application._tile_cache.set(self.mapfile,
              "%d/%d/%d.%s" % (self.z, self.x, self.y, 'json'), jsonp_str)
            self.write(self.application._tile_cache.get(self.mapfile_64, 
                "%d/%d/%d.%s" % (self.z, self.x, self.y, self.filetype)))
            self.finish()
        except RuntimeError:
            logging.error('Map for %s failed to render, cache reset', self.mapfile)
            self.application._map_cache.remove(self.mapfile)
            # Retry exactly once to re-render this tile.
            if not hasattr(self, 'retry'):
                self.retry = True
                self.get(self.mapfile, self.z, self.x, self.y, self.filetype)

class GridTileHandler(tornado.web.RequestHandler, TileLive):
    """ serve gridded tile data """
    @tornado.web.asynchronous
    def get(self, layout, mapfile_64, z, x, y, join_field_64):
        self.z, self.x, self.y = map(int, [z, x, y])
        self.join_field_64 =join_field_64
        self.join_field = safe64.decode(join_field_64)
        self.filetype = 'grid.json'
        self.mapfile_64 = mapfile_64
        if options.tile_cache and self.application._tile_cache.contains(self.mapfile_64, 
            "%d/%d/%d.%s.%s" % (self.z, self.x, self.y, self.join_field, self.filetype)):
            logging.info('serving from cache')
            self.set_header('Content-Type', 'text/javascript')
            self.write(self.application._tile_cache.get(self.mapfile_64, 
                "%d/%d/%d.%s.%s" % (self.z, self.x, self.y, self.join_field, self.filetype)))
            self.finish()
            return
        self.application._map_cache.get(self.mapfile_64, self, self.async_callback(self.async_get))

    def async_get(self, mapnik_map):
        envelope = self.application._merc.xyz_to_envelope(self.x, self.y, self.z)
        mapnik_map.zoom_to_box(envelope)
        mapnik_map.buffer_size = options.buffer_size
        code_string = self.fString(self.mapfile_64, self.z, self.x, self.y)
        try:
            fg = [] # feature grid
            for y in range(0, 256, 4):
                for x in range(0, 256, 4):
                    featureset = mapnik_map.query_map_point(0,x,y)
                    added = False
                    for feature in featureset.features:
                        fg.append(feature[self.join_field])
                        added = True
                    if not added:
                        fg.append('')
            jsonp_str = self.jsonp({
              'features': str('|'.join(self.rle_encode(fg))),
              'code_string': code_string
            }, code_string)
            logging.info('wrote jsonp')
            json_url = "%d/%d/%d.%s.%s" % (self.z, self.x, self.y, self.join_field_64, self.filetype)
            self.application._tile_cache.set(self.mapfile_64, json_url, jsonp_str)
            self.finish()
        except RuntimeError:
            logging.error('Map for %s failed to render, cache reset', self.mapfile_64)
            self.application._map_cache.remove(self.mapfile_64)
            # Retry exactly once to re-render this tile.
            if not hasattr(self, 'retry'):
                self.retry = True
                self.get(self.mapfile_64, self.z, self.x, self.y, self.filetype)

class TileHandler(tornado.web.RequestHandler, TileLive):
    """ handle all tile requests """
    @tornado.web.asynchronous
    def get(self, layout, mapfile, z, x, y, filetype):
        self.z, self.x, self.y = map(int, [z, x, y])
        self.filetype = filetype
        self.tms_style = (layout == 'tms')
        self.mapfile = mapfile
        if options.tile_cache and self.application._tile_cache.contains(self.mapfile, 
            "%d/%d/%d.%s" % (self.z, self.x, self.y, filetype)):
            self.set_header('Content-Type', 'image/png')
            self.write(self.application._tile_cache.get(self.mapfile, 
                "%d/%d/%d.%s" % (self.z, self.x, self.y, self.filetype)))
            self.finish()
            return
        self.application._map_cache.get(self.mapfile, self, self.async_callback(self.async_get))

    def async_get(self, mapnik_map):
        envelope = self.application._merc.xyz_to_envelope(self.x, self.y, self.z, self.tms_style)
        mapnik_map.zoom_to_box(envelope)
        mapnik_map.buffer_size = options.buffer_size
        try:
            if options.tile_cache:
                mapnik_map.set_metawriter_property('tile_dir', 
                    self.application._tile_cache.local_dir(self.mapfile, ''))
                mapnik_map.set_metawriter_property('z', str(self.z))
                mapnik_map.set_metawriter_property('x', str(self.x))
                mapnik_map.set_metawriter_property('y', str(self.y))
                url = "%d/%d/%d.%s" % (self.z, self.x, self.y, self.filetype)
                self.application._tile_cache.prepare_dir(self.mapfile, url)
                mapnik.render_to_file(mapnik_map, 
                    self.application._tile_cache.local_url(self.mapfile, url))
                if self.application._tile_cache.contains(self.mapfile, 
                    "%d/%d/%d.%s" % (self.z, self.x, self.y, self.filetype)):
                    self.set_header('Content-Type', 'image/png')
                    self.write(self.application._tile_cache.get(self.mapfile, 
                        "%d/%d/%d.%s" % (self.z, self.x, self.y, self.filetype)))
                    code_string = self.fString(self.mapfile, self.z, self.x, self.y)
                    jsonp_str = "%s(%s)" % (code_string, json_encode({
                      'features': json_decode(str(self.application._tile_cache.get(self.mapfile, 
                        "%d/%d/%d.%s" % (self.z, self.x, self.y, 'json')))),
                      'code_string': code_string}))
                    self.application._tile_cache.set(self.mapfile,
                      "%d/%d/%d.%s" % (self.z, self.x, self.y, 'json'), jsonp_str)
                    self.finish()
                return
            else:
                im = mapnik.Image(options.tilesize, options.tilesize)
                mapnik.render(mapnik_map, im)
                self.set_header('Content-Type', 'image/png')
                im_data = im.tostring('png')
                self.write(im_data)
                self.finish()
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
            (r"/(tile|zxy)/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.(png|jpg|gif)", TileHandler),
            (r"/(tms)/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.(png|jpg|gif)", TileHandler),
        ]

        if options.inspect:
            import inspect
            handlers.extend(inspect.handlers)

        if options.point_query:
            import point_query
            handlers.extend(point_query.handlers)

        if options.tile_cache:
            # since metawriters are only written on render_to_file, the
            # tile cache must be enabled to use their output
            self._tile_cache = cache.TileCache(directory=str(options.tile_cache_dir))
            handlers.extend([
              (r"/(zxy|tile)/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.(json)", DataTileHandler),
              (r"/(zxy|tile)/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.([^/\.]+)\.grid\.json", GridTileHandler)])

        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), 'templates'),
            static_path=os.path.join(os.path.dirname(__file__), 'static'),
        )

        tornado.web.Application.__init__(self, handlers, **settings)
        self._merc = SphericalMercator(levels=23, size=256)
        self._mercator = mapnik.Projection("+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +no_defs +over")
        self._map_cache = cache.MapCache(directory=str(options.map_cache_dir))

def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == '__main__':
    main()
