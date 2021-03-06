# -*- coding: utf-8 -*-
"""
Plugin to handle some typography stuff (monkey-patch typogrify).
"""

import re

from hyde.plugin import Plugin


class TypographyPlugin(Plugin):
    """Monkey-patch typogrify to correctly handle french punctuation and
    various other aspects not handled by typogrify."""

    NNBSP = u'&#x202f;'

    def __init__(self, site):
        # Patch typogrify
        from typogrify import filters
        original_applyfilters = filters.applyfilters
        original_process_ignores = filters.process_ignores
        filters.applyfilters = lambda text: self.frenchpunct(original_applyfilters(text))
        filters.process_ignores = self.process_ignores(original_process_ignores)

        # Don't use widont
        filters.widont = lambda t: t

    def process_ignores(self, orig):
        def process(text, ignore_tags=None):
            if ignore_tags is None:
                ignore_tags = []
            ignore_tags.append("latex")
            return orig(text, ignore_tags)
        return process

    def frenchpunct(self, text):
        tag_pattern = '</?\w+((\s+\w+(\s*=\s*(?:".*?"|\'.*?\'|[^\'">\s]+))?)+\s*|\s*)/?>'
        space_before_punct_finder = re.compile(r"""(\s|&nbsp;)([:;!\?%»])""", re.UNICODE)
        space_after_punct_finder = re.compile(r"""([«])(\s|&nbsp;)""", re.UNICODE)
        space_between_figures_finder = re.compile(r"""([0-9]|^)(\s|&nbsp;)([0-9]+(?:\W|$))""", re.UNICODE)
        version_number_finder = re.compile(r"""(\b[A-Z][a-zA-Z]+)(\s|&nbsp;)([0-9]+(?:\W|$))""", re.UNICODE)
        si_unit_finder = re.compile(ur"""(\b[0-9,.]+)( |&nbsp;)(\w|€)""", re.UNICODE)  # Cheating, nbsp already here...
        intra_tag_finder = re.compile(r'(?P<prefix>(%s)?)(?P<text>([^<]*))(?P<suffix>(%s)?)' % (tag_pattern, tag_pattern))

        def _space_process(groups):
            prefix = groups.group('prefix') or ''
            text = groups.group('text')
            text = space_before_punct_finder.sub(self.NNBSP + r"\2", text)
            text = space_after_punct_finder.sub(r"\1" + self.NNBSP, text)
            text = space_between_figures_finder.sub(r"\1" + self.NNBSP + r"\3", text)
            text = version_number_finder.sub(r"\1" + self.NNBSP + r"\3", text)
            text = si_unit_finder.sub(r"\1" + self.NNBSP + r"\3", text)
            suffix = groups.group('suffix') or ''
            return prefix + text + suffix

        output = intra_tag_finder.sub(_space_process, text)
        return output
