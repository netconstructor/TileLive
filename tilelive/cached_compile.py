import cascadenik, os, zipfile, urllib, urlparse, StringIO, tempfile, base64

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


def localize_shapefile(src, shapefile, dir=None, move_local_files=False, **kwargs):
    """ Given a stylesheet path, a shapefile name, and a temp directory,
        modify the shapefile name so it's an absolute path.
    
        Shapefile is assumed to be relative to the stylesheet path.
        If it's found to look like a URL (e.g. "http://...") it's assumed
        to be a remote zip file containing .shp, .shx, and .dbf files.
    """
    (scheme, netloc, path, params, query, fragment) = urlparse.urlparse(shapefile)

    print "Downloading %s" % shapefile

    if move_local_files:
        sys.stderr.write('WARNING: moving local shapefiles not yet supported\n')

    if scheme == '':
        # assumed to be local
        if MAPNIK_VERSION >= 601:
            # Mapnik 0.6.1 accepts relative paths, so we leave it unchanged
            # but compiled file must maintain same relativity to the files
            # as the stylesheet, which needs to be addressed separately
            return shapefile
        else:
            return os.path.realpath(urlparse.urljoin(src, shapefile))

    if kwargs.get('urlcache', None) and os.path.isdir(os.path.join(tempfile.gettempdir(), 
        base64.urlsafe_b64encode(shapefile))):
        b_dir = os.path.join(tempfile.gettempdir(), base64.urlsafe_b64encode(shapefile))
        for root, dirs, files in os.walk(b_dir):
            for file in files:
                if os.path.splitext(file)[1] == '.shp':
                    return os.path.join(root, file[:-4])

    # assumed to be a remote zip archive with .shp, .shx, and .dbf files
    zip_data = urllib.urlopen(shapefile).read()
    zip_file = zipfile.ZipFile(StringIO.StringIO(zip_data))
    
    infos = zip_file.infolist()
    extensions = [os.path.splitext(info.filename)[1] for info in infos]
    basenames = [os.path.basename(info.filename) for info in infos]
    
    if dir:
        base_dir = dir
    elif kwargs.get('urlcache', None):
        os.mkdir(os.path.join(tempfile.gettempdir(), base64.urlsafe_b64encode(shapefile)))
        base_dir = os.path.join(tempfile.gettempdir(), base64.urlsafe_b64encode(shapefile))
    else:
        base_dir = tempfile.mkdtemp(prefix='cascadenik-shapefile-')
    
    for (expected, required) in (('.shp', True), ('.shx', True), ('.dbf', True), ('.prj', False)):
        if required and expected not in extensions:
            raise Exception('Zip file %(shapefile)s missing extension "%(expected)s"' % locals())

        for (info, extension, basename) in zip(infos, extensions, basenames):
            if extension == expected:
                file_data = zip_file.read(info.filename)
                file_name = os.path.normpath('%(base_dir)s/%(basename)s' % locals())
                
                file = open(file_name, 'wb')
                file.write(file_data)
                file.close()
                
                if extension == '.shp':
                    local = file_name[:-4]
                
                break

    return local

def compile(src,**kwargs):
    """
    """
    
    dir = kwargs.get('dir',None)
    urlcache = kwargs.get('urlcache',False)
    move_local_files = kwargs.get('move_local_files',False)
    
    if os.path.exists(src): # local file
        # using 'file:' enables support on win32
        # for opening local files with urllib.urlopen
        # Note: this must only be used with abs paths to local files
        # otherwise urllib will think they are absolute, 
        # therefore in the future it will likely be
        # wiser to just open local files with open()
        if os.path.isabs(src) and sys.platform == "win32":
            src = 'file:%s' % src
    
    if dir and not os.path.exists(dir):
        os.mkdir(dir)

    doc = ElementTree.parse(urllib.urlopen(src))
    map = doc.getroot()
    
    declarations = cascadenik.compile.extract_declarations(map, src)
    
    add_map_style(map, get_applicable_declarations(map, declarations))

    for layer in map.findall('Layer'):
    
        for parameter in layer.find('Datasource').findall('Parameter'):
            if parameter.get('name', None) == 'file':
                # fetch a remote zipped shapefile or read a local one
                parameter.text = localize_shapefile(src, parameter.text, dir, move_local_files, urlcache=urlcache)

            elif parameter.get('name', None) == 'table':
                # remove line breaks from possible SQL
                # http://trac.mapnik.org/ticket/173
                if not MAPNIK_VERSION >= 601:
                    parameter.text = parameter.text.replace('\r', ' ').replace('\n', ' ')

        if layer.get('status') == 'off':
            # don't bother
            continue
    
        # the default...
        layer.set('status', 'off')

        layer_declarations = get_applicable_declarations(layer, declarations)
        
        #pprint.PrettyPrinter().pprint(layer_declarations)
        
        insert_layer_style(map, layer, 'polygon style %d' % next_counter(),
                           get_polygon_rules(layer_declarations) + get_polygon_pattern_rules(layer_declarations, dir, move_local_files))
        
        insert_layer_style(map, layer, 'line style %d' % next_counter(),
                           get_line_rules(layer_declarations) + get_line_pattern_rules(layer_declarations, dir, move_local_files))

        for (shield_name, shield_rule_els) in get_shield_rule_groups(layer_declarations, dir, move_local_files):
            insert_layer_style(map, layer, 'shield style %d (%s)' % (next_counter(), shield_name), shield_rule_els)

        for (text_name, text_rule_els) in get_text_rule_groups(layer_declarations):
            insert_layer_style(map, layer, 'text style %d (%s)' % (next_counter(), text_name), text_rule_els)

        insert_layer_style(map, layer, 'point style %d' % next_counter(), get_point_rules(layer_declarations, dir, move_local_files))
        
        layer.set('name', 'layer %d' % next_counter())
        
        if 'id' in layer.attrib:
            del layer.attrib['id']
    
        if 'class' in layer.attrib:
            del layer.attrib['class']

    xml_out = StringIO.StringIO()
    doc.write(xml_out)
    
    return xml_out.getvalue()
