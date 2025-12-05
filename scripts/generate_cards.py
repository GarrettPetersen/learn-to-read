"""Generate flashcard images and print-ready sheets for the reading decks.

Outputs:
- build/cards/<deck-id>/fronts/*.png            (trim size)
- build/cards/<deck-id>/back.png                (trim size)
- build/publisher/<deck-id>/fronts/*.png        (with bleed)
- build/publisher/<deck-id>/back.png            (with bleed)
- build/print_sheets/<deck-id>/<side>/page-XX.* (front, back, back-mirrored)
"""
from __future__ import annotations

import argparse
import json
import math
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageColor, ImageDraw, ImageFont


# ---------------------------
# Core configuration helpers
# ---------------------------


def inches_to_px(value_in: float, dpi: int) -> int:
    return int(round(value_in * dpi))


@dataclass
class CardSpec:
    trim_width_px: int
    trim_height_px: int
    bleed_px: int
    background: Tuple[int, int, int]
    text_color: Tuple[int, int, int]

    @property
    def total_width_px(self) -> int:
        return self.trim_width_px + self.bleed_px * 2

    @property
    def total_height_px(self) -> int:
        return self.trim_height_px + self.bleed_px * 2


@dataclass
class PageSpec:
    width_px: int
    height_px: int
    rows: int
    cols: int
    margin_px: int
    gutter_px: int


# ---------------------------
# Text utilities
# ---------------------------


def load_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path), size=size)


def measure_segments(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont,
    segments: Sequence[Tuple[str, Tuple[int, int, int]]],
) -> Tuple[int, int]:
    """Return width/height of composed text using font metrics for stable vertical centering."""
    text = "".join(seg[0] for seg in segments)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    ascent, descent = font.getmetrics()
    height = ascent + descent
    return width, height


def fit_font_size(
    draw: ImageDraw.ImageDraw,
    font_path: Path,
    segments: Sequence[Tuple[str, Tuple[int, int, int]]],
    max_width: int,
    max_height: int,
    floor: int = 24,
) -> ImageFont.FreeTypeFont:
    """Binary search the largest font that fits."""
    low, high = floor, max(segments[0][0].__len__() * max_width, max_height)
    best_font = load_font(font_path, size=floor)
    while low <= high:
        mid = (low + high) // 2
        font = load_font(font_path, size=mid)
        w, h = measure_segments(draw, font, segments)
        if w <= max_width and h <= max_height:
            best_font = font
            low = mid + 1
        else:
            high = mid - 1
    return best_font


def draw_segments(
    draw: ImageDraw.ImageDraw,
    position: Tuple[int, int],
    font: ImageFont.FreeTypeFont,
    segments: Sequence[Tuple[str, Tuple[int, int, int]]],
) -> None:
    x, y = position
    for text, color in segments:
        draw.text((x, y), text, fill=color, font=font)
        advance = draw.textlength(text, font=font)
        x += int(round(advance))


# ---------------------------
# Rendering helpers
# ---------------------------


def parse_color(value: str) -> Tuple[int, int, int]:
    return ImageColor.getrgb(value)


def slugify(text: str) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in text.lower())
    return "-".join(filter(None, safe.split("-")))


def compose_segments(card: Dict, deck_color: Tuple[int, int, int], default_color: Tuple[int, int, int]) -> List[Tuple[str, Tuple[int, int, int]]]:
    raw_segments = card.get("segments")
    if raw_segments:
        segments: List[Tuple[str, Tuple[int, int, int]]] = []
        for seg in raw_segments:
            text = seg["text"]
            color = parse_color(seg.get("color", None)) if seg.get("color") else deck_color
            segments.append((text, color))
        return segments
    text = card.get("text", "").strip()
    return [(text, default_color)]


