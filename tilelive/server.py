#!/usr/bin/env python

__author__ = 'Dane Springmeyer (dbsgeo [ -a- ] gmail.com)'
__copyright__ = 'Copyright 2009, Dane Springmeyer'
__version__ = '0.1.3'
__license__ = 'BSD'

import os, sys, time, re, json
from urlparse import parse_qs

from tilelive import cache, sphericalmercator
from sphericalmercator import SphericalMercator

try:
    import mapnik2 as mapnik
except ImportError:
    import mapnik

# repair compatibility with mapnik2 development series
if not hasattr(mapnik,'Envelope'):
    mapnik.Envelope = mapnik.Box2d

# http://spatialreference.org/ref/epsg/3785/proj4/
#MERC_PROJ4 = "+proj=merc +lon_0=0 +k=1 +x_0=0 +y_0=0 +a=6378137 +b=6378137 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs"

# http://spatialreference.org/ref/sr-org/6/
MERC_PROJ4 = "+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +k=1.0 +units=m +nadgrids=@null +no_defs +over"
mercator = mapnik.Projection(MERC_PROJ4)

#pattern = r'/(?P<version>\d{1,2}\.\d{1,3})/(?P<layername>[a-z]{1,64})/(?P<z>\d{1,10})/(?P<x>\d{1,10})/(?P<y>\d{1,10})\.(?P<extension>(?:png|jpg|gif))'
#request_re = re.compile(pattern)

def parse_config(cfg_file):
    from ConfigParser import SafeConfigParser
    config = SafeConfigParser()
    config.read(cfg_file)
    params = {}
    for section in config.sections():
        options = config.items(section)
        for param in options:
            params[param[0]] = param[1]
    return params

def is_image_request(path_info):
    """ confirm that a requests ends in a support image type """
    if path_info.endswith('.png') | path_info.endswith('.jpeg'):
        return True
    return False

def match(attr,value):
    if isinstance(attr, bool) and str(value).lower() in ['on', 'yes', 'y', 'true']:
        return True
    elif isinstance(attr, bool):
        return False
    elif isinstance(attr, int):
        return int(value)
    elif isinstance(attr, str):
        return value
    else:
        return None
    
