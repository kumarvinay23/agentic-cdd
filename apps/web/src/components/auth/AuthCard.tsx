import type { ReactNode } from "react";

export function AuthCard({ children }: { children: ReactNode }) {
  return (
    <div className="w-full max-w-[400px] rounded-[var(--radius-lg)] border border-border-primary bg-background-secondary p-8 shadow-none">
      {children}
    </div>
  );
}
