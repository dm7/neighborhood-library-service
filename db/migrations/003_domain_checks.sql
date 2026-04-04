-- Domain CHECK constraints: align DB boundary with API validation (PostgreSQL).

ALTER TABLE books
  ADD CONSTRAINT books_title_trimmed_nonempty CHECK (length(trim(title)) > 0),
  ADD CONSTRAINT books_author_trimmed_nonempty CHECK (length(trim(author)) > 0);

ALTER TABLE books
  ADD CONSTRAINT books_published_year_range CHECK (
    published_year IS NULL
    OR (
      published_year >= 1000
      AND published_year <= (EXTRACT(YEAR FROM CURRENT_DATE)::int + 5)
    )
  );

ALTER TABLE members
  ADD CONSTRAINT members_full_name_trimmed_nonempty CHECK (length(trim(full_name)) > 0),
  ADD CONSTRAINT members_email_trimmed_nonempty CHECK (length(trim(email)) > 0),
  ADD CONSTRAINT members_email_basic_format CHECK (
    email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
  );

ALTER TABLE book_copies
  ADD CONSTRAINT book_copies_barcode_trimmed_nonempty CHECK (length(trim(barcode)) > 0);
