from langchain_text_splitters import RecursiveCharacterTextSplitter
import uuid

def chunk_pages(pages, user_id: str, document_id: str, document_name: str):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        length_function=len
    )
    
    chunks = []
    
    for page in pages:
        splits = text_splitter.split_text(page["text"])
        
        for split in splits:
            chunk_id = f"{document_id}_{uuid.uuid4().hex[:8]}"
            
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