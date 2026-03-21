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
          {process.env.NODE_ENV === "production"
            ? "An unexpected error occurred loading the dashboard."
            : error.message || "An unexpected error occurred loading the dashboard."}
        </p>
        {error.digest && (
          <p className="text-xs text-dim">Error ID: {error.digest}</p>
        )}
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
