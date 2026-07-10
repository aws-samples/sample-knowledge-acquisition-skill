#!/usr/bin/env python3
# /// script
# dependencies = [
#   "pymupdf>=1.24,<2",
#   "pymupdf4llm>=0.0.10,<1",
# ]
# requires-python = ">=3.10"
# ///
import argparse
from pathlib import Path
import pymupdf
import pymupdf4llm

parser = argparse.ArgumentParser(description="Convert PDF to Markdown")
parser.add_argument("pdf", help="Path to PDF file")
parser.add_argument(
    "--margins",
    type=float,
    nargs=4,
    metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
    help="Points to trim from each edge (e.g. --margins 50 0 50 0 to strip line numbers)",
)
args = parser.parse_args()

pdf = Path(args.pdf)
doc = pymupdf.open(str(pdf))

if args.margins:
    left, top, right, bottom = args.margins
    for page in doc:
        r = page.rect
        page.set_cropbox(pymupdf.Rect(r.x0 + left, r.y0 + top, r.x1 - right, r.y1 - bottom))

md = pymupdf4llm.to_markdown(doc)
pdf.with_suffix(".md").write_text(md)
