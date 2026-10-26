import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "页匠 AI｜PageCraft AI Studio",
  description: "AI 商品图生成与文案创作平台"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
