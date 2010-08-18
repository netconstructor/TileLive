#!/usr/bin/env python

import tornado
from server import TileLive

class PointQueryHandler(tornado.web.RequestHandler, TileLive):
    """ handle all tile requests """
    @tornado.web.asynchronous
    def get(self, mapfile, z, x, y, filetype):
        # TODO: run tile getter to generate geojson
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
            # self.get_argument('jsoncallback', None))
            self.finish()
        except RuntimeError:
            logging.error('Map for %s failed to render, cache reset', self.mapfile)
            self.application._map_cache.remove(self.mapfile)
            # Retry exactly once to re-render this tile.
            if not hasattr(self, 'retry'):
                self.retry = True
                self.get(self.mapfile, self.z, self.x, self.y, self.filetype)

handlers = [(r"/tile/([^/]+)/([0-9]+)/([0-9]+)/([0-9]+)\.(json)", PointQueryHandler)]
