export default function Home() {
  return (
    <main style={{ padding: "2rem", fontFamily: "system-ui" }}>
      <h1>Neighborhood Library</h1>
      <p>Frontend scaffold — API base: {process.env.NEXT_PUBLIC_API_BASE ?? "(unset)"}</p>
    </main>
  );
}
