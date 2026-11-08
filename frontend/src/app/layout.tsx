import "./globals.css";

import type { Viewport } from "next";
import { Toaster } from "sonner";

import { QueryProvider } from "@/lib/query/query-provider";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  userScalable: true,
  interactiveWidget: "resizes-content",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased bg-slate-50 text-slate-900">
        <QueryProvider>{children}</QueryProvider>
        <Toaster position="top-right" closeButton richColors />
      </body>
    </html>
  );
}