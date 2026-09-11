# CoRA Mail LLM Inference Architecture And vLLM Transition

## Current Invocation Map

Current application code calls LLMs through `LocalLLMGateway`.

```text
Mail Decision run API
  -> MailDecisionRoutingService / MailDecisionRuntimeService
  -> AttachmentParserDispatcher
  -> VisionAttachmentAnalyzer.generate_structured_vision() when OCR/vision is required
  -> TextAttachmentAnalyzer.generate_structured() when parsed attachment text exists
  -> FactExtractionAgent.generate_structured()
  -> AgenticRetrievalService
       -> QdrantSimilarCaseRetriever.embed() for similar-case retrieval
  -> DecisionAgent.generate_structured()
```

```text
Search / Chats UI
  -> MailSearchService
  -> generate_structured() for mailbox query planning
  -> embed() for semantic query vector
  -> embed() for uncached candidate document vectors
  -> generate_structured() for grounded answer synthesis
```

```text
Qdrant production indexing / evaluation tools
  -> ProductionSimilarCaseIndexer
  -> LocalLLMGateway.embed()
```

Provider behavior before this transition:

- `CORAMAIL_LLM_PROVIDER=ollama` used Ollama native `/api/chat` for structured text and vision generation, with `format` set to the Pydantic JSON schema.
- Other OpenAI-compatible providers used `/chat/completions` with `response_format={"type":"json_object"}`.
- Embeddings used `/embeddings` except Gemini, which uses the Gemini REST embedding endpoint.
- The HTTP transport used synchronous `urllib.request` calls without connection pooling.

## Bottlenecks

For one Mail Decision run, the common sequential path is:

1. Parse each attachment locally.
2. For each scanned/image attachment page, call vision generation once.
3. For each text-bearing attachment, call text document understanding once.
4. Call fact extraction once.
5. Run retrieval. Exact/rule/capability retrieval is local/PostgreSQL; each similar-case query calls embedding once.
6. Call decision generation once.

This means a single email with one parsed text attachment and one similar-case retrieval query normally performs at least three text/embedding LLM calls after local parsing: document understanding, fact extraction, embedding, decision. Scanned PDFs add one vision generation per page without extracted text. These calls are mostly sequential today because `FactExtractionAgent` depends on attachment results, retrieval depends on extracted facts, and `DecisionAgent` depends on facts plus retrieval context.

Parallel opportunities are limited but real:

- Multiple attachments in the same email can be analyzed concurrently once parser output is available.
- Search document embeddings for uncached candidate documents can be batched, which the current code already does.
- Multiple independent Mail Decision runs can be processed concurrently by the application layer if requests arrive concurrently.

The main latency risks are:

- Sequential `FactExtractionAgent -> retrieval -> DecisionAgent` generation.
- Per-page vision calls for scanned PDFs.
- Search/Chats planner and answer synthesis are separate generation calls.
- Long prompts include raw body text, attachment extracted text, schema text, and retrieval hits.
- Synchronous HTTP transport previously opened requests without explicit pooling or role-level backpressure.

## Instrumentation

`LocalLLMGateway` now logs one metadata-only `llm_call` line per HTTP call:

- operation
- role: `text`, `vision`, or `embedding`
- provider
- model
- UTC start/end timestamps
- latency in milliseconds
- usage token counts when returned by the backend
- approximate input token count when usage is unavailable
- error and timeout flags
- HTTP status code

The log line intentionally does not include email body, attachment text, full prompts, image data, or model outputs. Workflow-level latency remains recorded in `mail_decision_steps.latency_ms` through the existing repository start/finish step hooks.

## vLLM Architecture

Recommended operating shape:

```text
CoRA Mail web/runtime
  +-- text generation ----> vLLM text server, OpenAI-compatible /v1
  +-- vision generation --> vLLM vision server or a separate vision/OCR backend
  +-- embeddings ---------> dedicated embedding backend, vLLM --task embed or another local embedding service
```

Text generation is the best first vLLM target. Mail Decision, Search/Chats planner, and answer synthesis can keep using `generate_structured()` while `CORAMAIL_LLM_PROVIDER=vllm` points to a vLLM OpenAI-compatible endpoint. vLLM supports structured JSON outputs through OpenAI-compatible `response_format={"type":"json_schema"}` and structured output backends.

