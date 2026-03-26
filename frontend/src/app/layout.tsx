import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { fetchSiteContent } from "@/lib/sanity";
import { Analytics } from "@vercel/analytics/react";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export async function generateMetadata(): Promise<Metadata> {
  const content = await fetchSiteContent();
  return {
    title: content?.site?.title ?? "uConsole Dashboard",
    description:
      content?.site?.description ??
      "Monitor your system backup repository on GitHub",
    appleWebApp: {
      capable: true,
      statusBarStyle: "black-translucent",
      title: "uConsole",
    },
    other: {
      "mobile-web-app-capable": "yes",
    },
  };
}

export function generateViewport() {
  return {
    themeColor: "#0a0a0a",
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
        <Analytics />
      </body>
    </html>
  );
}
