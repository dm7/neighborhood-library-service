# Neighborhood Library — architecture (Day 1)

## Runtime split (process model **B**)

Two Python processes, orchestrated by Docker Compose:

| Process | Role | Visibility | Notes |
|--------|------|------------|--------|
| **rest_gateway** | HTTP/REST API | **External** — browsers, integrations, staff tools | Coarse-grained resources; stable public contract. |
| **grpc_service** | gRPC API | **Internal** — only the gateway (and tests/ops) | Chatty, low-latency calls for lending workflows. |

**Why two processes:** keeps “public REST” and “internal gRPC” obvious in logs, metrics, and security boundaries. The gateway is the single entry point from the Internet/VPC edge; gRPC is not exposed to end users.

**Borrow / return (later days):** expect a **chatty gRPC** interaction model (validate member → check copy → write loan → emit events) while REST exposes aggregate commands or BFF-style payloads so the frontend does not open many HTTP requests for one user action.

## Data stores

| Store | Purpose |
|-------|---------|
| **PostgreSQL** | Normalized library domain data. **Day 2:** `books`, `members`, `book_copies` (physical items), `borrow_records` (loans; partial unique index enforces one open loan per copy). Later migrations add CHECK constraints for text and years. Migrations + seed: `db/migrations/`. See [schema.md](schema.md) for the ER model and invariants. |
| **MongoDB** | **Operational and analytics-oriented events** — startup, readiness probes, RPC markers, and future metrics-friendly documents. Not the system of record for lending state. |

### MongoDB event schema (`library_ops.service_events`)

Documents are append-only and **explicitly keyed** for rollups and dashboards:

- `service` — `grpc_service` \| `rest_gateway` (extend as you add workers).
- `event` — e.g. `startup`, `readiness_probe`, `rpc_ping`.
- `ts` — UTC timestamp.
- `extra` — optional JSON-safe object (booleans, counts, error classes — avoid huge payloads).

**Matrices / clarity:** filter by `service` × `event` × time window to see process-flow health (e.g. gateway readiness vs gRPC reachability) and later RPC volume or error rates.

## Interfaces (Day 3)

- **REST:** `GET /health` — liveness, `GET /health/ready` — dependency matrix, plus external book/member proxy routes:
  `GET/POST/PUT /books` and `GET/POST/PUT /members`, and lending aggregates `POST /api/borrow`, `GET /api/members/{id}/borrowed`, `POST /api/return`.
  Request bodies are validated with Pydantic (422 on bad input). Borrow conflicts (e.g. copy already on loan) map to **409** with a stable `detail` string; missing member/copy on the pre-check path map to **404**.
- **gRPC:** internal-only services: `LibraryService/Ping` (connectivity), `BookService` + `MemberService` CRUD RPCs, and a chatty `LendingService` borrow/return workflow surface.
  `CheckCopyAvailabilityResponse.reason` uses machine-stable codes (see comments in `proto/library/v1/library.proto`). Standard **gRPC Health Checking Protocol** (`grpc.health.v1.Health`) is also registered for ops probes.

## Repository layout

- `proto/` — Protobuf sources; run `./scripts/gen_proto.sh` after edits (requires `grpcio-tools`).
- `grpc_service/` — internal gRPC server implementation.
- `rest_gateway/` — FastAPI REST gateway.
- `frontend/` — Next.js UI (calls REST only).
- `db/` — PostgreSQL init/migrations assets.

## Local development

1. Copy `.env.example` to `.env` and adjust if needed.
2. `./scripts/gen_proto.sh` — regenerates `library.v1` Python stubs under each service `src/`.
3. `docker compose up --build` — Postgres, MongoDB, gRPC, REST, frontend.

Health checks:

- `curl -s http://localhost:8080/health`
- `curl -s http://localhost:8080/health/ready`
- gRPC health: use [`grpcurl`](https://github.com/fullstorydev/grpcurl) against `:50051` with `grpc.health.v1.Health/Check` (optional tooling).