Vision should not be forced onto the same text server. Vision models usually need separate model loading, larger context/image memory, and different throughput characteristics. Keep `CORAMAIL_VISION_LLM_BASE_URL` available so a vision vLLM server or another on-prem vision backend can be tested independently.

Embeddings should usually be separated from generation. Embedding models are smaller and high-throughput, but running them in the same GPU process as text generation can create avoidable latency competition. Use `CORAMAIL_EMBEDDING_BASE_URL` when embedding is served by a dedicated vLLM `--task embed` container or another local embedding service.

## Configuration

Backward-compatible defaults remain:

```env
CORAMAIL_LLM_PROVIDER=ollama
CORAMAIL_LLM_BASE_URL=http://127.0.0.1:11434/v1
```

Role-specific provider and endpoint overrides are optional:

```env
CORAMAIL_TEXT_LLM_PROVIDER=vllm
CORAMAIL_VISION_LLM_PROVIDER=ollama
CORAMAIL_EMBEDDING_PROVIDER=ollama
CORAMAIL_TEXT_LLM_BASE_URL=http://127.0.0.1:8001/v1
CORAMAIL_VISION_LLM_BASE_URL=http://127.0.0.1:11434/v1
CORAMAIL_EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
```

This is the preferred development shape: keep the global provider on Ollama for
rollback and non-text roles, then move only text generation to vLLM.

Concurrency guards are also role-specific:

```env
CORAMAIL_TEXT_LLM_MAX_CONCURRENCY=4
CORAMAIL_VISION_LLM_MAX_CONCURRENCY=2
CORAMAIL_EMBEDDING_LLM_MAX_CONCURRENCY=8
CORAMAIL_LLM_MAX_OUTPUT_TOKENS=1024
```

The `4/2/8` concurrency defaults are conservative Ollama-compatible defaults.
For the measured vLLM text profile on RTX 5060 Ti 16GB, use
`CORAMAIL_TEXT_LLM_MAX_CONCURRENCY=16` with `Qwen/Qwen2.5-7B-Instruct-AWQ`.

Start the optional vLLM text profile with:

```bash
CORAMAIL_LLM_PROVIDER=ollama \
CORAMAIL_TEXT_LLM_PROVIDER=vllm \
CORAMAIL_VISION_LLM_PROVIDER=ollama \
CORAMAIL_EMBEDDING_PROVIDER=ollama \
CORAMAIL_CONTAINER_LLM_BASE_URL=http://ollama:11434/v1 \
CORAMAIL_CONTAINER_TEXT_LLM_BASE_URL=http://vllm-text:8000/v1 \
CORAMAIL_VLLM_TEXT_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ \
CORAMAIL_TEXT_MODEL=qwen2.5-7b-awq \
CORAMAIL_CHAT_TEXT_MODEL=qwen2.5-7b-awq \
CORAMAIL_VLLM_TEXT_MAX_MODEL_LEN=4096 \
CORAMAIL_VLLM_TEXT_GPU_MEMORY_UTILIZATION=0.75 \
CORAMAIL_TEXT_LLM_MAX_CONCURRENCY=16 \
VLLM_WSL2_ENABLE_PIN_MEMORY=1 \
VLLM_WORKER_MULTIPROC_METHOD=spawn \
docker compose --profile vllm up --build
```

Add the embedding profile only when using a dedicated embedding model:

```bash
CORAMAIL_CONTAINER_EMBEDDING_BASE_URL=http://vllm-embedding:8000/v1 \
docker compose --profile vllm --profile vllm-embedding up --build
```

## Benchmark Plan

Use `scripts/benchmark_llm_inference.py` to compare engines with the same synthetic CoRA Mail prompts.

Example Ollama baseline:

```bash
uv run python scripts/benchmark_llm_inference.py \
  --engine ollama \
  --provider ollama \
  --base-url http://127.0.0.1:11434/v1 \
  --text-model llama3.2:latest \
  --concurrency 1 2 4 8 \
  --workload fact_extraction
```

Example vLLM run:

```bash
uv run python scripts/benchmark_llm_inference.py \
  --engine vllm \
  --provider vllm \
  --base-url http://127.0.0.1:8001/v1 \
  --text-model qwen2.5-7b-awq \
  --concurrency 1 2 4 8 \
  --max-output-tokens 1024 \
  --workload fact_extraction
```

Run all three workloads before deciding defaults:

- `fact_extraction`
- `decision`
- `mixed_chat`

