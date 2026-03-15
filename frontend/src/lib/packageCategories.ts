import type { AptCategory } from "@/lib/types";

const RULES: { test: (name: string) => boolean; category: string; color: string }[] = [
  { test: (n) => n.startsWith("lib"), category: "Libraries", color: "#58a6ff" },
  { test: (n) => n.endsWith("-dev"), category: "Development", color: "#bc8cff" },
  { test: (n) => n.startsWith("python3-") || n.startsWith("python-"), category: "Python", color: "#3fb950" },
  { test: (n) => n.startsWith("fonts-"), category: "Fonts", color: "#d29922" },
  { test: (n) => n.startsWith("gir1.2-"), category: "Introspection", color: "#79c0ff" },
  { test: (n) => n.startsWith("gstreamer"), category: "Multimedia", color: "#f85149" },
];

export function categorizeAptPackages(packages: string[]): AptCategory[] {
  const buckets: Record<string, { color: string; packages: string[] }> = {};

  for (const pkg of packages) {
    const name = pkg.toLowerCase();
    let matched = false;
    for (const rule of RULES) {
      if (rule.test(name)) {
        if (!buckets[rule.category]) {
          buckets[rule.category] = { color: rule.color, packages: [] };
        }
        buckets[rule.category].packages.push(pkg);
        matched = true;
        break;
      }
    }
    if (!matched) {
      if (!buckets["System"]) {
        buckets["System"] = { color: "#8b949e", packages: [] };
      }
      buckets["System"].packages.push(pkg);
    }
  }

  return Object.entries(buckets)
    .map(([name, { color, packages }]) => ({ name, color, packages }))
    .sort((a, b) => b.packages.length - a.packages.length);
}
