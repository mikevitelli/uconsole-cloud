"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center space-y-4">
        <h2 className="text-xl font-semibold text-red-400">
          Something went wrong
        </h2>
        <p className="text-sub text-sm max-w-md">
          {error.message || "An unexpected error occurred loading the dashboard."}
        </p>
        <button
          onClick={reset}
          className="text-sm underline text-sub hover:text-fg cursor-pointer"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