def render_front(
    card: Dict,
    deck: Dict,
    card_spec: CardSpec,
    font_path: Path,
    with_bleed: bool,
) -> Image.Image:
    bleed = card_spec.bleed_px if with_bleed else 0
    width = card_spec.trim_width_px + bleed * 2
    height = card_spec.trim_height_px + bleed * 2

    img = Image.new("RGB", (width, height), card_spec.background)
    draw = ImageDraw.Draw(img)

    bar_height = int(card_spec.trim_height_px * 0.22)
    bar_top = height - bar_height
    bar_color = parse_color(deck["color"])
    draw.rectangle([0, bar_top, width, height], fill=bar_color)

    padding = int(card_spec.trim_height_px * 0.08)
    safe_left = bleed + padding
    safe_right = width - bleed - padding
    safe_top = bleed + padding
    safe_bottom = bar_top - padding

    segments = compose_segments(card, deck_color=bar_color, default_color=card_spec.text_color)
    max_width = safe_right - safe_left
    max_height = safe_bottom - safe_top
    font = fit_font_size(draw, font_path, segments, max_width, max_height)
    text_width, text_height = measure_segments(draw, font, segments)
    text_x = safe_left + (max_width - text_width) // 2
    text_y = safe_top + (max_height - text_height) // 2
    draw_segments(draw, (text_x, text_y), font, segments)

    return img


def render_back(
    deck: Dict,
    card_spec: CardSpec,
    font_path: Path,
    with_bleed: bool,
) -> Image.Image:
    bleed = card_spec.bleed_px if with_bleed else 0
    width = card_spec.trim_width_px + bleed * 2
    height = card_spec.trim_height_px + bleed * 2

    background = parse_color(deck["color"])
    img = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(img)

    text = deck.get("back_text", deck["label"])
    padding = int(card_spec.trim_height_px * 0.1)
    safe_left = bleed + padding
    safe_right = width - bleed - padding
    safe_top = bleed + padding
    safe_bottom = height - bleed - padding

    segments = [(text, (255, 255, 255))]
    max_width = safe_right - safe_left
    max_height = safe_bottom - safe_top
    font = fit_font_size(draw, font_path, segments, max_width, max_height)
    text_width, text_height = measure_segments(draw, font, segments)
    text_x = safe_left + (max_width - text_width) // 2
    text_y = safe_top + (max_height - text_height) // 2
    draw_segments(draw, (text_x, text_y), font, segments)

    return img


# ---------------------------
# Layout helpers
# ---------------------------


def chunk(seq: Sequence, size: int) -> List[Sequence]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def render_sheet(
    images: Sequence[Path],
    card_size: Tuple[int, int],
    page_spec: PageSpec,
    name: str,
    mirrored: bool = False,
) -> List[Image.Image]:
    card_w, card_h = card_size
    per_page = page_spec.rows * page_spec.cols
    sheets: List[Image.Image] = []
    for page_images in chunk(images, per_page):
        sheet = Image.new("RGB", (page_spec.width_px, page_spec.height_px), "white")
        for idx, img_path in enumerate(page_images):
            img = Image.open(img_path)
            row = idx // page_spec.cols
            col = idx % page_spec.cols
            if mirrored:
                col = page_spec.cols - 1 - col
            x = page_spec.margin_px + col * (card_w + page_spec.gutter_px)
            y = page_spec.margin_px + row * (card_h + page_spec.gutter_px)
            sheet.paste(img, (x, y))
        sheets.append(sheet)
    return sheets


