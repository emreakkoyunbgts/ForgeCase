"""
Builds the layout fixtures used by the Reader's CF-49 tests.

The supplied test pack is all single-column prose — there is not one table or
multi-column page in it — so there was nothing to test layout-aware extraction
against. These fixtures fill that gap. They carry the same facts as
eng-01_closeout.pdf so a layout-aware read can be checked against a known
answer, laid out three ways a real closeout might be:

    two_column_closeout.pdf     facts in a two-column body
    ruled_table_closeout.pdf    header block as a bordered table
    unruled_table_closeout.pdf  header block aligned with whitespace only

The generated PDFs are committed, so running the tests needs nothing extra.
Regenerate them only if the fixtures need to change:

    pip install reportlab
    python reader/fixtures/make_fixtures.py
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_W, PAGE_H = A4

# The same engagement as eng-01, so the tests can assert on known values.
FIELDS = [
    ("Engagement ID", "eng-01"),
    ("Client", "Gulf Union Bank"),
    ("Client profile", "Tier-1 GCC retail bank"),
    ("Sector / domain", "core banking"),
    ("Region", "GCC"),
    ("Delivered", "2025"),
    ("Team size", "14 people"),
    ("Duration", "11 months"),
]

CHALLENGE = ("The legacy core banking platform could not support real-time "
             "payments, and end-of-day batch windows were overrunning into "
             "business hours.")
APPROACH = ("A phased migration from the legacy core to a modern event-driven "
            "platform, run as a shadow migration so the old and new systems "
            "processed in parallel until cutover.")
TECHNOLOGY = "Java, Spring Boot, Kafka, PostgreSQL"
OUTCOMES = ["payment latency reduced 45%",
            "batch window shortened from 6 hours to 90 minutes",
            "zero unplanned downtime during cutover"]


def _header(c, subtitle):
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, PAGE_H - 22 * mm, "BGTS INTERNATIONAL")
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, PAGE_H - 29 * mm, subtitle)


def _wrap(c, text, x, y, width, font="Helvetica", size=9, leading=11):
    """Draw text wrapped to `width`, return the y below the last line."""
    c.setFont(font, size)
    words, line = text.split(), ""
    for word in words:
        trial = f"{line} {word}".strip()
        if c.stringWidth(trial, font, size) <= width:
            line = trial
        else:
            c.drawString(x, y, line)
            y -= leading
            line = word
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def two_column():
    """
    A two-column body that flows the way a real one does: down the left column,
    then continue at the top of the right. Sections 1-2 are on the left, 3-4 on
    the right.

    Read straight down the page, this comes out as interleaved fragments of two
    unrelated sentences, and the section headings fuse into each other
    ("1. The Challenge 3. Technology"). Getting it right is CF-49.
    """
    path = os.path.join(HERE, "two_column_closeout.pdf")
    c = canvas.Canvas(path, pagesize=A4)
    _header(c, "Engagement Closeout Report")

    left_x, right_x = 20 * mm, 110 * mm
    col_w = 75 * mm

    # Header facts, two columns wide.
    y = PAGE_H - 42 * mm
    c.setFont("Helvetica", 9)
    half = len(FIELDS) // 2
    for i, (label, value) in enumerate(FIELDS[:half]):
        c.drawString(left_x, y - i * 5 * mm, f"{label}: {value}")
    for i, (label, value) in enumerate(FIELDS[half:]):
        c.drawString(right_x, y - i * 5 * mm, f"{label}: {value}")

    # Body: left column carries sections 1 and 2, right column 3 and 4.
    y = y - half * 5 * mm - 8 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left_x, y, "1. The Challenge")
    y_left = _wrap(c, CHALLENGE, left_x, y - 6 * mm, col_w)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left_x, y_left - 4 * mm, "2. Our Approach")
    _wrap(c, APPROACH, left_x, y_left - 10 * mm, col_w)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(right_x, y, "3. Technology")
    y_right = _wrap(c, TECHNOLOGY, right_x, y - 6 * mm, col_w)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(right_x, y_right - 4 * mm, "4. Outcomes")
    yy = y_right - 10 * mm
    for outcome in OUTCOMES:
        yy = _wrap(c, f"- {outcome}", right_x, yy, col_w)

    c.save()
    return path


def ruled_table():
    """Header facts in a bordered table — the layout pdfplumber can see."""
    path = os.path.join(HERE, "ruled_table_closeout.pdf")
    c = canvas.Canvas(path, pagesize=A4)
    _header(c, "Engagement Closeout Report")

    x, y = 20 * mm, PAGE_H - 45 * mm
    label_w, value_w, row_h = 45 * mm, 70 * mm, 8 * mm

    c.setStrokeColor(colors.black)
    c.setLineWidth(0.6)
    for i, (label, value) in enumerate(FIELDS):
        top = y - i * row_h
        c.rect(x, top - row_h, label_w, row_h)
        c.rect(x + label_w, top - row_h, value_w, row_h)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 2 * mm, top - row_h + 2.6 * mm, label)
        c.setFont("Helvetica", 9)
        c.drawString(x + label_w + 2 * mm, top - row_h + 2.6 * mm, value)

    y = y - len(FIELDS) * row_h - 12 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "1. The Challenge")
    _wrap(c, CHALLENGE, x, y - 6 * mm, 150 * mm)
    c.save()
    return path


def unruled_table():
    """
    The same facts aligned with whitespace and no ink at all — the common case
    in real documents, and the one a line-based table finder misses entirely.
    """
    path = os.path.join(HERE, "unruled_table_closeout.pdf")
    c = canvas.Canvas(path, pagesize=A4)
    _header(c, "Engagement Closeout Report")

    x, y, row_h = 20 * mm, PAGE_H - 45 * mm, 7 * mm
    col2 = x + 55 * mm
    for i, (label, value) in enumerate(FIELDS):
        top = y - i * row_h
        c.setFont("Helvetica", 9)
        c.drawString(x, top, label)
        c.drawString(col2, top, value)

    y = y - len(FIELDS) * row_h - 12 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "4. Outcomes")
    yy = y - 6 * mm
    c.setFont("Helvetica", 9)
    for outcome in OUTCOMES:
        yy = _wrap(c, f"- {outcome}", x, yy, 150 * mm)
    c.save()
    return path


if __name__ == "__main__":
    for build in (two_column, ruled_table, unruled_table):
        print("wrote", os.path.relpath(build(), os.getcwd()))
