#!/usr/bin/env python

__author__ = 'Dane Springmeyer (dbsgeo [ -a- ] gmail.com)'
__copyright__ = 'Copyright 2009, Dane Springmeyer'
__version__ = '0.1.3'
__license__ = 'BSD'

import os, sys, re, base64
import tornado.httpserver
import tornado.ioloop
import tornado.web
from tornado.escape import json_encode
from tornado.options import define, options
from cgi import parse_qs
import cache, sphericalmercator
from sphericalmercator import SphericalMercator
from cascadenik import compile
from exceptions import KeyError

try:
    import mapnik2 as mapnik
except ImportError:
    import mapnik

if not hasattr(mapnik,'Envelope'):
    mapnik.Envelope = mapnik.Box2d

define('port', default=8888, help='run on the given port', type=int)
define('buffer_size', default=128, help='mapnik buffer size', type=int)
define('tilesize', default=256, help='the size of generated tiles', type=int)

class TileHandler(tornado.web.RequestHandler):
    """ handle all tile requests """
    def get(self, mapfile, z, x, y, filetype):
        z, x, y = map(int, [z, x, y])

        envelope =   self.application._merc.xyz_to_envelope(x, y, z)
        mapnik_map = self.application._map_cache.get(mapfile)
        mapnik_map.zoom_to_box(envelope)
        mapnik_map.buffer_size = options.buffer_size
        mapnik.render(mapnik_map, self.application._im)

        self.set_header('Content-Type', 'image/png')
        self.write(self.application._im.tostring('png'))

class MainHandler(tornado.web.RequestHandler):
    """ home page, of little consequence """
    def get(self):
        self.render('home.html')

class InspectFieldHandler(tornado.web.RequestHandler):
    """ fields and field types of each datasource referenced by a mapfile """
    def get(self, mapfile_64):
        mapnik_map = self.application._map_cache.get(mapfile_64)

        json = json_encode(dict([
            (layer.datasource.params().as_dict().get('id', layer.name),
              dict(zip(layer.datasource.fields(),
                [field.__name__ for field in layer.datasource.field_types()]))
            ) for layer in mapnik_map.layers]))

        if self.get_argument('jsoncallback', None):
            json = "%s(%s)" % (self.get_argument('jsoncallback'), json)
            self.set_header('Content-Type', 'text/javascript')
        else:
            self.set_header('Content-Type', 'application/json')

        self.write(json)

class InspectValueHandler(tornado.web.RequestHandler):
    """ sample data from each datasource referenced by a mapfile """
    def get(self, mapfile, layer_id_64, field_name_64):
        self.set_header('Content-Type', 'text/javascript')

        layer_id   = base64.urlsafe_b64decode(layer_id_64)
        field_name = base64.urlsafe_b64decode(field_name_64)
        mapnik_map = self.application._map_cache.get(mapfile)

        try:
            layer = filter(
                lambda l:
                    l.datasource.params().as_dict().get('id', False) == 
                    layer_id,
                mapnik_map.layers)[0]

            field_values = [dict(f.properties).get(field_name)
                for f in layer.datasource.all_features()]

            start = 0 + int(self.get_argument('start', 0))
            end = 10 + int(self.get_argument('start', 0))
                
            json = json_encode(
                {
                    'min': min(field_values),
                    'max': max(field_values),
                    'values': sorted(list(set(field_values)))[start:end]
                }
            )

            if self.get_argument('jsoncallback', None):
                json = "%s(%s)" % (self.get_argument('jsoncallback'), json)
                self.set_header('Content-Type', 'text/javascript')
            else:
                self.set_header('Content-Type', 'application/json')
                
            self.write(json)

        except IndexError:
            self.write(json_encode({'error': 'Layer not found'}))
        except Exception, e:
            self.write(json_encode({'error': 'Exception: %s' % e}))
            

class Application(tornado.web.Application):
    """ routers and settings for TileLite """
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/tile/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.(png|jpg|gif)", TileHandler),
            (r"/([^/]+)/fields.json", InspectFieldHandler),
            (r"/([^/]+)/([^/]+)/([^/]+)/values.json", InspectValueHandler),
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), 'templates'),
            static_path=os.path.join(os.path.dirname(__file__), 'static'),
        )
        tornado.web.Application.__init__(self, handlers, **settings)
        self._merc = SphericalMercator(levels=23, size=256)
        self._im = mapnik.Image(options.tilesize, options.tilesize)
        self._map_cache = cache.MapCache(directory='mapfiles')

def main():
    tornado.options.parse_command_line()

    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()
    
if __name__ == '__main__':
    main()
