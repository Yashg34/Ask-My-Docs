from langchain_text_splitters import RecursiveCharacterTextSplitter
import hashlib
from config import settings

def chunk_pages(pages, user_id: str, document_id: str, document_name: str):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        length_function=len
    )
    
    chunks = []
    
    for page in pages:
        splits = text_splitter.split_text(page["text"])
        
        for split in splits:
            content_hash = hashlib.sha1(split.encode('utf-8')).hexdigest()[:16]
            chunk_id = f"{document_id}_{page['page_number']}_{content_hash}"
            
            chunks.append({
                "chunk_id": chunk_id,
                "text": split,
                "metadata": {
                    "page": page["page_number"],
                    "user_id": user_id,         
                    "document_id": document_id,
                    "document_name": document_name
                }
            })
            
    return chunks