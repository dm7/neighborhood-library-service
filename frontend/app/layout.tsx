import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Neighborhood Library",
  description: "Library staff tools",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
