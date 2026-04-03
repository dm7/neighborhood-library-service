"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { Book } from "@/lib/types";
import { StatusBanner } from "@/components/StatusBanner";

export default function BooksPage() {
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [isbn, setIsbn] = useState("");
  const [publishedYear, setPublishedYear] = useState("");

  const [editId, setEditId] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editAuthor, setEditAuthor] = useState("");
  const [editIsbn, setEditIsbn] = useState("");
  const [editYear, setEditYear] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const r = await apiFetch<Book[]>("/books?limit=100&offset=0");
    setLoading(false);
    if (!r.ok) {
      setError(`${r.status}: ${r.detail}`);
      return;
    }
    setBooks(r.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    const year = publishedYear.trim() ? Number(publishedYear) : 0;
    const r = await apiFetch<Book>("/books", {
      method: "POST",
      body: JSON.stringify({
        title: title.trim(),
        author: author.trim(),
        isbn: isbn.trim(),
        published_year: Number.isFinite(year) ? year : 0,
      }),
    });
    setBusy(false);
    if (!r.ok) {
      setError(`${r.status}: ${r.detail}`);
      return;
    }
    setSuccess(`Created book ${r.data.id}`);
    setTitle("");
    setAuthor("");
    setIsbn("");
    setPublishedYear("");
    void load();
  }

  async function onUpdate(e: React.FormEvent) {
    e.preventDefault();
    const id = editId.trim();
    if (!id) {
      setError("Book id is required for update.");
      return;
    }
    setBusy(true);
    setError(null);
    setSuccess(null);
    const year = editYear.trim() ? Number(editYear) : 0;
    const r = await apiFetch<Book>(`/books/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify({
        title: editTitle.trim(),
        author: editAuthor.trim(),
        isbn: editIsbn.trim(),
        published_year: Number.isFinite(year) ? year : 0,
      }),
    });
    setBusy(false);
    if (!r.ok) {
      setError(`${r.status}: ${r.detail}`);
      return;
    }
    setSuccess(`Updated book ${r.data.id}`);
    void load();
  }

  return (
    <main className="page">
      <h1>Books</h1>
      <p className="muted">REST: GET/POST /books, PUT /books/:id</p>
      <StatusBanner error={error} success={success} />

      <section className="panel">
        <h2>Catalog</h2>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : books.length === 0 ? (
          <p className="muted">No books.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Author</th>
                  <th>ISBN</th>
                  <th>Year</th>
                  <th>Id</th>
                </tr>
              </thead>
              <tbody>
                {books.map((b) => (
                  <tr key={b.id}>
                    <td>{b.title}</td>
                    <td>{b.author}</td>
                    <td>{b.isbn || "—"}</td>
                    <td>{b.published_year || "—"}</td>
                    <td className="mono">{b.id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <button
          type="button"
          className="secondary"
          style={{ marginTop: "0.75rem" }}
          onClick={() => void load()}
        >
          Refresh
        </button>
      </section>

      <section className="panel">
        <h2>Add book</h2>
        <form className="form-grid two" onSubmit={onCreate}>
          <label>
            Title
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
          </label>
          <label>
            Author
            <input
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              required
            />
          </label>
          <label>
            ISBN
            <input value={isbn} onChange={(e) => setIsbn(e.target.value)} />
          </label>
          <label>
            Published year
            <input
              type="number"
              value={publishedYear}
              onChange={(e) => setPublishedYear(e.target.value)}
            />
          </label>
          <div className="stack" style={{ gridColumn: "1 / -1" }}>
            <button type="submit" disabled={busy}>
              Create
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <h2>Update book</h2>
        <form className="form-grid two" onSubmit={onUpdate}>
          <label style={{ gridColumn: "1 / -1" }}>
            Book id
            <input
              className="mono"
              value={editId}
              onChange={(e) => setEditId(e.target.value)}
              placeholder="uuid"
              required
            />
          </label>
          <label>
            Title
            <input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              required
            />
          </label>
          <label>
            Author
            <input
              value={editAuthor}
              onChange={(e) => setEditAuthor(e.target.value)}
              required
            />
          </label>
          <label>
            ISBN
            <input value={editIsbn} onChange={(e) => setEditIsbn(e.target.value)} />
          </label>
          <label>
            Published year
            <input
              type="number"
              value={editYear}
              onChange={(e) => setEditYear(e.target.value)}
            />
          </label>
          <div className="stack" style={{ gridColumn: "1 / -1" }}>
            <button type="submit" disabled={busy}>
              Save
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
