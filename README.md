# Ask My Docs — Production RAG Application

## 1. Problem Statement

Standard single-prompt LLM usage breaks down quickly when used as a "chat with your documents" tool, for three structural reasons:

* **Hallucination when the model runs out of real evidence:** A single LLM call, when it doesn't actually know the answer from the supplied text, will often generate a fluent, confident-sounding answer anyway — filling the gap from its own parametric memory rather than admitting the document set doesn't cover the question.
* **Recall failure from single-strategy retrieval:** Pure vector (semantic) search can miss exact-match queries (error codes, product names, config keys), while pure keyword search misses paraphrased questions. We retrieve *wide* with vector search (Qdrant Cloud) and let a FlashRank reranker do the precision pass — catching both paraphrases and exact/symbolic matches without maintaining a second keyword index.
* **No self-check before the answer ships:** A single forward pass has no mechanism to verify its own output against the retrieved evidence once generation is done. The citation itself can be a hallucination.

This project addresses these failure modes with a **vector-retrieval + FlashRank-reranked, citation-enforced, self-correcting pipeline**: guardrailed input, wide Qdrant Cloud retrieval, FlashRank reranking, and a validator that corrects its own citations. The result is a system structurally biased toward catching its own errors, rather than one that hopes a single generation gets everything right the first time.

## 2. Expected Architecture

```mermaid
graph TD
    subgraph "MERN Layer (Frontend & Backend)"
        User((User)) -->|1. Upload Docs / Ask Question| React[React Frontend]
        React -->|2. REST / WebSocket| Node[Node.js + Express API]
        Node -->|Save/Load State| Mongo[(MongoDB)]
    end

    Node -->|3. Trigger Ingestion / Query| FastAPI

    subgraph "Ingestion Pipeline"
        FastAPI -.->|Parse / Chunk / Embed| Ingest[Ingestion Service]
        Ingest --> Qdrant[(Qdrant Cloud Vector Store)]
    end

    subgraph "AI Orchestration (LangGraph)"
        FastAPI[Graph Entry]
        FastAPI --> Guardrail[Guardrail Gate - Input Safety]
        Guardrail -->|blocked| Done[Final Answer]
        Guardrail --> Router[Router: Triage + Query Rewrite]
        Router -->|GREETING / SUMMARY| Done
        Router -->|RAG| Retriever[Retriever Node]
        Retriever -->|wide vector query| Qdrant
        Retriever --> Reranker[FlashRank Reranker]
        Reranker --> Assembler[Context Assembler]
        Assembler --> GenGuard[Context Safety Guardrail]
        GenGuard --> Generator[Generator Node]
        Generator --> Validator[Citation Validator Node]
        Validator -->|Invalid: revise, capped at 3| Generator
        Validator -->|Valid| Done
    end

    Generator --> Gateway
    Validator --> Gateway

    subgraph "LLM Gateway & Observability"
        Gateway{LLM Gateway - LiteLLM} --> Models[cheap / strong / evaluator models]
        Guardrail -.->|spans / counters| Logfire[(Logfire)]
        Done -.->|traces| LangSmith[(LangSmith Traces)]
    end

    Done -->|8. Return to Node| Node
    Node -.->|WebSockets| React

    classDef frontend fill:#ffffff,stroke:#2563eb,stroke-width:2px,color:#111827;
    classDef backend fill:#ffffff,stroke:#16a34a,stroke-width:2px,color:#111827;
    classDef myGraph fill:#ffffff,stroke:#d97706,stroke-width:2px,color:#111827;
    classDef gateway fill:#ffffff,stroke:#4f46e5,stroke-width:2px,color:#111827;
    classDef guardrail fill:#ffffff,stroke:#dc2626,stroke-width:2px,color:#111827;
    classDef optimize fill:#ffffff,stroke:#22c55e,stroke-width:2px,color:#111827;
    classDef llm fill:#ffffff,stroke:#9333ea,stroke-width:2px,color:#111827;
    classDef eval fill:#ffffff,stroke:#ea580c,stroke-width:2px,color:#111827;

    class React,User frontend;
    class Node,Mongo backend;
    class FastAPI,Ingest,Retriever,Reranker,Assembler,Generator,Validator,Done,Qdrant,Router myGraph;
    class Gateway gateway;
    class Guardrail,GenGuard guardrail;
    class Models llm;
    class LangSmith,Logfire eval;