"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/backtesting", label: "📊 Backtesting" },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <nav className="mb-6 flex gap-2 border-b border-border pb-3">
      {LINKS.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
              active ? "bg-accent text-white" : "text-gray-400 hover:bg-surface hover:text-gray-100"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
