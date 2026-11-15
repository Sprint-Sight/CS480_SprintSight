type RunsPaginationProps = {
  page: number;
  pages: number;
  onPageChange: (page: number) => void;
};

/** Previous / next controls for the runs table. Renders nothing when there is one page. */
export function RunsPagination({ page, pages, onPageChange }: RunsPaginationProps) {
  if (pages <= 1) return null;

  return (
    <nav className="flex items-center justify-end gap-2 text-sm" aria-label="Pagination">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        className="rounded border px-2 py-1 disabled:opacity-50"
      >
        Previous
      </button>
      <span>
        Page {page} of {pages}
      </span>
      <button
        type="button"
        disabled={page >= pages}
        onClick={() => onPageChange(page + 1)}
        className="rounded border px-2 py-1 disabled:opacity-50"
      >
        Next
      </button>
    </nav>
  );
}
