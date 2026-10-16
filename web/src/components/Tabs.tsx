import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

import { cx } from "./cx";

export interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
}

/** WAI-ARIA tabs: arrow keys / Home / End move between tabs. Only the active panel is rendered. */
export function Tabs({
  items,
  value,
  onChange,
  label,
}: {
  items: TabItem[];
  value: string;
  onChange: (id: string) => void;
  label: string;
}) {
  const base = useId();
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const active = items.find((t) => t.id === value) ?? items[0];

  const onKeyDown = (e: KeyboardEvent, index: number) => {
    let next = -1;
    if (e.key === "ArrowRight") next = (index + 1) % items.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + items.length) % items.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    if (next < 0) return;
    e.preventDefault();
    const item = items[next];
    if (item) {
      onChange(item.id);
      refs.current[next]?.focus();
    }
  };

  return (
    <div>
      <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto border-b border-surface-line">
        {items.map((t, i) => {
          const selected = t.id === active?.id;
          return (
            <button
              key={t.id}
              ref={(el) => {
                refs.current[i] = el;
              }}
              id={`${base}-tab-${t.id}`}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={`${base}-panel-${t.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(t.id)}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={cx(
                "min-h-touch whitespace-nowrap border-b-4 px-4 text-base font-semibold",
                selected ? "border-primary-600 text-primary-700" : "border-transparent text-ink-600 hover:text-ink-800",
              )}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      {active && (
        <div
          role="tabpanel"
          id={`${base}-panel-${active.id}`}
          aria-labelledby={`${base}-tab-${active.id}`}
          tabIndex={0}
          className="pt-4"
        >
          {active.content}
        </div>
      )}
    </div>
  );
}
