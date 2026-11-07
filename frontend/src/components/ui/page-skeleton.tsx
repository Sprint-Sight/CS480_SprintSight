import { Skeleton } from "@/components/ui/skeleton";

type PageSkeletonVariant = "cards" | "table" | "form";

type PageSkeletonProps = { variant?: PageSkeletonVariant };

const ITEM_KEYS = [0, 1, 2, 3, 4, 5];

export function PageSkeleton({ variant = "cards" }: PageSkeletonProps) {
  return (
    <div role="status" className="space-y-6 p-4 sm:p-6">
      <span className="sr-only">Loading…</span>
      <div className="space-y-2">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>

      {variant === "cards" && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {ITEM_KEYS.map((key) => (
            <Skeleton key={key} className="h-32 rounded-xl" />
          ))}
        </div>
      )}

      {variant === "table" && (
        <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
          {ITEM_KEYS.map((key) => (
            <Skeleton key={key} className="h-10 w-full" />
          ))}
        </div>
      )}

      {variant === "form" && (
        <div className="max-w-2xl space-y-5 rounded-xl border border-slate-200 bg-white p-6">
          {ITEM_KEYS.slice(0, 4).map((key) => (
            <div key={key} className="space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-11 w-full" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
