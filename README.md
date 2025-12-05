# Learn-to-Read Cards

Flashcard-style reading decks inspired by the Engelmann sequence. Generates:
- Individual card PNGs (fronts and backs) at trim size.
- Publisher assets with bleed for each card.
- Print-and-play sheets (front, back, and mirrored-back layouts) ready for duplex printing and cutting.

## Requirements
- Python 3.10+
- Pip dependencies: `pip install -r requirements.txt`
- Lexend font is vendored in `Lexend/` and used automatically.

## How to build everything
```bash
python scripts/generate_cards.py --config data/decks.json --output build
```

After running, you'll find:
- `build/cards/<deck-id>/fronts/*.png` – trim-size fronts.
- `build/cards/<deck-id>/back.png` – trim-size back (shared).
- `build/publisher/<deck-id>/fronts/*.png` – with 0.125" bleed.
- `build/publisher/<deck-id>/back.png` – with bleed.
- `build/print_sheets/<deck-id>/front|back|back-mirrored/` – 8.5"x11" sheets as PNG and PDF.

Use `front` + `back` for typical duplex printing (flip on long edge). If your printer flips differently, try `back-mirrored`.

## Card specs
- Trim: 2.5" x 3.5" (poker size)
- Bleed: 0.125" each side (publisher assets end up 2.75" x 3.75")
- DPI: 300
- Front: white background, deck-colored bar along the bottom, large centered text.
- Back: solid deck color with white deck label text.

## Page layout for print-and-play
- Page: 8.5" x 11", 300 DPI
- Grid: 3 cols x 3 rows (9 cards/page), zero gutter, 0.25" page margin.

## Editing decks
Decks are defined in `data/decks.json`.

Key fields:
- `card` / `page`: global sizing, bleed, colors, dpi.
- `font.path`: path to the Lexend TTF (relative paths are resolved from repo root).
- `decks`: array of decks. Each deck has:
  - `id`: folder-safe identifier.
  - `label` / `back_text`: text for backs.
  - `color`: hex color used for backs and the front bar.
  - `cards`: array of cards.

Card formats:
- Simple text card: `{ "text": "m" }`
- Multi-color segments (for digraph highlighting): 
  ```json
  {
    "segments": [
      { "text": "sh", "color": "#D7263D" },
      { "text": "ip" }
    ]
  }
  ```
  If `color` is omitted on a segment, the deck color is used.

## Current deck progression (rough Engelmann-inspired)
- Deck 1: early consonants/vowel (m, s, a, t, r, n)
- Deck 2: adds f, o, l, w, i, j
- Deck 3: CVC words using prior letters
- Deck 4: introduces h, e, b, k, g, v, p, d plus starter words
- Deck 5: common digraphs (sh, ch, th, wh, ng) with highlighted words

Feel free to reshuffle or expand the JSON—rerun the script to regenerate assets.

