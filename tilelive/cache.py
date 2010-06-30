import os, base64, urllib2, fnmatch, zipfile, mapnik, shutil

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
            mapnik.load_map(self.mapnik_maps[url], self.filecache(url))
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
              [x for x in os.listdir(self.directory) if os.path.isfile(os.path.join(self.directory, x))]
          )

class DataCache(TLCache):
    """ datasource cache """
    def __init__(self, **kwargs):
        self.directory = kwargs['directory']
        self.data_sources = {}
        self._data_sources = []
        self.size = kwargs.get('size', 10)

        if not os.path.isdir(self.directory): os.mkdir(self.directory)
        
    def get(self, url):
        """ get a datasource object, regardless of whether it is pre-cached """
        if not self.data_sources.has_key(url):
            if len(self._data_sources) == self.size:
                del self.data_sources[self._data_sources.pop()]
            self.data_sources[url] = self.dscache(url)
            self._data_sources.insert(0, url)
        return self.data_sources[url]

    def clear(self, url):
        """ remove a file, object and its associated tiles from the cache """
        try:
            # Remove the data files
            shutil.rmtree(os.path.join(self.directory, 
                url))

            # remove the list entry for fifo
            if url in self._data_sources:
                self._data_sources.remove(url)

            # remove the object
            if self.data_sources.has_key(url):
                del self.data_sources[url]

        except Exception, e:
            return False
        
    def list(self):
        """ get a list of cached urls """
        return map(self.fs2url, 
          [x for x in os.listdir(self.directory) if 
            os.path.isdir(os.path.join(self.directory, x))])

    def dscache(self, url):
        """ get a mapnik.Shapefile from a URL """
        local_path = self.filecache(url)
        return mapnik.Shapefile(file=self.shpzip(local_path))
         
    def shpzip(self, local_path):
        """ given local path of zipfile, return location of shapefile """
        dir = local_path + "_unzip"
        if not os.path.isdir(dir):
            self.unzip_file_into_dir(local_path, dir)
        shapefiles = list(locate("*.shp", dir))
        if len(shapefiles) > 0:
            return shapefiles[0]
            
    def unzip_file_into_dir(self, file, dir):
        """ unzip a file into a directory """
        os.mkdir(dir, 0777)
        zfobj = zipfile.ZipFile(file)
        for name in zfobj.namelist():
            if name.endswith('/'):
                os.mkdir(os.path.join(dir, name))
            else:
                outfile = open(os.path.join(dir, name), 'wb')
                outfile.write(zfobj.read(name))
                outfile.close()
