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


def tokenize_with_phonemes(
    text: str,
    phoneme_colors: Dict[str, str],
    default_color: Tuple[int, int, int],
) -> List[Tuple[str, Tuple[int, int, int]]]:
    """Split text into segments, coloring configured phonemes and leaving others default."""
    if not text:
        return []
    lower = text.lower()
    # Sort phonemes longest-first to catch trigraphs before digraphs.
    phonemes = sorted(phoneme_colors.keys(), key=len, reverse=True)
    segments: List[Tuple[str, Tuple[int, int, int]]] = []
    i = 0
    while i < len(text):
        matched = None
        for phoneme in phonemes:
            if lower.startswith(phoneme, i):
                matched = phoneme
                break
        if matched:
            color = parse_color(phoneme_colors[matched])
            span = len(matched)
            segments.append((text[i : i + span], color))
            i += span
        else:
            segments.append((text[i], default_color))
            i += 1
    return segments


def compose_segments(
    card: Dict,
    deck_color: Tuple[int, int, int],
    default_color: Tuple[int, int, int],
    phoneme_colors: Optional[Dict[str, str]] = None,
) -> List[Tuple[str, Tuple[int, int, int]]]:
    raw_segments = card.get("segments")
    if raw_segments:
        segments: List[Tuple[str, Tuple[int, int, int]]] = []
        for seg in raw_segments:
            text = seg["text"]
            color = parse_color(seg.get("color", None)) if seg.get("color") else deck_color
            segments.append((text, color))
        return segments
    text = card.get("text", "").strip()
    if phoneme_colors:
        return tokenize_with_phonemes(text, phoneme_colors, default_color)
    return [(text, default_color)]


