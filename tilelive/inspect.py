#!/usr/bin/env python

import tornado
from server import TileLive
import safe64, cache, tempfile, os, logging
from tornado.escape import json_encode, json_decode
from osgeo import ogr

# TODO: tempfile should not be required

"""
  Data type inspection machinery. Could be sensitive; don't enable this
  all the time.
"""

class InspectStatusHandler(tornado.web.RequestHandler, TileLive):
    """ sample data from each datasource referenced by a mapfile """
    def get(self):
        self.jsonp(json_encode({
            'status': True
            }), self.get_argument('jsoncallback', None))
        self.finish()

class InspectValueHandler(tornado.web.RequestHandler, TileLive):
    """ sample data from each datasource referenced by a mapfile """
    @tornado.web.asynchronous
    def get(self, mapfile_64, layer_id_64, field_name_64):
        self.layer_id   = safe64.decode(layer_id_64)
        self.field_name = safe64.decode(field_name_64)
        self.application._map_cache.get(mapfile_64, self, self.async_callback(self.async_get))

    def async_get(self, mapnik_map):
        try:
            layer = self.layer_by_id(mapnik_map, self.layer_id)

            field_values = [dict(f).get(self.field_name)
                for f in layer.datasource.all_features()]

            start = 0 + int(self.get_argument('start', 0))
            end = int(self.get_argument('limit', 30)) + \
                int(self.get_argument('start', 0))

            stringlen = {'key': len} if isinstance(field_values[0], basestring) else {}

            json = json_encode({
                'min': min(field_values, **stringlen),
                'max': max(field_values, **stringlen),
                'count': len(set(field_values)),
                'field': self.field_name,
                'values': sorted(list(set(field_values)))[start:end]
            })
            self.jsonp(json, self.get_argument('jsoncallback', None))
        except IndexError:
            self.jsonp({'error': 'Layer not found'}, self.get_argument('jsoncallback', None))
        except Exception, e:
            self.jsonp(json_encode({'error': 'Exception: %s' % e}), self.get_argument('jsoncallback', None))
        self.finish()

class InspectLayerHandler(tornado.web.RequestHandler, TileLive):
    """ fields and field types of each datasource referenced by a mapfile """
    @tornado.web.asynchronous
    def get(self, mapfile_64, layer_id_64):
        self.layer_id = safe64.decode(layer_id_64)
        self.application._map_cache.get(mapfile_64, self, self.async_callback(self.async_get))

    def async_get(self, mapnik_map):
        layer = self.layer_by_id(mapnik_map, self.layer_id)
        shapefile_path = layer.datasource.params().as_dict().get('file', None)

        if not shapefile_path:
            return false

        json = json_encode({
          'layer_id': self.layer_id,
          'srs': self.shapefile_projection(shapefile_path)
        })

        self.jsonp(json, self.get_argument('jsoncallback', None))
        self.finish()

    def shapefile_projection(self, shapefile_path):
        """ given a path to a shapefile, get the proj4 string """

        shapefile = ogr.Open(shapefile_path)
        if shapefile is not None:
            layer = shapefile.GetLayer(0).GetSpatialRef()
            if layer is not None:
                return layer.ExportToProj4()
        return False

class InspectDataHandler(tornado.web.RequestHandler, TileLive):
    """ fields and field types of each datasource referenced by a mapfile """
    @tornado.web.asynchronous
    def get(self, data_url_64):
        self.get_url = safe64.decode(data_url_64)
        self.precache = cache.PreCache(directory=tempfile.gettempdir(), request_handler = self)
        self.precache.add(self.get_url)
        self.precache.execute(self.async_callback(self.async_get))
        return "Reimplementing"

    def async_get(self):
        self.jsonp({
          'data_url': self.get_url,
          'srs': self.shapefile_projection(shapefile_path + '.shp')
        }, self.get_argument('jsoncallback', None))
        self.finish()

    def shapefile_projection(self, shapefile_path):
        """ given a path to a shapefile, get the proj4 string """
        # TODO: remove OGR dependency
        logging.info(shapefile_path)
        shapefile = ogr.Open(shapefile_path)
        if shapefile is not None:
            layer = shapefile.GetLayer(0).GetSpatialRef()
            if layer is not None:
                return layer.ExportToProj4()
        return False

class InspectFieldHandler(tornado.web.RequestHandler, TileLive):
    """ fields and field types of each datasource referenced by a mapfile """
    @tornado.web.asynchronous
    def get(self, mapfile_64):
        self.application._map_cache.get(mapfile_64, self, self.async_callback(self.async_get))

    def async_get(self, mapnik_map):
        json = json_encode(dict([
            (layer.datasource.params().as_dict().get('id', layer.name),
              {
                'fields': dict(zip(layer.datasource.fields(),
                [field.__name__ for field in layer.datasource.field_types()])),
                'extent': self.layer_envelope(layer)
              }
            ) for layer in mapnik_map.layers]))
        self.jsonp(json, self.get_argument('jsoncallback', None))
        self.finish()

    def layer_envelope(self, layer):
        """ given a layer object, return an envelope of it in merc """
        e = layer.envelope()
        return [e.minx, e.miny, e.maxx, e.maxy]

class InspectDataHandler(tornado.web.RequestHandler, TileLive):
    """ fields and field types of each datasource referenced by a mapfile """
    @tornado.web.asynchronous
    def get(self, data_url_64):
        self.get_url = safe64.decode(data_url_64)
        self.precache = cache.PreCache(directory=tempfile.gettempdir(), request_handler=self)
        self.precache.add(self.get_url)
        self.precache.execute(self.async_callback(self.async_get))

    def async_get(self):
        shapefile_dir = os.path.join(self.precache.directory, safe64.dir(self.get_url))
        shapefile_path = [f for f in os.listdir(shapefile_dir) if f.endswith('shp')][0]
        self.jsonp({
          'data_url': self.get_url,
          'srs': self.shapefile_projection(os.path.join(shapefile_dir, shapefile_path))
        }, self.get_argument('jsoncallback', None))
        self.finish()

    def shapefile_projection(self, shapefile_path):
        """ given a path to a shapefile, get the proj4 string """
        # TODO: remove OGR dependency
        shapefile = ogr.Open(shapefile_path)
        if shapefile is not None:
            layer = shapefile.GetLayer(0).GetSpatialRef()
            if layer is not None:
                return layer.ExportToProj4()
        return False

# Provide handlers to server
handlers = [
  (r"/status.json", InspectStatusHandler),
  (r"/([^/]+)/fields.json", InspectFieldHandler),
  (r"/([^/]+)/data.json", InspectDataHandler),
  (r"/([^/]+)/([^/]+)/layer.json", InspectLayerHandler),
  (r"/([^/]+)/([^/]+)/([^/]+)/values.json", InspectValueHandler)]
