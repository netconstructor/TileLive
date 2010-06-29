#!/usr/bin/env python

import os
import sys
import socket
from optparse import OptionParser
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler

CONFIG = 'tilelite.cfg'
MAP_FROM_ENV = 'MAPNIK_MAP_FILE'
    
parser = OptionParser(usage="""
    python liteserv.py [options]
    """)

parser.add_option('-i', '--ip', default='0.0.0.0', dest='host',
    help='Specify a ip to listen on (defaults to 0.0.0.0/localhost)'
    )

parser.add_option('-p', '--port', default=8000, dest='port', type='int',
    help='Specify a custom port to run on: eg. 8080'
    )

parser.add_option('--config', default=None, dest='config',
    help='''Specify the use of a custom TileLite config file to override default settings. By default looks for a file locally called 'tilelite.cfg'.'''
    )

parser.add_option('-s', '--size', default=None, dest='size', type='int',
    help='Specify a custom tile size (defaults to 256)'
    )

parser.add_option('-b', '--buffer-size', default=None, dest='buffer_size', type='int',
    help='Specify a custom map buffer_size (defaults to 128)'
    )

parser.add_option('-z', '--max-zoom', default=None, dest='max_zoom', type='int',
    help='Max zoom level to support (defaults to 22)'
    )
    
parser.add_option('-f', '--format', default=None, dest='format',
    help='Specify a custom image format (png or jpeg) (defaults to png)'
    )

parser.add_option('--paletted', default=False, dest='paletted', action='store_true',
    help='Use paletted/8bit PNG (defaults to False)'
    )

parser.add_option('-d','--debug', default=True, dest='debug', action='store_true',
    help='Run in debug mode (defaults to True)'
    )

parser.add_option('-c','--caching', default=False, dest='caching', action='store_true',
    help='Turn on tile caching mode (defaults to False)'
    )

parser.add_option('--cache-path', default=None, dest='cache_path',
    help='Path to tile cache directory (defaults to "/tmp")'
    )

parser.add_option('--cache-force', default=False, dest='cache_force', action='store_true',
    help='Force regeneration of tiles while in caching mode (defaults to False)'
    )

def run(process):
    try:
        process.serve_forever()
    except KeyboardInterrupt:
        process.server_close()
        sys.exit(0)

def strip_opts(options):
    remove = [None,'config','port','host']
    params = {}
    for k,v in options.items():
        if not k in remove and not v is None:
            params[k] = v
    return params

if __name__ == '__main__':
    (options, args) = parser.parse_args()
        
    print "[TileLite Debug] --> Started without Mapfile"
        
    if options.config:
        if not os.path.isfile(options.config):
            sys.exit('That does not appear to be a valid config file')
        else:
            CONFIG = options.config

    if not os.path.exists(CONFIG):
        if options.config:
            sys.exit('Could not locate custom config file')
        else:
            CONFIG = None
    
    if CONFIG:
        print "[TileLite Debug] --> Using config file: '%s'" % os.path.abspath(CONFIG)        

    if options.cache_path and not options.caching:
        options.caching = True

    if options.cache_force and not options.caching:
        options.caching = True

    #parser.error("Caching must be turned on with '--caching' flag for liteserv.py to accept '--cache-path' option")
    #http_setup = options.host, options.port
    #httpd = simple_server.WSGIServer(http_setup, WSGIRequestHandler)
    #httpd.set_app(application)

    from tilelite.server import Server
    application = Server(CONFIG)
    application.absorb_options(strip_opts(options.__dict__))
    
    httpd = make_server(options.host, options.port, application)
    print "Listening on %s:%s..." % (options.host,options.port)
    print "To access locally view: http://localhost:%s" % options.port
    remote = "To access remotely view: http://%s" % socket.getfqdn()
    if not options.port == 80:
        remote += ":%s" % options.port
    print remote
    if not application.debug:
        print 'TileLite debug mode is *off*...'
    
    run(httpd)
