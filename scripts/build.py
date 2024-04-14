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

from io import StringIO
from pcpp.preprocessor import Preprocessor

from ufo2ft import compileOTF, compileTTF
from ufoLib2 import Font


REMOVE_GLYPHS = "com.schriftgestaltung.customParameter.GSFontMaster.Remove Glyphs"


def cleanAnchors(font):
    """Removes anchor classes (and associated lookups) that are used only
    internally for building composite glyph."""

    anchors = {
        "Dash",
        # "DigitAbove",
        "DigitBelow",
        "DotAbove",
        "DotAlt",
        "DotBelow",
        "DotBelowAlt",
        "DotHmaza",
        "MarkDotAbove",
        "MarkDotBelow",
        "RingBelow",
        "RingDash",
        "Stroke",
        # "TaaAbove",
        "TaaBelow",
        "Tail",
        "TashkilAboveDot",
        "TashkilBelowDot",
        "TwoDotsAbove",
        "TwoDotsBelow",
        "TwoDotsBelowAlt",
        "VAbove",
    }

    for glyph in font:
        glyph.anchors = [a for a in glyph.anchors if a.name not in anchors]


def generateFeatures(font, args):
    """Generates feature text by merging feature file with mark positioning
    lookups (already in the font) and making sure they come after kerning
    lookups (from the feature file), which is required by Uniscribe to get
    correct mark positioning for kerned glyphs."""

    # open feature file and insert the generated GPOS features in place of the
    # placeholder text
    preprocessor = Preprocessor()
    if args.quran:
        preprocessor.define("QURAN")
    with open(args.features) as f:
        preprocessor.parse(f)
    o = StringIO()
    preprocessor.write(o)
    font.features.text = o.getvalue() + font.features.text


def generateFont(options, font):
    generateFeatures(font, options)

    from datetime import datetime

    info = font.info
    major, minor = options.version.split(".")
    info.versionMajor, info.versionMinor = int(major), int(minor)

    if options.output.endswith(".ttf"):
        from fontTools.ttLib import newTable
        from fontTools.ttLib.tables import ttProgram

        otf = compileTTF(
            font, inplace=True, removeOverlaps=True, overlapsBackend="pathops"
        )

        otf["prep"] = prep = newTable("prep")
        prep.program = ttProgram.Program()
        prep.program.fromAssembly(
            ["PUSHW[]", "511", "SCANCTRL[]", "PUSHB[]", "4", "SCANTYPE[]"]
        )
    else:
        otf = compileOTF(
            font,
            inplace=True,
            optimizeCFF=1,
            removeOverlaps=True,
            overlapsBackend="pathops",
        )

    if info.styleMapStyleName and "italic" in info.styleMapStyleName:
        otf["name"].names = [n for n in otf["name"].names if n.nameID != 17]
        for name in otf["name"].names:
            if name.nameID == 2:
                name.string = info.styleName

    return otf


def drawOverline(font, name, uni, pos, thickness, width):
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
    minwidth = 100

    # collect glyphs grouped by their widths rounded by 100 units, we will use
    # them to decide the widths of over/underline glyphs we will draw
    widths = {}
    for glyph in font:
        u = glyph.unicode
        if (
            (u is None) or (0x0600 <= u <= 0x06FF) or u == ord(" ")
        ) and glyph.width > 0:
            width = round(glyph.width / minwidth) * minwidth
            width = width > minwidth and width or minwidth
            if not width in widths:
                widths[width] = []
            widths[width].append(glyph.name)

    base = "overlinecomb"
    drawOverline(font, base, 0x0305, pos, thickness, 500)

    mark = ast.FeatureBlock("mark")
    overset = ast.GlyphClassDefinition("OverSet", ast.GlyphClass([base]))
    lookupflag = ast.LookupFlagStatement(markFilteringSet=ast.GlyphClassName(overset))
    mark.statements.extend([overset, lookupflag])

    for width in sorted(widths.keys()):
        # for each width group we create an over/underline glyph with the same
        # width, and add a contextual substitution lookup to use it when an
        # over/underline follows any glyph in this group
        replace = f"overlinecomb.{width}"
        drawOverline(font, replace, None, pos, thickness, width)
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


def mergeLatin(font):
    fontname = font.info.postscriptFontName.replace("Amiri", "AmiriLatin")
    latin = openFont("sources/%s.ufo" % fontname)
    for glyph in latin:
        try:
            font.addGlyph(glyph)
        except KeyError:
            pass

    font.glyphOrder += latin.glyphOrder
    font.lib["public.openTypeCategories"].update(latin.lib["public.openTypeCategories"])
    font.groups.update(latin.groups)
    font.kerning.update(latin.kerning)


