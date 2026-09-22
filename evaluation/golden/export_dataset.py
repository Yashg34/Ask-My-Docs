import sys
import os
import json

# Python ko 'ai-research' folder ka rasta (path) batana
current_dir = os.path.dirname(os.path.abspath(__file__)) # golden/
eval_dir = os.path.dirname(current_dir)                  # evaluation/
root_dir = os.path.dirname(eval_dir)                     # Ask-My-Docs/
ai_research_dir = os.path.join(root_dir, "ai-research")  # ai-research/

# Path add kar diya taaki imports fail na hon
sys.path.append(ai_research_dir)

# Ab yeh imports bina kisi error ke successfully chalenge
from retrieval.vector_store import get_qdrant_client
from config import settings

def export_qdrant_to_json(output_filename="qdrant_dataset.json"):
    print(f"🚀 Connecting to Qdrant collection: {settings.QDRANT_COLLECTION_NAME}...")
    client = get_qdrant_client()
    
    all_payloads = []
    offset = None
    
    while True:
        records, offset = client.scroll(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False
        )
        
        for record in records:
            if record.payload:
                all_payloads.append(record.payload)
        
        print(f"📦 Fetched {len(all_payloads)} chunks so far...")
        
        if offset is None:
            break
            
    # Output file bhi 'golden' folder mein hi save hogi
    output_path = os.path.join(current_dir, output_filename)
    print(f"💾 Saving data to {output_path}...")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_payloads, f, indent=4, ensure_ascii=False)
        
    print(f"✅ Successfully exported all {len(all_payloads)} data points!")

if __name__ == "__main__":
    export_qdrant_to_json()