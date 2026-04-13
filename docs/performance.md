# Performance Characteristics

Performance numbers are estimates based on typical hardware (Apple Silicon Mac). Your results may vary.

See also: [Configuration](configuration.md) and [Architecture](architecture.md).

## Token Savings

The main efficiency gain is avoiding broad file reads during each AI conversation.

- Traditional workflow: assistant repeatedly reads many files per conversation (often ~50K-100K tokens).
- Indexed workflow: assistant queries semantic index and receives only relevant chunks.
- With a typical result set of ~10 chunks and default chunk size near 512 tokens, context returned is roughly ~5K tokens.
- Estimated token reduction: ~80-90% in many practical workflows.

Actual savings depend on query quality/relevance, chunk distribution, and workspace size.

## Index Size

From the current implementation:

- Vector dimension (`VECTOR_DIM`): 768.
- Embedding storage type: float32 (`4 bytes` per value).

Rough per-chunk size estimate:

- Vector: $768 \times 4 = 3072$ bytes (~3.0 KB)
- Chunk text: typically ~2 KB (varies by language and chunk type)
- Metadata: path, lines, symbols, types, timestamps

Practical planning number: ~5-6 KB per chunk.

Examples:

- 1,000 chunks: ~5-6 MB
- 5,000 chunks: ~25-30 MB

LanceDB uses columnar storage and may compress efficiently, so real on-disk size can be lower.

## Indexing Speed

Indexing time is primarily dominated by embedding generation through Ollama.

- Embedding batch size (`EMBED_BATCH_SIZE`): 100 chunks per request.
- Rough embedding time per batch: ~1-5 seconds depending on hardware load and model throughput.

Back-of-the-envelope estimate:

- A ~500-file repo may produce ~2,000 chunks.
- At 100 chunks/batch, that is ~20 embedding batches.
- Expected full index time: ~20-100 seconds (plus file walk/chunking overhead).

Incremental indexing is significantly faster because only changed files are re-chunked and re-embedded, often completing in seconds.

## Search Latency

Typical end-to-end search path:

1. Embed query with Ollama.
2. Run vector similarity search in LanceDB.
3. Return top matching chunks.

Typical latency profile:

- LanceDB search: often <100 ms for datasets up to ~50K chunks.
- Query embedding (Ollama): ~50-200 ms.
- Total round-trip: commonly <500 ms.

## Chunking

Default chunking behavior from config:

- `max_tokens`: 512
- `overlap_tokens`: 64 (used by fallback chunking flow)

Token estimation uses a lightweight approximation:

- `estimated_tokens = len(text) // 4`

Structure-aware chunkers (for example, function/class/section boundaries) may produce smaller chunks than the configured max.

## Resource Usage

- Memory: LanceDB is file-based and generally has a low runtime memory footprint.
- Disk: indexes are stored under `~/.local/share/codebase-rag/indexes/{workspace_hash}/`.
- CPU: relatively low outside chunking and embedding.
- Ollama: uses GPU acceleration when available, with CPU fallback.

## Tips For Large Workspaces

- Use `repos.paths` to index only the repositories you need.
- Tighten `index.exclude` to skip generated/vendor/build artifacts.
- Use `codebase-rag index --repo <name>` for targeted indexing.
- Max indexed file size is limited by `MAX_FILE_SIZE_BYTES = 1024 * 1024` (1 MiB per file).
