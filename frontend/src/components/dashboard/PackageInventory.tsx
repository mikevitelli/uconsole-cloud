"use client";

import { useState } from "react";
import { Donut } from "@/components/viz/Donut";
import { HBar } from "@/components/viz/HBar";

const COLORS = ["#58a6ff", "#3fb950", "#d29922", "#f85149", "#bc8cff", "#79c0ff"];

interface PackageInventoryProps {
  packages: Record<string, string[]>;
}

export function PackageInventory({ packages }: PackageInventoryProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const managers = Object.keys(packages);
  const total = managers.reduce((sum, m) => sum + packages[m].length, 0);
  const barItems = managers
    .filter((m) => packages[m].length > 0)
    .map((m) => ({ name: m, value: packages[m].length, label: String(packages[m].length) }));

  return (
    <section className="bg-card border border-border rounded-xl p-4 mb-4">
      <h2 className="text-base font-bold text-bright mb-3 flex items-center gap-2">
        <span>&#x1F4E6;</span> Package Inventory
      </h2>

      <div className="flex gap-4 justify-center flex-wrap my-2">
        <Donut
          percent={100}
          size={120}
          label="Total Packages"
          centerText={String(total)}
          subText={`${managers.length} managers`}
        />
        {barItems.map((item, i) => (
          <Donut
            key={item.name}
            percent={(item.value * 100) / total}
            size={80}
            label={item.name}
            centerText={String(item.value)}
            color={COLORS[i % COLORS.length]}
          />
        ))}
      </div>

      {barItems.length > 0 && <HBar items={barItems} />}

      {managers.map((m) => {
        const pkgs = packages[m];
        if (!pkgs.length) return null;
        const isOpen = expanded === m;
        return (
          <div key={m}>
            <button
              onClick={() => setExpanded(isOpen ? null : m)}
              className="bg-transparent border border-border text-accent rounded-md px-3 py-1 text-xs cursor-pointer mt-1.5 hover:bg-border"
            >
              {m} ({pkgs.length}) &mdash; {isOpen ? "Collapse" : "Show all"}
            </button>
            {isOpen && (
              <div className="mt-2 max-h-[300px] overflow-y-auto bg-background border border-border rounded-md p-3 text-xs text-sub font-mono leading-7">
                {pkgs.join("\n")}
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}
