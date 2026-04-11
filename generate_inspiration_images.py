#!/usr/bin/env python3
"""
generate_inspiration_images.py
================================
Run ONCE from the printmind_app directory to replace the bad gallery images
with proper product-on-white-background renders.

Usage:
    cd C:\\printmind\\printmind_app
    python generate_inspiration_images.py

What it does:
  1. Loads SDXL-Turbo (downloads ~6.7 GB on first run, instant after)
  2. Generates 80 product images (10 per category, ~2-3s each on RTX 4070)
  3. Saves JPEGs to frontend/static/assets/inspiration/<category>/
  4. Rewrites library.json with correct titles and paths
"""

import os
import json
import torch
from pathlib import Path
from PIL import Image

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE        = Path(__file__).parent
INSPIRE_DIR  = _HERE / "frontend" / "static" / "assets" / "inspiration"
LIBRARY_JSON = INSPIRE_DIR / "library.json"
DEVICE       = "cuda" if torch.cuda.is_available() else "cpu"
IMG_SIZE     = 640   # square px — matches idea-thumb aspect ratio

print(f"[ImageGen] Device: {DEVICE}")
print(f"[ImageGen] Output: {INSPIRE_DIR}")

# ── Image catalogue ────────────────────────────────────────────────────────────
# (category_folder, display_title, short_detail, SDXL_prompt)
CATALOGUE = [
    # ── HOME OBJECTS ──────────────────────────────────────────────────────
    ("home_objects", "Phone Stand",
     "Clean minimalist phone holder",
     "minimalist white plastic phone stand, single object centered, pure white background, product photography, studio lighting, sharp focus"),
    ("home_objects", "Ceramic Vase",
     "Simple vase for flowers or decor",
     "simple modern white ceramic vase, single object centered, pure white background, product photography, studio lighting"),
    ("home_objects", "Small Planter",
     "Geometric desk planter with drainage",
     "small geometric concrete planter pot, single object centered, white background, product photography, studio shot"),
    ("home_objects", "Soap Dish",
     "Slotted soap dish with drainage channels",
     "modern white soap dish with drainage slots, single object centered, white background, product photography"),
    ("home_objects", "Desk Tray",
     "Flat catch-all organizer tray",
     "flat rectangular white desk tray organizer, single object, white background, product photography, top-down slight angle"),
    ("home_objects", "Bookend",
     "Minimal L-bracket style bookend",
     "matte black geometric L-shaped bookend, single object, white background, product photography, studio shot"),
    ("home_objects", "Candle Holder",
     "Cylindrical pillar candle holder",
     "simple cylindrical white candle holder, single object centered, white background, product photography, clean minimal"),
    ("home_objects", "Pen Cup",
     "Desktop pen and pencil cup",
     "concrete cylindrical pen holder cup, single object, white background, product photography, minimal design"),
    ("home_objects", "Coaster",
     "Hexagonal textured drink coaster",
     "hexagonal coaster with geometric texture pattern, white background, product photography, slightly elevated angle"),
    ("home_objects", "Cable Clip",
     "Snap-on desk cable management clip",
     "small white cable management clip, single object, white background, product photography, simple plastic design"),

    # ── AUTOMOTIVE PARTS ──────────────────────────────────────────────────
    ("automotive_parts", "Gear Knob",
     "Custom aftermarket shift knob",
     "polished chrome car gear shift knob, single object centered, white background, product photography, studio lighting"),
    ("automotive_parts", "Phone Mount",
     "Car air vent phone holder",
     "black plastic car phone vent mount clip, single object centered, white background, product photography"),
    ("automotive_parts", "Cup Holder Insert",
     "Organizer insert for cup holder",
     "black car cup holder organizer insert tray, single object, white background, product photography"),
    ("automotive_parts", "Key Fob Case",
     "Protective silicone key fob cover",
     "black rubber car key fob case cover, single object, white background, product photography"),
    ("automotive_parts", "Vent Clip",
     "Air freshener vent clip holder",
     "car air vent clip accessory, single object, white background, product photography, minimal plastic"),
    ("automotive_parts", "Dashboard Clip",
     "Cable routing dashboard clip",
     "small black cable management dashboard clip, single object, white background, product photography"),
    ("automotive_parts", "Console Divider",
     "Modular center console organizer",
     "black car center console organizer divider tray, single object, white background, product photography"),
    ("automotive_parts", "Headrest Hook",
     "Bag hook for rear headrest",
     "car headrest hook hanger accessory, single object, white background, product photography"),
    ("automotive_parts", "Charging Tray",
     "Dashboard wireless charging tray",
     "car dashboard charging tray pad, single object, white background, product photography, modern design"),
    ("automotive_parts", "Visor Clip",
     "Sun visor card and ticket holder",
     "car sun visor card holder clip, single object, white background, product photography"),

    # ── COSMETICS PACKAGING ───────────────────────────────────────────────
    ("cosmetics_packaging", "Perfume Bottle",
     "Elegant faceted perfume bottle",
     "elegant minimal glass perfume bottle, single object centered, white background, product photography, studio lighting, luxury"),
    ("cosmetics_packaging", "Lipstick Case",
     "Cylindrical metallic lipstick case",
     "sleek metallic lipstick case tube, single object centered, white background, product photography, rose gold"),
    ("cosmetics_packaging", "Brush Holder",
     "Makeup brush organizer stand",
     "white marble makeup brush holder stand, single object, white background, product photography"),
    ("cosmetics_packaging", "Cream Jar",
     "Face cream jar with lid",
     "minimalist white face cream jar with lid, single object, white background, product photography, clean label"),
    ("cosmetics_packaging", "Nail Polish Bottle",
     "Small nail polish glass bottle",
     "glass nail polish bottle, single object, white background, product photography, clear glass"),
    ("cosmetics_packaging", "Dropper Bottle",
     "Glass serum dropper bottle",
     "minimalist glass dropper serum bottle, single object, white background, product photography, frosted glass"),
    ("cosmetics_packaging", "Compact Mirror",
     "Round clamshell compact mirror",
     "rose gold round compact mirror, single object, white background, product photography, metallic"),
    ("cosmetics_packaging", "Lotion Pump",
     "Minimalist lotion pump bottle",
     "minimal white lotion pump dispenser bottle, single object, white background, product photography"),
    ("cosmetics_packaging", "Soap Dispenser",
     "Ceramic liquid soap dispenser",
     "ceramic white soap dispenser bottle with pump, single object, white background, product photography"),
    ("cosmetics_packaging", "Storage Cup",
     "Small cosmetics organizer cup",
     "small white ceramic cosmetics organizer cup, single object, white background, product photography"),

    # ── DESK ACCESSORIES ──────────────────────────────────────────────────
    ("desk_accessories", "Headphone Stand",
     "Minimal aluminum headphone stand",
     "minimalist aluminum headphone stand, single object centered, white background, product photography, studio lighting"),
    ("desk_accessories", "Cable Organizer",
     "Desk cable management bar",
     "white desk cable organizer bar with clips, single object, white background, product photography"),
    ("desk_accessories", "Pen Holder",
     "Geometric concrete pen holder",
     "geometric concrete pen holder, single object, white background, product photography, minimal design"),
    ("desk_accessories", "Phone Dock",
     "Angled wireless phone charging dock",
     "minimalist wood phone charging dock stand, single object, white background, product photography"),
    ("desk_accessories", "Card Holder",
     "Desktop business card display stand",
     "metal business card holder stand, single object, white background, product photography, brushed steel"),
    ("desk_accessories", "Monitor Riser",
     "Wooden monitor stand riser",
     "wooden monitor stand riser foot, single object, white background, product photography, light oak"),
    ("desk_accessories", "Catch-All Tray",
     "Leather-look desk catch-all tray",
     "minimal leather desk catch-all tray, single object, white background, product photography, dark brown"),
    ("desk_accessories", "USB Hub Dock",
     "Compact USB hub shell",
     "compact USB hub dock, single object, white background, product photography, matte black"),
    ("desk_accessories", "Sticky Note Holder",
     "Weighted sticky note block holder",
     "minimalist sticky note holder stand, single object, white background, product photography"),
    ("desk_accessories", "Mini Shelf",
     "Small desk shelf riser tier",
     "small two-tier desk shelf organizer, single object, white background, product photography, bamboo"),

    # ── GAMES & TOYS ──────────────────────────────────────────────────────
    ("games_toys", "Dice Tower",
     "Tabletop dice rolling tower",
     "wooden tabletop dice tower, single object centered, white background, product photography, dark walnut"),
    ("games_toys", "Chess Pawn",
     "Classic marble chess pawn piece",
     "white marble chess pawn piece, single object centered, white background, product photography, elegant"),
    ("games_toys", "Mini Figure",
     "Tabletop game miniature figure",
     "small painted tabletop miniature warrior figure, single object, white background, product photography"),
    ("games_toys", "Game Token",
     "Flat circular game token",
     "round wooden game token coin, single object, white background, product photography, top-down view"),
    ("games_toys", "Dice Tray",
     "Felt-lined dice rolling tray",
     "square dice rolling tray with dark felt interior, single object, white background, product photography"),
    ("games_toys", "Card Stand",
     "Playing card hand holder stand",
     "wooden playing card holder stand, single object, white background, product photography"),
    ("games_toys", "Controller Stand",
     "Game controller display stand",
     "minimalist game controller stand, single object, white background, product photography, matte black"),
    ("games_toys", "Board Game Insert",
     "Custom board game box organizer",
     "laser-cut wooden board game organizer insert tray, single object, white background, product photography"),
    ("games_toys", "Meeple Piece",
     "Wooden meeple game piece",
     "colorful wooden meeple game piece, single object, white background, product photography, red"),
    ("games_toys", "Tabletop Tile",
     "Hexagonal tabletop terrain tile",
     "hexagonal tabletop terrain tile, single object, white background, product photography, painted stone"),

    # ── INDUSTRIAL PARTS ──────────────────────────────────────────────────
    ("industrial_parts", "Spur Gear",
     "Precision plastic spur gear",
     "nylon spur gear mechanical component, single object, white background, product photography, industrial"),
    ("industrial_parts", "Hex Bolt Set",
     "M8 hex bolt and nut",
     "stainless steel hex bolt and nut, single object, white background, product photography, metallic hardware"),
    ("industrial_parts", "L-Bracket",
     "Reinforced steel mounting bracket",
     "steel L-bracket with mounting holes, single object, white background, product photography, industrial hardware"),
    ("industrial_parts", "Pipe Clamp",
     "Split pipe clamp fitting",
     "stainless steel pipe clamp fitting, single object, white background, product photography, metal"),
    ("industrial_parts", "Pulley Wheel",
     "Small guide pulley with bearing",
     "small V-groove pulley wheel, single object, white background, product photography, aluminum"),
    ("industrial_parts", "Knurled Knob",
     "Adjustment knob with grip texture",
     "black knurled adjustment knob, single object, white background, product photography, industrial metal"),
    ("industrial_parts", "Cable Gland",
     "Waterproof nylon cable gland",
     "black nylon cable gland fitting, single object, white background, product photography"),
    ("industrial_parts", "T-Slot Nut",
     "Aluminum extrusion T-slot nut",
     "aluminum T-slot nut for extrusion profile, single object, white background, product photography"),
    ("industrial_parts", "Snap Clip",
     "Plastic snap-fit assembly clip",
     "white plastic snap-fit assembly clip, single object, white background, product photography"),
    ("industrial_parts", "Hinge",
     "Small plastic living hinge",
     "small plastic barrel hinge, single object, white background, product photography"),

    # ── ABSTRACT DECOR ────────────────────────────────────────────────────
    ("abstract_decor", "Wave Sculpture",
     "Flowing frozen wave form",
     "abstract white ceramic wave sculpture, single object centered, white background, product photography, modern art"),
    ("abstract_decor", "Twisted Column",
     "Helix tower sculpture",
     "white twisted helix column sculpture, single object, white background, product photography, minimal modern"),
    ("abstract_decor", "Faceted Sphere",
     "Geometric faceted sphere",
     "gold metallic faceted geometric sphere, single object, white background, product photography"),
    ("abstract_decor", "Arc Sculpture",
     "Minimal curved arch form",
     "minimalist white concrete arc sculpture, single object, white background, product photography"),
    ("abstract_decor", "Pyramid Set",
     "Nested geometric pyramids",
     "set of nested white marble pyramids, single object, white background, product photography"),
    ("abstract_decor", "Cube Tower",
     "Stacked offset cube form",
     "stacked offset cube tower sculpture, white background, product photography, matte white ceramic"),
    ("abstract_decor", "Torus Ring",
     "Donut torus sculpture",
     "glossy white torus ring sculpture, single object, white background, product photography"),
    ("abstract_decor", "Fluid Form",
     "Organic flowing sculpture",
     "smooth organic fluid sculpture, white ceramic, single object, white background, product photography"),
    ("abstract_decor", "Diamond Crystal",
     "Cut crystal diamond form",
     "clear crystal diamond sculpture, single object, white background, product photography, glass"),
    ("abstract_decor", "Spiral Tower",
     "Upward spiral decorative piece",
     "white ceramic spiral tower sculpture, single object, white background, product photography"),

    # ── ARCHITECTURE MODELS ───────────────────────────────────────────────
    ("architecture_models", "Modern House",
     "Scale model of a modern house",
     "architectural scale model modern house, white plaster, single object, white background, product photography"),
    ("architecture_models", "Column Capital",
     "Classical Corinthian column capital",
     "white plaster classical column capital, single object, white background, product photography"),
    ("architecture_models", "Arch Bridge",
     "Scale arch bridge model",
     "white architectural scale model arch bridge, single object, white background, product photography"),
    ("architecture_models", "Dome Structure",
     "Geodesic dome roof model",
     "white plaster geodesic dome architectural model, single object, white background, product photography"),
    ("architecture_models", "Tower Block",
     "Abstract tower building model",
     "white cardboard architectural tower block model, single object, white background, product photography"),
    ("architecture_models", "Floor Plan Model",
     "3D raised floor plan model",
     "3D architectural floor plan model, white plaster, single object, white background, product photography"),
    ("architecture_models", "Facade Detail",
     "Building facade ornament piece",
     "architectural facade ornament detail model, white plaster, single object, white background, product photography"),
    ("architecture_models", "Spiral Staircase",
     "Scale spiral staircase model",
     "white resin architectural spiral staircase model, single object, white background, product photography"),
    ("architecture_models", "City Block",
     "Urban city block miniature",
     "architectural urban city block scale model, white foam, single object, white background, product photography"),
    ("architecture_models", "Window Frame",
     "Ornate window frame model",
     "ornate white plaster window frame architectural model, single object, white background, product photography"),
]


