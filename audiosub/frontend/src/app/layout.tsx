import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "AudioSub AI",
  description: "Audio / video transcription, subtitles and AI translation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <header className="border-b border-gray-200 bg-white">
          <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <span className="rounded bg-indigo-600 px-1.5 py-0.5 text-xs font-bold text-white">CC</span>
              AudioSub AI
            </Link>
            <nav className="flex gap-4 text-sm text-gray-600">
              <Link href="/" className="hover:text-gray-900">New project</Link>
              <Link href="/glossary" className="hover:text-gray-900">Glossary</Link>
            </nav>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
