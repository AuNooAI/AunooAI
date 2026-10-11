# What can leave the GPU box

_11 Oct 2026. Inventory of what on this host needs the local GPU, what does not, and what each move
would take. Figures are from the live host on the morning of 11 Oct._

## Summary

Three processes use the card. Everything else is CPU work plus calls to Bedrock through LiteLLM,
and talks to those three only over HTTP on localhost. So any tenant, the saas stack and Postgres can
move to a host without a GPU, as long as the new host can reach a DeBERTa encoder and a LiteLLM
endpoint. The one large GPU dependency, Phi-3 under vLLM, is also the easiest to remove.

The pressure on this box is memory, not compute. 62 GB of RAM, 56 GB in use, swap full, and 30 GB of
vector indexes that the 8 GB page cache cannot hold. Postgres reads them from disk on every
nearest-neighbour query, which is what the `md2_read_storm` alert measures once the embedding-loop
bug fixed this morning is gone.

## What uses the GPU

RTX 4000 Ada, 20.5 GB. 20.1 GB in use.

| Process | GPU memory | Port | Who calls it |
|---|---|---|---|
| vLLM serving Phi-3-mini-4k, from laouad's venv | 17.4 GB | 8765 | Monolith services: summarisation, hybrid relevance, category, KeyBERT tagging, ontology-aware classifier, explanation. saas analyst pipeline: the summarise step. All of them check whether vLLM is up and fall back to an API model when it is not. |
| E5 multilingual-large encoder | 1.8 GB | 8002 | saas only: the ML embedding backfill and the v2 copy channel. Its index is 20 GB. |
| DeBERTa-base encoder, `/opt/deberta-encoder` | 0.9 GB | 8001 | Every tenant and saas: article embeddings, relevance, semantic search. saas prod made 28,968 calls in the last 24 h. Its index is 10 GB. |

The LiteLLM proxy has one alias on the local vLLM, `qwen-vllm`, pointing at Qwen3-8B. The server is
loaded with Phi-3, so that alias is stale and nothing on our side uses it. The monolith and saas
reach vLLM directly through `VLLM_BASE_URL`, not through LiteLLM.

## What is already CPU-only

- The eight monolith tenants (22 GB RSS between them) and the saas web app and worker (6 GB).
- Postgres 16 on 5432 (12 GB RSS) and pgbouncer.
- The two classifier services on 8012 and 8013, and the reranker.
- The LiteLLM proxy on 4000 (6 GB, also laouad's).
- The 19 docker containers, including the firehose stack. None has a GPU device attached.
- neo4j, Redis, the health checks and timers.

All paid model traffic already goes to Bedrock through LiteLLM. On saas prod in the last 24 h:
Nova Lite 16,451 calls for $1.60, Llama 3.3 70B 10,821 for $9.20, Haiku 4.5 3,598 for $10.19,
Sonnet 4.5 813 for $28.06.

## The moves, cheapest first

**1. Replace Phi-3 with a hosted small model.** Point the six monolith services and the saas
summarise step at Nova Lite or Haiku through LiteLLM, or simply stop vLLM and let the existing
fallbacks take over. Frees 17.4 GB of GPU and about 1.5 GB of RAM. Cost goes up by whatever those
calls become on Bedrock; the volume is not in the ledger because local calls are free, so the first
step is a day of counting. About 2 hours of AI work including the count, plus a day of watching the
bill. After this the card holds 2.7 GB and the two encoders have headroom.

**2. Run the DeBERTa encoder on CPU.** DeBERTa-base is about 180M parameters. On CPU it does
perhaps 5 to 20 texts a second, against hundreds on the card. The monolith tenants each make a few
hundred calls an hour, which CPU covers easily. saas prod's 29,000 a day is roughly one every three
seconds on average, so CPU covers that too, but a backfill of millions of rows would not be
practical. About 1 hour to stand up on another host; the service is a single uvicorn app with the
model files under `/opt/deberta-encoder`.

**3. Move a monolith tenant.** Each one needs: its tree and `.venv`, its Postgres database (dump and
restore, sizes vary from a few GB to tens of GB), its encrypted `.env` and the decrypt hooks, a
reachable DeBERTa encoder and LiteLLM endpoint, `VLLM_BASE_URL` pointing at something or left to fall
back, DNS and the reverse proxy entry. The tenants share nothing else. A few hours of AI work each,
most of it the database copy and the first-restart checks. wileytest is a paying customer and goes
last.

**4. Move Postgres to a host with more RAM.** This is the move that ends the read storm. The
database holds 30 GB of HNSW vector indexes and runs with `shared_buffers` at 256 MB, the default.
A host with 64 GB for Postgres alone would keep both indexes in memory. Everything that talks to the
database already goes through pgbouncer or a host:port setting. Half a day of AI work including the
cut-over, plus the copy time for 1.7 TB of data, which is hours of wall clock regardless of who does
it.

**5. Move the saas stack.** Same as a tenant, plus the E5 encoder. E5-large on CPU is slow enough
that the remaining backfill would take days; the options are a small GPU on the new host, keeping
8002 here and calling it over the network, or moving to a Bedrock embedding model and re-embedding
2.8 million rows, since vectors from different models cannot be compared. The last option is the
only one that removes the GPU entirely, and it is a project rather than a move.

## What stays coupled to the card today

Only the two encoders if Phi-3 goes. Together they need under 3 GB, so the floor is a small GPU, or
CPU for DeBERTa and a decision about E5.

## Memory on the box, by component

| Component | RSS |
|---|---|
| Monolith tenants (8 sites) | 22.1 GB |
| Postgres | 12.1 GB |
| saas web, worker and helpers | 6.2 GB |
| LiteLLM proxy | 6.1 GB |
| ML services (encoders, classifiers) | 3.0 GB |
| vLLM host side | 1.5 GB |
| Other (system, monitors, sessions, docker, neo4j) | about 15 GB |

The 30 GB of vector indexes compete with all of this for the 8 GB of page cache that is left.