The benchmark writes JSON results to `data/evaluation/llm_benchmark_latest.json` by default. Use the same GPU, same or equivalent model weights, same quantization policy where possible, and the same concurrency list for both engines. Do not compare a smaller vLLM model with a larger Ollama model as serving-engine evidence.

## Recommendation

Keep Ollama as the development and rollback provider, but make vLLM the preferred operating path for text generation once benchmark results show lower p95 latency and higher successful throughput at concurrency 4-8 under CoRA Mail workloads.

Measured on WSL2, NVIDIA GeForce RTX 5060 Ti 16GB, vLLM 0.27.1:

| Model + engine | Structured output | Real agent path | Concurrency / burst result | Peak or idle VRAM | Decision |
|---|---:|---:|---|---:|---|
| `llama3.2:latest` Q4_K_M + Ollama | Stable | 5/5 | fact c8 p95 about 10.3s, throughput about 0.75 rps | about 4.5GB with embedding loaded | Keep as rollback baseline |
| `meta-llama/Llama-3.2-3B-Instruct` BF16 + vLLM | Mixed | 4/5 | fact c8 p95 about 3.3s, throughput about 2.2 rps | about 11.6-14.2GB | Not recommended because schema stability regressed |
| `Qwen/Qwen2.5-7B-Instruct-AWQ` + vLLM | 80/80 | 5/5 | fact c8 p95 about 3.6s, decision burst 20 throughput about 9.2 rps | about 12.7GB | Recommended text candidate |

`VLLM_WSL2_ENABLE_PIN_MEMORY=1` allowed the vLLM V2 runner to start in the
measured WSL2 environment. In Docker on WSL2, CUDA was visible to the parent
process while forked workers could fail CUDA initialization, so the development
profile also uses `VLLM_WORKER_MULTIPROC_METHOD=spawn`. Native Linux deployments
should test the default runner/process method first and only enable WSL2-specific
workarounds where needed.

Runtime activation status on 2026-08-26:

- CoRA Mail now supports role-specific providers, so the intended operating
  shape can be expressed directly: `text=vllm`, `vision=ollama`,
  `embedding=ollama`.
- The web runtime accepted that configuration and resolved text to
  `http://vllm-text:8000/v1` with model `qwen2.5-7b-awq`.
- vLLM 0.27.1 in the current WSL2 Docker environment failed during server
  startup before CoRA Mail could send production traffic. The host and container
  both showed the RTX 5060 Ti via `nvidia-smi`, and Ollama models were unloaded
  to remove VRAM pressure, but vLLM `EngineCore` still failed with
  `RuntimeError: No CUDA GPUs are available`.
- Tried workarounds included `VLLM_WSL2_ENABLE_PIN_MEMORY=1`,
  `VLLM_WORKER_MULTIPROC_METHOD=spawn`, `VLLM_USE_V2_MODEL_RUNNER=0`,
  `VLLM_ENABLE_V1_MULTIPROCESSING=0`, Compose `gpus: all`, and manual
  `docker run --gpus all`.
- Until that host/runtime issue is resolved, keep the active development service
  on Ollama. The role-specific provider implementation remains the correct
  application-side change for switching text to vLLM once the vLLM server starts.

Use `Qwen/Qwen2.5-7B-Instruct-AWQ` as the first on-prem text candidate for the
next migration step. It preserves structured output reliability in the tested
schemas and significantly improves concurrent background Mail Decision and
interactive Search/Chats responsiveness compared with the Ollama baseline.

Do not switch the default provider blindly. The default should move to `vllm` only after:

- structured JSON validation passes for `MailFacts`, `DecisionAgentOutput`, Search plan, and Search synthesis schemas;
- p95 latency improves or remains acceptable at concurrency 4-8;
- timeout/error rate does not regress;
- GPU memory headroom is verified for text plus any concurrent vision/embedding services;
- interactive Search/Chats requests remain responsive while background Mail Decision runs are active.

Current minimum operating recommendation:

- Text: vLLM text server with `Qwen/Qwen2.5-7B-Instruct-AWQ`, max model length 4096, GPU memory utilization 0.75, and text concurrency 16 on the measured RTX 5060 Ti 16GB development machine.
- Vision: keep Ollama until a separate vision backend is benchmarked.
- Embedding: keep Ollama on the development machine; move to a separate embedding backend only when search/routing traffic grows or a larger/multi-GPU operating server is available.
