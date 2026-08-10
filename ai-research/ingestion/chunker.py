from typing import List, Dict

def chunk_pages(pages: List[Dict], chunk_size: int = 1000, chunk_overlap: int = 150) -> List[Dict]:
    """
    Splits page text into overlapping chunks while preserving section/page metadata.
    """
    chunks = []
    chunk_counter = 0

    for page in pages:
        text = page["text"]
        page_num = page["page_number"]
        doc_name = page["document_name"]
        
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end]
            
            chunk_id = f"{doc_name}:p{page_num}:c{chunk_counter}"
            
            chunks.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "metadata": {
                    "chunk_id": chunk_id,
                    "document": doc_name,
                    "page": page_num
                }
            })
            
            chunk_counter += 1
            start += (chunk_size - chunk_overlap)

    return chunks