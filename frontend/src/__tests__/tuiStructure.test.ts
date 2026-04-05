/**
 * Tests for the TUI console structure and integrity.
 * Validates menu structure, script references, themes, categories,
 * and configuration without requiring curses or a real terminal.
 */
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../");
const EXAMPLE_DEVICE = path.join(REPO_ROOT, "example-device");
const SCRIPTS_DIR = path.join(EXAMPLE_DEVICE, "scripts");
const TUI_DIR = path.join(EXAMPLE_DEVICE, "lib", "tui");
const FRAMEWORK = fs.readFileSync(path.join(TUI_DIR, "framework.py"), "utf-8");
const NETWORK = fs.readFileSync(path.join(TUI_DIR, "network.py"), "utf-8");
const SERVICES = fs.readFileSync(path.join(TUI_DIR, "services.py"), "utf-8");

// All .sh files in example-device/scripts/ (relative paths)
function getScriptFiles(): Set<string> {
  const files = new Set<string>();
  function walk(dir: string) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) walk(path.join(dir, entry.name));
      else if (entry.name.endsWith(".sh"))
        files.add(path.relative(SCRIPTS_DIR, path.join(dir, entry.name)));
    }
  }
  walk(SCRIPTS_DIR);
  return files;
}

// Parse SUBMENUS from the Python source
// Format: ("Label", "subdir/script.sh args", "description", "mode")
function parseSubmenuEntries(): Array<{
  submenu: string;
  label: string;
  script: string;
  desc: string;
  mode: string;
}> {
  const entries: Array<{
    submenu: string;
    label: string;
    script: string;
    desc: string;
    mode: string;
  }> = [];
  // Find each submenu block
  const submenuPattern =
    /"(sub:\w+)":\s*\[([\s\S]*?)(?=\],\n\s+"sub:|\],\n\})/g;
  let match;
  while ((match = submenuPattern.exec(FRAMEWORK)) !== null) {
    const submenuName = match[1];
    const block = match[2];
    // Parse entries within the block
    const entryPattern =
      /\("([^"]+)",\s+"([^"]+)",\s+"([^"]+)",\s+"([^"]+)"\)/g;
    let entry;
    while ((entry = entryPattern.exec(block)) !== null) {
      entries.push({
        submenu: submenuName,
        label: entry[1],
        script: entry[2],
        desc: entry[3],
        mode: entry[4],
      });
    }
  }
  return entries;
}

// Parse CATEGORIES from the Python source
function parseCategoryEntries(): Array<{
  category: string;
  label: string;
  script: string;
  mode: string;
}> {
  const entries: Array<{
    category: string;
    label: string;
    script: string;
    mode: string;
  }> = [];
  const catPattern =
    /"name":\s*"(\w+)",\s*"items":\s*\[([\s\S]*?)(?=\],\n\s+\},|\],\n\s+\])/g;
  let match;
  while ((match = catPattern.exec(FRAMEWORK)) !== null) {
    const catName = match[1];
    const block = match[2];
    const entryPattern =
      /\("([^"]+)",\s+"([^"]+)",\s+"([^"]+)",\s+"([^"]+)"\)/g;
    let entry;
    while ((entry = entryPattern.exec(block)) !== null) {
      entries.push({
        category: catName,
        label: entry[1],
        script: entry[2],
        mode: entry[4],
      });
    }
  }
  return entries;
}

const VALID_MODES = ["panel", "stream", "action", "fullscreen", "submenu"];
const submenuEntries = parseSubmenuEntries();
const categoryEntries = parseCategoryEntries();
const existingScripts = getScriptFiles();

// ── Menu structure ──────────────────────────────────────────────────────

describe("TUI menu structure", () => {
  it("has at least 15 submenus", () => {
    const uniqueSubmenus = new Set(submenuEntries.map((e) => e.submenu));
    expect(uniqueSubmenus.size).toBeGreaterThanOrEqual(15);
  });

  it("has at least 7 categories", () => {
    const uniqueCats = new Set(categoryEntries.map((e) => e.category));
    expect(uniqueCats.size).toBeGreaterThanOrEqual(7);
  });

  it("all submenu entries have valid modes", () => {
    const invalidModes = submenuEntries.filter(
      (e) => !VALID_MODES.includes(e.mode)
    );
    expect(invalidModes).toEqual([]);
  });

  it("all category entries have valid modes", () => {
    const invalidModes = categoryEntries.filter(
      (e) => !VALID_MODES.includes(e.mode)
    );
    expect(invalidModes).toEqual([]);
  });

  it("all category submenu references exist in SUBMENUS", () => {
    const definedSubmenus = new Set(submenuEntries.map((e) => e.submenu));
    const submenuRefs = categoryEntries
      .filter((e) => e.mode === "submenu")
      .map((e) => e.script);
    const missing = submenuRefs.filter((ref) => !definedSubmenus.has(ref));
    expect(missing).toEqual([]);
  });

  it("no empty submenus", () => {
    const counts = new Map<string, number>();
    for (const e of submenuEntries) {
      counts.set(e.submenu, (counts.get(e.submenu) || 0) + 1);
    }
    const empty = [...counts.entries()].filter(([, c]) => c === 0);
    expect(empty).toEqual([]);
  });

  it("no duplicate entry labels within the same submenu", () => {
    const bySubmenu = new Map<string, string[]>();
    for (const e of submenuEntries) {
      if (!bySubmenu.has(e.submenu)) bySubmenu.set(e.submenu, []);
      bySubmenu.get(e.submenu)!.push(e.label);
    }
    for (const [sub, labels] of bySubmenu) {
      const dupes = labels.filter((l, i) => labels.indexOf(l) !== i);
      expect(dupes, `Duplicate labels in ${sub}`).toEqual([]);
    }
  });
});

