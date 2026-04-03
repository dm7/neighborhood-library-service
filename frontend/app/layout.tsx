import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Neighborhood Library",
  description: "Library staff tools",
};

const nav = [
  { href: "/", label: "Home" },
  { href: "/books", label: "Books" },
  { href: "/members", label: "Members" },
  { href: "/borrow", label: "Borrow" },
  { href: "/return", label: "Return" },
  { href: "/my-borrowed", label: "My borrowed" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <header
          style={{
            borderBottom: "1px solid var(--border)",
            background: "var(--surface)",
            padding: "0.75rem 1.25rem",
          }}
        >
          <nav className="stack" aria-label="Main">
            {nav.map((item) => (
              <Link key={item.href} href={item.href}>
                {item.label}
              </Link>
            ))}
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
