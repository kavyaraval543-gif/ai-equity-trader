import type { Metadata } from "next";
import "./globals.css";
import NavBar from "@/components/NavBar";

export const metadata: Metadata = {
  title: "AI Equity Trader",
  description: "Paper-trading automated equity trading dashboard.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-gray-100 antialiased">
        <div className="mx-auto max-w-6xl px-4 py-6">
          <NavBar />
          {children}
        </div>
      </body>
    </html>
  );
}
