import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "选机有据 · 电脑推荐平台",
  description: "从真实需求出发，让每一项电脑推荐都有依据。",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
