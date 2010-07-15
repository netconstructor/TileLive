#!/usr/bin/env python

__author__ = 'Dane Springmeyer (dbsgeo [ -a- ] gmail.com)'
__copyright__ = 'Copyright 2009, Dane Springmeyer'
__version__ = '0.1.3'
__license__ = 'BSD'

import os, sys, base64
import tornado.httpserver
import tornado.ioloop
import tornado.web
from tornado.escape import json_encode
from tornado.options import define, options
import cache, sphericalmercator, cached_compile
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

class InspectFieldHandler(tornado.web.RequestHandler, TileLive):
    """ fields and field types of each datasource referenced by a mapfile """
    def get(self, mapfile_64):
        mapnik_map = self.application._map_cache.get(mapfile_64)

        json = json_encode(dict([
            (layer.datasource.params().as_dict().get('id', layer.name),
              {
                'fields': dict(zip(layer.datasource.fields(),
                [field.__name__ for field in layer.datasource.field_types()])),
                'extent': self.layer_envelope(layer)
              }
            ) for layer in mapnik_map.layers]))
        self.jsonp(json, self.get_argument('jsoncallback', None))

    def layer_envelope(self, layer):
        """ given a layer object, return an envelope of it in merc """
        e = layer.envelope()
        return [e.minx, e.miny, e.maxx, e.maxy]

class InspectDataHandler(tornado.web.RequestHandler, TileLive):
    """ fields and field types of each datasource referenced by a mapfile """
    def get(self, data_url_64):
        data_url = base64.urlsafe_b64decode(data_url_64)
        shapefile_path = cached_compile.localize_shapefile('', data_url, urlcache = True)

        if not shapefile_path:
            return false

        json = json_encode({
          'data_url': data_url,
          'srs': self.shapefile_projection(shapefile_path + '.shp')
        })

        self.jsonp(json, self.get_argument('jsoncallback', None))

    def shapefile_projection(self, shapefile_path):
        """ given a path to a shapefile, get the proj4 string """

        shapefile = ogr.Open(shapefile_path)
        return shapefile.GetLayer(0).GetSpatialRef().ExportToProj4()

class InspectLayerHandler(tornado.web.RequestHandler, TileLive):
    """ fields and field types of each datasource referenced by a mapfile """
    def get(self, mapfile_64, layer_id_64):
        mapnik_map = self.application._map_cache.get(mapfile_64)
        layer_id   = base64.urlsafe_b64decode(layer_id_64)

        layer = self.layer_by_id(mapnik_map, layer_id)
        shapefile_path = layer.datasource.params().as_dict().get('file', None)

        if not shapefile_path:
            return false

        json = json_encode({
          'layer_id': layer_id,
          'srs': self.shapefile_projection(shapefile_path)
        })

        self.jsonp(json, self.get_argument('jsoncallback', None))

    def shapefile_projection(self, shapefile_path):
        """ given a path to a shapefile, get the proj4 string """
        shapefile = ogr.Open(shapefile_path)
        return shapefile.GetLayer(0).GetSpatialRef().ExportToProj4()

class InspectValueHandler(tornado.web.RequestHandler, TileLive):
    """ sample data from each datasource referenced by a mapfile """
    def get(self, mapfile, layer_id_64, field_name_64):
        self.set_header('Content-Type', 'text/javascript')

        layer_id   = base64.urlsafe_b64decode(layer_id_64)
        field_name = base64.urlsafe_b64decode(field_name_64)
        mapnik_map = self.application._map_cache.get(mapfile)

        try:
            layer = self.layer_by_id(mapnik_map, layer_id)

            field_values = [dict(f.properties).get(field_name)
                for f in layer.datasource.all_features()]

            start = 0 + int(self.get_argument('start', 0))
            end = int(self.get_argument('limit', 30)) + \
                int(self.get_argument('start', 0))

            stringlen = {'key': len} if isinstance(field_values[0], basestring) else {}

            json = json_encode({
                'min': min(field_values, **stringlen),
                'max': max(field_values, **stringlen),
                'count': len(set(field_values)),
                'field': field_name,
                'values': sorted(list(set(field_values)))[start:end]
            })
            self.jsonp(json, self.get_argument('jsoncallback', None))

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
            (r"/([^/]+)/data.json", InspectDataHandler),
            (r"/([^/]+)/([^/]+)/layer.json", InspectLayerHandler),
            # (r"/([^/]+)/([^/]+)/values.json", InspectLayerValuesHandler),
            (r"/([^/]+)/([^/]+)/([^/]+)/values.json", InspectValueHandler),
        ]
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
