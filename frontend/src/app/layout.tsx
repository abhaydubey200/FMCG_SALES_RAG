import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QueryBridge — Sales & Marketing Intelligence",
  description:
    "Enterprise AI Decision Intelligence Workspace. Ask questions about your data, get evidence-backed answers.",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full bg-slate-50 text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}
