"""
LAYOUT — the geometry half of the Reader (CF-49).

L1 pulled a flat string out of a PDF. That works only while documents are one
column of prose. Real closeout reports put facts in tables, split pages into
columns, and drop figures in the middle — and a top-to-bottom read of a
two-column page interleaves the two columns into nonsense.

This module reads a page the way a person does:

    words  ->  lines  ->  columns  ->  reading order
                      ->  tables (ruled and whitespace-aligned)
                      ->  labelled fields
                      ->  numbered sections

Every element carries the box it came from. That is deliberate: the boxes are
what CF-50 needs next sprint to say *where on the page* a fact was found,
rather than just which page.

Nothing here guesses. If a label is not on the page, it is not in the output.
"""
import re

# Two words closer than this horizontally belong to the same cell; a wider gap
# is a column boundary. Body text here runs ~10pt, where an ordinary space is
# about 2-3pt, so 12pt is comfortably past "just a space".
CELL_GAP = 12.0

# Words whose tops differ by less than this are on the same line.
LINE_TOLERANCE = 3.0

# A vertical whitespace channel must be at least this wide to count as a gutter
# between columns rather than an accident of ragged text.
MIN_GUTTER = 18.0

# Cell starts within this many points of each other count as the same column.
COLUMN_ALIGN_TOLERANCE = 6.0

# Table cells are short. Prose is not. This is what stops a two-column page of
# paragraphs from being mistaken for a table with two columns of cells.
MAX_CELL_CHARS = 45

# An unrecognised label is only kept if it actually looks like a label rather
# than a sentence that happened to contain a colon.
MAX_LABEL_WORDS = 4

# Labels we recognise in a closeout header, mapped to the names the rest of
# CaseForge uses. Unknown labels are still captured, under their own slug.
FIELD_LABELS = {
    "engagement id": "id",
    "client": "client",
    "client profile": "client_type",
    "sector / domain": "domain",
    "sector/domain": "domain",
    "domain": "domain",
    "sector": "domain",
    "region": "region",
    "team size": "team_size",
    "duration": "duration_months",
    "delivered": "delivered",
}

# Numbered headings: "1. The Challenge", "4, Outcomes" (OCR turns dots into
# commas often enough that it is worth accepting both).
SECTION_HEADING = re.compile(r"^\s*(\d{1,2})\s*[.,)]\s+(.{2,60})$")

LABEL_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z /_-]{1,30}?)\s*:\s*(.+?)\s*$")


# ---------------------------------------------------------------------------
# words -> lines
# ---------------------------------------------------------------------------

def group_words_into_rows(words):
    """
    Cluster words by vertical position into raw rows — everything printed at
    the same height, whichever column it is in.

    These are not yet reading-order lines: on a two-column page one row holds
    the left column's line AND the right column's line. Splitting them is the
    job of group_lines(), once the gutters are known.
    """
    rows = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        for row in rows:
            if abs(row["top"] - word["top"]) <= LINE_TOLERANCE:
                row["words"].append(word)
                break
        else:
            rows.append({"top": word["top"], "words": [word]})

    for row in rows:
        row["words"].sort(key=lambda w: w["x0"])
    return sorted(rows, key=lambda r: r["top"])


def _as_line(words, column):
    ws = sorted(words, key=lambda w: w["x0"])
    return {
        "words": ws,
        "column": column,
        "text": " ".join(w["text"] for w in ws),
        "bbox": (min(w["x0"] for w in ws), min(w["top"] for w in ws),
                 max(w["x1"] for w in ws), max(w["bottom"] for w in ws)),
    }


def group_lines(words, gutters):
    """
    Turn words into reading-order lines, split at the gutters.

    A row that has words on both sides of a gutter is really two lines, one per
    column — merging them is precisely the mistake that turns a two-column page
    into interleaved nonsense. A row containing a word that straddles a gutter
    is genuinely full-width (a banner or a spanning heading), so it stays whole
    and is marked as spanning with column = None.
    """
    lines = []
    for row in group_words_into_rows(words):
        straddles = any(w["x0"] < g_end and w["x1"] > g_start
                        for w in row["words"] for g_start, g_end in gutters)
        if straddles or not gutters:
            lines.append(_as_line(row["words"], None))
            continue

        by_column = {}
        for word in row["words"]:
            index = sum(1 for g_start, _ in gutters if word["x0"] >= g_start)
            by_column.setdefault(index, []).append(word)
        for index in sorted(by_column):
            lines.append(_as_line(by_column[index], index))

    return sorted(lines, key=lambda l: (l["bbox"][1], l["bbox"][0]))