// ── Script references ───────────────────────────────────────────────────

describe("TUI script references resolve to real files", () => {
  // Filter to only entries that are actual script commands (not _native_tools or submenus)
  const scriptEntries = [
    ...submenuEntries.filter(
      (e) => !e.script.startsWith("_") && !e.script.startsWith("sub:")
    ),
    ...categoryEntries.filter(
      (e) => !e.script.startsWith("_") && !e.script.startsWith("sub:")
    ),
  ];

  it("has at least 80 script references", () => {
    expect(scriptEntries.length).toBeGreaterThanOrEqual(80);
  });

  it("all script paths include a subdirectory", () => {
    const flat = scriptEntries.filter((e) => !e.script.includes("/"));
    expect(flat.map((e) => `${e.label}: ${e.script}`)).toEqual([]);
  });

  it("all referenced .sh files exist in example-device/scripts/", () => {
    const missing: string[] = [];
    for (const entry of scriptEntries) {
      const scriptFile = entry.script.split(/\s+/)[0]; // strip args
      if (!existingScripts.has(scriptFile)) {
        missing.push(`${entry.label}: ${scriptFile}`);
      }
    }
    expect(missing).toEqual([]);
  });
});

// ── _resolve_cmd compatibility ──────────────────────────────────────────

describe("_resolve_cmd path resolution", () => {
  it("_resolve_cmd resolves script names to file paths", () => {
    expect(FRAMEWORK).toContain("def _resolve_cmd(script_name):");
    // Should split the script_name and resolve the first token as a file path
    expect(FRAMEWORK).toContain("parts = script_name.split()");
  });

  it("script refs with args will resolve correctly via split()[0]", () => {
    const withArgs = submenuEntries.filter(
      (e) =>
        !e.script.startsWith("_") &&
        !e.script.startsWith("sub:") &&
        e.script.includes(" ")
    );
    for (const entry of withArgs) {
      const parts = entry.script.split(/\s+/);
      expect(
        parts[0].endsWith(".sh"),
        `${entry.label}: first token "${parts[0]}" should end with .sh`
      ).toBe(true);
    }
  });
});

// ── CONFIRM_SCRIPTS ─────────────────────────────────────────────────────

describe("CONFIRM_SCRIPTS (dangerous command gate)", () => {
  it("references power/power.sh reboot and shutdown", () => {
    expect(FRAMEWORK).toContain('"power/power.sh reboot"');
    expect(FRAMEWORK).toContain('"power/power.sh shutdown"');
  });

  it("confirmation targets appear in the submenu entries", () => {
    const confirmTargets = [
      "power/power.sh reboot",
      "power/power.sh shutdown",
    ];
    const allScriptRefs = submenuEntries.map((e) => e.script);
    for (const target of confirmTargets) {
      expect(
        allScriptRefs,
        `${target} should appear in submenu entries`
      ).toContain(target);
    }
  });
});

// ── Theme structure ─────────────────────────────────────────────────────