def save_sheet_images_and_pdf(sheets: List[Image.Image], out_dir: Path, base_name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, sheet in enumerate(sheets, start=1):
        png_path = out_dir / f"{base_name}-page-{i:02d}.png"
        sheet.save(png_path, dpi=sheet.info.get("dpi", (300, 300)))
    if sheets:
        pdf_path = out_dir / f"{base_name}.pdf"
        rgb_sheets = [s.convert("RGB") for s in sheets]
        rgb_sheets[0].save(pdf_path, save_all=True, append_images=rgb_sheets[1:], resolution=300)


# ---------------------------
# CLI and orchestration
# ---------------------------


def load_config(config_path: Path) -> Dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_font_path(config: Dict, repo_root: Path) -> Path:
    font_path = Path(config["font"]["path"])
    if not font_path.is_absolute():
        font_path = repo_root / font_path
    if not font_path.exists():
        raise FileNotFoundError(f"Font not found at {font_path}")
    return font_path


def build_specs(config: Dict) -> Tuple[CardSpec, PageSpec]:
    card_cfg = config["card"]
    page_cfg = config["page"]
    dpi = int(card_cfg.get("dpi", page_cfg.get("dpi", 300)))
    card_spec = CardSpec(
        trim_width_px=inches_to_px(card_cfg["trim_width_in"], dpi),
        trim_height_px=inches_to_px(card_cfg["trim_height_in"], dpi),
        bleed_px=inches_to_px(card_cfg.get("bleed_in", 0), dpi),
        background=parse_color(card_cfg.get("background", "#FFFFFF")),
        text_color=parse_color(card_cfg.get("text_color", "#111111")),
    )
    page_spec = PageSpec(
        width_px=inches_to_px(page_cfg["width_in"], page_cfg.get("dpi", dpi)),
        height_px=inches_to_px(page_cfg["height_in"], page_cfg.get("dpi", dpi)),
        rows=page_cfg["rows"],
        cols=page_cfg["cols"],
        margin_px=inches_to_px(page_cfg.get("margin_in", 0.0), page_cfg.get("dpi", dpi)),
        gutter_px=inches_to_px(page_cfg.get("gutter_in", 0.0), page_cfg.get("dpi", dpi)),
    )
    return card_spec, page_spec


def generate_deck(
    deck: Dict,
    card_spec: CardSpec,
    page_spec: PageSpec,
    font_path: Path,
    out_root: Path,
) -> None:
    deck_id = deck["id"]
    deck_dir = out_root / "cards" / deck_id
    deck_dir.mkdir(parents=True, exist_ok=True)

    publisher_dir = out_root / "publisher" / deck_id
    publisher_dir.mkdir(parents=True, exist_ok=True)

    fronts_dir = deck_dir / "fronts"
    fronts_dir.mkdir(exist_ok=True)
    publisher_fronts_dir = publisher_dir / "fronts"
    publisher_fronts_dir.mkdir(exist_ok=True)

    # Render back once
    back_trim = render_back(deck, card_spec, font_path, with_bleed=False)
    back_trim_path = deck_dir / "back.png"
    back_trim.save(back_trim_path)

    back_bleed = render_back(deck, card_spec, font_path, with_bleed=True)
    back_bleed_path = publisher_dir / "back.png"
    back_bleed.save(back_bleed_path)

    front_paths: List[Path] = []
    for idx, card in enumerate(deck["cards"], start=1):
        name = card.get("text") or "".join(seg["text"] for seg in card.get("segments", []))
        slug = slugify(name or f"{deck_id}-{idx}")

        front_trim = render_front(card, deck, card_spec, font_path, with_bleed=False)
        front_trim_path = fronts_dir / f"{idx:03d}-{slug}.png"
        front_trim.save(front_trim_path)
        front_paths.append(front_trim_path)

        front_bleed = render_front(card, deck, card_spec, font_path, with_bleed=True)
        front_bleed_path = publisher_fronts_dir / f"{idx:03d}-{slug}.png"
        front_bleed.save(front_bleed_path)

    # Print sheets (trim size) for fronts and backs
    print_dir = out_root / "print_sheets" / deck_id
    front_sheets = render_sheet(
        images=front_paths,
        card_size=(card_spec.trim_width_px, card_spec.trim_height_px),
        page_spec=page_spec,
        name="front",
        mirrored=False,
    )
    save_sheet_images_and_pdf(front_sheets, print_dir / "front", base_name="front")

    back_images = [back_trim_path] * len(front_paths)
    back_sheets = render_sheet(
        images=back_images,
        card_size=(card_spec.trim_width_px, card_spec.trim_height_px),
        page_spec=page_spec,
        name="back",
        mirrored=False,
    )
    save_sheet_images_and_pdf(back_sheets, print_dir / "back", base_name="back")

    mirrored_back_sheets = render_sheet(
        images=back_images,
        card_size=(card_spec.trim_width_px, card_spec.trim_height_px),
        page_spec=page_spec,
        name="back-mirrored",
        mirrored=True,
    )
    save_sheet_images_and_pdf(mirrored_back_sheets, print_dir / "back-mirrored", base_name="back-mirrored")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate flashcard images, print sheets, and publisher assets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Example:
              python scripts/generate_cards.py --config data/decks.json --output build
            """
        ),
    )
    parser.add_argument("--config", type=Path, default=Path("data/decks.json"), help="Path to deck configuration JSON.")
    parser.add_argument("--output", type=Path, default=Path("build"), help="Output directory for generated assets.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    config = load_config(repo_root / args.config if not args.config.is_absolute() else args.config)
    font_path = ensure_font_path(config, repo_root)
    card_spec, page_spec = build_specs(config)

    for deck in config["decks"]:
        generate_deck(deck, card_spec, page_spec, font_path, out_root=args.output)
    print(f"Generated decks into {args.output.resolve()}")


if __name__ == "__main__":
    main()

