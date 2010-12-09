# TileLive

_This is a branch of TileLite - it significantly changes the way that tiles are requested and data is stored. The main TileLite branch works as a traditional tile server - the user specifies a Mapnik XML file or Cascadenik file at startup and datasources are initialized at that point._

In contrast, this branch doesn't require a mapping server to intially contain any layer configuration, data, or mapfiles. Instead, the data and mapfile for each request is specified *within the tile URL*. Performance is ensured by caching, so that tile requests of this type are typically as fast as the other system, and further performance tweaks make this branch faster in certain cases. However, it is necessary to underline the fact that the schemes for requesting tiles for the two applications are different and incompatible.

## Caching

From the client perspective, this branch of TileLite could be re-requesting data and mapfiles for each request. The caching system is written so that clients can make this assumption and the server will respond correctly to each request. In order to do this, there's a multi-layered caching system that reflects the performance hit of types of refetching. From the outside in, a tile request will hit the following caches:

1. **Tile cache** Once tiles are rendered and served to the client, they're saved as files on the local filesystem. From this point, it's strongly recommended that *another server* serves from this cache, in the style of [StaticGenerator](http://superjared.com/projects/static-generator/). This way, Python is not invoked for extremely lightweight requests in which it needs to open a file and deliver it to the client, but a faster server can do this and only hit Python when it needs to render a tile.
2. **Map and Data static cache** Rendering a map with Mapnik involves creating Mapnik objects that wrap datasources and mapfiles. This version of TileLite makes sure that the initialization time for these objects, which can be significant, is not a hit on performance for every tile request. As such, it maintains a [FIFO](http://en.wikipedia.org/wiki/FIFO) cache of `Mapnik.Datasource` and `Mapnik.Map` objects. This cache is small - it only contains 10 objects of each type. The intent is not to thoroughly cache such objects, but to take care of situations in which multiple maps are being requested simultaneously. This cache stays small, as well, because it is in memory and TileLite doesn't aim to do memory management.
3. **Map and Data file cache** Map XML and Data files are cached locally by Mapnik. They are only removed when the cache is manually cleared by an authorized client - given the size of the files, it's unlikely that these files will fill a disk.

## Caching Strategy

* Tile request initially hits `TileHandler.get()`, which is decorated by `@tornado.web.asynchronous`, which ensures that the connection is not automatically closed when the method returns.
* `TileHandler.get()` returns None, but calls `_map_cache.get()` with a callback to `TileHandler.async_get()`.
* If the map is *static-cached*, and exists in `self.mapnik_maps`, `TileHandler.async_get()` is immediately triggered with that map.
* Otherwise, a new `PreCache` object is initialized for this map file alone. The initial callback to `TileHandler.async_get()` is thus passed down to `PreCache.execute()`
* `PreCache.execute()` calls `PreCache.process_request()` for each shapefile, which uses Tornado's async download procedure. It runs itself in a timeout-loop while files are still downloading.
* When all download locks are cleared, `PreCache.execute()` is called again, and calls its callback, which is async_get, which finally renders the map with the given `mapnik_map` value.


    

        req -> TileHandler.get() -> _map_cache.get() -> TileHandler.async_get() -> PreCache.execute() ->
                    ^ keeps open connection

        PreCache.process_request() -> TileHandler.async_get() -> render & self.finish()
               ^ timeout loop 

## Resources

### Tiles

    http://toomanypets.com/{base64-encoded mapfile url}/{z}/{x}/{y}.png

### Data Tiles

    http://toomanypets.com/{base64-encoded mapfile url}/{z}/{x}/{y}.json

### Grid Tiles

    http://toomanypets.com/{base64-encoded mapfile url}/{z}/{x}/{y}.grid.json

### Data fields

    http://toomanypets.com/{base64-encoded mapfile url}/fields.json

## Requires

This software is unsupported on Windows

* Python 2.5 - 2.7 with cssutils, pil and pycurl.
* [Tornado](http://www.tornadoweb.org/documentation#download)
* **Mapnik 2** is **required** to use the metawriter functionality in this branch.

        svn checkout -r2301 http://svn.mapnik.org/trunk

* [Cascadenik](https://github.com/mapnik/Cascadenik/wiki/Cascadenik)

        svn checkout -r1044 http://mapnik-utils.googlecode.com/svn/trunk/serverside/cascadenik

* [Mac OSX Installers](http://dbsgeo.com/downloads/) | [Mac OSX from source](http://trac.mapnik.org/wiki/MacInstallation/Source)
* [Installation on Linux](http://trac.mapnik.org/wiki/LinuxInstallation)

For deployment, running a fast server like [Nginx](http://nginx.org/) in front of TileLite to serve static files is highly recommended.

### Building Mapnik 2

Using [Mapnik 2](http://trac.mapnik.org/wiki/Mapnik2) means using subversion `trunk` and compiling it yourself. There are not binary installers available yet for Mapnik 2. After running `scon.py configure` by sure that `gdal` is listing as an `INPUT_PLUGIN` (you may need to add it manually) in config.py. You'll want a line like:. 

>  INPUT_PLUGINS = 'gdal,ogr,postgis,raster,shape'

### Using MacPorts

Using MacPorts to build and install Tilelive's dependencies is possible, but there are a few things to watch out for.

* Be sure you compile Boost with the bindings for Python, ICU and Regex. You can use a command like `port install boost +python26+icu+regex` to do this.
* MacPorts makes the Python `easy_install` utility available in the package `py26-setuptools`, but sure to install that and specify `easy_install-2.6` when using it to install software.

## Installation and Running

1. Download or git clone TileLive
2. `python setup.py install`
3. Run `liveserv.py` in your Terminal

## Running in Production

Typically TileLive in production typically means running it in a more complex stack than simply `liveserv`'ing. A setup looks like

1. Nginx frontend, with a config similar to the one in sample_configuration. This will round-robin distribute requests across 4 TileLive backends
2. TileLive backends, managed by [supervisord](http://supervisord.org/) or similar, running on a range of ports, like 8000-8003.
3. Disk cache, in a mounted partition or `/tmp`

### Clearing caches

It occasionally becomes necessary to clear different kinds of caches:

* Tile cache, if data/style is updated and tiles are cached. This can be cleared selectively by mapfile / domain. For instance, if you want to clear all tiles generated from a certain mapfile, find the mapfile part of their url, and `rm -rf /mnt/cache/tile/{that mapfile url}`
* Mapfile cache, if mapfiles are updated
* Static caches
* Data cache, if downloaded data is invalid. However, it's more preferable to update the URL of now-resolving data, rather than resolve bad data.

## Mapfiles

TileLive has some expectations about provided mapfiles, given the great variety of mapfiles possible with Mapnik and its demands upon how data is handled.

In order to support data tiles (enabled whenever `--tile_cache` is set), the mapfile must contain a valid MetaWriter entry

    <MetaWriter 
        name="metawriter" 
        only-nonempty="false"
        type="point" 
        file="[tile_dir]/[z]/[x]/[y].json" />

The only support value of `type` is `point` and the only supported value of `file` is `[tile_dir]/[z]/[x]/[y].json` as shown.

Mapfiles should specify a map in EPSG:900913 projection. Support of datasources in mapfiles is dependent upon the version of Cascadenik.

## Runtime options

    --buffer_size                    mapnik buffer size
    --geojson                        allow output of GeoJSON
    --inspect                        open inspection endpoints for data
    --port                           run on the given port
    --tile_cache                     enable development tile cache
    --tilesize                       the size of generated tiles

## Integration

The [StyleWriter](http://github.com/tmcw/stylewriter) Drupal module provides integration with TileLite, both for generating mapfiles handling tiles. Any system capable of base64-encoding can be used with this tile layout scheme. This module, as well as Drupal itself, are by no means required for TileLive operation; it can be used with any client that provides mapfiles and uses a map display library compatible with the XYZ/OSM specification. 

## Seeding

This branch of TileSeed includes a very simple, restricted seeding script. The 
script has no external dependencies and uses four threads to make requests 
faster when servers have multiple TileLite threads running as well. The script, 
`tileseed.py` is also made to integrate with the StyleWriter module.
