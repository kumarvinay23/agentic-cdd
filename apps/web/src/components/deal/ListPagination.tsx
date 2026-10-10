"use client";

import { useEffect, useMemo, useState } from "react";

export const DEFAULT_PAGE_SIZE = 25;
export const PAGE_SIZE_OPTIONS = [25, 50, 100] as const;

export function useClientPagination<T>(
  items: readonly T[],
  pageSize: number = DEFAULT_PAGE_SIZE,
) {
  const [page, setPage] = useState(0);
  const total = items.length;
  const pageCount = Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));

  useEffect(() => {
    setPage(0);
  }, [items, pageSize]);

  useEffect(() => {
    if (page > pageCount - 1) setPage(Math.max(0, pageCount - 1));
  }, [page, pageCount]);

  const pageItems = useMemo(() => {
    const start = page * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, page, pageSize]);

  const from = total === 0 ? 0 : page * pageSize + 1;
  const to = Math.min(total, (page + 1) * pageSize);

  return {
    page,
    setPage,
    pageCount,
    pageItems,
    total,
    from,
    to,
    hasPrev: page > 0,
    hasNext: page < pageCount - 1,
  };
}

export function ListPagination({
  page,
  pageCount,
  total,
  from,
  to,
  pageSize,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = PAGE_SIZE_OPTIONS,
}: {
  page: number;
  pageCount: number;
  total: number;
  from: number;
  to: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  pageSizeOptions?: readonly number[];
}) {
  if (total === 0) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#e5e7eb] bg-[#fafafa] px-4 py-2.5 text-[12px] text-[#64748b]">
      <div className="flex flex-wrap items-center gap-2">
        <span>
          Showing {from}–{to} of {total}
        </span>
        {onPageSizeChange ? (
          <label className="inline-flex items-center gap-1.5">
            <span className="text-[#94a3b8]">Per page</span>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="rounded border border-[#e5e7eb] bg-white px-1.5 py-1 text-[12px] text-[#0f172a] outline-none focus:border-[#1e3a5f]"
            >
              {pageSizeOptions.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          disabled={page <= 0}
          onClick={() => onPageChange(page - 1)}
          className="rounded border border-[#e5e7eb] bg-white px-2.5 py-1 font-medium text-[#0f172a] hover:bg-[#f8fafc] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Previous
        </button>
        <span className="min-w-[4.5rem] text-center text-[#0f172a]">
          {page + 1} / {pageCount}
        </span>
        <button
          type="button"
          disabled={page >= pageCount - 1}
          onClick={() => onPageChange(page + 1)}
          className="rounded border border-[#e5e7eb] bg-white px-2.5 py-1 font-medium text-[#0f172a] hover:bg-[#f8fafc] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}