def load_pipeline():
    from diffusers import AutoPipelineForText2Image
    dtype = torch.float16 if DEVICE == "cuda" else torch.float32
    print("[ImageGen] Loading SDXL-Turbo…")
    print("  First run downloads ~6.7 GB from HuggingFace (one time only)")
    pipe = AutoPipelineForText2Image.from_pretrained(
        "stabilityai/sdxl-turbo",
        torch_dtype=dtype,
        variant="fp16" if DEVICE == "cuda" else None,
    ).to(DEVICE)
    if DEVICE == "cuda":
        pipe.enable_attention_slicing()
    print("[ImageGen] ✓ SDXL-Turbo ready")
    return pipe


def generate_one(pipe, prompt: str) -> Image.Image:
    """4-step SDXL-Turbo — ~2 s on RTX 4070."""
    result = pipe(
        prompt=prompt,
        num_inference_steps=4,
        guidance_scale=0.0,     # required for turbo mode
        width=IMG_SIZE,
        height=IMG_SIZE,
    )
    return result.images[0]


def build_library_json(catalogue) -> list:
    entries = []
    counter: dict[str, int] = {}
    for category, title, detail, _ in catalogue:
        counter[category] = counter.get(category, 0) + 1
        idx = counter[category]
        entries.append({
            "category":    category,
            "title":       title,
            "detail":      detail,
            "image_url":   f"/static/assets/inspiration/{category}/{category}_{idx:02d}.jpg",
            "source_url":  "",
            "source_title": "AI generated product reference",
        })
    return entries


