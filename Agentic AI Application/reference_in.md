
Agentic AI System — End-to-End Architecture (Refined Notes)

1. PDF Ingestion & Storage
- PDFs are loaded and stored as binary files in a database table named document_table.
- The table includes: s.no, pdf_path, and content (binary PDF data).
- Each PDF is processed later for chunking and embedding.

2. Chunking the Documents
- Convert PDF bihttps://dbc-403662d3-a416.cloud.databricks.com/editor/files/1551098506958498?o=7474645706802829$0nary data into text.
- Split text into chunks using a text splitter with overlap.
- Store each chunk (or update content field) while retaining pdf_path for traceability.
- Chunks remain individual but linked to their source PDF.

3. Embedding the Chunks
- Pass each chunk through a pretrained embedding model.
- Tokenizer converts words/subwords → tokens.
- Tokens map to vocabulary indices.
- Embedding layer of size V×D maps tokens to initial vectors.
- Positional encodings + self-attention + transformer layers build contextual embeddings.
- Apply pooling (mean/CLS) to get a final chunk embedding.
- Save embeddings in a table or vector storage.

4. Indexing Embeddings
- Store chunk embeddings in a vector database using HNSW indexing.
- HNSW allows efficient retrieval of semantically similar chunks.

5. Query Handling & Retrieval (RAG)
- Convert user query into an embedding using the same model.
- Retrieve top similar chunks using HNSW.
- Attach retrieved chunks as context.
- Send combined query + context to the LLM for answering.

6. How Agentic AI Works
- Before agents, understand the basic chain:
  {query, retriever_output} → prompt_creator → LLM → output_renderer
- The retriever fetches context; prompt creator builds structured prompt; 
  LLM generates answer; renderer formats the output.
- This is a single-purpose chain.

7. Multi-Chain Systems(still non agentic)
- Example:
  Chain1: get top songs → Chain2: get Spotify links → Chain3: compose answer
- These are manually connected flows and not fully agentic.

8. Real Agentic AI (Autonomous Tool Use)
- Instead of manually linking chains, each chain becomes a tool.
- The LLM decides which tool to use and in what order based on user goals.
- Tools are described in the prompt.
- LLM outputs a plan (e.g., tool3 → tool1 → tool4).
- Backend code executes tools step-by-step.
- LLM is the brain; tools are body parts; backend code is the nervous system.
- After each tool call, results are fed back to the LLM if needed for replanning.

9. Summary
- RAG: Retrieval-enhanced responses.
- Chains: Multi-step deterministic workflows.
- Agentic AI: LLM autonomously plans and executes tool sequences.