def render_front(
    card: Dict,
    deck: Dict,
    card_spec: CardSpec,
    font_path: Path,
    phoneme_colors: Optional[Dict[str, str]],
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

    segments = compose_segments(
        card,
        deck_color=bar_color,
        default_color=card_spec.text_color,
        phoneme_colors=phoneme_colors,
    )
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

    deck_color = parse_color(deck["color"])
    background = (255, 255, 255)
    img = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(img)

    # Light cross-hatch to save ink while keeping deck identity.
    _draw_hatch(draw, width, height, color=deck_color)

    text = deck.get("back_text", deck["label"])
    padding = int(card_spec.trim_height_px * 0.1)
    safe_left = bleed + padding
    safe_right = width - bleed - padding
    safe_top = bleed + padding
    safe_bottom = height - bleed - padding

    segments = [(text, deck_color)]
    max_width = safe_right - safe_left
    max_height = safe_bottom - safe_top
    font = fit_font_size(draw, font_path, segments, max_width, max_height)
    text_width, text_height = measure_segments(draw, font, segments)
    text_x = safe_left + (max_width - text_width) // 2
    text_y = safe_top + (max_height - text_height) // 2

    # Add a white box behind the deck text for readability.
    pad = int(card_spec.trim_height_px * 0.04)
    bg_box = [
        text_x - pad,
        text_y - pad,
        text_x + text_width + pad,
        text_y + text_height + pad,
    ]
    draw.rectangle(bg_box, fill="white")
    draw_segments(draw, (text_x, text_y), font, segments)

    return img


def _draw_hatch(draw: ImageDraw.ImageDraw, width: int, height: int, color: Tuple[int, int, int]) -> None:
    """Draw a sparse diagonal hatch pattern to reduce ink coverage."""
    spacing = max(8, min(width, height) // 20)  # adaptive spacing
    thickness = 2
    # Diagonal down-right
    for offset in range(-height, width + height, spacing):
        start = (offset, 0)
        end = (offset + height, height)
        draw.line([start, end], fill=color, width=thickness)
    # Diagonal down-left
    for offset in range(0, width + height, spacing):
        start = (offset, 0)
        end = (offset - height, height)
        draw.line([start, end], fill=color, width=thickness)


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
    grid_w = page_spec.cols * card_w + (page_spec.cols - 1) * page_spec.gutter_px
    grid_h = page_spec.rows * card_h + (page_spec.rows - 1) * page_spec.gutter_px
    offset_x = page_spec.margin_px + max(0, (page_spec.width_px - 2 * page_spec.margin_px - grid_w) // 2)
    offset_y = page_spec.margin_px + max(0, (page_spec.height_px - 2 * page_spec.margin_px - grid_h) // 2)
    sheets: List[Image.Image] = []
    for page_images in chunk(images, per_page):
        sheet = Image.new("RGB", (page_spec.width_px, page_spec.height_px), "white")
        draw = ImageDraw.Draw(sheet)
        for idx, img_path in enumerate(page_images):
            img = Image.open(img_path)
            row = idx // page_spec.cols
            col = idx % page_spec.cols
            if mirrored:
                col = page_spec.cols - 1 - col
            x = offset_x + col * (card_w + page_spec.gutter_px)
            y = offset_y + row * (card_h + page_spec.gutter_px)
            sheet.paste(img, (x, y))
        _draw_cut_lines(draw, page_spec, card_size, offset_x, offset_y)
        sheets.append(sheet)
    return sheets


def _draw_cut_lines(
    draw: ImageDraw.ImageDraw,
    page_spec: PageSpec,
    card_size: Tuple[int, int],
    offset_x: int,
    offset_y: int,
) -> None:
    """Draw light cut lines along card edges to guide trimming."""
    card_w, card_h = card_size
    x_edges = set()
    y_edges = set()
    for col in range(page_spec.cols):
        x = offset_x + col * (card_w + page_spec.gutter_px)
        x_edges.add(x)
        x_edges.add(x + card_w)
    for row in range(page_spec.rows):
        y = offset_y + row * (card_h + page_spec.gutter_px)
        y_edges.add(y)
        y_edges.add(y + card_h)

    min_x = min(x_edges, default=offset_x)
    max_x = max(x_edges, default=page_spec.width_px - offset_x)
    min_y = min(y_edges, default=offset_y)
    max_y = max(y_edges, default=page_spec.height_px - offset_y)

    line_color = "#B0B0B0"
    line_width = 1
    for x in sorted(x_edges):
        draw.line([(x, min_y), (x, max_y)], fill=line_color, width=line_width)
    for y in sorted(y_edges):
        draw.line([(min_x, y), (max_x, y)], fill=line_color, width=line_width)


def save_sheet_images_and_pdf(sheets: List[Image.Image], out_dir: Path, base_name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, sheet in enumerate(sheets, start=1):
        png_path = out_dir / f"{base_name}-page-{i:02d}.png"
        sheet.save(png_path, dpi=sheet.info.get("dpi", (300, 300)))
    if sheets:
        pdf_path = out_dir / f"{base_name}.pdf"
        rgb_sheets = [s.convert("RGB") for s in sheets]
        rgb_sheets[0].save(pdf_path, save_all=True, append_images=rgb_sheets[1:], resolution=300)


def save_alternating_pdf(front_sheets: List[Image.Image], back_sheets: List[Image.Image], out_dir: Path, base_name: str) -> None:
    """Save a single PDF with pages alternating front/back for print submission."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not front_sheets or not back_sheets:
        return
    count = min(len(front_sheets), len(back_sheets))
    pages: List[Image.Image] = []
    for i in range(count):
        pages.append(front_sheets[i].convert("RGB"))
        pages.append(back_sheets[i].convert("RGB"))
    pdf_path = out_dir / f"{base_name}.pdf"
    pages[0].save(pdf_path, save_all=True, append_images=pages[1:], resolution=300)


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
    phoneme_colors: Optional[Dict[str, str]],
    out_root: Path,
) -> Tuple[List[Path], List[Path], List[Image.Image], List[Image.Image]]:
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
    back_paths: List[Path] = []
    for idx, card in enumerate(deck["cards"], start=1):
        name = card.get("text") or "".join(seg["text"] for seg in card.get("segments", []))
        slug = slugify(name or f"{deck_id}-{idx}")

        front_trim = render_front(card, deck, card_spec, font_path, phoneme_colors, with_bleed=False)
        front_trim_path = fronts_dir / f"{idx:03d}-{slug}.png"
        front_trim.save(front_trim_path)
        front_paths.append(front_trim_path)
        back_paths.append(back_trim_path)

        front_bleed = render_front(card, deck, card_spec, font_path, phoneme_colors, with_bleed=True)
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

    # Combined alternating PDF: front page 1, back page 1, etc. for easy print submission.
    save_alternating_pdf(front_sheets, back_sheets, print_dir / "front-back", base_name="front-back")

    return front_paths, back_paths, front_sheets, back_sheets


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

    phoneme_colors = config.get("phoneme_colors", {})
    all_front_sheets: List[Image.Image] = []
    all_back_sheets: List[Image.Image] = []
    all_card_fronts: List[Path] = []
    all_card_backs: List[Path] = []
    for deck in config["decks"]:
        front_paths, back_paths, front_sheets, back_sheets = generate_deck(
            deck, card_spec, page_spec, font_path, phoneme_colors, out_root=args.output
        )
        all_front_sheets.extend(front_sheets)
        all_back_sheets.extend(back_sheets)
        all_card_fronts.extend(front_paths)
        all_card_backs.extend(back_paths)

    # Combined all-deck alternating PDF.
    if all_card_fronts and all_card_backs:
        combined_dir = args.output / "print_sheets" / "all-decks"
        combined_front_sheets = render_sheet(
            images=all_card_fronts,
            card_size=(card_spec.trim_width_px, card_spec.trim_height_px),
            page_spec=page_spec,
            name="front",
            mirrored=False,
        )
        combined_back_sheets = render_sheet(
            images=all_card_backs,
            card_size=(card_spec.trim_width_px, card_spec.trim_height_px),
            page_spec=page_spec,
            name="back",
            mirrored=False,
        )
        save_sheet_images_and_pdf(combined_front_sheets, combined_dir / "front", base_name="front")
        save_sheet_images_and_pdf(combined_back_sheets, combined_dir / "back", base_name="back")
        save_alternating_pdf(combined_front_sheets, combined_back_sheets, combined_dir, base_name="all-front-back")
    print(f"Generated decks into {args.output.resolve()}")


if __name__ == "__main__":
    main()

