"""Build placeholder PWA icons (192/512/maskable) with the kanji 漢 on
a flat brand-colour background. Regenerate by running this script."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT   = Path(__file__).resolve().parent.parent
OUTDIR = ROOT / "icons"

BRAND_BG = (33, 150, 243)   # #2196f3 — matches meta theme-color
GLYPH_FG = (255, 255, 255)
GLYPH    = "漢"

# Maskable icons need the "safe zone": content only inside the inner 80%.
MASKABLE_SAFE_RATIO = 0.8

def find_jp_font():
    """Pick the first available CJK-capable font on this machine."""
    for path in (
        r"C:\Windows\Fonts\meiryo.ttc",
        r"C:\Windows\Fonts\YuGothM.ttc",
        r"C:\Windows\Fonts\msgothic.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ):
        if Path(path).exists():
            return path
    raise RuntimeError("No CJK font found — edit find_jp_font() to add a path")

def render(size: int, glyph_scale: float, out: Path):
    img  = Image.new("RGB", (size, size), BRAND_BG)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(find_jp_font(), int(size * glyph_scale))
    bbox = draw.textbbox((0, 0), GLYPH, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]),
        GLYPH, font=font, fill=GLYPH_FG,
    )
    img.save(out, "PNG")
    print(f"wrote {out.relative_to(ROOT)} ({size}x{size})")

def main():
    OUTDIR.mkdir(exist_ok=True)
    render(192, 0.70, OUTDIR / "icon-192.png")
    render(512, 0.70, OUTDIR / "icon-512.png")
    # Maskable: shrink glyph so it stays inside the 80% safe zone.
    render(512, 0.70 * MASKABLE_SAFE_RATIO, OUTDIR / "icon-maskable-512.png")

if __name__ == "__main__":
    main()