def scaleGlyph(font, glyph, scale):
    """Scales the glyph, but keeps it centered around its original bounding
    box."""
    from fontTools.pens.recordingPen import RecordingPointPen
    from fontTools.pens.transformPen import TransformPointPen
    from fontTools.misc.transform import Identity

    width = glyph.width
    bbox = glyph.getBounds(font)
    x = (bbox.xMin + bbox.xMax) / 2
    y = (bbox.yMin + bbox.yMax) / 2
    matrix = Identity
    matrix = matrix.translate(-x * scale + x, -y * scale + y)
    matrix = matrix.scale(scale)

    rec = RecordingPointPen()
    glyph.drawPoints(rec)
    glyph.clearContours()
    glyph.clearComponents()

    pen = TransformPointPen(glyph.getPointPen(), matrix)
    rec.replay(pen)

    for a in glyph.anchors:
        a.x, a.y = matrix.transformPoint((a.x, a.y))

    if width == 0:
        glyph.width = width


def makeQuran(options):
    from fontTools import subset

    font = makeDesktop(options, False)
    mergeLatin(font)

    # fix metadata
    info = font.info
    info.postscriptFontName = info.postscriptFontName.replace(
        "-Regular", "QuranColored-Regular"
    )
    info.familyName += " Quran Colored"
    info.postscriptFullName += " Quran Colored"
    info.openTypeNameSampleText = "بِسۡمِ ٱللَّهِ ٱلرَّحۡمَـٰنِ ٱلرَّحِیمِ ۝١ ٱلۡحَمۡدُ لِلَّهِ رَبِّ ٱلۡعَـٰلَمِینَ ۝٢"
    info.openTypeOS2TypoAscender = info.openTypeHheaAscender = 1815

    # scale some vowel marks and dots down a bit
    marks = [
        "fathatan-ar",
        "dammatan-ar",
        "fatha-ar",
        "damma-ar",
        "hahabove-ar",
        "openfathatan-ar",
        "opendammatan-ar",
        "openkasratan-ar",
        "twodotshorizontalabove-ar",
        "threedotsupabove-ar",
        "twodotsverticalabove-ar",
    ]
    shadda = ["shadda-ar"]
    for scale, names in ((0.9, marks), (0.8, shadda)):
        for name in names:
            scaleGlyph(font, font[name], scale)

    # create overline glyph to be used for sajda line, it is positioned
    # vertically at the level of the base of waqf marks
    makeOverLine(font)

    otf = generateFont(options, font)

    unicodes = [
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        ".",
        "(",
        ")",
        "[",
        "]",
        "{",
        "}",
        "|",
        " ",
        "/",
        "\\",
        0x00A0,
        0x00AB,
        0x00BB,
        0x0305,
        0x030A,
        0x0325,
        0x060C,
        0x0615,
        0x0617,
        0x0618,
        0x0619,
        0x061A,
        0x061B,
        0x061E,
        0x061F,
        0x0621,
        0x0622,
        0x0623,
        0x0624,
        0x0625,
        0x0626,
        0x0627,
        0x0628,
        0x0629,
        0x062A,
        0x062B,
        0x062C,
        0x062D,
        0x062E,
        0x062F,
        0x0630,
        0x0631,
        0x0632,
        0x0633,
        0x0634,
        0x0635,
        0x0636,
        0x0637,
        0x0638,
        0x0639,
        0x063A,
        0x0640,
        0x0641,
        0x0642,
        0x0643,
        0x0644,
        0x0645,
        0x0646,
        0x0647,
        0x0648,
        0x0649,
        0x064A,
        0x064B,
        0x064C,
        0x064D,
        0x064E,
        0x064F,
        0x0650,
        0x0651,
        0x0652,
        0x0653,
        0x0654,
        0x0655,
        0x0656,
        0x0657,
        0x0658,
        0x065C,
        0x0660,
        0x0661,
        0x0662,
        0x0663,
        0x0664,
        0x0665,
        0x0666,
        0x0667,
        0x0668,
        0x0669,
        0x066E,
        0x066F,
        0x0670,
        0x0671,
        0x067A,
        0x06A1,
        0x06BA,
        0x06CC,
        0x06D6,
        0x06D7,
        0x06D8,
        0x06D9,
        0x06DA,
        0x06DB,
        0x06DC,
        0x06DD,
        0x06DE,
        0x06DF,
        0x06E0,
        0x06E1,
        0x06E2,
        0x06E3,
        0x06E4,
        0x06E5,
        0x06E6,
        0x06E7,
        0x06E8,
        0x06E9,
        0x06EA,
        0x06EB,
        0x06EC,
        0x06ED,
        0x06F0,
        0x06F1,
        0x06F2,
        0x06F3,
        0x06F4,
        0x06F5,
        0x06F6,
        0x06F7,
        0x06F8,
        0x06F9,
        0x08F0,
        0x08F1,
        0x08F2,
        0x08F3,
        0x2000,
        0x2001,
        0x2002,
        0x2003,
        0x2004,
        0x2005,
        0x2006,
        0x2007,
        0x2008,
        0x2009,
        0x200A,
        0x200B,
        0x200C,
        0x200D,
        0x200E,
        0x200F,
        0x2028,
        0x2029,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x202F,
        0x25CC,
        0xFD3E,
        0xFD3F,
        0xFDFA,
        0xFDFD,
    ]
    unicodes = [isinstance(u, str) and ord(u) or u for u in unicodes]

    opts = subset.Options()
    opts.set(
        name_IDs="*",
        name_languages="*",
        notdef_outline=True,
        glyph_names=True,
        layout_scripts=["DFLT", "arab.dflt", "arab.ARA ", "arab.URD "],
        recalc_average_width=True,
        recalc_max_context=True,
    )
    for feature in ("pnum", "numr", "dnom"):
        if feature in opts.layout_features:
            opts.layout_features.remove(feature)
    subsetter = subset.Subsetter(options=opts)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(otf)

    # Use FontBBox for Win metrics since we use larger marks that can result in
    # bigger font bbox that the regular fonts.
    head = otf["head"]
    os_2 = otf["OS/2"]
    os_2.usWinAscent = max(head.yMax, os_2.usWinAscent)
    os_2.usWinDescent = max(abs(head.yMin), os_2.usWinDescent)

    otf.save(options.output)