def split_line_into_cells(line):
    """
    Split one line wherever the horizontal gap is wide enough to be a column
    boundary rather than a space. Returns a list of
    {"text": str, "bbox": (...)}.
    """
    cells, current = [], [line["words"][0]] if line["words"] else []
    for previous, word in zip(line["words"], line["words"][1:]):
        if word["x0"] - previous["x1"] > CELL_GAP:
            cells.append(current)
            current = [word]
        else:
            current.append(word)
    if current:
        cells.append(current)

    return [{
        "text": " ".join(w["text"] for w in ws),
        "bbox": (min(w["x0"] for w in ws), min(w["top"] for w in ws),
                 max(w["x1"] for w in ws), max(w["bottom"] for w in ws)),
    } for ws in cells]


# ---------------------------------------------------------------------------
# columns
# ---------------------------------------------------------------------------

def find_gutters(words, page_width):
    """
    Find the vertical whitespace channels that separate columns.

    Measured from the words themselves, per row: for each thin vertical strip of
    the page, count how many rows put any word in it. A gutter is a strip that
    almost every row leaves empty. Counting rows rather than words is what lets
    a single full-width banner cross the channel without hiding it — one row
    disagreeing is not enough to outvote twenty that agree.

    Returns a list of (x_start, x_end), left to right.
    """
    rows = group_words_into_rows(words)
    if len(rows) < 3:
        return []

    step = 2.0
    bins = int(page_width // step) + 2
    hits = [0] * bins
    for row in rows:
        covered = set()
        for word in row["words"]:
            for b in range(int(word["x0"] // step),
                           min(int(word["x1"] // step) + 1, bins)):
                covered.add(b)
        for b in covered:
            hits[b] += 1

    threshold = int(len(rows) * 0.12)      # tolerate the odd spanning line

    channels, run_start = [], None
    for b in range(bins):
        empty = hits[b] <= threshold
        if empty and run_start is None:
            run_start = b
        elif not empty and run_start is not None:
            channels.append((run_start * step, b * step))
            run_start = None
    if run_start is not None:
        channels.append((run_start * step, bins * step))

    # The margins are whitespace too, but they are not gutters: a gutter has
    # text on both sides of it.
    text_left = min(w["x0"] for w in words)
    text_right = max(w["x1"] for w in words)
    return [(a, b) for a, b in channels
            if b - a >= MIN_GUTTER and a > text_left and b < text_right]


def reading_order(lines, gutters):
    """
    Put the lines in the order a human would read them.

    Spanning lines act as horizontal rules: everything between two of them is
    one band, and inside a band we read column 1 top to bottom, then column 2,
    and so on. Without this, a two-column page reads as alternating fragments
    of two unrelated sentences.
    """
    if not gutters:
        return sorted(lines, key=lambda l: (l["bbox"][1], l["bbox"][0]))

    ordered, band = [], []

    def flush():
        if band:
            ordered.extend(sorted(band, key=lambda l: (l["column"],
                                                       l["bbox"][1])))
            band.clear()

    for line in sorted(lines, key=lambda l: l["bbox"][1]):
        if line["column"] is None:
            flush()
            ordered.append(line)
        else:
            band.append(line)
    flush()
    return ordered


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------

def find_ruled_tables(page):
    """Tables drawn with actual lines — pdfplumber does this well."""
    tables = []
    try:
        found = page.find_tables({"vertical_strategy": "lines",
                                  "horizontal_strategy": "lines"})
    except Exception:
        return tables

    for table in found:
        rows = [[(cell or "").strip() for cell in row]
                for row in table.extract()]
        rows = [r for r in rows if any(r)]
        if len(rows) >= 2:
            tables.append({"kind": "ruled", "bbox": tuple(table.bbox),
                           "rows": rows})
    return tables


def find_unruled_tables(lines):
    """
    Tables held together by alignment rather than ink.

    Most business documents lay out a table with tabs and never draw a single
    line, so pdfplumber sees only text. What makes it a table is that several
    consecutive lines start their cells at the *same* x positions. That is what
    we look for — and requiring the alignment to repeat is what stops ordinary
    prose from being mistaken for a table.
    """
    rows = []
    for line in lines:
        cells = split_line_into_cells(line)
        rows.append((line, cells) if len(cells) >= 2 else (line, None))

    tables, run = [], []

    def starts(cells):
        return [c["bbox"][0] for c in cells]

    def aligned(a, b):
        if len(a) != len(b):
            return False
        return all(abs(x - y) <= COLUMN_ALIGN_TOLERANCE for x, y in zip(a, b))

    def flush():
        body = [[c["text"] for c in cells] for _, cells in run]
        # Cells are short by nature. If these "cells" are sentences, this is a
        # multi-column paragraph, not a table.
        short = all(len(text) <= MAX_CELL_CHARS for row in body for text in row)
        if len(run) >= 2 and short:
            xs = [c["bbox"] for _, cells in run for c in cells]
            tables.append({
                "kind": "unruled",
                "bbox": (min(b[0] for b in xs), min(b[1] for b in xs),
                         max(b[2] for b in xs), max(b[3] for b in xs)),
                "rows": body,
            })
        run.clear()

    for line, cells in rows:
        if cells is None:
            flush()
            continue
        if run and aligned(starts(run[-1][1]), starts(cells)):
            run.append((line, cells))
        else:
            flush()
            run.append((line, cells))
    flush()
    return tables


# ---------------------------------------------------------------------------
# fields and sections
# ---------------------------------------------------------------------------

def _normalise(label):
    """
    Map a printed label to the name the rest of CaseForge uses.

    An unfamiliar label is still kept — documents vary, and dropping a fact
    because we did not anticipate its label would be worse. But it has to look
    like a label: a whole sentence that happens to contain a colon is not one,
    and inventing a field out of it would put junk into the record.
    """
    key = re.sub(r"\s+", " ", label.strip().lower())
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    if len(key.split()) > MAX_LABEL_WORDS or len(key) > 30:
        return None
    if not re.match(r"^[a-z][a-z /_-]*$", key):
        return None                       # digits, punctuation: not a label
    return re.sub(r"[^a-z0-9]+", "_", key).strip("_") or None


def _typed(key, value):
    """team_size '14 people' -> 14; duration '11 months' -> 11; else as-is."""
    if key in ("team_size", "duration_months"):
        m = re.search(r"\d+", value)
        return int(m.group()) if m else value
    return value


def extract_fields(lines, tables, page_number):
    """
    Pull "Label: value" facts out of the page — from ordinary lines and from
    two-column tables, because the same header block is written both ways in
    different documents.

    Every field records the box it was read from, so a later sprint can point
    at the exact region instead of the whole page.
    """
    fields = {}

    def add(label, value, bbox):
        key = _normalise(label)
        if not key or not value or key in fields:
            return                      # first occurrence wins
        fields[key] = {
            "value": _typed(key, value),
            "raw": value,
            "label": label.strip(),
            "page": page_number,
            "bbox": [round(v, 1) for v in bbox],
        }

    for line in lines:
        # A label:value line has its own cells when it sits in a table-like
        # header, so try cells first and fall back to the whole line.
        cells = split_line_into_cells(line)
        if len(cells) == 2 and cells[0]["text"].rstrip().endswith(":"):
            add(cells[0]["text"].rstrip(":"), cells[1]["text"],
                (cells[0]["bbox"][0], cells[0]["bbox"][1],
                 cells[1]["bbox"][2], cells[1]["bbox"][3]))
            continue
        m = LABEL_LINE.match(line["text"])
        if m:
            add(m.group(1), m.group(2), line["bbox"])

    # A two-column table is often the header block written as a grid. Only rows
    # whose left cell is genuinely a label count — otherwise every row of every
    # two-column table would become a field.
    for table in tables:
        for row in table["rows"]:
            if len(row) != 2 or not row[0] or not row[1]:
                continue
            label = row[0].rstrip(":")
            looks_like_label = (row[0].rstrip().endswith(":")
                                or label.strip().lower() in FIELD_LABELS)
            if looks_like_label:
                add(label, row[1], table["bbox"])

    return fields


def extract_sections(ordered_lines):
    """
    Split the body into its numbered sections ("1. The Challenge", ...).

    The closeouts always use this shape, and keeping the text grouped by
    heading is what lets the next stage ask for "the challenge" rather than
    hunting through one long string.
    """
    sections, current = [], None
    for line in ordered_lines:
        m = SECTION_HEADING.match(line["text"])
        if m and len(line["text"]) < 60:
            current = {"number": int(m.group(1)), "heading": m.group(2).strip(),
                       "lines": [], "bbox": list(line["bbox"])}
            sections.append(current)
        elif current is not None:
            current["lines"].append(line["text"])
            bbox = current["bbox"]
            current["bbox"] = [min(bbox[0], line["bbox"][0]),
                               min(bbox[1], line["bbox"][1]),
                               max(bbox[2], line["bbox"][2]),
                               max(bbox[3], line["bbox"][3])]

    for section in sections:
        section["text"] = "\n".join(section.pop("lines")).strip()
        section["bbox"] = [round(v, 1) for v in section["bbox"]]
    return sections


# ---------------------------------------------------------------------------
# the page, put together
# ---------------------------------------------------------------------------

def analyse_page(page, page_number):
    """Everything above, applied to one pdfplumber page."""
    words = page.extract_words()
    if not words:
        return {
            "page": page_number, "width": round(page.width, 1),
            "height": round(page.height, 1), "columns": 1, "gutters": [],
            "figures": [{"bbox": [round(im["x0"], 1), round(im["top"], 1),
                                  round(im["x1"], 1), round(im["bottom"], 1)]}
                        for im in (page.images or [])],
            "tables": [], "fields": {}, "sections": [], "text": "",
        }

    gutters = find_gutters(words, page.width)
    lines = group_lines(words, gutters)
    ordered = reading_order(lines, gutters)

    ruled = find_ruled_tables(page)
    # Whitespace tables are only looked for outside the ruled ones, so a single
    # table is never reported twice.
    ruled_boxes = [t["bbox"] for t in ruled]

    def inside_ruled(line):
        x0, top, x1, bottom = line["bbox"]
        return any(x0 >= b[0] - 2 and x1 <= b[2] + 2 and
                   top >= b[1] - 2 and bottom <= b[3] + 2 for b in ruled_boxes)

    tables = ruled + find_unruled_tables([l for l in ordered
                                          if not inside_ruled(l)])

    return {
        "page": page_number,
        "width": round(page.width, 1),
        "height": round(page.height, 1),
        "columns": len(gutters) + 1 if gutters else 1,
        "gutters": [[round(a, 1), round(b, 1)] for a, b in gutters],
        "figures": [{"bbox": [round(im["x0"], 1), round(im["top"], 1),
                              round(im["x1"], 1), round(im["bottom"], 1)]}
                    for im in (page.images or [])],
        "tables": tables,
        "fields": extract_fields(ordered, tables, page_number),
        "sections": extract_sections(ordered),
        "text": "\n".join(l["text"] for l in ordered),
    }


def analyse(pdf_path):
    """
    Layout-aware read of a whole PDF.

    Returns {"pages": [...], "text": ..., "fields": {...}, "tables": [...],
    "sections": [...]} where text is in true reading order — column by column,
    not straight down the page.
    """
    import pdfplumber

    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            pages.append(analyse_page(page, i))

    fields = {}
    for page in pages:
        for key, value in page["fields"].items():
            fields.setdefault(key, value)

    return {
        "source": pdf_path,
        "pages": pages,
        "text": "\n".join(p["text"] for p in pages),
        "fields": fields,
        "tables": [t for p in pages for t in p["tables"]],
        "sections": [s for p in pages for s in p["sections"]],
    }
