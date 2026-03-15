import { StatCards } from "@/components/viz/StatCards";
import { StatusGrid } from "@/components/viz/StatusGrid";

interface BrowserExtensionsContent {
  heading?: string;
  statLabel?: string;
  emptyState?: string;
}

interface BrowserExtensionsProps {
  extensions: string[];
  content?: BrowserExtensionsContent;
}

export function BrowserExtensions({ extensions, content }: BrowserExtensionsProps) {
  return (
    <section className="bg-card border border-border rounded-xl p-4 mb-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F310;</span>{" "}
        {content?.heading ?? "Browser"}
      </h2>
      {extensions.length > 0 ? (
        <>
          <StatCards
            items={[
              {
                value: String(extensions.length),
                label: content?.statLabel ?? "Chromium Extensions",
                color: "var(--accent)",
              },
            ]}
          />
          <div className="max-h-[300px] overflow-y-auto">
            <StatusGrid
              items={extensions.map((ext) => ({
                name: ext,
                color: "var(--accent)",
              }))}
            />
          </div>
        </>
      ) : (
        <p className="text-sub text-sm">
          {content?.emptyState ?? "No extension data found."}
        </p>
      )}
    </section>
  );
}
