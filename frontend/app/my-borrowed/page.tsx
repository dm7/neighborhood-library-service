"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { LoanRow } from "@/lib/types";
import { StatusBanner } from "@/components/StatusBanner";

const STORAGE_KEY = "library:lastMemberId";

export default function MyBorrowedPage() {
  const [memberId, setMemberId] = useState("");
  const [loans, setLoans] = useState<LoanRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetched, setFetched] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) setMemberId(saved);
    } catch {
      /* ignore */
    }
  }, []);

  const load = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      const id = memberId.trim();
      if (!id) {
        setError("Enter a member id.");
        return;
      }
      setLoading(true);
      setError(null);
      setFetched(false);
      try {
        localStorage.setItem(STORAGE_KEY, id);
      } catch {
        /* ignore */
      }
      const r = await apiFetch<LoanRow[]>(
        `/api/members/${encodeURIComponent(id)}/borrowed`,
      );
      setLoading(false);
      if (!r.ok) {
        setLoans([]);
        setError(`${r.status}: ${r.detail}`);
        return;
      }
      setFetched(true);
      setLoans(r.data);
    },
    [memberId],
  );

  return (
    <main className="page">
      <h1>My borrowed books</h1>
      <p className="muted">
        REST: GET /api/members/:member_id/borrowed — member id is remembered in
        this browser.
      </p>

      <section className="panel">
        <form className="form-grid" onSubmit={(ev) => void load(ev)}>
          <label>
            Member id
            <input
              className="mono"
              value={memberId}
              onChange={(e) => setMemberId(e.target.value)}
              placeholder="22222222-2222-2222-2222-222222222201"
              required
            />
          </label>
          <div className="stack">
            <button type="submit" disabled={loading}>
              {loading ? "Loading…" : "Load"}
            </button>
          </div>
        </form>
        <StatusBanner error={error} />
        {fetched && !error && loans.length === 0 && (
          <p className="muted" style={{ marginTop: "0.75rem" }}>
            No active loans for this member.
          </p>
        )}
        {loans.length > 0 && (
          <div style={{ marginTop: "1rem", overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Author</th>
                  <th>Barcode</th>
                  <th>Due</th>
                  <th>Copy id</th>
                </tr>
              </thead>
              <tbody>
                {loans.map((row) => (
                  <tr key={row.borrow_record.id}>
                    <td>{row.book.title}</td>
                    <td>{row.book.author}</td>
                    <td className="mono">{row.copy_barcode}</td>
                    <td className="mono">{row.borrow_record.due_at}</td>
                    <td className="mono">{row.borrow_record.copy_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
