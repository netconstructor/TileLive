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

* Python 2.5 - 2.7
* **Mapnik 2** is **required** to use the metawriter functionality in this branch.
* [Cascadenik](http://code.google.com/p/mapnik-utils/wiki/Cascadenik)
 * [Mac OSX Installers](http://dbsgeo.com/downloads/)
 * [Installation on Linux](http://trac.mapnik.org/wiki/LinuxInstallation)

For deployment, running a fast server like [Nginx](http://nginx.org/) in front of TileLite to serve static files is highly recommended.

## Installation and Running

1. Download or git clone TileLive
2. `python setup.py install`
3. Run `liveserv.py` in your Terminal

## Mapfiles

TileLiteLive has some expectations about provided mapfiles, given the great variety of mapfiles possible with Mapnik and its demands upon how data is handled.

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
