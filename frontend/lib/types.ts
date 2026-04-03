export type Book = {
  id: string;
  title: string;
  author: string;
  isbn: string;
  published_year: number;
  created_at: string;
};

export type Member = {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  created_at: string;
};

export type BorrowRecord = {
  id: string;
  copy_id: string;
  member_id: string;
  borrowed_at: string;
  due_at: string;
  returned_at: string;
  notes: string;
};

export type LoanRow = {
  borrow_record: BorrowRecord;
  book: Book;
  member: Member;
  copy_barcode: string;
};
