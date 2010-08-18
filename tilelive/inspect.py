#!/usr/bin/env python

import tornado
from server import TileLive

"""
  
  Data type inspection machinery. Could be sensitive; don't enable this
  all the time.

"""

class InspectValueHandler(tornado.web.RequestHandler, TileLive):
    """ sample data from each datasource referenced by a mapfile """
    @tornado.web.asynchronous
    def get(self, mapfile_64, layer_id_64, field_name_64):
        self.layer_id   = base64.urlsafe_b64decode(layer_id_64)
        self.field_name = base64.urlsafe_b64decode(field_name_64)
        self.application._map_cache.get(mapfile_64, self, self.async_callback(self.async_get))

    def async_get(self, mapnik_map):
        try:
            layer = self.layer_by_id(mapnik_map, self.layer_id)

            field_values = [dict(f.properties).get(self.field_name)
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
            self.write(json_encode({'error': 'Layer not found'}))
        except Exception, e:
            self.write(json_encode({'error': 'Exception: %s' % e}))
        self.finish()

class InspectLayerHandler(tornado.web.RequestHandler, TileLive):
    """ fields and field types of each datasource referenced by a mapfile """
    @tornado.web.asynchronous
    def get(self, mapfile_64, layer_id_64):
        self.layer_id = base64.urlsafe_b64decode(layer_id_64)
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
        self.get_url = base64.urlsafe_b64decode(data_url_64)
        self.precache = cache.PreCache(directory=tempfile.gettempdir(), request_handler = self)
        self.precache.add(self.get_url)
        self.precache.execute(self.async_callback(self.async_get))
        return "Reimplementing"

    def async_get(self):
        # shapefile_path = cached_compile.localize_shapefile('', self.get_url, urlcache = True)

        # if not shapefile_path:
        #     return false

        json = json_encode({
          'data_url': self.get_url,
          'srs': self.shapefile_projection(shapefile_path + '.shp')
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
        self.get_url = base64.urlsafe_b64decode(data_url_64)
        self.precache = cache.PreCache(directory=tempfile.gettempdir(), request_handler = self)
        self.precache.add(self.get_url)
        self.precache.execute(self.async_callback(self.async_get))
        return "Reimplementing"

    def async_get(self):
        # shapefile_path = cached_compile.localize_shapefile('', self.get_url, urlcache = True)

        # if not shapefile_path:
        #     return false

        json = json_encode({
          'data_url': self.get_url,
          'srs': self.shapefile_projection(shapefile_path + '.shp')
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

handlers = [(r"/([^/]+)/fields.json", InspectFieldHandler),
  (r"/([^/]+)/data.json", InspectDataHandler),
  (r"/([^/]+)/([^/]+)/layer.json", InspectLayerHandler),
  (r"/([^/]+)/([^/]+)/([^/]+)/values.json", InspectValueHandler)]
