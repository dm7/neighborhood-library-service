# PostgreSQL domain schema

This document explains the **normalized** relational model for the library system of record. SQL lives in `db/migrations/`.

## Entity–relationship overview

- **`books`** — Logical title (catalog entry): one row per work/edition you track.
- **`book_copies`** — Physical item on the shelf. Many copies can reference one `book_id`. Borrowing always targets a **copy**, not an abstract book.
- **`members`** — Patrons who may borrow copies.
- **`borrow_records`** — Loan history: who has which copy, when it is due, and when it was returned.

Relationships:

- `book_copies.book_id` → `books.id` (**many-to-one**), `ON DELETE CASCADE` (removing a catalog entry removes its copies).
- `borrow_records.copy_id` → `book_copies.id` (**many-to-one**), `ON DELETE RESTRICT` (cannot delete a copy that still has loan rows you must preserve).
- `borrow_records.member_id` → `members.id` (**many-to-one**), `ON DELETE RESTRICT`.

## Invariants

| Invariant | Enforcement |
|-----------|-------------|
| At most one **open** loan per physical copy | Partial unique index on `borrow_records (copy_id)` **where** `returned_at IS NULL`. |
| Copy circulation state | Enum `copy_status`: `available`, `on_loan`, `lost`, `retired`. |
| One ISBN per book (when ISBN is set) | `UNIQUE (isbn)` on `books` (nullable ISBN allowed). |
| One email per member | `UNIQUE (email)` on `members`. |
| One barcode per copy | `UNIQUE (barcode)` on `book_copies`. |

Later migrations add **CHECK** constraints for non-empty trimmed text and sensible `published_year` ranges so bad rows are rejected at the database boundary as well as in the API layer.

## Indexes

- `book_copies (book_id)` — list copies for a title.
- `book_copies (status)` — filter by shelf state.
- `borrow_records (member_id)`, `borrow_records (copy_id)` — loan lookups.

## Lending lifecycle (state)

1. A copy in **`available`** may start a new open `borrow_records` row and move to **`on_loan`** (see gRPC `LendingService` / REST `POST /api/borrow`).
2. Return closes the open row (`returned_at` set) and moves the copy back to **`available`** (`POST /api/return`).
3. **`lost`** / **`retired`** copies should not circulate; `CheckCopyAvailability` reports them with explicit reasons (see proto comments on `CheckCopyAvailabilityResponse`).

For internal RPC semantics and REST ↔ gRPC status mapping, see [architecture.md](architecture.md) and the **Testing & API errors** section in the root [README](../README.md).
