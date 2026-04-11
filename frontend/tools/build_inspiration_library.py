"""
Build a local-only inspiration library for PrintMind.

This script uses local object images that already exist on this machine,
normalizes them to consistent 640x640 previews, and writes:
  frontend/static/assets/inspiration/<category>/<category>_NN.jpg
  frontend/static/assets/inspiration/library.json

Usage:
  C:\printmind\venv310\Scripts\python c:\printmind\printmind_app\frontend\tools\build_inspiration_library.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1] / "static" / "assets" / "inspiration"
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
LOCAL_SOURCE_DIR = WORKSPACE_ROOT / "hunyuan" / "Hunyuan3D-2" / "assets" / "example_images"

PER_CATEGORY = 10
TARGET_SIZE = 640

OBJECT_SOURCE_STEMS = [
    "052", "075", "101", "1022", "1029", "1037", "1079", "1111", "1128", "1135",
    "1146", "1180", "1196", "1204", "1234", "1354", "1596", "1601", "1654", "167",
    "1679", "1698", "1735", "1738", "1744", "1758", "1772", "1778", "179", "191",
    "195", "197", "202", "380", "419", "583", "888", "example_000", "example_002",
]

CATEGORIES: dict[str, dict[str, Any]] = {
    "home_objects": {
        "label": "Home",
        "objects": ["Phone Stand", "Vase", "Planter", "Bowl", "Soap Dispenser", "Bookend", "Pen Tray", "Candle Holder", "Desk Organizer", "Coaster"],
    },
    "automotive_parts": {
        "label": "Automotive",
        "objects": ["Gear Knob", "Phone Mount", "Cup Holder", "Hubcap", "Vent Clip", "Bracket", "Console Tray", "Mirror Hanger", "Dash Mount", "Key Fob Case"],
    },
    "cosmetics_packaging": {
        "label": "Cosmetics",
        "objects": ["Perfume Bottle", "Lipstick Case", "Brush Holder", "Cream Jar", "Nail Polish", "Soap Bottle", "Compact Mirror", "Lotion Bottle", "Dropper Bottle", "Storage Cup"],
    },
    "desk_accessories": {
        "label": "Desk",
        "objects": ["Headphone Stand", "Cable Organizer", "Pen Holder", "USB Holder", "Phone Dock", "Card Holder", "Tray", "Monitor Stand", "Keyboard Riser", "Mini Shelf"],
    },
    "games_toys": {
        "label": "Games",
        "objects": ["Dice Tower", "Chess Piece", "Mini Figure", "Token", "Controller Stand", "Dice Tray", "Card Holder", "Pawn", "Game Tile", "Tabletop Piece"],
    },
    "industrial_parts": {
        "label": "Industrial",
        "objects": ["Gear", "Bearing", "Bolt", "Nut", "Bracket", "Clamp", "Pulley", "Knob", "Fitting", "Sprocket"],
    },
    "abstract_decor": {
        "label": "Abstract",
        "objects": ["Abstract Form", "Twisted Form", "Geometric Decor", "Sculpted Arc", "Decorative Orb", "Modern Piece", "Minimal Form", "Fluid Shape", "Column Form", "Art Object"],
    },
    "architecture_models": {
        "label": "Architecture",
        "objects": ["Mini House", "Arch Model", "Column Detail", "Facade Block", "Bridge Model", "Dome Piece", "Tower Model", "Window Frame", "Relief Tile", "Structure Block"],
    },
}


def _clear_existing() -> None:
    for p in ROOT.glob("**/*.jpg"):
        try:
            p.unlink()
        except Exception:
            pass


def _collect_local_sources() -> list[Path]:
    indexed: dict[str, Path] = {}
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for p in LOCAL_SOURCE_DIR.glob(ext):
            indexed[p.stem] = p
    files = [indexed[s] for s in OBJECT_SOURCE_STEMS if s in indexed]
    if not files:
        raise RuntimeError(f"No curated local source images found in {LOCAL_SOURCE_DIR}")
    return files


def _prepare_preview(src: Path, variant: int) -> Image.Image:
    img = Image.open(src).convert("RGBA")
    if variant == 1:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    alpha = img.getchannel("A")
    alpha_bbox = alpha.getbbox()

    # Most local source files here are transparent-background object renders.
    if alpha_bbox:
        obj = img.crop(alpha_bbox)
        ow, oh = obj.size
        scale = min((TARGET_SIZE * 0.82) / max(ow, 1), (TARGET_SIZE * 0.82) / max(oh, 1))
        nw = max(1, int(ow * scale))
        nh = max(1, int(oh * scale))
        obj = obj.resize((nw, nh), Image.Resampling.LANCZOS)
        if variant == 2:
            # Subtle zoom-in variant to increase variety without changing style.
            z = max(1, int(min(obj.width, obj.height) * 0.08))
            obj = obj.crop((z, z, obj.width - z, obj.height - z)).resize((nw, nh), Image.Resampling.LANCZOS)

        bg = Image.new("RGB", (TARGET_SIZE, TARGET_SIZE), (236, 241, 248))
        shadow = Image.new("RGBA", (nw + 20, nh + 20), (0, 0, 0, 0))
        sx = (TARGET_SIZE - shadow.width) // 2
        sy = (TARGET_SIZE - shadow.height) // 2 + 8
        bg_rgba = bg.convert("RGBA")
        bg_rgba.alpha_composite(shadow, (sx, sy))

        x = (TARGET_SIZE - nw) // 2
        y = (TARGET_SIZE - nh) // 2
        bg_rgba.alpha_composite(obj, (x, y))
        return bg_rgba.convert("RGB")

    # Non-transparent fallback: center-crop to square.
    rgb = img.convert("RGB")
    w, h = rgb.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    out = rgb.crop((left, top, left + side, top + side))
    if variant == 2:
        z = max(1, int(side * 0.08))
        out = out.crop((z, z, side - z, side - z))
    return out.resize((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)


def build() -> list[dict[str, str]]:
    ROOT.mkdir(parents=True, exist_ok=True)
    _clear_existing()

    sources = _collect_local_sources()
    variants: list[tuple[Path, int]] = []
    for src in sources:
        variants.append((src, 0))
        variants.append((src, 1))
        variants.append((src, 2))
    random.Random(17).shuffle(variants)
    need = len(CATEGORIES) * PER_CATEGORY
    variants = variants[:need]

    library: list[dict[str, str]] = []
    cursor = 0

    for category, cfg in CATEGORIES.items():
        label = str(cfg["label"])
        objects = list(cfg["objects"])
        cat_dir = ROOT / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        for i in range(1, PER_CATEGORY + 1):
            src, variant = variants[cursor]
            cursor += 1
            preview = _prepare_preview(src, variant)

            fname = f"{category}_{i:02d}.jpg"
            out = cat_dir / fname
            preview.save(out, format="JPEG", quality=92, optimize=True)

            title = objects[(i - 1) % len(objects)]
            rel = f"/static/assets/inspiration/{category}/{fname}"
            library.append(
                {
                    "category": category,
                    "title": title,
                    "detail": f"{label} local object reference",
                    "image_url": rel,
                    "source_url": str(src),
                    "source_title": "local curated source",
                }
            )
            print(category, i, rel, "<-", src.name, f"(v{variant})")

    return library


def main() -> None:
    library = build()
    out = ROOT / "library.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(library, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(library)} entries -> {out}")


if __name__ == "__main__":
    main()
