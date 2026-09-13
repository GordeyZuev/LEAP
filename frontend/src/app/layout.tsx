import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Geist, Geist_Mono } from "next/font/google";
import { QueryProvider } from "@/lib/query-provider";
import { THEME_DARK_COOKIE } from "@/lib/theme";
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

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const dark = (await cookies()).get(THEME_DARK_COOKIE)?.value === "1";
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased${dark ? " dark" : ""}`}
    >
      <body className="h-full">
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
