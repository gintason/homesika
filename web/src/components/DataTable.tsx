import type { ReactNode } from "react";

import { errorText } from "../lib/api";
import { strings } from "../i18n";
import { Banner } from "./Banner";
import { Button } from "./Button";
import { cx } from "./cx";
import { EmptyState } from "./EmptyState";
import { LoadingBlock } from "./Skeleton";

export interface Column<T> {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  align?: "left" | "right";
  /** Visually hide the header (e.g. an actions column); it stays available to screen readers. */
  hideHeader?: boolean;
}

/**
 * A real table on wide screens; on phones each row becomes a stacked card with the column name next
 * to each value. Explicit ARIA roles keep table semantics even when CSS changes the display.
 * Handles loading (skeleton), error (with retry), empty and "load more".
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  loading,
  error,
  onRetry,
  empty,
  hasMore,
  loadingMore,
  onLoadMore,
}: {
  caption: string;
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T, index: number) => string;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  empty?: { title: string; body?: ReactNode; action?: ReactNode };
  hasMore?: boolean;
  loadingMore?: boolean;
  onLoadMore?: () => void;
}) {
  if (loading) return <LoadingBlock />;
  if (error && !rows?.length) {
    return (
      <Banner tone="error" title={strings.errors.loadFailed} onRetry={onRetry}>
        {errorText(error)}
      </Banner>
    );
  }
  if (!rows || rows.length === 0) {
    return empty ? <EmptyState {...empty} /> : null;
  }
  return (
    <div className="space-y-4">
      <table role="table" className="block w-full text-left md:table md:rounded-lg md:bg-surface-card md:shadow-sm md:ring-1 md:ring-surface-line">
        <caption className="sr-only">{caption}</caption>
        <thead role="rowgroup" className="sr-only md:not-sr-only md:table-header-group">
          <tr role="row" className="md:border-b md:border-surface-line">
            {columns.map((c) => (
              <th
                key={c.key}
                role="columnheader"
                scope="col"
                className={cx(
                  "px-4 py-3 text-sm font-semibold text-ink-600",
                  c.align === "right" && "md:text-right",
                  c.hideHeader && "md:sr-only",
                )}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role="rowgroup" className="block space-y-3 md:table-row-group md:space-y-0">
          {rows.map((row, index) => (
            <tr
              key={rowKey(row, index)}
              role="row"
              className="block rounded-lg bg-surface-card p-4 shadow-sm ring-1 ring-surface-line md:table-row md:rounded-none md:p-0 md:shadow-none md:ring-0 md:[&:not(:last-child)]:border-b md:[&:not(:last-child)]:border-surface-line"
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  role="cell"
                  className={cx(
                    "flex items-start justify-between gap-4 py-1 text-base text-ink-800 md:table-cell md:px-4 md:py-3",
                    c.align === "right" && "md:text-right",
                  )}
                >
                  {!c.hideHeader && (
                    <span aria-hidden="true" className="text-sm text-ink-600 md:hidden">
                      {c.header}
                    </span>
                  )}
                  <span className={cx("min-w-0 break-words", c.hideHeader ? "w-full" : "text-right md:text-inherit")}>
                    {c.cell(row)}
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {error ? <Banner tone="error" onRetry={onRetry}>{errorText(error)}</Banner> : null}
      {hasMore && onLoadMore && (
        <div className="flex justify-center">
          <Button variant="secondary" onClick={onLoadMore} loading={loadingMore}>
            {strings.common.loadMore}
          </Button>
        </div>
      )}
    </div>
  );
}
