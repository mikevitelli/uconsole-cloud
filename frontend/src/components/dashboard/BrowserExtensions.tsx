import { StatCards } from "@/components/viz/StatCards";

interface BrowserExtensionsContent {
  heading?: string;
  statLabel?: string;
  emptyState?: string;
}

interface BrowserExtensionsProps {
  extensions: string[];
  content?: BrowserExtensionsContent;
}

function parseExtension(ext: string): { id: string; name: string } {
  // Format: "extensionId ExtensionName" or just "extensionId"
  const spaceIdx = ext.indexOf(" ");
  if (spaceIdx > 0) {
    return { id: ext.slice(0, spaceIdx), name: ext.slice(spaceIdx + 1) };
  }
  return { id: ext, name: ext };
}

export function BrowserExtensions({ extensions, content }: BrowserExtensionsProps) {
  const parsed = extensions.map(parseExtension);

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F310;</span>{" "}
        {content?.heading ?? "Browser"}
      </h2>
      {parsed.length > 0 ? (
        <>
          <StatCards
            items={[
              {
                value: String(parsed.length),
                label: content?.statLabel ?? "Chromium Extensions",
                color: "var(--accent)",
              },
            ]}
          />
          <div className="max-h-72 overflow-y-auto mt-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {parsed.map((ext) => (
                <div
                  key={ext.id}
                  className="flex items-center gap-2.5 bg-background border border-border rounded-lg px-3 py-2 text-sm"
                >
                  <span className="w-2 h-2 rounded-full bg-accent shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-foreground font-medium truncate text-xs">
                      {ext.name}
                    </div>
                    <div className="text-dim text-[10px] font-mono truncate">
                      {ext.id}
                    </div>
                  </div>
                </div>
              ))}
            </div>
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