def main():
    print("=" * 62)
    print("  PrintMind Inspiration Library Generator")
    print("=" * 62)

    # Create category directories
    cats = list(dict.fromkeys(c for c, *_ in CATALOGUE))
    for cat in cats:
        (INSPIRE_DIR / cat).mkdir(parents=True, exist_ok=True)

    # Load model
    try:
        pipe = load_pipeline()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        print("Fix: pip install diffusers accelerate transformers")
        return

    total   = len(CATALOGUE)
    counter: dict[str, int] = {}
    ok = 0

    for i, (category, title, detail, prompt) in enumerate(CATALOGUE, 1):
        counter[category] = counter.get(category, 0) + 1
        idx      = counter[category]
        filename = f"{category}_{idx:02d}.jpg"
        out_path = INSPIRE_DIR / category / filename

        # Skip if already exists (re-run safe)
        if out_path.exists():
            print(f"[{i:2d}/{total}] skip (exists): {filename}")
            ok += 1
            continue

        print(f"[{i:2d}/{total}] {category}/{filename}  '{title}'...", end="", flush=True)
        try:
            img = generate_one(pipe, prompt).convert("RGB")
            img.save(str(out_path), format="JPEG", quality=92)
            print("✓")
            ok += 1
        except Exception as e:
            print(f"FAILED: {e}")

    # Write library.json
    entries = build_library_json(CATALOGUE)
    with open(LIBRARY_JSON, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print()
    print(f"[Done] {ok}/{total} images written")
    print(f"[Done] library.json → {LIBRARY_JSON}")
    print()
    print("Restart the PrintMind server and hard-refresh the page.")


if __name__ == "__main__":
    main()