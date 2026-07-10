#!/usr/bin/env python3
# /// script
# dependencies = [
#   "pymupdf>=1.24,<2",
# ]
# requires-python = ">=3.10"
# ///
"""Extract structured JSON from a PDF paper (title, sections, references).

Outputs a JSON object with section boundaries — designed for programmatic consumption by agents.

Usage:
    uv run ./scripts/summarize_paper.py paper.pdf
    uv run ./scripts/summarize_paper.py paper.pdf -o paper.json
    uv run ./scripts/summarize_paper.py paper.pdf --sections-only
"""

import argparse
import json
import os
import re
import sys

import fitz

SECTION_PATTERNS = [
    (r"^\s*abstract\s*$", "Abstract"),
    (r"^\s*\d*\.?\s*introduction\s*$", "Introduction"),
    (r"^\s*\d*\.?\s*related\s+work", "Related Work"),
    (r"^\s*\d*\.?\s*background", "Background"),
    (r"^\s*\d*\.?\s*method(?:s|ology)?", "Methods"),
    (r"^\s*\d*\.?\s*(?:proposed\s+)?(?:approach|framework|model|system)", "Methods"),
    (r"^\s*\d*\.?\s*experiment(?:s|al)?", "Experiments"),
    (r"^\s*\d*\.?\s*results?", "Results"),
    (r"^\s*\d*\.?\s*evaluation", "Evaluation"),
    (r"^\s*\d*\.?\s*discussion", "Discussion"),
    (r"^\s*\d*\.?\s*(?:conclusion|concluding)", "Conclusion"),
    (r"^\s*\d*\.?\s*limitation", "Limitations"),
    (r"^\s*\d*\.?\s*(?:acknowledge?ment)", "Acknowledgements"),
    (r"^\s*\d*\.?\s*references?\s*$", "References"),
    (r"^\s*\d*\.?\s*(?:appendix|supplementary)", "Appendix"),
]


def extract_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        text = page.get_text("text")
        if text.strip():
            pages.append(text)
    doc.close()
    return "\n\n".join(pages)


def detect_sections(text: str) -> list[dict]:
    lines = text.split("\n")
    sections = []
    current_name = "Preamble"
    current_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current_lines.append("")
            continue
        matched = False
        if len(stripped) < 80:
            for pattern, name in SECTION_PATTERNS:
                if re.match(pattern, stripped, re.IGNORECASE):
                    if current_lines:
                        content = "\n".join(current_lines).strip()
                        if content:
                            sections.append({"name": current_name, "content": content})
                    current_name = name
                    current_lines = []
                    matched = True
                    break
        if not matched:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append({"name": current_name, "content": content})

    return sections


def extract_title(text: str) -> str:
    """Heuristic: first non-empty line that's reasonably short."""
    for line in text.split("\n"):
        line = line.strip()
        if line and 10 < len(line) < 200 and not line.startswith("%"):
            return line
    return ""


def main():
    parser = argparse.ArgumentParser(description="Extract structured JSON from a PDF paper")
    parser.add_argument("pdf", help="Path to PDF file")
    parser.add_argument("--output", "-o", help="Output JSON file (default: stdout)")
    parser.add_argument("--sections-only", action="store_true", help="Output only section names and lengths")
    args = parser.parse_args()

    text = extract_text(args.pdf)
    sections = detect_sections(text)
    title = extract_title(text)

    # Find abstract content
    abstract = ""
    for s in sections:
        if s["name"] == "Abstract":
            abstract = s["content"][:1000]
            break

    if args.sections_only:
        result = {
            "title": title,
            "sections": [{"name": s["name"], "length": len(s["content"])} for s in sections],
        }
    else:
        result = {
            "title": title,
            "abstract": abstract,
            "sections": sections,
            "total_chars": len(text),
            "num_sections": len(sections),
        }

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
