#!/usr/bin/env python

import os, time, copy,tempfile, urllib2, urlparse
import zipfile, shutil, logging
import tornado, StringIO

import cascadenik
import tornado.httpclient
import safe64

try:
    import mapnik2 as mapnik
except ImportError:
    import mapnik

try:
    import lxml.etree as ElementTree
    from lxml.etree import Element
except ImportError:
    try:
        import xml.etree.ElementTree as ElementTree
        from xml.etree.ElementTree import Element
    except ImportError:
        import elementtree.ElementTree as ElementTree
        from elementtree.ElementTree import Element

"""

Cache backend for TileLive. Includes a MapCache backend for mapfiles,
and a DataCache backend for data files. Static cache of 10 each, plus 
non-managed file cache of all files of each.

"""

class TLCache(object):
    """ base cache object for TileLite """
    def __init__(self, **kwargs):
        """ init object and ensure that cache dir exists """
        self.directory = kwargs.get('directory', '')
        if not os.path.isdir(self.directory): os.mkdir(self.directory)

    def url2fs(self, url):
        """ encode a URL to be safe as a filename """
        uri, extension = os.path.splitext(url)
        return safe64.dir(uri) + extension

    def fs2url(self, url):
        """ decode a filename to the URL it is derived from """
        return safe64.decode(url)

    def filecache(self, in_url):
        """ given a URL, return a local file path """
        local_url = os.path.join(self.directory, in_url)
        if not os.path.isfile(local_url):
            url = self.fs2url(in_url)
            remote_file = urllib2.urlopen(url)
            output = open(local_url, 'wb')
            output.write(remote_file.read())
            output.close()
        return local_url

class TileCache(TLCache):

    def local_url(self, mapfile, url):
        return os.path.join(self.directory, 
            'tile', 
            mapfile, 
            url)

    def local_dir(self, mapfile, url):
        return os.path.split(self.local_url(mapfile, url))[0]

    def prepare_dir(self, mapfile, url):
        if not os.path.isdir(os.path.split(self.local_url(mapfile, url))[0]):
            os.makedirs(os.path.split(self.local_url(mapfile, url))[0])

    def contains(self, mapfile, url):
        return os.path.isfile(self.local_url(mapfile, url))

    def set(self, mapfile, url, data):
        self.prepare_dir(mapfile, url)
        with open(self.local_url(mapfile, url), 'wb') as output:
            if (data):
                output.write(data)
            return self.local_url(mapfile, url)

    def get(self, mapfile, url):
        with open(self.local_url(mapfile, url), 'r') as f:
            return f.read()

"""
PreCache handler for TL. Provides an asynchronous queue of shapefile requests
corresponding to a given map. Once all shapefile requests have been made and
unzipped, the callback function at PreCache.execute(callback) is called. A
shared locking mechanism can be passed such that concurrent requests do not
simultaneously download the same remote resources.
"""
class PreCache(TLCache):
    def __init__(self, **kwargs):
        self.locks = kwargs.get('locks', [])
        self.directory = kwargs['directory']
        self.request_handler = kwargs['request_handler']
        logging.info('running cache in %s' % self.directory)
        self.queue = []
        self.callback = None
        self.kwargs = None
        if not os.path.isdir(self.directory): os.mkdir(self.directory)

    def add(self, url):
        """ add a request to the queue """
        self.queue.append(url)

    def execute(self, callback, **kwargs):
        """ execute all requests and fire callback once completed """
        self.callback = callback
        self.kwargs = kwargs
        for url in copy.copy(self.queue):
            self.process_request(url)
        if len(self.queue) == 0 and len(self.locks) == 0:
            self.callback(**self.kwargs)

    def process_request(self, request_url):
        # Directory exists, request has already been successfully processed.
        base_dir = os.path.join(self.directory, safe64.dir(request_url))
        if os.path.isdir(base_dir):
            if request_url in self.queue: self.queue.remove(request_url)
            if request_url in self.locks: self.locks.remove(request_url)
        # Request is in queue and not locked. Fire asynchronous HTTP request.
        elif request_url in self.queue and request_url not in self.locks:
            self.queue.remove(request_url)
            self.locks.append(request_url)
            logging.info("Locked: %s", request_url)
            http = tornado.httpclient.AsyncHTTPClient()
            http.fetch(request_url, request_timeout=60, callback=self.cache)
        # Request is in locks. Perform a holding pattern.
        elif request_url in self.locks:
            tornado.ioloop.IOLoop.instance().add_timeout(
                time.time() + 5, lambda: self.process_request(request_url))
        # All queued requests have been processed. Continue to callback.
        if len(self.queue) == 0 and len(self.locks) == 0:
            self.callback(**self.kwargs)
        return

    def unzip_shapefile(self, zipdata, base_dir, request):
        """ unzip a shapefile into a directory, creating the directory
        structure if it doesn't exist """
        # try:
        #     import pylzma
        #     from py7zlib import Archive7z
        #     zip_file = Archive7z(StringIO.StringIO(zipdata))
        #     infos = zip_file.getnames()
        # except ImportError:
        try:
            zip_file = zipfile.ZipFile(StringIO.StringIO(zipdata))
            infos = zip_file.infolist()
        except Exception:
            logging.info('File is not a zipfile')
            if not os.path.isdir(base_dir):
                os.makedirs(base_dir)
            basename = os.path.basename(request.url)
            file_name = os.path.normpath('%(base_dir)s/%(basename)s' % locals())
            file = open(file_name, 'wb')
            file.write(zipdata)
            file.close()
            return

        extensions = [os.path.splitext(info.filename)[1].lower() for info in infos]
        basenames  = [os.path.basename(info.filename).lower() for info in infos]
        # Caching only requires that .shp is present
        for (expected, required) in (('.shp', True), ('.shx', False), ('.dbf', False), ('.prj', False)):
            if required and expected not in extensions:
                raise Exception('Zip file %(shapefile)s missing extension "%(expected)s"' % locals())
            for (info, extension, basename) in zip(infos, extensions, basenames):
                if extension == expected:
                    if not os.path.isdir(base_dir):
                        os.makedirs(base_dir)
                    try:
                        # pylzma
                        file_data = zip_file.getmember(info.filename).read()
                    except:
                        file_data = zip_file.read(info.filename)
                    file_name = os.path.normpath('%(base_dir)s/%(basename)s' % locals())
                    file = open(file_name, 'wb')
                    file.write(file_data)
                    file.close()

    def cache(self, response):
        """ asynchttp request callback. caches the downloaded zipfile. """
        try:
            # Check that the directory does not exist yet, as there *can* be
            # concurrent jobs at this point. Do not actually create the
            # directory until we are sure that a successful shapefile can be
            # extracted from a zip.
            base_dir = os.path.join(self.directory, safe64.dir(response.request.url))
            if not os.path.isdir(base_dir):
                self.unzip_shapefile(response.body, base_dir, response.request)
        except Exception, e:
            logging.info('Failed: %s', response.request.url)
            logging.info('Exception: %s', e)
            if response.request.url in self.locks : self.locks.remove(response.request.url)
            if response.request.url not in self.queue : self.queue.append(response.request.url)
            self.request_handler.finish()
            return
        logging.info("Unlocked: %s", response.request.url)
        if response.request.url in self.locks: self.locks.remove(response.request.url)
        if len(self.queue) == 0 and len(self.locks) == 0:
            self.callback(**self.kwargs)

