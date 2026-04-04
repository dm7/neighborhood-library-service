# Neighborhood Library Service

Take-home scaffold: **REST (external)** + **gRPC (internal)**, PostgreSQL for domain data, MongoDB for operational/analytics events.

## Evaluator quick start (Docker)

Prerequisites: **Docker** with Compose v2, and free ports **3000**, **8080**, **50051**, **5432**, **27017**.

```bash
cp .env.example .env
./scripts/gen_proto.sh
docker compose up --build
```

| Surface | Where |
|--------|--------|
| Frontend | http://localhost:3000 |
| REST API | http://localhost:8080 (`/health`, `/books`, `/members`, `/api/borrow`, …) |
| gRPC (internal) | `localhost:50051` — `LibraryService`, `BookService`, `MemberService`, `LendingService`, plus standard gRPC health |
| PostgreSQL | `localhost:5432` — user `library`, password `library`, database `library` |
| MongoDB | `localhost:27017` |

Smoke checks: `curl -s http://localhost:8080/health` and [Sample `curl` commands](#sample-curl-commands). For raw gRPC, see [Optional: internal gRPC demo (Python)](#optional-internal-grpc-demo-python).

## PostgreSQL setup

Schema and seed live in `db/migrations/` (`001_schema.sql`, `002_seed.sql`). On **first** container start, Postgres runs `db/init/*.sh`; `99_apply_migrations.sh` applies every `*.sql` from the mounted migrations directory, so a **new** volume gets tables + seed automatically.

**Reset the database** (recommended after schema changes):

```bash
docker compose down -v
docker compose up -d postgres
# when healthy, bring up the full stack:
docker compose up --build
```

**Apply migrations to Postgres that is already running** (host or container), using [`psql`](https://www.postgresql.org/docs/current/app-psql.html) via `POSTGRES_DSN` (default matches `.env.example`):

```bash
export POSTGRES_DSN="${POSTGRES_DSN:-postgresql://library:library@localhost:5432/library}"
./scripts/db-migrate.sh
```

`GET /health/ready` requires a working Postgres connection and the core tables `books`, `members`, `book_copies`, and `borrow_records`.

**Optional pytest against a live DB** (same DSN as the gateway):

```bash
cd rest_gateway && pip install -e ".[dev]" && POSTGRES_DSN="$POSTGRES_DSN" pytest tests/test_db_schema.py -v
```

## Protocol buffer code generation

From the **repository root**. The script uses `grpc_service/.venv/bin/python` when that venv exists; otherwise it uses `python3` and must be able to import `grpc_tools`. If it exits with “grpc_tools not found”, run once:

`cd grpc_service && python3 -m venv .venv && .venv/bin/pip install -e .`

```bash
./scripts/gen_proto.sh
```

This invokes `python3 -m grpc_tools.protoc` on `proto/library/v1/library.proto` and emits `library/v1/library_pb2.py` and `library_pb2_grpc.py` under both `grpc_service/src/` and `rest_gateway/src/`. **Regenerate after any `.proto` change**, then rebuild Docker images or restart local processes.

## Run the gRPC server (local Python)

Requires **PostgreSQL** and **MongoDB** reachable at the configured DSN/URI (e.g. start `postgres` and `mongo` with `docker compose up -d postgres mongo`).

```bash
./scripts/gen_proto.sh
cd grpc_service
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
export GRPC_BIND_HOST=0.0.0.0
export GRPC_PORT=50051
export POSTGRES_DSN=postgresql://library:library@localhost:5432/library
export MONGODB_URI=mongodb://localhost:27017
export MONGODB_DB=library_ops
python -m neighborhood_library_grpc
```

Listens on **50051** by default.

## Run the REST gateway (local Python)

```bash
./scripts/gen_proto.sh
cd rest_gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
export REST_BIND_HOST=0.0.0.0
export REST_PORT=8080
export GRPC_TARGET=localhost:50051
export POSTGRES_DSN=postgresql://library:library@localhost:5432/library
export MONGODB_URI=mongodb://localhost:27017
export MONGODB_DB=library_ops
python -m neighborhood_library_gateway
```

## Run the frontend (local Node)

```bash
cd frontend
npm install
export NEXT_PUBLIC_API_BASE=http://localhost:8080
npm run dev
```

Dev server: http://localhost:3000 (Next.js).

## Sample `curl` commands

Assumes REST at `http://localhost:8080` and seed UUIDs from `db/migrations/002_seed.sql`.

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8080/health/ready

curl -s "http://localhost:8080/books?limit=5"
curl -s "http://localhost:8080/members?limit=5"

curl -s -X POST http://localhost:8080/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Demo Book","author":"You","isbn":"","published_year":2026}'

curl -s -X POST http://localhost:8080/members \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Demo Member","email":"demo@example.local","phone":""}'

# Borrow: gateway runs multiple LendingService RPCs (chatty internal workflow)
curl -s -X POST http://localhost:8080/api/borrow \
  -H "Content-Type: application/json" \
  -d '{"member_id":"22222222-2222-2222-2222-222222222202","copy_id":"33333333-3333-3333-3333-333333333303","due_at":"2026-06-01T23:59:59Z"}'

curl -s "http://localhost:8080/api/members/22222222-2222-2222-2222-222222222202/borrowed"

curl -s -X POST http://localhost:8080/api/return \
  -H "Content-Type: application/json" \
  -d '{"copy_id":"33333333-3333-3333-3333-333333333303"}'
```

**Seed loan already on file** (Ada + `COPY-LHD-001`):  
`curl -s "http://localhost:8080/api/members/22222222-2222-2222-2222-222222222201/borrowed"`

## Optional: internal gRPC demo (Python)

[`scripts/grpc_chatty_demo.py`](scripts/grpc_chatty_demo.py) performs the same **chatty** `LendingService` sequence as the gateway (check eligibility → check copy → `StartBorrow` → `MarkCopyOnLoan`, then `ListBorrowedByMember`, then `GetOpenBorrowByCopy` → `ReturnBorrow` → `MarkCopyAvailable`).

```bash
./scripts/gen_proto.sh
cd grpc_service && pip install -e . && cd ..
export GRPC_TARGET=localhost:50051
PYTHONPATH=grpc_service/src python3 scripts/grpc_chatty_demo.py
```

Defaults target seed **Grace Hopper** and available copy **COPY-PHM-001**. If that copy is already on loan, pass `--copy-id` for another available copy or reset the DB (`docker compose down -v`).

## Day 3 interfaces

- External REST (gateway): `GET/POST/PUT /books`, `GET/POST/PUT /members`, `POST /api/borrow`, `GET /api/members/{id}/borrowed`, `POST /api/return`
- Internal gRPC-only:
  - `BookService` CRUD RPCs
  - `MemberService` CRUD RPCs
  - `LendingService` chatty borrow/return RPC workflow

## Tests

```bash
# Python (from repo root; use a venv with dev deps)
cd grpc_service && pip install -e ".[dev]" && pytest
cd ../rest_gateway && pip install -e ".[dev]" && pytest

# Frontend
cd frontend && npm install && npm test
```

**Integration (live services):**

```bash
# gRPC against a running grpc_service + migrated Postgres
export RUN_INTEGRATION=1 GRPC_TARGET=localhost:50051
cd grpc_service && pytest tests/test_grpc_live_rpcs.py -v

# REST against a running gateway
export RUN_INTEGRATION=1 REST_BASE_URL=http://localhost:8080
cd rest_gateway && pytest tests/test_rest_live.py -v
```

**Optional HTTP smoke** (read-only; expects seed data):

```bash
REST_BASE_URL=http://localhost:8080 ./scripts/rest_smoke.sh
```

## Testing and API errors (evaluation)

| gRPC code | Typical case | REST status |
|-----------|----------------|-------------|
| `INVALID_ARGUMENT` | Bad field values, bad timestamps | 400 |
| `NOT_FOUND` | Missing book, member, or open borrow | 404 |
| `ALREADY_EXISTS` | Duplicate ISBN or email | 409 |
| `FAILED_PRECONDITION` | Copy not available (e.g. **already checked out**), bad shelf state | 409 |
| `ABORTED` | Idempotent conflict (e.g. already returned) | 409 |
| `UNAVAILABLE` | Backend / gRPC down | 503 |

`POST /api/borrow` runs internal `CheckMemberEligibility` and `CheckCopyAvailability` first: unknown member or copy → **404**; `copy_already_checked_out` (and related codes) → **409** with the reason string in `detail`. Proto comments in `proto/library/v1/library.proto` document `CheckCopyAvailabilityResponse.reason` values.

## Documentation

See [docs/architecture.md](docs/architecture.md) for process model, data stores, and event schema, and [docs/schema.md](docs/schema.md) for PostgreSQL relationships and invariants.

## Git and Husky

This repository is intended to track [dm7/neighborhood-library-service](https://github.com/dm7/neighborhood-library-service) as `origin` on branch `main`.

### Branch model

| Branch | Role |
|--------|------|
| `main` | Default integration branch; merge reviewed work here. |
| `development` | Day-to-day integration (optional alternative to `main` if you prefer Git Flow). |
| `staging` | Pre-production / release candidate validation. |
| `testing` | QA and automated/manual test runs against a stable tip. |
| `production` | What you deploy or tag for production (promote from `staging` when ready). |
| `feature/*` | Short-lived work (e.g. `feature/scaffolding-split-runtime`). |

Work for **Scaffolding + split runtime** should be committed on **`feature/scaffolding-split-runtime`** (that is the current branch if you followed the repo setup). After your first commit, create the other long-lived branches at the same revision:

```bash
./scripts/git-create-workflow-branches.sh
```

That adds `main`, `development`, `staging`, `testing`, and `production` when they do not already exist. Merge or reset them to match your team’s promotion rules.

### Hooks and “restricted” committers (local)

[Husky](https://typicode.github.io/husky/) runs **`.husky/pre-commit`** on every commit:

1. **Committer allowlist** — If `config/git-allowed-committers` exists (not committed; copy from `config/git-allowed-committers.example`), the hook allows commits only when `git config user.email` matches a line in that file. With no file present, the check is skipped unless you set `GIT_STRICT_COMMITTER=1` (then the file is required). Emergency bypass (use sparingly): `GIT_COMMITTER_ALLOW_ALL=1 git commit ...`.
2. **Python** — `python3 -m compileall` on gRPC and REST packages.
3. **Frontend** — `npm run test` under `frontend/` when `node_modules` is installed.

**Important:** Local hooks are trivial to bypass; real enforcement belongs on the server (for example [GitHub branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), required reviews, and restricting who can push to `production` / `main`).

After cloning, install root dev dependencies so Git wires Husky:

```bash
git clone https://github.com/dm7/neighborhood-library-service.git
cd neighborhood-library-service
npm install
```

If the GitHub repo already has commits (for example `LICENSE` / `README`), integrate them before the first push:

```bash
git fetch origin
git pull origin main --allow-unrelated-histories
# resolve conflicts if any, then:
git push -u origin main
```

Or, if you intend to replace the remote history entirely, use a forced push only when you accept overwriting what is on GitHub.

## What stays out of Git

See `.gitignore`: local PDFs, `.env`, virtualenvs (including under `grpc_service/` / `rest_gateway/`), `node_modules`, Python caches (e.g. `.pytest_cache`, `*.egg-info`), `frontend/package-lock.json`, and build output such as `frontend/.next/`.
