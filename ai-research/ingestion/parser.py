import pymupdf
from typing import List, Dict

def parse_pdf_slice(pdf_path: str) -> List[Dict]:
    """
    Parses a PDF and returns a list of pages with text and metadata.
    """
    doc = pymupdf.open(pdf_path)
    extracted_pages = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()
        
        if text:  # Filter out empty pages
            extracted_pages.append({
                "page_number": page_num + 1,
                "text": text,
                "document_name": pdf_path.split("/")[-1]
            })

    doc.close()
    return extracted_pages