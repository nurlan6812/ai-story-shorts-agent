import type { Metadata } from "next";
import { Manrope, Inter, JetBrains_Mono, Noto_Sans_KR } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";

const manrope = Manrope({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["600", "700", "800"],
});

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const notoSansKR = Noto_Sans_KR({
  variable: "--font-korean",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "썰알람 · 관제 대시보드",
  description: "유머/썰 YouTube Shorts 자동화 관제 시스템",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body
        className={`${manrope.variable} ${inter.variable} ${notoSansKR.variable} ${jetbrainsMono.variable} antialiased`}
      >
        <Sidebar />
        <div className="pl-56">
          <Header />
          <main className="min-h-[calc(100vh-3.5rem)] p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
