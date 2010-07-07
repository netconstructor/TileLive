import os
import base64
import urllib2
import fnmatch
import zipfile
import mapnik
import shutil
import cascadenik

"""

Cache backend for TileLive. Includes a MapCache backend for mapfiles,
and a DataCache backend for data files. Static cache of 10 each, plus 
non-managed file cache of all files of each.

"""
 
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

class MapCache(TLCache):
    """ mapfile and mapnik map cache """
    def __init__(self, **kwargs):
        self.directory = kwargs['directory']
        self.mapnik_maps = {}
        self.size = kwargs.get('size', 10)
        self.tilesize = kwargs.get('tilesize', 256)
        if not os.path.isdir(self.directory): os.mkdir(self.directory)

    def get(self, url):
        """ get a mapnik.Map object from a URL of a map.xml file, 
        regardless of cache status """
        if not self.mapnik_maps.has_key(url):
            self.mapnik_maps[url] = mapnik.Map(self.tilesize, self.tilesize)
            open("%s_compiled.xml" % self.filecache(url), 'w').write(cascadenik.compile(self.filecache(url), urlcache=True))
            mapnik.load_map(self.mapnik_maps[url], "%s_compiled.xml" % self.filecache(url))
        return self.mapnik_maps[url]
    
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
