import base64, os

"""
simulate an unlimited-length kv store using normal directories
"""

def key(base):
    """ get a list of all *leaf* directories as strings

    >>> list(key('/tmp/this/'))
    ['is/a/test/for/dirs']
    """
    for root, dirs, files in os.walk(base, topdown=False):
        for file in files:
            yield os.path.join(root, file)
            # if root != base and root != dir:
            #     yield os.path.join(root, dir)

def chunk(url):
    """ create filesystem-safe places for url-keyed data to be stored
    
    >>> chunk('test')
    ['dGVzdA==']
    >>> k = chunk('http://tilemill.s3.amazonaws.com/x86_64-1.9.part.86?AWSAccessKeyId=11YC4XXY9VV9X7K5F9G2&Expires=1378620506&Signature=DWXVChV4qYgkPyp5tjLD1Rc8XdIDWXVChV4qYgkPyp5tjLD1Rc8XdI%3DDWXVChV4qYgkPyp5tjLD1Rc8XdI%3D')
    >>> k
    ['aHR0cDovL3RpbGVtaWxsLnMzLmFtYXpvbmF3cy5jb20veDg2XzY0LTEuOS5wYXJ0Ljg2P0FXU0FjY2Vzc0tleUlkPTExWUM0WFhZOVZWOVg3SzVGOUcyJkV4cGlyZXM9MTM3ODYyMDUwNiZTaWduYXR1cmU9RFdYVkNoVjRxWWdrUHlwNXRqTEQxUmM4WGRJRFdYVkNoVjRxWWdrUHlwNXRqTEQxUmM4WGRJJTNERFdYVkNoVjRxWWdrUHlwNXR', 'qTEQxUmM4WGRJJTNE']
    >>> len(k[0]) == 255
    True
    """
    chunks = lambda l, n: [l[x: x+n] for x in xrange(0, len(l), n)]
    url_64 = base64.urlsafe_b64encode(url)
    return chunks(url_64, 25)

def dir(url):
    """ use safe64 to create a proper directory

    >>> dir('http://tilemill.s3.amazonaws.com/x86_64-1.9.part.86?AWSAccessKeyId=11YC4XXY9VV9X7K5F9G2&Expires=1378620506&Signature=DWXVChV4qYgkPyp5tjLD1Rc8XdIDWXVChV4qYgkPyp5tjLD1Rc8XdI%3DDWXVChV4qYgkPyp5tjLD1Rc8XdI%3D')
    'aHR0cDovL3RpbGVtaWxsLnMzLmFtYXpvbmF3cy5jb20veDg2XzY0LTEuOS5wYXJ0Ljg2P0FXU0FjY2Vzc0tleUlkPTExWUM0WFhZOVZWOVg3SzVGOUcyJkV4cGlyZXM9MTM3ODYyMDUwNiZTaWduYXR1cmU9RFdYVkNoVjRxWWdrUHlwNXRqTEQxUmM4WGRJRFdYVkNoVjRxWWdrUHlwNXRqTEQxUmM4WGRJJTNERFdYVkNoVjRxWWdrUHlwNXR/qTEQxUmM4WGRJJTNE'
    """
    return "/".join(chunk(url))

def decode(url):
    """ use safe64 to create a proper directory

    >>> decode('aHR0cDovL3RpbGVtaWxsLnMzLmFtYXpvbmF3cy5jb20veDg2XzY0LTEuOS5wYXJ0Ljg2P0FXU0FjY2Vzc0tleUlkPTExWUM0WFhZOVZWOVg3SzVGOUcyJkV4cGlyZXM9MTM3ODYyMDUwNiZTaWduYXR1cmU9RFdYVkNoVjRxWWdrUHlwNXRqTEQxUmM4WGRJRFdYVkNoVjRxWWdrUHlwNXRqTEQxUmM4WGRJJTNERFdYVkNoVjRxWWdrUHlwNXR/qTEQxUmM4WGRJJTNE')
    """
    return base64.urlsafe_b64decode(url.replace('/', ''))

if __name__ == "__main__":
    import doctest
    doctest.testmod()
