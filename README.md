# Ask My Docs — Production RAG Application

## 1. Problem Statement

Standard single-prompt LLM usage breaks down quickly when used as a "chat with your documents" tool, for three structural reasons:

* **Hallucination when the model runs out of real evidence:** A single LLM call, when it doesn't actually know the answer from the supplied text, will often generate a fluent, confident-sounding answer anyway — filling the gap from its own parametric memory rather than admitting the document set doesn't cover the question.
* **Recall failure from single-strategy retrieval:** Pure vector (semantic) search misses exact-match queries (error codes, product names, config keys) where lexical overlap matters more than semantic similarity. Pure keyword search misses paraphrased questions. 
* **No self-check before the answer ships:** A single forward pass has no mechanism to verify its own output against the retrieved evidence once generation is done. The citation itself can be a hallucination.

This project addresses these failure modes with a **hybrid-retrieval, citation-enforced, self-correcting pipeline**. The result is a system structurally biased toward catching its own errors, rather than one that hopes a single generation gets everything right the first time.

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
        FastAPI -.->|Parse/Chunk/Embed| Ingest[Ingestion Service]
        Ingest --> VectorDB[(Vector Store - Chroma)]
        Ingest --> BM25[(BM25 / Keyword Index)]
    end

    subgraph "AI Orchestration (LangGraph)"
        FastAPI[Graph Entry] --> Retriever[Retriever Node]
        Retriever -->|Query| VectorDB
        Retriever -->|Query| BM25
        Retriever --> Reranker[Reranker Node]
        Reranker --> Assembler[Context Assembler]
        Assembler --> Generator[Generator Node]
        Generator --> Validator[Citation Validator Node]
        Validator -->|Invalid: revise, capped| Generator
        Validator -->|Valid| Done[Final Answer]
    end

    Generator --> Gateway
    Validator --> Gateway

    subgraph "LLM Security & Routing Layer"
        Gateway{LLM Gateway - LiteLLM} -->|4. Check Cache| Cache[(Semantic Cache)]
        Cache -.->|Hit: Fast TTFT| Gateway
        Gateway -->|Miss| InGuard[Input Guardrails: PII, Injection]
        InGuard -->|5. Safe Prompt| Router[Semantic / Fallback Router]
        Router -->|Fast/Cheap| Fast[Small Model]
        Router -->|Reasoning-Heavy| Strong[Strong Model]
        Fast -.->|Stream Tokens| OutGuard
        Strong -.->|Stream Tokens| OutGuard
        OutGuard[Output Guardrails: Schema/Citation Format] -->|6. Validated Output| Gateway
    end

    Gateway -->|7. Return to Graph| Done
    Done -->|8. Stream Result| Node
    Node -.->|WebSockets| React

    Gateway -.->|9. Async Logging| LangSmith[(LangSmith Traces)]
    LangSmith -.->|10. Batch Scoring| Eval[Ragas Evaluators]
    Eval -.->|Metrics: Faithfulness, Context Precision| CI([CI/CD Quality Gate])

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
    class FastAPI,Ingest,Retriever,Reranker,Assembler,Generator,Validator,Done,VectorDB,BM25 myGraph;
    class Gateway gateway;
    class InGuard,OutGuard guardrail;
    class Cache,Router optimize;
    class Fast,Strong llm;
    class LangSmith,Eval,CI eval;