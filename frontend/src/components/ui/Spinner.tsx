export function Spinner({ className = "w-7 h-7" }: { className?: string }) {
  return (
    <div
      className={`${className} border-3 border-border border-t-accent rounded-full animate-spin`}
    />
  );
}
