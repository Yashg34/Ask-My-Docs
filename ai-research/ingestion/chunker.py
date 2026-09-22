from langchain_text_splitters import RecursiveCharacterTextSplitter
import hashlib
import re
from typing import List, Dict, Optional
from config import settings

GENERIC_SEPARATORS = [
    r"\n\n",
    r"\n\d+\.\d*\s+[A-Z]",        # numbered headings, e.g. "3.1 Something"
    re.escape("\nSection "),
    re.escape("\nChapter "),
    re.escape("\nArticle "),
    re.escape("\n\u2022 "),        # unicode bullet
    re.escape("\n• "),
    re.escape("\n- "),             # markdown-style bullet
    r"\n",
    r"\. ",
    r" ",
    r"",
]

# Domain-specific markers, layered on top of GENERIC_SEPARATORS at higher
# priority (checked first). Add new document types here rather than
# hardcoding them into the main separator list.
DOMAIN_SEPARATORS = {
    "academic_paper": [
        re.escape("\nDefinition "),
        re.escape("\nTheorem "),
        re.escape("\nAxiom"),
        re.escape("\nLemma "),
        re.escape("\nProof"),
    ],
    "legal": [
        re.escape("\nWHEREAS"),
        re.escape("\nSection "),
        re.escape("\nArticle "),
        r"\n\([a-z]\)\s",           # (a), (b), (c) clauses
    ],
    "manual": [
        re.escape("\nStep "),
        re.escape("\nWarning:"),
        re.escape("\nNote:"),
    ],
}


def build_separators(doc_type: Optional[str] = None) -> List[str]:
    """
    Returns a priority-ordered regex separator list for RecursiveCharacterTextSplitter.
    "\n\n" (paragraph boundary) always stays highest priority since it's the
    most reliable universal signal; domain markers slot in right after it.
    """
    domain_extra = DOMAIN_SEPARATORS.get(doc_type, []) if doc_type else []
    rest = [s for s in GENERIC_SEPARATORS if s != r"\n\n"]
    return [r"\n\n"] + domain_extra + rest


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
def chunk_pages(
    pages: List[Dict],
    user_id: str,
    document_id: str,
    document_name: str,
    doc_type: Optional[str] = None,
) -> List[Dict]:
    """
    Splits parsed pages into chunks, biasing splits toward paragraph and
    structural boundaries (headings, bullets, definitions, etc.) rather than
    raw character counts.

    doc_type: optional hint ("academic_paper", "legal", "manual", ...) that
    adds domain-specific separators on top of the generic set. Pass None
    for general-purpose documents.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        length_function=len,
        add_start_index=True,
        is_separator_regex=True,
        separators=build_separators(doc_type),
    )

    full_text = ""
    page_offsets = []

    for page in pages:
        page_offsets.append((len(full_text), page["page_number"]))
        full_text += page["text"] + "\n\n"  # matches parser's paragraph join

    def get_page_number(char_index: int) -> int:
        for offset, p_num in reversed(page_offsets):
            if char_index >= offset:
                return p_num
        return page_offsets[0][1] if page_offsets else 1

    splits = text_splitter.create_documents([full_text])

    # Merge any chunk under MIN_CHUNK_SIZE into the previous chunk instead of
    # indexing a stray sentence/fragment on its own.
    MIN_CHUNK_SIZE = max(100, settings.CHUNK_SIZE // 8)
    merged_splits = []
    for split in splits:
        if merged_splits and len(split.page_content) < MIN_CHUNK_SIZE:
            prev = merged_splits[-1]
            prev.page_content = prev.page_content + "\n\n" + split.page_content
        else:
            merged_splits.append(split)

    chunks = []
    for chunk_index, split in enumerate(merged_splits):
        start_char = split.metadata["start_index"]
        end_char = start_char + len(split.page_content) - 1

        page_start = get_page_number(start_char)
        page_end = get_page_number(end_char)

        content_hash = hashlib.sha1(split.page_content.encode("utf-8")).hexdigest()[:16]
        chunk_id = f"{document_id}_{page_start}-{page_end}_{chunk_index:04d}_{content_hash}"

        chunks.append({
            "chunk_id": chunk_id,
            "text": split.page_content,
            "metadata": {
                "page_start": page_start,
                "page_end": page_end,
                "user_id": user_id,
                "document_id": document_id,
                "document_name": document_name,
            }
        })

    return chunks