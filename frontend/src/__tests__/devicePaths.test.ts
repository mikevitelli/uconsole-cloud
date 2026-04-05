/**
 * Tests that device-side script references match the actual script directory layout.
 * Validates that webdash ALLOWED_SCRIPTS, TUI menu entries, and CLI push paths
 * all point to scripts that exist in example-device/scripts/.
 */
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../");
const EXAMPLE_DEVICE = path.join(REPO_ROOT, "example-device");
const SCRIPTS_DIR = path.join(EXAMPLE_DEVICE, "scripts");
const WEBDASH_APP = path.join(EXAMPLE_DEVICE, "webdash", "app.py");
const TUI_FRAMEWORK = path.join(EXAMPLE_DEVICE, "lib", "tui", "framework.py");
const TUI_NETWORK = path.join(EXAMPLE_DEVICE, "lib", "tui", "network.py");
const CLI_SCRIPT = path.join(
  REPO_ROOT,
  "frontend",
  "public",
  "scripts",
  "uconsole"
);

// Collect all .sh files in example-device/scripts/ recursively
function getScriptFiles(dir: string): Set<string> {
  const files = new Set<string>();
  function walk(d: string) {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        walk(path.join(d, entry.name));
      } else if (entry.name.endsWith(".sh")) {
        // Relative path from scripts/ root, e.g. "power/battery.sh"
        files.add(path.relative(dir, path.join(d, entry.name)));
      }
    }
  }
  walk(dir);
  return files;
}

describe("device script directory layout", () => {
  it("has subdirectories for all categories", () => {
    const subdirs = fs
      .readdirSync(SCRIPTS_DIR, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => d.name)
      .sort();
    expect(subdirs).toEqual(
      expect.arrayContaining(["network", "power", "radio", "system", "util"])
    );
  });

  it("has no .sh files at the scripts root (all in subdirs)", () => {
    const rootScripts = fs
      .readdirSync(SCRIPTS_DIR)
      .filter((f) => f.endsWith(".sh"));
    expect(rootScripts).toEqual([]);
  });
});

describe("webdash ALLOWED_SCRIPTS paths", () => {
  const appPy = fs.readFileSync(WEBDASH_APP, "utf-8");
  const existingScripts = getScriptFiles(SCRIPTS_DIR);

  // Extract all _script('subdir', 'name.sh', ...) calls
  const scriptPattern = /_script\(\s*'([^']+)',\s*'([^']+)'/g;
  const referencedScripts: Array<{ subdir: string; name: string }> = [];
  let match;
  while ((match = scriptPattern.exec(appPy)) !== null) {
    referencedScripts.push({ subdir: match[1], name: match[2] });
  }

  it("references at least 50 script entries", () => {
    expect(referencedScripts.length).toBeGreaterThanOrEqual(50);
  });

  it("all referenced scripts exist in example-device/scripts/", () => {
    const missing: string[] = [];
    for (const { subdir, name } of referencedScripts) {
      const relPath = `${subdir}/${name}`;
      if (!existingScripts.has(relPath)) {
        missing.push(relPath);
      }
    }
    expect(missing).toEqual([]);
  });

  it("uses APP_DIR for static assets, not SCRIPTS_DIR", () => {
    expect(appPy).toContain("send_from_directory(APP_DIR, 'favicon.png'");
    expect(appPy).toContain("send_from_directory(APP_DIR, 'uConsole.gif'");
    expect(appPy).toContain("send_from_directory(APP_DIR, 'uconsole.crt'");
    expect(appPy).not.toMatch(
      /send_from_directory\(SCRIPTS_DIR,\s*'favicon/
    );
  });

  it("uses _systemctl helper for timer commands", () => {
    const timerEntries = appPy
      .split("\n")
      .filter((l) => l.includes("timer-enable") || l.includes("timer-disable"));
    for (const line of timerEntries) {
      if (line.includes("ALLOWED_SCRIPTS") || line.trim().startsWith("#"))
        continue;
      expect(line).toContain("_systemctl(");
    }
  });

  it("defines PACKAGE_MODE detection", () => {
    expect(appPy).toContain(
      "PACKAGE_MODE = os.path.isdir('/opt/uconsole/scripts')"
    );
  });

  it("supports UCONSOLE_SCRIPTS_DIR env override", () => {
    expect(appPy).toContain("os.environ.get('UCONSOLE_SCRIPTS_DIR'");
  });
});

describe("TUI framework script paths", () => {
  const frameworkPy = fs.readFileSync(TUI_FRAMEWORK, "utf-8");
  const existingScripts = getScriptFiles(SCRIPTS_DIR);

  // Extract script references from SUBMENUS and CATEGORIES:
  // ("Label", "subdir/script.sh args", ...)
  const menuPattern = /"\s*([\w/.-]+\.sh(?:\s+[\w-]+)*)"/g;
  const referencedPaths: string[] = [];
  let match;
  while ((match = menuPattern.exec(frameworkPy)) !== null) {
    const scriptPath = match[1].split(/\s+/)[0];
    referencedPaths.push(scriptPath);
  }

  it("references scripts with subdirectory prefixes", () => {
    const flat = referencedPaths.filter((p) => !p.includes("/"));
    expect(flat).toEqual([]);
  });

  it("all referenced scripts exist in example-device/scripts/", () => {
    const missing: string[] = [];
    for (const scriptPath of referencedPaths) {
      if (!existingScripts.has(scriptPath)) {
        missing.push(scriptPath);
      }
    }
    expect(missing).toEqual([]);
  });

  it("supports UCONSOLE_SCRIPTS env override", () => {
    expect(frameworkPy).toContain("os.environ.get('UCONSOLE_SCRIPTS'");
  });
});

describe("TUI network.py script paths", () => {
  const networkPy = fs.readFileSync(TUI_NETWORK, "utf-8");

  it("references hotspot.sh via SCRIPT_DIR", () => {
    expect(networkPy).toContain('SCRIPT_DIR, "hotspot.sh"');
  });

  it("references wifi-fallback.sh via SCRIPT_DIR", () => {
    expect(networkPy).toContain('SCRIPT_DIR, "wifi-fallback.sh"');
  });
});

describe("CLI push-status.sh path resolution", () => {
  const cli = fs.readFileSync(CLI_SCRIPT, "utf-8");

  it("uses system/ subdir for push-status.sh in package mode", () => {
    expect(cli).toContain("${SCRIPTS_DIR}/system/push-status.sh");
  });

  it("cmd_doctor already uses system/ subdir for package mode", () => {
    expect(cli).toContain(
      '[ "$INSTALL_MODE" = "package" ] && push_script="${SCRIPTS_DIR}/system/push-status.sh"'
    );
  });

  it("standalone mode checks both old flat and new subdir paths", () => {
    expect(cli).toContain("uconsole/scripts/system/push-status.sh");
    expect(cli).toContain("uconsole/scripts/push-status.sh");
  });
});
