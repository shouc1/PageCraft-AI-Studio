"use client";

import { Library, Package, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  label: string;
  icon: typeof Package;
  href: string;
  isActive: (pathname: string) => boolean;
};

const navItems: NavItem[] = [
  {
    label: "会话",
    icon: Package,
    href: "/",
    isActive: (p) => p === "/" || p.startsWith("/sessions"),
  },
  {
    label: "风格库",
    icon: Library,
    href: "/styles",
    isActive: (p) => p === "/styles" || p.startsWith("/styles/"),
  },
  {
    label: "设置",
    icon: Settings,
    href: "/settings",
    isActive: (p) => p === "/settings" || p.startsWith("/settings/"),
  },
];

export function AppHeader() {
  const pathname = usePathname();

  return (
    <header className="flex h-16 items-center justify-between border-b border-line bg-white px-5">
      <Link href="/" className="block">
        <h1 className="text-base font-semibold text-ink">
          页匠 AI｜PageCraft AI Studio
        </h1>
        <p className="text-xs text-slate-500">商品图生成与文案创作平台</p>
      </Link>

      <nav className="flex items-center gap-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = item.isActive(pathname);
          return (
            <Link
              key={item.label}
              href={item.href}
              className={`flex h-9 items-center gap-2 rounded-md px-3 text-sm transition ${
                active
                  ? "bg-ink text-white"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}