---
name: rag-implementation
description: Governs how retrieval-augmented generation pipelines are built end to end - chunking strategy, embedding model selection, vector index configuration, hybrid search, reranking, and grounding the generated answer in retrieved evidence. Use when designing or debugging a RAG pipeline's retrieval quality, choosing a chunking or embedding strategy, configuring a vector index, or adding reranking to a retrieval-augmented system.
---

# RAG Implementation

This skill governs how retrieval-augmented generation pipelines are built so that generated answers are grounded in retrieved evidence rather than parametric memory, covering chunking, embedding selection, index configuration, hybrid search, reranking, and citation discipline. Adapted from the wshobson/agents llm-application-dev plugin (MIT). A RAG pipeline is a retrieval system first: the generation step can only be as accurate as the context it is handed, so every design choice here is judged by its effect on what evidence reaches the model, not on how elaborate the pipeline looks.

## Chunking strategy

Fixed-size token windows (roughly 512 tokens, 10-20 percent overlap) are the baseline and the first failure mode: naive splitting cuts a sentence, table row, or code block mid-thought, damaging both retrieval precision and the context the generator receives. Recursive character splitting — paragraph boundaries first, then sentence, then word, falling through only when a chunk is still too large — preserves semantic units far better for prose. Semantic chunking, placing boundaries at embedding-distance breakpoints between adjacent sentences, is worth its extra embedding calls on long, topically heterogeneous documents where fixed windows would straddle unrelated sections. The parent-document (or sentence-window) pattern indexes small, precise chunks for matching but returns the surrounding parent chunk to the generator, so retrieval precision and generation context are tuned independently instead of trading off in one chunk size. 200-500 tokens is the working range for prose; structured content (tables, code, config) should chunk on its own natural unit — one row, one function, one section — never split arbitrarily by token count.

## Embedding model selection

Match the embedding model to the domain and language of the corpus: a code-specific embedding model beats a general-purpose one for code search, and a multilingual model (for example an e5-family multilingual model) is required, not optional, once the corpus mixes languages. Dimension (roughly 1024-3072 in common models) is a cost/accuracy tradeoff, not a quality signal on its own. Never mix vectors from two embedding models or model versions in one index — cosine distance between vectors from different models is meaningless, and the failure is silent, returning plausible-looking but wrong neighbors. A model upgrade means re-embedding the entire corpus, not incrementally adding new vectors alongside the old ones.

## Indexing and hybrid search

HNSW is the standard approximate nearest-neighbor index across pgvector, Qdrant, Milvus, and Weaviate. Tune `M` (graph connectivity, typically 16-64; higher trades memory for recall), `ef_construction` (build-time search width), and especially `ef_search` (query-time search width) — the primary recall/latency knob, and the one most often left at its low default, capping recall well below what the index can deliver for negligible extra latency. Dense retrieval alone misses exact-match terms (IDs, error codes, acronyms, SKUs) that an embedding space smooths over; combine it with sparse retrieval (BM25) as hybrid search, and fuse the rankings with Reciprocal Rank Fusion (`score = sum(1 / (k + rank))` across rankers, `k` around 60) rather than a hand-tuned linear weight, which overfits one test corpus and needs retuning on the next.

## Reranking and query transformation

Dense retrieval's top-k is a recall pass, not a final ranking. Feed the top 20-50 candidates through a cross-encoder reranker (an ms-marco-MiniLM-class model, or a hosted reranker) that scores query and document jointly — more accurate than cosine similarity, but too slow to run over the full corpus, which is why it sits after the ANN pass, not instead of it. Apply Maximal Marginal Relevance when diversity matters, so the top results are not five near-duplicate chunks of the same passage. Query transformation earns its extra LLM call when the raw query underperforms: multi-query (generate three to five paraphrases, retrieve for each, deduplicate) improves recall on ambiguous phrasing, and HyDE (embed a generated hypothetical answer instead of the question) helps when the query and the answer live in different linguistic registers, such as a short question against a dense technical passage.

## Grounding and citation discipline

Instruct the generation model explicitly to answer only from the supplied context and to say so when the context does not contain the answer — a RAG system that silently falls back to parametric memory on a retrieval miss is worse than no RAG, because the wrong answer now looks sourced. Attach provenance (source document, section, retrieval score) to every chunk passed to the generator, and log which chunks were actually cited versus merely retrieved, so retrieval failures and generation failures can be debugged separately instead of conflated into one vague "bad answer." Context ordering matters: models attend most reliably to the start and end of a long context window (the lost-in-the-middle effect), so place the highest-relevance chunk first or last in a multi-chunk stuff, not buried in the middle. End-to-end evaluation of the pipeline (Recall@k, NDCG, groundedness scoring) is owned by `llm_evaluation`; build and tune the pipeline here, gate it there.

## Common pitfalls

- Fixed-size chunking that splits a table or code block mid-row, destroying the one clean semantic unit that mattered.
- Mixing embeddings from two model versions in one index after a silent upgrade, corrupting every nearest-neighbor query.
- `ef_search` left at its default, capping recall far below what the index is capable of at negligible latency cost.
- Hybrid fusion with a hand-tuned linear weight instead of Reciprocal Rank Fusion, overfit to one corpus and wrong on the next.
- No reranking stage, shipping raw cosine-similarity order as the final context ordering handed to the generator.
- A relevant chunk buried in the middle of a large stuffed context, ignored by the generator despite being retrieved correctly.
- A generation prompt with no explicit "say you don't know" instruction, turning a retrieval miss into a confident hallucination.

## Definition of done

- [ ] Chunking strategy matches document structure (prose versus tabular versus code) and is stated with size and overlap.
- [ ] Embedding model matches domain and language and is versioned; no mixed-model index.
- [ ] Index parameters (`M`, `ef_construction`, `ef_search`) tuned, with the recall/latency tradeoff recorded.
- [ ] Hybrid search in place when exact-match terms matter, fused via Reciprocal Rank Fusion.
- [ ] A reranking stage runs over the top-k candidates before generation.
- [ ] Chunk provenance attached and logged; retrieved-versus-cited chunks distinguishable for debugging.
- [ ] Generation prompt enforces grounded, context-only answers with an explicit fallback for missing context.
- [ ] Context ordering accounts for lost-in-the-middle; the pipeline is handed to `llm_evaluation` for Recall@k and groundedness gating.
