"use client";

import { useState } from "react";
import { StatCards } from "@/components/viz/StatCards";

interface BrowserExtensionsProps {
  extensions: string[];
}

export function BrowserExtensions({ extensions }: BrowserExtensionsProps) {
  const [open, setOpen] = useState(false);

  return (
    <section className="bg-card border border-border rounded-xl p-4 mb-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F310;</span> Browser
      </h2>
      {extensions.length > 0 ? (
        <>
          <StatCards
            items={[
              {
                value: String(extensions.length),
                label: "Chromium Extensions",
                color: "var(--accent)",
              },
            ]}
          />
          <button
            onClick={() => setOpen(!open)}
            className="bg-transparent border border-border text-accent rounded-md px-3 py-1 text-xs cursor-pointer mt-1.5 hover:bg-border"
          >
            {open ? "Collapse" : "Show all"}
          </button>
          {open && (
            <div className="mt-2 max-h-[300px] overflow-y-auto bg-background border border-border rounded-md p-3 text-xs text-sub font-mono leading-7">
              {extensions.join("\n")}
            </div>
          )}
        </>
      ) : (
        <p className="text-sub text-sm">No extension data found.</p>
      )}
    </section>
  );
}
