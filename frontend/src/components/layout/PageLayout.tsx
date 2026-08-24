"use client";

import { AppShell } from "./AppShell";

export function PageLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
