import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { QueryProvider } from "@/lib/query-provider";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "LEAP",
  description: "AI-powered educational video processing platform",
  icons: {
    // Transparent symbol — blue mark reads on both light and dark browser tabs.
    icon: "/logo_symb.svg",
    shortcut: "/logo_symb.svg",
    // iOS prefers an opaque, app-icon-like asset for the home screen.
    apple: "/logo_inverse.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="h-full">
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
