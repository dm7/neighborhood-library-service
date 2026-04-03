"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import type { BorrowRecord } from "@/lib/types";
import { StatusBanner } from "@/components/StatusBanner";

function toIsoOrEmpty(localDatetime: string): string {
  if (!localDatetime.trim()) return "";
  const d = new Date(localDatetime);
  return Number.isNaN(d.getTime()) ? localDatetime : d.toISOString();
}

export default function ReturnPage() {
  const [copyId, setCopyId] = useState("");
  const [returnedLocal, setReturnedLocal] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [record, setRecord] = useState<BorrowRecord | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    setRecord(null);
    const returned_at = toIsoOrEmpty(returnedLocal);
    const r = await apiFetch<BorrowRecord>("/api/return", {
      method: "POST",
      body: JSON.stringify({
        copy_id: copyId.trim(),
        returned_at,
      }),
    });
    setBusy(false);
    if (!r.ok) {
      setError(`${r.status}: ${r.detail}`);
      return;
    }
    setRecord(r.data);
    setSuccess("Return recorded.");
  }

  return (
    <main className="page">
      <h1>Return</h1>
      <p className="muted">
        REST: POST /api/return — leave return time empty to use server time.
      </p>

      <section className="panel">
        <form className="form-grid" onSubmit={onSubmit}>
          <label>
            Copy id
            <input
              className="mono"
              value={copyId}
              onChange={(e) => setCopyId(e.target.value)}
              required
            />
          </label>
          <label>
            Returned at (optional, local)
            <input
              type="datetime-local"
              value={returnedLocal}
              onChange={(e) => setReturnedLocal(e.target.value)}
            />
          </label>
          <div className="stack">
            <button type="submit" disabled={busy}>
              Return copy
            </button>
          </div>
        </form>
        <StatusBanner error={error} success={success} />
        {record && (
          <pre
            className="mono"
            style={{
              marginTop: "1rem",
              padding: "0.75rem",
              background: "#f4f2ef",
              borderRadius: 4,
              fontSize: "0.8rem",
              overflow: "auto",
            }}
          >
            {JSON.stringify(record, null, 2)}
          </pre>
        )}
      </section>
    </main>
  );
}
