-- Day 2: core domain tables (PostgreSQL 16+; gen_random_uuid() is built-in).

CREATE TYPE copy_status AS ENUM ('available', 'on_loan', 'lost', 'retired');

CREATE TABLE books (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  author TEXT NOT NULL,
  isbn TEXT,
  published_year SMALLINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT books_isbn_key UNIQUE (isbn)
);

CREATE TABLE members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT members_email_key UNIQUE (email)
);

CREATE TABLE book_copies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID NOT NULL REFERENCES books (id) ON DELETE CASCADE,
  barcode TEXT NOT NULL,
  status copy_status NOT NULL DEFAULT 'available',
  acquired_at DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT book_copies_barcode_key UNIQUE (barcode)
);

CREATE INDEX book_copies_book_id_idx ON book_copies (book_id);
CREATE INDEX book_copies_status_idx ON book_copies (status);

CREATE TABLE borrow_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  copy_id UUID NOT NULL REFERENCES book_copies (id) ON DELETE RESTRICT,
  member_id UUID NOT NULL REFERENCES members (id) ON DELETE RESTRICT,
  borrowed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  due_at TIMESTAMPTZ NOT NULL,
  returned_at TIMESTAMPTZ,
  notes TEXT
);

CREATE INDEX borrow_records_member_id_idx ON borrow_records (member_id);
CREATE INDEX borrow_records_copy_id_idx ON borrow_records (copy_id);

-- At most one open loan per physical copy.
CREATE UNIQUE INDEX borrow_records_one_open_per_copy_idx
  ON borrow_records (copy_id)
  WHERE returned_at IS NULL;
