# Neighborhood Library Service

Take-home scaffold: **REST (external)** + **gRPC (internal)**, PostgreSQL for domain data, MongoDB for operational/analytics events.

## Quick start

```bash
cp .env.example .env
./scripts/gen_proto.sh
docker compose up --build
```

- REST: http://localhost:8080/health  
- gRPC: `localhost:50051` (internal `LibraryService`, standard health service)  
- Frontend: http://localhost:3000  

## Day 3 interfaces

- External REST (gateway): `GET/POST/PUT /books`, `GET/POST/PUT /members`
- Internal gRPC-only:
  - `BookService` CRUD RPCs
  - `MemberService` CRUD RPCs
  - `LendingService` chatty borrow/return RPC workflow

## Database (PostgreSQL)

Schema and seed live under `db/migrations/` (`001_schema.sql`, `002_seed.sql`). On first container start, Postgres runs `db/init/*.sh` and SQL in order; `99_apply_migrations.sh` applies every `*.sql` file from the mounted migrations directory, so a **new** volume gets tables + seed automatically.

**Reproduce from scratch (recommended when schema changes):**

```bash
docker compose down -v
docker compose up -d postgres
# wait until healthy, then optionally bring up the rest:
docker compose up --build
```

**Apply migrations to an already-running local Postgres** (requires [`psql`](https://www.postgresql.org/docs/current/app-psql.html); uses `POSTGRES_DSN` from the environment or the default in `.env.example`):

```bash
export POSTGRES_DSN="${POSTGRES_DSN:-postgresql://library:library@localhost:5432/library}"
./scripts/db-migrate.sh
```

`GET /health/ready` treats Postgres as ready only when it can connect and the core tables `books`, `members`, `book_copies`, and `borrow_records` exist.

**Optional pytest against a live DB** (same DSN as the gateway):

```bash
cd rest_gateway && pip install -e ".[dev]" && POSTGRES_DSN="$POSTGRES_DSN" pytest tests/test_db_schema.py -v
```

## Tests

```bash
# Python (from repo root; use a venv with dev deps)
cd grpc_service && pip install -e ".[dev]" && pytest
cd ../rest_gateway && pip install -e ".[dev]" && pytest

# Frontend
cd frontend && npm install && npm test
```

## Documentation

See [docs/architecture.md](docs/architecture.md) for process model, data stores, and event schema.

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
