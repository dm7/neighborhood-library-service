"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import type { BorrowRecord } from "@/lib/types";
import { StatusBanner } from "@/components/StatusBanner";

function dueAtToIso(localDatetime: string): string {
  if (!localDatetime) return "";
  const d = new Date(localDatetime);
  return Number.isNaN(d.getTime()) ? localDatetime : d.toISOString();
}

export default function BorrowPage() {
  const [memberId, setMemberId] = useState("");
  const [copyId, setCopyId] = useState("");
  const [dueLocal, setDueLocal] = useState("");
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
    const due_at = dueAtToIso(dueLocal.trim());
    if (!due_at) {
      setBusy(false);
      setError("Due date/time is required.");
      return;
    }
    const r = await apiFetch<BorrowRecord>("/api/borrow", {
      method: "POST",
      body: JSON.stringify({
        member_id: memberId.trim(),
        copy_id: copyId.trim(),
        due_at,
      }),
    });
    setBusy(false);
    if (!r.ok) {
      setError(`${r.status}: ${r.detail}`);
      return;
    }
    setRecord(r.data);
    setSuccess("Borrow recorded.");
  }

  return (
    <main className="page">
      <h1>Borrow</h1>
      <p className="muted">REST: POST /api/borrow</p>

      <section className="panel">
        <form className="form-grid" onSubmit={onSubmit}>
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
          <label>
            Copy id
            <input
              className="mono"
              value={copyId}
              onChange={(e) => setCopyId(e.target.value)}
              placeholder="33333333-3333-3333-3333-333333333302"
              required
            />
          </label>
          <label>
            Due (local)
            <input
              type="datetime-local"
              value={dueLocal}
              onChange={(e) => setDueLocal(e.target.value)}
              required
            />
          </label>
          <div className="stack">
            <button type="submit" disabled={busy}>
              Borrow
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
