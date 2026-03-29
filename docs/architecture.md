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
| **PostgreSQL** | Normalized library domain data: books, members, loans, holds, etc. |
| **MongoDB** | **Operational and analytics-oriented events** — startup, readiness probes, RPC markers, and future metrics-friendly documents. Not the system of record for lending state. |

### MongoDB event schema (`library_ops.service_events`)

Documents are append-only and **explicitly keyed** for rollups and dashboards:

- `service` — `grpc_service` \| `rest_gateway` (extend as you add workers).
- `event` — e.g. `startup`, `readiness_probe`, `rpc_ping`.
- `ts` — UTC timestamp.
- `extra` — optional JSON-safe object (booleans, counts, error classes — avoid huge payloads).

**Matrices / clarity:** filter by `service` × `event` × time window to see process-flow health (e.g. gateway readiness vs gRPC reachability) and later RPC volume or error rates.

## Interfaces (Day 1)

- **REST:** `GET /health` — liveness. `GET /health/ready` — dependency matrix (gRPC ping, Postgres, optional Mongo).
- **gRPC:** `library.v1.LibraryService/Ping` — internal connectivity. Standard **gRPC Health Checking Protocol** (`grpc.health.v1.Health`) is registered for ops probes.

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
