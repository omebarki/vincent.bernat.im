# -*- coding: utf-8 -*-
"""
Contains classes to handle images related things

# Requires PIL/Pillow
"""

from hyde.plugin import Plugin
from hyde.plugin import CLTransformer
from hyde.ext.plugins.images import PILPlugin
from fswrap import File, Folder

import xml.etree.ElementTree as ET

from PIL import Image
import new
import os
import re
from functools import partial

class Thumb(object):
    def __init__(self, path, **kwargs):
        self.path = path
        for arg in kwargs:
            setattr(self, arg, kwargs[arg])
    def __str__(self):
        return self.path       

def thumb(self, defaults={}, width=None, height=None):
    """
    Generate a thumbnail for the given image
    """
    if width is None and height is None:
        width, height = defaults['width'], defaults['height']
    im = Image.open(self.path)
    if im.mode != 'RGBA':
        im = im.convert('RGBA')
    # Convert to a thumbnail
    if width is None:
        # height is not None
        width = im.size[0]*height/im.size[1] + 1
    elif height is None:
        # width is not None
        height = im.size[1]*width/im.size[0] + 1
    im.thumbnail((width, height), Image.ANTIALIAS)
    # Prepare path
    path = os.path.join(os.path.dirname(self.get_relative_deploy_path()),
                        "%s%s" % (defaults['prefix'],
                                  self.name))
    target = File(Folder(self.site.config.deploy_root_path).child(path))
    target.parent.make()
    if self.name.endswith(".jpg"):
        im.save(target.path, "JPEG", optimize=True, quality=75)
    else:
        im.save(target.path, "PNG", optimize=True)
    return Thumb(path, width=im.size[0], height=im.size[1])

class ImageThumbnailsPlugin(Plugin):
    """
    Provide a function to get thumbnail for any image resource.

    Each image resource will get a `thumb()` function. This function
    can take the following keywords:
      - width (int)
      - height (int)
      - prefix (string): prefix to use for thumbnails

    This plugin can be configured with the exact same keywords to set
    site defaults. The `thumb()` function will return a path to the
    thumbnail. This path will have `width` and `height` as an
    attribute.

    Thumbnails are created in the same directory of their image.

    Currently, only supports PNG and JPG.
    """

    def __init__(self, site):
        super(ImageThumbnailsPlugin, self).__init__(site)

    def begin_site(self):
        """
        Find any image resource to add them the thumb() function.
        """
        # Grab default values from config
        config = self.site.config
        defaults = { "width": None,
                     "height": 40,
                     "prefix": 'thumb_',
                     }
        if hasattr(config, 'thumbnails'):
            defaults.update(config.thumbnails)
        # Make the thumbnailing function
        thumbfn = partial(thumb, defaults=defaults)
        thumbfn.__doc__ = "Create a thumbnail for this image"

        # Add it to any image resource
        for node in self.site.content.walk():
            for resource in node.resources:
                if resource.source_file.kind not in ["jpg", "png"]:
                    continue
                self.logger.debug("Adding thumbnail function to [%s]" % resource)
                resource.thumb = new.instancemethod(thumbfn, resource, resource.__class__)


class JPEGTranPlugin(CLTransformer):
    """
    The plugin class for JPEGTran
    """

    def __init__(self, site):
        super(JPEGTranPlugin, self).__init__(site)

    @property
    def plugin_name(self):
        """
        The name of the plugin.
        """
        return "jpegtran"

    def option_prefix(self, option):
        return "-"

    def binary_resource_complete(self, resource):
        """
        Run jpegtran to compress the jpg file.
        """

        if not resource.source_file.kind == 'jpg':
            return

        supported = [
            "optimize",
            "progressive",
            "restart",
            "arithmetic",
            "perfect",
            "copy",
        ]
        source = File(self.site.config.deploy_root_path.child(
                resource.relative_deploy_path))
        target = File.make_temp('')
        jpegtran = self.app
        args = [unicode(jpegtran)]
        args.extend(self.process_args(supported))
        args.extend(["-outfile", unicode(target), unicode(source)])
        self.call_app(args)
        target.copy_to(source)
        target.delete()


