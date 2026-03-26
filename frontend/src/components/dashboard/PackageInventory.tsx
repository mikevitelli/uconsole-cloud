"use client";

import { useState } from "react";
import { Donut } from "@/components/viz/Donut";
import { Treemap } from "@/components/viz/Treemap";
import { CategoryPills } from "@/components/viz/CategoryPills";
import type { AptCategory } from "@/lib/types";

interface PackageInventoryContent {
  heading?: string;
  totalLabel?: string;
}

interface PackageInventoryProps {
  packages: Record<string, string[]>;
  aptCategories: AptCategory[];
  content?: PackageInventoryContent;
}

type Selection = { type: "apt-category" | "manager"; name: string } | null;

export function PackageInventory({
  packages,
  aptCategories,
  content,
}: PackageInventoryProps) {
  const [selected, setSelected] = useState<Selection>(null);

  const managers = Object.keys(packages);
  const total = managers.reduce((sum, m) => sum + packages[m].length, 0);
  const aptCount = (packages["APT"] || []).length;
  const otherCount = total - aptCount;

  // Treemap items from APT categories
  const treemapItems = aptCategories.map((c) => ({
    name: c.name,
    value: c.packages.length,
    color: c.color,
  }));

  // Pills: APT subcategories + non-APT managers
  const nonAptManagers = managers.filter(
    (m) => m !== "APT" && packages[m].length > 0
  );
  const pillItems = [
    ...aptCategories.map((c) => ({
      name: c.name,
      count: c.packages.length,
      color: c.color,
    })),
    ...nonAptManagers.map((m, i) => ({
      name: m,
      count: packages[m].length,
      color: ["#56d364", "#e3b341", "#ff7b72", "#d2a8ff", "#79c0ff"][i % 5],
    })),
  ];

  function handleSelect(name: string) {
    const isAptCat = aptCategories.some((c) => c.name === name);
    if (selected?.name === name) {
      setSelected(null);
    } else {
      setSelected({ type: isAptCat ? "apt-category" : "manager", name });
    }
  }

  function handlePillSelect(name: string | null) {
    if (!name) {
      setSelected(null);
      return;
    }
    handleSelect(name);
  }

  // Get detail packages for current selection
  let detailPackages: string[] = [];
  let detailLabel = "";
  if (selected) {
    if (selected.type === "apt-category") {
      const cat = aptCategories.find((c) => c.name === selected.name);
      detailPackages = cat?.packages || [];
      detailLabel = `${selected.name} (${detailPackages.length.toLocaleString()} packages)`;
    } else {
      detailPackages = packages[selected.name] || [];
      detailLabel = `${selected.name} (${detailPackages.length.toLocaleString()} packages)`;
    }
  }

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F4E6;</span>{" "}
        {content?.heading ?? "Package Inventory"}
      </h2>

      <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr] gap-4 items-center">
        {/* Left: Total donut */}
        <div className="flex flex-col items-center gap-1">
          <Donut
            percent={100}
            size={110}
            label={content?.totalLabel ?? "Total Packages"}
            centerText={total.toLocaleString()}
            subText={`${managers.length} managers`}
          />
          <div className="flex flex-wrap justify-center gap-1 mt-2">
            {managers.filter(m => packages[m].length > 0).map((m) => (
              <button
                key={m}
                onClick={() => handleSelect(m)}
                className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-full border transition-all cursor-pointer"
                style={{
                  background: selected?.name === m ? "var(--accent)" : "transparent",
                  borderColor: selected?.name === m ? "var(--accent)" : "var(--border)",
                  color: selected?.name === m ? "var(--bg)" : "var(--sub)",
                }}
              >
                {m} {packages[m].length.toLocaleString()}
              </button>
            ))}
          </div>
        </div>

        {/* Right: Treemap */}
        {treemapItems.length > 0 && (
          <Treemap
            items={treemapItems}
            height={180}
            onSelect={handleSelect}
            selected={
              selected?.type === "apt-category" ? selected.name : null
            }
          />
        )}
      </div>

      {/* Pills */}
      <CategoryPills
        items={pillItems}
        selected={selected?.name ?? null}
        onSelect={handlePillSelect}
      />

      {/* Detail panel */}
      {selected && detailPackages.length > 0 && (
        <div className="mt-2 bg-background border border-border rounded-md p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-foreground font-medium">
              {detailLabel}
            </span>
            <button
              onClick={() => setSelected(null)}
              className="text-dim hover:text-foreground text-xs cursor-pointer bg-transparent border-none"
            >
              &#x2715;
            </button>
          </div>
          <div className="max-h-[300px] overflow-y-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-0.5 text-xs text-sub font-mono">
            {detailPackages.map((p) => (
              <span key={p}>{p}</span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
