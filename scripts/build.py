#!/usr/bin/env python
# coding=utf-8
#
# build.py - Amiri font build utility
#
# Copyright 2010-2022 Khaled Hosny <khaled@aliftype.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


def generateFeatures(font, args):
    """Generates feature text by merging feature file with mark positioning
    lookups (already in the font) and making sure they come after kerning
    lookups (from the feature file), which is required by Uniscribe to get
    correct mark positioning for kerned glyphs."""

    # open feature file and insert the generated GPOS features in place of the
    # placeholder text
    with open(args.features) as f:
        font.features.text = f.read() + font.features.text


def generateFont(options, font):
    from ufo2ft import compileOTF, compileTTF

    generateFeatures(font, options)

    info = font.info
    major, minor = options.version.split(".")
    info.versionMajor, info.versionMinor = int(major), int(minor)

    if options.output.endswith(".ttf"):
        otf = compileTTF(
            font,
            inplace=True,
            removeOverlaps=True,
            overlapsBackend="pathops",
        )
    else:
        otf = compileOTF(
            font,
            inplace=True,
            optimizeCFF=1,
            removeOverlaps=True,
            overlapsBackend="pathops",
        )

    return otf


def drawOverline(font, name, pos, thickness, width):
    try:
        glyph = font[name]
    except KeyError:
        glyph = font.newGlyph(name)
        glyph.width = 0

    pen = glyph.getPen()
    glyph.clear()

    pen.moveTo((-50, pos))
    pen.lineTo((-50, pos + thickness))
    pen.lineTo((width + 50, pos + thickness))
    pen.lineTo((width + 50, pos))
    pen.closePath()

    return glyph


def makeOverLine(font, posGlyph="qafLamAlefMaksuraabove-ar"):
    from fontTools.feaLib import ast

    pos = font[posGlyph].getBounds(font).yMax
    thickness = font.info.postscriptUnderlineThickness
    min_width = 100

    # collect glyphs grouped by their widths rounded by 100 units, we will use
    # them to decide the widths of over/underline glyphs we will draw
    widths = {}
    for glyph in font:
        u = glyph.unicode
        if (
            (u is None) or (0x0600 <= u <= 0x06FF) or u == ord(" ")
        ) and glyph.width > 0:
            width = round(glyph.width / min_width) * min_width
            width = width > min_width and width or min_width
            if not width in widths:
                widths[width] = []
            widths[width].append(glyph.name)

    base = "overlinecomb"
    drawOverline(font, base, pos, thickness, 500)

    mark = ast.FeatureBlock("mark")
    overset = ast.GlyphClassDefinition("OverSet", ast.GlyphClass([base]))
    lookup_flags = ast.LookupFlagStatement(markFilteringSet=ast.GlyphClassName(overset))
    mark.statements.extend([overset, lookup_flags])

    for width in sorted(widths.keys()):
        # for each width group we create an over/underline glyph with the same
        # width, and add a contextual substitution lookup to use it when an
        # over/underline follows any glyph in this group
        replace = f"overlinecomb.{width}"
        drawOverline(font, replace, pos, thickness, width)
        sub = ast.SingleSubstStatement(
            [ast.GlyphName(base)],
            [ast.GlyphName(replace)],
            [ast.GlyphClass(widths[width])],
            [],
            False,
        )
        font.lib["public.openTypeCategories"][replace] = "mark"
        mark.statements.append(sub)

    font.features.text += str(mark)


def makeDesktop(font, options):

    makeOverLine(font, posGlyph="overlinecomb")
    return generateFont(options, font)


if __name__ == "__main__":
    import argparse
    from ufoLib2 import Font

    parser = argparse.ArgumentParser(description="Build Amiri fonts.")
    parser.add_argument(
        "--input", metavar="FILE", required=True, help="input font to process"
    )
    parser.add_argument(
        "--output", metavar="FILE", required=True, help="output font to write"
    )
    parser.add_argument(
        "--features", metavar="FILE", required=True, help="feature file to include"
    )
    parser.add_argument("--version", type=str, required=True, help="font version")

    args = parser.parse_args()

    font = Font.open(args.input)
    otf = makeDesktop(font, args)
    otf.save(args.output)