class Server(object):
    def __init__(self, config=None):
        # private
        self._changed = []
        self._config = config
        
        # mutable
        self.size = 256
        self.buffer_size = 128
        self.format = 'png'
        self.max_zoom = 18
        self.debug = True
        self.watch_interval = 2
        self.max_failures = 6

        self.cache_force = False
        self.cache_path = '/tmp/tilelite' #tempfile.gettempdir()
        self.map_cache_path = 'mapfiles' #tempfile.gettempdir()
        self.data_cache_path = 'data' #tempfile.gettempdir()

        self.whitelist_data = "*" 
        self.whitelist_mapfile= "*" 

        if self._config:
            self.absorb_options(parse_config(self._config))

        self._key = parse_config(self._config)['_key']

        self._whitelist_data_re = re.compile(self.whitelist_data)
        self._whitelist_mapfile_re = re.compile(self.whitelist_mapfile)

        self._merc = SphericalMercator(levels=self.max_zoom+1, size=self.size)
        self._map_cache = cache.MapCache(directory=self.map_cache_path)
        self._data_cache = cache.DataCache(directory=self.data_cache_path)
        self._im = mapnik.Image(self.size, self.size)
               
    def msg(self,message):
        """ WSGI apps must not print to stdout.
        """
        if self.debug:
            print >> sys.stderr, '[TileLite Debug] --> %s' % message

    def settings(self):
        settings = '\n'
        for k,v in self.__dict__.items():
            if not k.startswith('_'):
                if k in self._changed:
                    v = '%s *changed' % v
                settings += '%s = %s\n' % (k,v)
        return settings

    def settings_dict(self):
        settings = {}
        for k,v in self.__dict__.items():
            if not k.startswith('_'):
                settings[k] = v
        return settings

    def instance_dict(self):
        d = {}
        m = self._mapnik_map
        m.zoom_all()
        e = m.envelope()
        c = e.center()
        e2 = mercator.inverse(e)
        c2 = e2.center()
        d['extent'] = [e.minx,e.miny,e.maxx,e.maxy]
        d['center'] = [c.x,c.y]
        d['lonlat_extent'] = [e2.minx,e2.miny,e2.maxx,e2.maxy]
        d['lonlat_center'] = [c2.x,c2.y]        
        return d
        
    def absorb_options(self, opts):
        """ parse settings file and append settings to self object """
        for opt in opts.items():
            attr = opt[0]
            if hasattr(self, attr) and not attr.startswith('_'):
                cur = getattr(self, attr)
                new = match(cur, opt[1])
                if not new == cur:
                    setattr(self, attr, new)
                    self._changed.append(attr)
        self.msg(self.settings())

    def ready_cache(self, path_to_check):
        """ ensure directory structure for caching exists """
        dirname = os.path.dirname(path_to_check)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

    def hit(self, env):
        return self.envelope.intersects(env)

    def settings_page():
        """/settings"""
        mime_type = 'text/html'
        response = '<h2>TileLite Settings</h2>'
        response += '<pre>%s</pre>' % (self.settings())
        if self._config:
            response += '<h4>From: %s</h4>' % self._config
        else:
            response += '<h4>*default settings*</h4>'
        return (mime_type, response)

    def render_map(self, x, y, zoom, data, mapfile):
        """ given the parameters for a tile, return a tile. requires
        an object with _im, _merc, _map_cache, _data_cache defined """
        start_time = time.time()
        envelope = self._merc.xyz_to_envelope(x, y, zoom)
        mapnik_map = self._map_cache.get(mapfile)
        map_time = time.time()

        for layer in mapnik_map.layers:
            layer.datasource = self._data_cache.get(data)
        data_time = time.time()

        mapnik_map.zoom_to_box(envelope)
        mapnik_map.buffer_size = self.buffer_size

        arender_time = time.time()
        mapnik.render(mapnik_map, self._im)
        render_time = time.time()

        response = self._im.tostring(self.format)
        mime_type = 'image/%s' % self.format

        return (mime_type, response)
       
    def __call__(self, environ, start_response):
        """ WSGI request handler """
        response_status = "200 OK"
        mime_type = 'text/html'
        already_sent = False
        path_info = environ['PATH_INFO']
        query = parse_qs(environ['QUERY_STRING'])

        if is_image_request(path_info):

            uri, self.format = path_info.split('.')
            zoom, x, y = map(int, uri.split('/')[-3:])
            data, mapfile = uri.split('/')[-5:-3]
            
            tile_dir = os.path.join(self.cache_path, 
                data, 
                mapfile, 
                str(zoom),str(x), '%s.%s' % (str(y),self.format))

            if self.cache_force or not os.path.exists(tile_dir):
                (mime_type, response) = self.render_map(x, y, zoom, data, mapfile)

                already_sent = True
                self.msg('Zoom,X,Y: %s,%s,%s' % (zoom, x, y))
                start_response(response_status, [('Content-Type', mime_type)])
                yield response

                self.ready_cache(tile_dir)
                self._im.save(tile_dir)

            else:
                self._im = self._im.open(tile_dir)
                mime_type = 'image/%s' % self.format
                response = self._im.tostring(self.format)
                self.msg('cache hit!')
                    
        elif path_info.endswith('settings/'):
            # Settings page
            (mime_type, response) = self.settings_page()

        elif path_info.endswith('cache.json'):
            # Cache status as JSON
            
            length = int(environ.get('CONTENT_LENGTH', '0'))
            qs = environ['wsgi.input'].read(length)
            q = parse_qs(qs)
            
            mime_type = 'application/json'
            response = json.dumps(
                {
                  'data': self._data_cache.list(),
                  'mapfile': self._map_cache.list()
                }
            )

        elif path_info.endswith('settings.json'):
            # Settings as JSON
            mime_type = 'application/json'
            response = str(self.settings_dict())

        elif path_info.endswith('cache/'):
            # Cache control via request
            mime_type = 'application/json'
            key = query['key'][0] if query.has_key('key') else False
            if key == self._key:
                try:
                    data = query['data'][0] # data parameter is required
                    mapfile = query['mapfile'][0] if query.has_key('mapfile') else None
                    if data or mapfile:
                        if self.clear_cache(data, mapfile):
                            response = json.dumps({'status': 'ok', 'msg': 'Cache cleared'})
                        else:
                            response = json.dumps({'status': 'ok', 'msg': 'Cache empty'})
                except Exception, e:
                    response = json.dumps({'status': 'exception', 
                      'msg': 'Data parameter missing'})
            else:
                response = json.dumps({'status': 'exception', 
                  'msg': 'Key empty or incorrect.'})
            
        elif not path_info.strip('/'):
            # Homepage
            mime_type = 'text/html'
            root = '%s%s' % (environ['SCRIPT_NAME'], path_info.strip('/'))
            response = '''<h2>TileLite</h2>
            <div><p>Welcome, ready to accept a tile request in the format of %(root)s/zoom/x/y.png</p>
            <p>url: <a href="%(root)s/1/0/0.png">%(root)s/1/0/0.png</a></p>
            <p>js: var tiles = new OpenLayers.Layer.OSM("Mapnik", "http://%(http_host)s/${z}/${x}/${y}.png");</p>
            <p>See TileLite settings: <a href="%(root)s/settings/">%(root)s/settings/</a>
            | <a href="%(root)s/settings.json">%(root)s/settings.json</a></p>
            <p> More info: <a href="http://bitbucket.org/springmeyer/tilelite/">
            bitbucket.org/springmeyer/tilelite/</a></p></div>
            ''' % {'root': root,'http_host':environ['HTTP_HOST']}
        else:
            response = '<h1> Page Not found </h1>'
            response_status = "404 Not Found"
             
        if not already_sent:
            start_response(response_status, [('Content-Type', mime_type)])
            yield response

if __name__ == '__main__':
    import doctest
    doctest.testmod()