class ImageSizerPlugin(PILPlugin):
    """Each HTML page is modified to add width and height for images if
    they are not already specified. Moreover, images are embedded into
    a container to ensure their aspect ratio is conserved if their
    width is constrained.
    """

    def __init__(self, site):
        super(ImageSizerPlugin, self).__init__(site)
        self.cache = {}

    def _topx(self, x):
        mo = re.match(r'(?P<size>\d+(?:\.\d*)?)(?P<unit>.*)', x)
        if not mo:
            raise ValueError("cannot convert {} to pixel".format(x))
        unit = mo.group("unit")
        size = float(mo.group("size"))
        if unit in ["", "px"]:
            return int(size)
        if unit == "pt":
            return int(size*4/3)
        raise ValueError("unknown unit {}".format(unit))

    def _handle_img_size(self, image):
        if image.source_file.kind not in ['png', 'jpg', 'jpeg', 'gif', 'svg']:
            self.logger.warn(
                "[%s] has an img tag not linking to an image" % resource)
            return (None, None)
        # Now, get the size of the image
        try:
            if image.source_file.kind == 'svg':
                svg = ET.parse(image.path).getroot()
                return tuple(x and self._topx(x) or None
                             for x in (svg.attrib.get('width', None),
                                       svg.attrib.get('height', None)))
            return self.Image.open(image.path).size
        except IOError:
            self.logger.warn(
                "Unable to process image [%s]" % image)
            return (None, None)

    def _handle_img(self, resource, src, width, height):
        """Determine what should be added to an img tag."""
        if height is not None and width is not None:
            return None
        if src is None:
            self.logger.warn(
                "[%s] has an img tag without src attribute" % resource)
            return None
        if src not in self.cache:
            if src.startswith(self.site.config.media_url):
                path = src[len(self.site.config.media_url):].lstrip("/")
                path = self.site.config.media_root_path.child(path)
                image = self.site.content.resource_from_relative_deploy_path(
                    path)
            elif re.match(r'([a-z]+://|//).*', src):
                # Not a local link
                return None
            elif src.startswith("/"):
                # Absolute resource
                path = src.lstrip("/")
                image = self.site.content.resource_from_relative_deploy_path(
                    path)
            else:
                # Relative resource
                path = resource.node.source_folder.child(src)
                image = self.site.content.resource_from_path(path)
            if image is None:
                self.logger.warn(
                    "[%s] has an unknown image" % resource)
                return None
            self.cache[src] = self._handle_img_size(image)
            self.logger.debug("Image [%s] is %s" % (src,
                                                    self.cache[src]))
        new_width, new_height = self.cache[src]
        if new_width is None or new_height is None:
            return None
        if width is not None:
            return (width, int(width) * new_height / new_width)
        elif height is not None:
            return (int(height) * new_width / new_height, height)
        return (new_width, new_height)

    def _handle_img_str(self, resource, mo):
        width, height, src, title, alt = None, None, None, None, None
        classes = ""
        original = mo.group(0)
        paragraph = mo.group("popening") is not None
        atag = mo.group("aopening") or ""
        img = mo.group("img")
        mo = re.search(r"\bwidth=([\"'])(?P<value>\d+)\1", img)
        if mo:
            width = int(mo.group("value"))
            img = img[:mo.start()] + img[mo.end():]
        mo = re.search(r"\bheight=([\"'])(?P<value>\d+)\1", img)
        if mo:
            height = int(mo.group("value"))
            img = img[:mo.start()] + img[mo.end():]
        mo = re.search(r"\bclass=([\"'])(?P<value>.*?)\1", img)
        if mo:
            classes = mo.group("value")
            img = img[:mo.start()] + img[mo.end():]
        mo = re.search(r"\bsrc=([\"'])(?P<value>.*?)\1", img)
        if mo:
            src = mo.group("value")
        mo = re.search(r"\btitle=([\"'])(?P<value>.*?)\1", img)
        if mo:
            title = mo.group("value")
        mo = re.search(r"\balt=([\"'])(?P<value>.*?)\1", img)
        if mo:
            alt = mo.group("value")
        wh = self._handle_img(resource, src, width, height)
        if wh is None:
            return original
        width, height = wh
        if paragraph:
            classes += " lf-img"
            classes = classes.lstrip()
        # SVG are converted to object
        if "/obj/" in src and src.endswith('.svg'):
            img = '<object data="%s" type="image/svg+xml">' % src
        img = '%s width="%s" height="%s"%s>' % (
            img[:-1],
            width, height,
            classes and (' class="%s"' % classes) or "")
        if "/obj/" in src and src.endswith('.svg'):
            img = '%s&#128444; %s</object>' % (img, alt or "")
        if atag:
            img = "%s%s</a>" % (atag, img)
        if not paragraph:
            return img
        img = '<span class="lf-img-inner" style="padding-bottom: %.3f%%;">%s</span>' % (
            float(height)*100./width, img)
        img = '<div class="lf-img-outer" style="width: %dpx;">%s</div>' % (
            width, img)
        if title is not None:
            img = ('<figure>%s'
                   '<figcaption>%s</figcaption>'
                   '</figure>') % (img, title)
        return img

    def text_resource_complete(self, resource, text):
        """
        When the resource is generated, search for img tag and specify
        their sizes.

        Some img tags may be missed, this is not a perfect parser.
        """
        if not resource.source_file.kind == 'html':
            return

        # This is quite hacky, but rely on a regex.
        return re.sub(r'(?P<popening><p>)?'
                      r'(?P<aopening><a\s+[^>]*>)?'
                      r'(?P<img><img\s+[^>]*>)'
                      r'(?P<aclosing></a>)?'
                      r'(?P<pclosing></p>)?',
                      partial(self._handle_img_str, resource),
                      text, flags=re.DOTALL)
