#!/usr/bin/python

from math import pi,cos,sin,log,exp,atan
from subprocess import call
import sys, os
from optparse import OptionParser
from Queue import Queue
import threading
from base64 import urlsafe_b64encode
from urlparse import urlparse
import httplib, time

"""

  A HTTP-based seeding script based on code from generate_tiles.py

"""

DEG_TO_RAD = pi/180
RAD_TO_DEG = 180/pi

# Default number of rendering threads to spawn, should be roughly equal to number of CPU cores available
NUM_THREADS = 4


def minmax (a,b,c):
    a = max(a,b)
    a = min(a,c)
    return a

class GoogleProjection:
    def __init__(self,levels=18):
        self.Bc = []
        self.Cc = []
        self.zc = []
        self.Ac = []
        c = 256
        for d in range(0,levels):
            e = c/2;
            self.Bc.append(c/360.0)
            self.Cc.append(c/(2 * pi))
            self.zc.append((e,e))
            self.Ac.append(c)
            c *= 2
                
    def fromLLtoPixel(self, ll, zoom):
         """ given a latitude and longitude and zoom level, return tuple of x, y """
         d = self.zc[zoom]
         e = round(d[0] + ll[0] * self.Bc[zoom])
         f = minmax(sin(DEG_TO_RAD * ll[1]),-0.9999,0.9999)
         g = round(d[1] + 0.5*log((1+f)/(1-f))*-self.Cc[zoom])
         return (e,g)
     
    def fromPixelToLL(self, px, zoom):
         """ given a pixel and zoom level, return lat, lon tuple """
         e = self.zc[zoom]
         f = (px[0] - e[0])/self.Bc[zoom]
         g = (px[1] - e[1])/-self.Cc[zoom]
         h = RAD_TO_DEG * ( 2 * atan(exp(g)) - 0.5 * pi)
         return (f,h)

class RenderThread:
    def __init__(self, data, mapfile, url, q, printLock, maxZoom):
        self.q = q
        self.printLock = printLock
        # Load style XML
        # Projects between tile pixel co-ordinates and LatLong (EPSG:4326)
        self.tileproj = GoogleProjection(maxZoom+1)

    def timed_transfer(self, path):
        """ test a transfer by loading a file but not downloading it to anywhere """
        pts = urlparse(path)
        conn = httplib.HTTPConnection(pts.hostname, pts.port)
        start = time.time()  
        conn.request('GET', pts.path)
        request_time = time.time()
        resp = conn.getresponse()
        response_time = time.time()
        conn.close()     
        print "%s took %.5f" % (path, (response_time - start))

    def loop(self):
        """ iterate through all necessary tiles, running timed_transfer for each """
        while True:
            #Fetch a tile from the queue and render it
            r = self.q.get()
            if (r == None):
                self.q.task_done()
                break
            else:
                (tile_uri, x, y, z) = r
            self.timed_transfer(tile_uri)
            self.q.task_done()

def render_tiles(bbox, minZoom,maxZoom, data, mapfile, url):
    print "render_tiles(",bbox, data, mapfile, url, ")"

    # Launch rendering threads
    queue = Queue(32)
    printLock = threading.Lock()
    renderers = {}
    for i in range(NUM_THREADS):
        renderer = RenderThread(data, mapfile, url, queue, printLock, maxZoom)
        render_thread = threading.Thread(target=renderer.loop)
        render_thread.start()
        #print "Started render thread %s" % render_thread.getName()
        renderers[i] = render_thread

    gprj = GoogleProjection(maxZoom+1) 

    ll0 = (bbox[0],bbox[3])
    ll1 = (bbox[2],bbox[1])

    for z in range(minZoom,maxZoom + 1):
        px0 = gprj.fromLLtoPixel(ll0,z)
        px1 = gprj.fromLLtoPixel(ll1,z)

        # check if we have directories in place
        for x in range(int(px0[0]/256.0),int(px1[0]/256.0)+1):
            # Validate x co-ordinate
            if (x < 0) or (x >= 2**z):
                continue
            # check if we have directories in place
            for y in range(int(px0[1]/256.0),int(px1[1]/256.0)+1):
                # Validate x co-ordinate
                if (y < 0) or (y >= 2**z):
                    continue
                tile_uri = "%s/%s/%s/%d/%d/%d.png" % (
                        url.rstrip('/'),
                        urlsafe_b64encode(options.data),
                        urlsafe_b64encode(options.mapfile),
                        z,
                        x,
                        y)
                # Submit tile to be rendered into the queue
                t = (tile_uri, x, y, z)
                queue.put(t)

    # Signal render threads to exit by sending empty request to queue
    for i in range(NUM_THREADS):
        queue.put(None)
    # wait for pending rendering jobs to complete
    queue.join()
    for i in range(NUM_THREADS):
        renderers[i].join()

if __name__ == "__main__":
    """ run as a command-line tool """

    parser = OptionParser(usage="""%prog [options] [zoom...]""", version='0.1.3.1')
    parser.add_option('-d', '--data', dest='data',
                  help='Data URL')

    parser.add_option('-m', '--mapfile', dest='mapfile',
                      help='Mapfile URL')

    parser.add_option('-u', '--url', dest='url',
                      help='Map Server Base URL')

    parser.add_option('-b', '--bbox', dest='bbox',
                      help='Bounding box in floating point geographic coordinates: south west north east.',
                      type='float', nargs=4)

    parser.add_option('-e', '--extension', dest='extension',
                      help='Optional file type for rendered tiles. Default value is "png".')

    options, zooms = parser.parse_args()

    if options.data and options.url and options.extension:
        bbox = (-180.0,-90.0, 180.0,90.0)
        render_tiles(bbox, int(zooms[0]), int(zooms[1]), options.data, options.mapfile, options.url)
    else:
        parser.error("required arguments missing")
