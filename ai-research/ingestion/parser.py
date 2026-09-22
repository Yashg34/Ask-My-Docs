import pymupdf
import unicodedata
from typing import List, Dict

LIGATURE_MAP = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "ft", "ﬆ": "st",
}

def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for lig, repl in LIGATURE_MAP.items():
        text = text.replace(lig, repl)
    return text

def parse_pdf_slice(pdf_path: str) -> List[Dict]:
    """
    Parses a PDF and returns a list of pages with cleaned text and metadata.
    Uses block-level extraction so paragraph boundaries are preserved as
    double-newlines, which the chunker relies on to find structure.
    """
    doc = pymupdf.open(pdf_path)
    extracted_pages = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
        # Sort top-to-bottom, left-to-right (default PDF block order can be off for multi-column)
        blocks = sorted(blocks, key=lambda b: (round(b[1], 1), b[0]))

        # Join blocks with double-newline so a paragraph/bullet-boundary splitter
        # ("\n\n") has real separators to key off, instead of a wall of single \n's
        page_text = "\n\n".join(
            _clean_text(b[4]).strip() for b in blocks if b[4].strip()
        )

        if page_text:
            extracted_pages.append({
                "page_number": page_num + 1,
                "text": page_text,
            })

    doc.close()
    return extracted_pages