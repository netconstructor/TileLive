# TileLite

An ultra lightweight Mapnik tile-server written as a WSGI (Web Server Gateway Interface) application.

This is a branch of TileLite - it significantly changes the way that tiles are requested and data is stored. The main TileLite branch works as a traditional tile server - the user specifies a Mapnik XML file or Cascadenik file at startup and datasources are initialized at that point.

In contrast, this branch doesn't require a mapping server to intially contain any layer configuration, data, or mapfiles. Instead, the data and mapfile for each request is specified *within the tile URL*. Performance is ensured by caching, so that tile requests of this type are typically as fast as the other system, and further performance tweaks make this branch faster in certain cases. However, it is necessary to underline the fact that the schemes for requesting tiles for the two applications are different and incompatible.

## Caching

From the client perspective, this branch of TileLite could be re-requesting data and mapfiles for each request. The caching system is written so that clients can make this assumption and the server will respond correctly to each request. In order to do this, there's a multi-layered caching system that reflects the performance hit of types of refetching. From the outside in, a tile request will hit the following caches:

1. **Tile cache** Once tiles are rendered and served to the client, they're saved as files on the local filesystem. From this point, it's strongly recommended that *another server* serves from this cache, in the style of [StaticGenerator](http://superjared.com/projects/static-generator/). This way, Python is not invoked for extremely lightweight requests in which it needs to open a file and deliver it to the client, but a faster server can do this and only hit Python when it needs to render a tile.
2. **Map and Data static cache** Rendering a map with Mapnik involves creating Mapnik objects that wrap datasources and mapfiles. This version of TileLite makes sure that the initialization time for these objects, which can be significant, is not a hit on performance for every tile request. As such, it maintains a [FIFO](http://en.wikipedia.org/wiki/FIFO) cache of `Mapnik.Datasource` and `Mapnik.Map` objects. This cache is small - it only contains 10 objects of each type. The intent is not to thoroughly cache such objects, but to take care of situations in which multiple maps are being requested simultaneously. This cache stays small, as well, because it is in memory and TileLite doesn't aim to do memory management.
3. **Map and Data file cache** Map XML and Data files are cached locally by Mapnik. They are only removed when the cache is manually cleared by an authorized client - given the size of the files, it's unlikely that these files will fill a disk.

## Requires

This software is unsupported on Windows

* Python 2.5 or 2.6
* Mapnik (>= 0.6.0)
 * [Mac OSX Installers](http://dbsgeo.com/downloads/)
 * [Installation on Linux](http://trac.mapnik.org/wiki/LinuxInstallation)

For deployment, running a fast server like [Nginx](http://nginx.org/) in front of TileLite to serve static files is highly recommended.

## Installation and Running

1. Download or git clone TileLive
2. `python setup.py install`
3. `liveserv.py`

## Integration

The [StyleWriter](http://github.com/tmcw/stylewriter) Drupal module provides integration with TileLite, both for generating mapfiles handling tiles. Any system capable of base64-encoding can be used with this tile layout scheme.

## Seeding

This branch of TileSeed includes a very simple, restricted seeding script. The 
script has no external dependencies and uses four threads to make requests 
faster when servers have multiple TileLite threads running as well. The script, 
`tileseed.py` is also made to integrate with the StyleWriter module.

## References

[1] If you need to WMS, TMS, seeding, or custom projection support TileCache is awesome (http://tilecache.org/)

[2] If you need server queuing, threading, and expiry support use the powerful Mod_tile (http://wiki.openstreetmap.org/wiki/Mod_tile)

[3] http://svn.openstreetmap.org/applications/rendering/mapnik/generate_tiles.py