def _build_production_name(glyph, font):
    """Build a production name for a single glyph."""

    # use name derived from unicode value
    unicode_val = glyph.unicode
    if glyph.unicode is not None:
        return "{}{:04X}".format("u" if unicode_val > 0xFFFF else "uni", unicode_val)

    # use production name + last (non-script) suffix if possible
    parts = glyph.name.rsplit(".", 1)
    if len(parts) == 2 and parts[0] in font:
        return "{}.{}".format(
            _build_production_name(font[parts[0]], font),
            parts[1],
        )

    # use ligature name, making sure to look up components with suffixes
    parts = glyph.name.split(".", 1)
    if len(parts) == 2:
        liga_parts = ["{}.{}".format(n, parts[1]) for n in parts[0].split("_")]
    else:
        liga_parts = glyph.name.split("_")
    if len(liga_parts) > 1 and all(n in font for n in liga_parts):
        unicode_vals = [font[n].unicode for n in liga_parts]
        if all(v and v <= 0xFFFF for v in unicode_vals):
            return "uni" + "".join("%04X" % v for v in unicode_vals)
        return "_".join(_build_production_name(font[n], font) for n in liga_parts)

    return glyph.name


def openFont(path):
    font = Font.open(path)

    if REMOVE_GLYPHS in font.lib:
        import re

        pat = re.compile("(" + "|".join(font.lib[REMOVE_GLYPHS]) + ")")
        for name in list(font.keys()):
            if pat.match(name):
                del font[name]

    return font


def makeDesktop(options, generate=True):
    font = openFont(options.input)

    # remove anchors that are not needed in the production font
    cleanAnchors(font)

    if generate:
        mergeLatin(font)
        makeOverLine(font, posGlyph="overlinecomb")
        otf = generateFont(options, font)
        otf.save(options.output)
    else:
        return font


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build Amiri fonts.")
    parser.add_argument(
        "--input", metavar="FILE", required=True, help="input font to process"
    )
    parser.add_argument(
        "--output", metavar="FILE", required=True, help="ouput font to write"
    )
    parser.add_argument(
        "--features", metavar="FILE", required=True, help="feature file to include"
    )
    parser.add_argument("--version", type=str, required=True, help="font version")
    parser.add_argument("--license", type=str, required=True, help="license file")
    parser.add_argument(
        "--quran", action="store_true", required=False, help="build Quran variant"
    )

    args = parser.parse_args()

    if args.quran:
        makeQuran(args)
    else:
        makeDesktop(args)
