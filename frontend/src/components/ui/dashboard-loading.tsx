import Image from "next/image";

export default function DashboardLoading() {
  return (
    <div
      className="flex min-h-[70vh] w-full flex-col items-center justify-center p-6"
      role="status"
      aria-label="Loading page"
    >
      <div className="relative flex items-center justify-center">
        {/* Outer Spinning Ring */}
        <div className="h-36 w-36 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600 border-r-blue-600" />

        {/* Ambient Pulsing Glow */}
        <div className="absolute h-28 w-28 animate-pulse rounded-full bg-blue-50/80 shadow-inner" />

        {/* Centered Logo Container */}
        <div className="absolute flex h-28 w-28 items-center justify-center rounded-full bg-white p-3 shadow-sm border border-slate-100">
          <Image
            src="/logo.png"
            alt="SprintSight Logo"
            width={90}
            height={90}
            priority
            className="object-contain"
          />
        </div>
      </div>

      {/* Animated Loading Text */}
      <div className="mt-6 flex flex-col items-center gap-1 text-center">
        <span className="text-base font-semibold tracking-tight text-slate-800">
          SprintSight
        </span>
        <span className="text-xs font-medium text-slate-500 animate-pulse">
          Loading sprint workspace...
        </span>
      </div>
    </div>
  );
}