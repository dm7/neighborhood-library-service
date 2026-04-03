"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { Member } from "@/lib/types";
import { StatusBanner } from "@/components/StatusBanner";

export default function MembersPage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");

  const [editId, setEditId] = useState("");
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const r = await apiFetch<Member[]>("/members?limit=100&offset=0");
    setLoading(false);
    if (!r.ok) {
      setError(`${r.status}: ${r.detail}`);
      return;
    }
    setMembers(r.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    const r = await apiFetch<Member>("/members", {
      method: "POST",
      body: JSON.stringify({
        full_name: fullName.trim(),
        email: email.trim(),
        phone: phone.trim(),
      }),
    });
    setBusy(false);
    if (!r.ok) {
      setError(`${r.status}: ${r.detail}`);
      return;
    }
    setSuccess(`Created member ${r.data.id}`);
    setFullName("");
    setEmail("");
    setPhone("");
    void load();
  }

  async function onUpdate(e: React.FormEvent) {
    e.preventDefault();
    const id = editId.trim();
    if (!id) {
      setError("Member id is required for update.");
      return;
    }
    setBusy(true);
    setError(null);
    setSuccess(null);
    const r = await apiFetch<Member>(`/members/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify({
        full_name: editName.trim(),
        email: editEmail.trim(),
        phone: editPhone.trim(),
      }),
    });
    setBusy(false);
    if (!r.ok) {
      setError(`${r.status}: ${r.detail}`);
      return;
    }
    setSuccess(`Updated member ${r.data.id}`);
    void load();
  }

  return (
    <main className="page">
      <h1>Members</h1>
      <p className="muted">REST: GET/POST /members, PUT /members/:id</p>
      <StatusBanner error={error} success={success} />

      <section className="panel">
        <h2>Directory</h2>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : members.length === 0 ? (
          <p className="muted">No members.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Phone</th>
                  <th>Id</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id}>
                    <td>{m.full_name}</td>
                    <td>{m.email}</td>
                    <td>{m.phone || "—"}</td>
                    <td className="mono">{m.id}</td>
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
        <h2>Add member</h2>
        <form className="form-grid two" onSubmit={onCreate}>
          <label>
            Full name
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </label>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label style={{ gridColumn: "1 / -1" }}>
            Phone
            <input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          <div className="stack" style={{ gridColumn: "1 / -1" }}>
            <button type="submit" disabled={busy}>
              Create
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <h2>Update member</h2>
        <form className="form-grid two" onSubmit={onUpdate}>
          <label style={{ gridColumn: "1 / -1" }}>
            Member id
            <input
              className="mono"
              value={editId}
              onChange={(e) => setEditId(e.target.value)}
              placeholder="uuid"
              required
            />
          </label>
          <label>
            Full name
            <input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              required
            />
          </label>
          <label>
            Email
            <input
              type="email"
              value={editEmail}
              onChange={(e) => setEditEmail(e.target.value)}
              required
            />
          </label>
          <label style={{ gridColumn: "1 / -1" }}>
            Phone
            <input value={editPhone} onChange={(e) => setEditPhone(e.target.value)} />
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