describe("TUI themes", () => {
  // Parse theme names from THEMES dict
  const themeNamePattern = /"(\w+)":\s*\{"header"/g;
  const themeNames: string[] = [];
  let m;
  while ((m = themeNamePattern.exec(FRAMEWORK)) !== null) {
    themeNames.push(m[1]);
  }

  it("has at least 20 themes", () => {
    expect(themeNames.length).toBeGreaterThanOrEqual(20);
  });

  it("all THEME_FOLDERS entries exist in THEMES", () => {
    const folderPattern = /\("(\w+)",\s*\[((?:"[^"]+",?\s*)+)\]\)/g;
    let match;
    while ((match = folderPattern.exec(FRAMEWORK)) !== null) {
      const folder = match[1];
      const names =
        match[2].match(/"(\w+)"/g)?.map((s) => s.replace(/"/g, "")) || [];
      for (const name of names) {
        if (name === "custom") continue;
        expect(
          themeNames,
          `Theme "${name}" from folder "${folder}" not in THEMES`
        ).toContain(name);
      }
    }
  });

  it("each theme has all required keys", () => {
    const requiredKeys = [
      "header",
      "cat",
      "item",
      "sel_fg",
      "sel_bg",
      "border",
      "footer_fg",
      "footer_bg",
      "status",
    ];
    for (const name of themeNames) {
      for (const key of requiredKeys) {
        const pattern = new RegExp(`"${name}":\\s*\\{[^}]*"${key}":`);
        expect(FRAMEWORK, `Theme "${name}" missing key "${key}"`).toMatch(
          pattern
        );
      }
    }
  });
});

// ── Categories contain expected sections ────────────────────────────────

describe("TUI category coverage", () => {
  const catNames = [...new Set(categoryEntries.map((e) => e.category))];

  it("includes SYSTEM, MONITOR, FILES, POWER, NETWORK, HARDWARE, TOOLS, CONFIG", () => {
    const expected = [
      "SYSTEM",
      "MONITOR",
      "FILES",
      "POWER",
      "NETWORK",
      "HARDWARE",
      "TOOLS",
      "CONFIG",
    ];
    for (const cat of expected) {
      expect(catNames, `Missing category: ${cat}`).toContain(cat);
    }
  });

  it("each category has at least 3 items", () => {
    const counts = new Map<string, number>();
    for (const e of categoryEntries) {
      counts.set(e.category, (counts.get(e.category) || 0) + 1);
    }
    for (const [cat, count] of counts) {
      expect(
        count,
        `Category ${cat} has only ${count} items`
      ).toBeGreaterThanOrEqual(3);
    }
  });

  it("HARDWARE category includes radio submenus", () => {
    const hwEntries = categoryEntries.filter(
      (e) => e.category === "HARDWARE"
    );
    const scripts = hwEntries.map((e) => e.script);
    expect(scripts).toContain("sub:gps");
    expect(scripts).toContain("sub:sdr");
    expect(scripts).toContain("sub:lora");
    expect(scripts).toContain("sub:esp32");
  });
});

// ── Native tool references ──────────────────────────────────────────────

describe("TUI native tool references", () => {
  const nativeRefs = [
    ...submenuEntries.filter((e) => e.script.startsWith("_")),
    ...categoryEntries.filter((e) => e.script.startsWith("_")),
  ];

  it("native tools start with underscore", () => {
    for (const entry of nativeRefs) {
      expect(entry.script).toMatch(/^_\w+/);
    }
  });

  it("includes key native tools", () => {
    const names = nativeRefs.map((e) => e.script);
    expect(names).toContain("_monitor");
    expect(names).toContain("_wifi");
    expect(names).toContain("_git");
    expect(names).toContain("_notes");
  });
});

// ── Module imports ──────────────────────────────────────────────────────

describe("TUI module imports", () => {
  it("network.py imports SCRIPT_DIR from framework", () => {
    expect(NETWORK).toContain("SCRIPT_DIR");
    expect(NETWORK).toMatch(/from tui\.framework import/);
  });

  it("services.py imports SCRIPT_DIR from framework", () => {
    expect(SERVICES).toContain("SCRIPT_DIR");
    expect(SERVICES).toMatch(/from tui\.framework import/);
  });

  it("services.py uses package-mode-aware systemctl", () => {
    expect(SERVICES).toContain("SCRIPT_DIR");
    expect(SERVICES).toContain('"systemctl", "--user"');
  });
});

// ── Gamepad constants ───────────────────────────────────────────────────

describe("TUI gamepad mapping", () => {
  it("defines GP_A, GP_B, GP_X, GP_Y buttons", () => {
    expect(FRAMEWORK).toMatch(/GP_A\s*=\s*1/);
    expect(FRAMEWORK).toMatch(/GP_B\s*=\s*2/);
    expect(FRAMEWORK).toMatch(/GP_X\s*=\s*0/);
    expect(FRAMEWORK).toMatch(/GP_Y\s*=\s*3/);
  });
});

// ── Display mode coverage ───────────────────────────────────────────────

describe("TUI display modes", () => {
  it("every mode used in entries is one of the valid set", () => {
    const allModes = [
      ...submenuEntries.map((e) => e.mode),
      ...categoryEntries.map((e) => e.mode),
    ];
    for (const mode of allModes) {
      expect(VALID_MODES, `Invalid mode: ${mode}`).toContain(mode);
    }
  });

  it("uses all display modes across the menu tree", () => {
    const usedModes = new Set([
      ...submenuEntries.map((e) => e.mode),
      ...categoryEntries.map((e) => e.mode),
    ]);
    for (const mode of VALID_MODES) {
      expect(
        usedModes.has(mode),
        `Mode "${mode}" never used in any menu entry`
      ).toBe(true);
    }
  });
});
