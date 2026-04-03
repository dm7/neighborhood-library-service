import Link from "next/link";

export default function Home() {
  const base =
    process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080 (default)";
  return (
    <main className="page">
      <h1>Neighborhood Library</h1>
      <p className="muted">
        Staff UI over the REST gateway. API base:{" "}
        <span className="mono">{base}</span>
      </p>
      <ul style={{ marginTop: "1.5rem", lineHeight: 1.8 }}>
        <li>
          <Link href="/books">Books</Link> — list, add, update
        </li>
        <li>
          <Link href="/members">Members</Link> — list, add, update
        </li>
        <li>
          <Link href="/borrow">Borrow</Link> — check out a copy for a member
        </li>
        <li>
          <Link href="/return">Return</Link> — check in by copy id
        </li>
        <li>
          <Link href="/my-borrowed">My borrowed</Link> — active loans for a
          member id
        </li>
      </ul>
    </main>
  );
}
