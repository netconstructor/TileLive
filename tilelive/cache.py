import os
import base64
import urllib2
import urllib
import urlparse
import fnmatch
import zipfile
import mapnik
import shutil
import cascadenik
import tornado.httpclient
import tempfile
import time

"""

Cache backend for TileLive. Includes a MapCache backend for mapfiles,
and a DataCache backend for data files. Static cache of 10 each, plus 
non-managed file cache of all files of each.

"""

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
 
def locate(pattern, root=os.curdir):
   """ find a file in a directory and its subdirectories """
   for path, dirs, files in os.walk(os.path.abspath(root)):
       for filename in fnmatch.filter(files, pattern):
           yield os.path.join(path, filename)

class TLCache(object):
    """ base cache object for TileLite """
    def __init__(self, **kwargs):
        self.directory = kwargs.get('directory', '')
        if not os.path.isdir(self.directory): os.mkdir(self.directory)

    def url2fs(self, url):
        """ encode a URL to be safe as a filename """
        uri, extension = os.path.splitext(url)
        return base64.urlsafe_b64encode(uri) + extension

    def fs2url(self, url):
        """ decode a filename to the URL it is derived from """
        return base64.urlsafe_b64decode(url)

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

"""
PreCache handler for TL. Provides an asynchronous queue of shapefile requests
corresponding to a given map. Once all shapefile requests have been made and
unzipped, the callback function at PreCache.execute(callback) is called. A
shared locking mechanism can be passed such that concurrent requests do not
simultaneously download the same remote resources.
"""
class PreCache(TLCache):
    def __init__(self, **kwargs):
        self.locks = kwargs['locks']
        self.directory = kwargs['directory']
        self.request_handler = kwargs['request_handler']
        self.requests = []
        self.callback = None
        self.kwargs = None
        self.completed = 0
        if not os.path.isdir(self.directory): os.mkdir(self.directory)

    """ add a request to the queue """
    def add(self, url):
        self.requests.append(url)

    """ execute all requests and fire callback once completed """
    def execute(self, callback, **kwargs):
        self.callback = callback
        self.kwargs = kwargs
        for url in self.requests:
            base_dir = os.path.join(self.directory, base64.urlsafe_b64encode(url))
            if os.path.isdir(base_dir):
                self.completed = self.completed + 1
            else:
                if not self.locks.has_key(url):
                    self.locks[url] = True
                    http = tornado.httpclient.AsyncHTTPClient()
                    http.fetch(url, callback=self.cache)
                else:
                    self.standby(url, **self.kwargs);
        if self.completed == len(self.requests):
            self.callback(**self.kwargs)

    """ standby while a request is locked. once the resource has been downloaded
        the lock is released and we can proceed. """
    def standby(self, locked_url, **kwargs):
        if self.locks.has_key(locked_url):
            if self.locks[locked_url] is True:
                print "Locked: " + locked_url
                tornado.ioloop.IOLoop.instance().add_timeout(time.time() + 2, lambda: self.standby(locked_url, **kwargs))
            else:
                self.request_handler.finish()
                return
        else:
            print "Unlocked: " + locked_url
            self.completed = self.completed + 1
            if self.completed == len(self.requests):
                self.callback(**kwargs)

    """ asynchttp request callback. caches the downloaded zipfile. """
    def cache(self, response):
        import StringIO, zipfile
        try:
            zip_file = zipfile.ZipFile(StringIO.StringIO(response.body))
            infos = zip_file.infolist()
            extensions = [os.path.splitext(info.filename)[1] for info in infos]
            basenames = [os.path.basename(info.filename) for info in infos]

            base_dir = os.path.join(self.directory, base64.urlsafe_b64encode(response.effective_url))
            if not os.path.isdir(base_dir):
                os.mkdir(base_dir)
                # Caching only requires that .shp is present
                for (expected, required) in (('.shp', True), ('.shx', False), ('.dbf', False), ('.prj', False)):
                    if required and expected not in extensions:
                        raise Exception('Zip file %(shapefile)s missing extension "%(expected)s"' % locals())
                    for (info, extension, basename) in zip(infos, extensions, basenames):
                        if extension == expected:
                            file_data = zip_file.read(info.filename)
                            file_name = os.path.normpath('%(base_dir)s/%(basename)s' % locals())
                            file = open(file_name, 'wb')
                            file.write(file_data)
                            file.close()
        except:
            self.locks[response.effective_url] = False
            self.request_handler.finish()
            return
        self.completed = self.completed + 1
        del self.locks[response.effective_url]
        if self.completed == len(self.requests):
            self.callback(**self.kwargs)

class MapCache(TLCache):
    """ mapfile and mapnik map cache """
    def __init__(self, **kwargs):
        self.directory = kwargs['directory']
        self.mapnik_maps = {}
        self.size = kwargs.get('size', 10)
        self.tilesize = kwargs.get('tilesize', 256)
        self.locks = {}
        if not os.path.isdir(self.directory): os.mkdir(self.directory)

    def compile(self, url, compile_callback):
        self.mapnik_maps[url] = mapnik.Map(self.tilesize, self.tilesize)
        open("%s_compiled.xml" % self.filecache(url), 'w').write(cascadenik.compile(self.filecache(url), urlcache=True))
        mapnik.load_map(self.mapnik_maps[url], "%s_compiled.xml" % self.filecache(url))
        compile_callback(self.mapnik_maps[url])

    def get(self, url, request_handler, callback):
        """ get a mapnik.Map object from a URL of a map.xml file, 
        regardless of cache status """
        if not self.mapnik_maps.has_key(url):
            precache = PreCache(directory=tempfile.gettempdir(), request_handler=request_handler, locks=self.locks)
            doc = ElementTree.parse(urllib.urlopen(self.filecache(url)))
            map = doc.getroot()
            for layer in map.findall('Layer'):
                for parameter in layer.find('Datasource').findall('Parameter'):
                    if parameter.get('name', None) == 'file':
                        (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(parameter.text)
                        if scheme != '':
                            precache.add(parameter.text)
            precache.execute(self.compile, url=url, compile_callback=callback)
        else:
            callback(self.mapnik_maps[url])

    def remove(self, url):
        """ remove a map file, object and associated tiles from the cache """
        try:
            # Remove the data files
            shutil.rmtree(os.path.join(self.directory, 
                url))

            # remove the object
            if self.mapnik_maps.has_key(url):
                del self.mapnik_maps[url]


        except Exception, e:
            return False

    def list(self):
        """ return a list of cached URLs """
        return map(self.fs2url, 
              [x for x in os.listdir(self.directory) if 
                os.path.isfile(os.path.join(self.directory, x))]
          )
