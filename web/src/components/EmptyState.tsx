import type { ReactNode } from "react";

export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-surface-line bg-surface-card px-6 py-10 text-center">
      <svg aria-hidden="true" viewBox="0 0 48 48" className="h-12 w-12 text-sky-400" fill="none">
        <path d="M8 22 24 9l16 13v17a2 2 0 0 1-2 2H10a2 2 0 0 1-2-2V22Z" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" />
        <path d="M19 41V29h10v12" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" />
      </svg>
      <h2 className="font-display text-lg font-semibold text-ink-900">{title}</h2>
      {body && <p className="max-w-md text-base text-ink-600">{body}</p>}
      {action}
    </div>
  );
}