class MapCache(TLCache):
    """ mapfile and mapnik map cache """
    def __init__(self, **kwargs):
        self.directory = kwargs['directory']
        self.mapnik_maps = {}
        self.mapnik_locks = {}
        self.size = kwargs.get('size', 10)
        self.tilesize = kwargs.get('tilesize', 256)
        if not os.path.isdir(self.directory): os.mkdir(self.directory)

    def compile(self, url, compile_callback):
        """ retrieve and compile a mapnik xml file. only called when the map
        is not already in static cache. calls compile_callback when  """
        self.mapnik_maps[url] = mapnik.Map(self.tilesize, self.tilesize)
        open("%s_compiled.xml" % self.filecache(url), 'w').write(
            cascadenik.compile(self.filecache(url), urlcache=True))
        mapnik.load_map(self.mapnik_maps[url], "%s_compiled.xml" % self.filecache(url))
        compile_callback(self.mapnik_maps[url])

    def mapfile_datasources(self, url):
        """ parse a map.xml file and return the urls of all file-based datasources """
        doc = ElementTree.parse(open(self.filecache(url)))
        map = doc.getroot()
        # ElementTree 1.3 will make this cleaner...
        for layer in map.findall('Layer'):
            type = [p for p in layer.find('Datasource').findall('Parameter') if 'type' in p.keys() and p.get('type', None) != 'shape']
            if len(type) == 0:
                break
            for parameter in layer.find('Datasource').findall('Parameter'):
                if parameter.get('name', None) == 'file':
                    (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(parameter.text)
                    if scheme != '':
                        yield parameter.text

    def get(self, url, request_handler, callback):
        """ get a mapnik.Map object from a URL of a map.xml file, 
        regardless of cache status """
        if not self.mapnik_maps.has_key(url):
            if not self.mapnik_locks.has_key(url):
                self.mapnik_locks[url] = []
            precache = PreCache(directory=tempfile.gettempdir(), 
                request_handler=request_handler, 
                locks=self.mapnik_locks[url])
            [precache.add(ds_url) for ds_url in self.mapfile_datasources(url)]
            precache.execute(self.compile, url=url, compile_callback=callback)
        else:
            callback(self.mapnik_maps[url])

    def remove(self, url):
        """ remove a map file, object and associated tiles from the cache """
        try:
            # remove the object and data files
            if self.mapnik_maps.has_key(url):
                del self.mapnik_maps[url]
            if self.mapnik_locks.has_key(url):
                del self.mapnik_locks[url]
            if os.path.isdir(os.path.join(self.directory, url)):
                shutil.rmtree(os.path.join(self.directory, url))
        except Exception:
            return False

    def list(self):
        """ return a list of cached URLs """
        return map(self.fs2url, 
              [x for x in os.listdir(self.directory) if 
                os.path.isfile(os.path.join(self.directory, x))])

if __name__ == "__main__":
    import doctest
    doctest.testmod()
