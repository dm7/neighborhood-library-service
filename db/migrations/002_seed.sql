-- Idempotent seed (fixed UUIDs) for local dev and demos.

INSERT INTO books (id, title, author, isbn, published_year)
VALUES
  (
    '11111111-1111-1111-1111-111111111101',
    'The Left Hand of Darkness',
    'Ursula K. Le Guin',
    '9780441478125',
    1969
  ),
  (
    '11111111-1111-1111-1111-111111111102',
    'Project Hail Mary',
    'Andy Weir',
    '9780593135204',
    2021
  ),
  (
    '11111111-1111-1111-1111-111111111103',
    'Working Effectively with Legacy Code',
    'Michael Feathers',
    '9780131177055',
    2004
  )
ON CONFLICT (id) DO NOTHING;

INSERT INTO members (id, full_name, email, phone)
VALUES
  (
    '22222222-2222-2222-2222-222222222201',
    'Ada Lovelace',
    'ada@example.local',
    NULL
  ),
  (
    '22222222-2222-2222-2222-222222222202',
    'Grace Hopper',
    'grace@example.local',
    NULL
  )
ON CONFLICT (id) DO NOTHING;

INSERT INTO book_copies (id, book_id, barcode, status, acquired_at)
VALUES
  (
    '33333333-3333-3333-3333-333333333301',
    '11111111-1111-1111-1111-111111111101',
    'COPY-LHD-001',
    'on_loan',
    '2024-01-15'
  ),
  (
    '33333333-3333-3333-3333-333333333302',
    '11111111-1111-1111-1111-111111111101',
    'COPY-LHD-002',
    'available',
    '2024-02-01'
  ),
  (
    '33333333-3333-3333-3333-333333333303',
    '11111111-1111-1111-1111-111111111102',
    'COPY-PHM-001',
    'available',
    '2024-03-10'
  ),
  (
    '33333333-3333-3333-3333-333333333304',
    '11111111-1111-1111-1111-111111111103',
    'COPY-LEG-001',
    'available',
    '2023-11-20'
  )
ON CONFLICT (id) DO NOTHING;

-- Open loan: Ada has COPY-LHD-001
INSERT INTO borrow_records (id, copy_id, member_id, borrowed_at, due_at, returned_at, notes)
VALUES
  (
    '44444444-4444-4444-4444-444444444401',
    '33333333-3333-3333-3333-333333333301',
    '22222222-2222-2222-2222-222222222201',
    '2025-03-01 10:00:00+00',
    '2025-03-29 23:59:59+00',
    NULL,
    'Day 2 seed loan'
  )
ON CONFLICT (id) DO NOTHING;

-- Returned loan (history): Grace had COPY-LHD-002 in the past
INSERT INTO borrow_records (id, copy_id, member_id, borrowed_at, due_at, returned_at, notes)
VALUES
  (
    '44444444-4444-4444-4444-444444444402',
    '33333333-3333-3333-3333-333333333302',
    '22222222-2222-2222-2222-222222222202',
    '2024-12-01 14:00:00+00',
    '2024-12-15 23:59:59+00',
    '2024-12-10 16:30:00+00',
    'Returned early'
  )
ON CONFLICT (id) DO NOTHING;
