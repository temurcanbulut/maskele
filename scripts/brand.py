"""maskele marka varlıkları: işaret, ikon, favicon, kelime işareti (yazı vektöre çevrilmiş).

İşaret: token parantezleri; aralarından akan veri çizgileri ve çizgilerin taşıdığı iki token
hapı. Okunuşu: "veri girer, token olarak geçer, yerine geri döner."
"""

from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

OUT = Path(__file__).resolve().parents[1] / "assets" / "brand"
FONT = "/usr/share/fonts/opentype/inter/InterDisplay-SemiBold.otf"
FONT_T = "/usr/share/fonts/opentype/inter/InterDisplay-Medium.otf"
TAGLINE = "Share the problem, not the data."

# Palet
NIGHT, INDIGO, VIOLET, LAVENDER, MIST = "#0B1020", "#6366F1", "#A78BFA", "#CBD5FF", "#F4F6FB"
DEEP = "#4F46E5"  # açık zeminde haplar (kontrast için bir ton koyu)
SLATE, SLATE_D = "#5B6478", "#9AA3BF"  # alt yazı

LIGHT = dict(br=INDIGO, wave=VIOLET, wave_op=0.55, pill=DEEP, ink=NIGHT, muted=SLATE)
DARK = dict(br="#818CF8", wave=VIOLET, wave_op=0.6, pill=LAVENDER, ink=MIST, muted=SLATE_D)
ON_INDIGO = dict(br="#FFFFFF", wave="#FFFFFF", wave_op=0.42, pill="#FFFFFF")

# 128 x 128 ızgara
BRACKETS = "M31 16 H17 V112 H31 M97 16 H111 V112 H97"
WAVES = [f"M35 {y} C56 {y} 70 {y + 14} 93 {y + 14}" for y in (39, 57, 75)]
PILLS = [(37, 33, 28, 12), (63, 65, 28, 12)]


def mark(c, waves=True, stroke=11):
    out = [
        f'<path d="{BRACKETS}" fill="none" stroke="{c["br"]}" stroke-width="{stroke}" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    ]
    if waves:
        out.append(
            f'<g fill="none" stroke="{c["wave"]}" stroke-opacity="{c["wave_op"]}" '
            'stroke-width="4.5" stroke-linecap="round">' + "".join(f'<path d="{d}"/>' for d in WAVES) + "</g>"
        )
    out += [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{c["pill"]}"/>' for x, y, w, h in PILLS]
    return "".join(out)


def mark_small(c):
    """24 pikselin altı: dalgasız, kalın parantez, büyük haplar."""
    return (
        f'<path d="M36 16 H18 V112 H36 M92 16 H110 V112 H92" fill="none" stroke="{c["br"]}" '
        'stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<rect x="38" y="36" width="34" height="18" rx="9" fill="{c["pill"]}"/>'
        f'<rect x="56" y="74" width="34" height="18" rx="9" fill="{c["pill"]}"/>'
    )


def text_path(text, font_file, size, x=0.0, y=0.0, tracking=0.0):
    f = TTFont(font_file)
    gs, cmap = f.getGlyphSet(), f.getBestCmap()
    scale = size / f["head"].unitsPerEm
    pen = SVGPathPen(gs)
    cx = x
    for ch in text:
        g = cmap[ord(ch)]
        gs[g].draw(TransformPen(pen, (scale, 0, 0, -scale, cx, y)))
        cx += gs[g].width * scale + tracking * size
    return pen.getCommands(), cx - tracking * size - x


def svg(viewbox, body, label="maskele"):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" role="img" aria-label="{label}">{body}</svg>\n'


def write(name, content):
    (OUT / name).write_text(content, encoding="utf-8")


def icon(dark=False):
    """Uygulama ikonu: indigo zemin (renkli) ya da gece zemin (koyu)."""
    if dark:
        return (
            f'<rect width="128" height="128" rx="28" fill="{NIGHT}"/>'
            f'<g transform="translate(14 14) scale(.78)">{mark(DARK)}</g>'
        )
    return (
        f'<rect width="128" height="128" rx="28" fill="{INDIGO}"/>'
        f'<g transform="translate(14 14) scale(.78)">{mark(ON_INDIGO)}</g>'
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)

    # Tema uyumlu işaret: tek dosya, açık/koyu
    css = (
        f"<style>.b{{stroke:{INDIGO}}}.w{{stroke:{VIOLET}}}.p{{fill:{DEEP}}}"
        "@media (prefers-color-scheme:dark)"
        f"{{.b{{stroke:{DARK['br']}}}.p{{fill:{LAVENDER}}}}}</style>"
    )
    themed = (
        mark(LIGHT)
        .replace(f'stroke="{INDIGO}"', 'class="b"', 1)
        .replace(f'stroke="{VIOLET}"', 'class="w"', 1)
        .replace(f'fill="{DEEP}"', 'class="p"')
    )
    write("mark.svg", svg("0 0 128 128", css + themed))
    write("mark-light.svg", svg("0 0 128 128", mark(LIGHT)))
    write("mark-dark.svg", svg("0 0 128 128", mark(DARK)))

    write("icon.svg", svg("0 0 128 128", icon()))
    write("icon-dark.svg", svg("0 0 128 128", icon(dark=True)))
    write(
        "favicon.svg",
        svg(
            "0 0 128 128",
            f'<rect width="128" height="128" rx="28" fill="{INDIGO}"/>'
            f'<g transform="translate(10 10) scale(.84)">{mark_small(ON_INDIGO)}</g>',
        ),
    )

    # Logo: işaret + kelime işareti + alt yazı. İşaret 112 px, yazı 64 px.
    word, ww = text_path("maskele", FONT, 66, x=132, y=66, tracking=-0.025)
    tag, tw = text_path(TAGLINE, FONT_T, 19, x=135, y=102)
    W = int(max(132 + ww, 135 + tw)) + 6
    for name, c in (("logo-light.svg", LIGHT), ("logo-dark.svg", DARK)):
        write(
            name,
            svg(
                f"0 0 {W} 120",
                f'<g transform="translate(0 4) scale(.875)">{mark(c)}</g>'
                f'<path d="{word}" fill="{c["ink"]}"/><path d="{tag}" fill="{c["muted"]}"/>',
                f"maskele — {TAGLINE}",
            ),
        )
    word2, ww2 = text_path("maskele", FONT, 66, x=132, y=80, tracking=-0.025)
    WW = int(132 + ww2) + 6
    for name, c in (("wordmark-light.svg", LIGHT), ("wordmark-dark.svg", DARK)):
        write(
            name, svg(f"0 0 {WW} 112", f'<g transform="scale(.875)">{mark(c)}</g><path d="{word2}" fill="{c["ink"]}"/>')
        )
    print("ok", W, WW)
