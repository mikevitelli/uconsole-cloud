/**
 * Tests for APT repository structure, installer script, and next.config headers.
 * Validates that the repo is well-formed and the installer points to the right URLs.
 */
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../");
const PUBLIC_DIR = path.join(REPO_ROOT, "frontend", "public");
const APT_DIR = path.join(PUBLIC_DIR, "apt");
const INSTALLER = path.join(PUBLIC_DIR, "install.sh");
const NEXT_CONFIG = path.join(REPO_ROOT, "frontend", "next.config.ts");

// ── APT repo structure ─────────────────────────────────────────────────

describe("APT repository structure", () => {
  it("has a GPG public key", () => {
    expect(fs.existsSync(path.join(APT_DIR, "uconsole.gpg"))).toBe(true);
  });

  it("has Release file", () => {
    expect(
      fs.existsSync(path.join(APT_DIR, "dists", "stable", "Release"))
    ).toBe(true);
  });

  it("has InRelease file (signed)", () => {
    expect(
      fs.existsSync(path.join(APT_DIR, "dists", "stable", "InRelease"))
    ).toBe(true);
  });

  it("has Release.gpg (detached signature)", () => {
    expect(
      fs.existsSync(path.join(APT_DIR, "dists", "stable", "Release.gpg"))
    ).toBe(true);
  });

  it("has Packages file for arm64", () => {
    const packagesPath = path.join(
      APT_DIR,
      "dists",
      "stable",
      "main",
      "binary-arm64",
      "Packages"
    );
    expect(fs.existsSync(packagesPath)).toBe(true);
  });

  it("has compressed Packages.gz", () => {
    const gzPath = path.join(
      APT_DIR,
      "dists",
      "stable",
      "main",
      "binary-arm64",
      "Packages.gz"
    );
    expect(fs.existsSync(gzPath)).toBe(true);
  });

  it("Packages file references uconsole-cloud package", () => {
    const packages = fs.readFileSync(
      path.join(
        APT_DIR,
        "dists",
        "stable",
        "main",
        "binary-arm64",
        "Packages"
      ),
      "utf-8"
    );
    expect(packages).toContain("Package: uconsole-cloud");
    expect(packages).toContain("Architecture: arm64");
  });

  it("has at least one .deb in pool/", () => {
    const poolDir = path.join(APT_DIR, "pool");
    const debs: string[] = [];
    function walk(dir: string) {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (entry.isDirectory()) walk(path.join(dir, entry.name));
        else if (entry.name.endsWith(".deb")) debs.push(entry.name);
      }
    }
    walk(poolDir);
    expect(debs.length).toBeGreaterThanOrEqual(1);
    expect(debs[0]).toMatch(/uconsole-cloud.*\.deb$/);
  });

  it("Packages file Filename field matches pool path", () => {
    const packages = fs.readFileSync(
      path.join(
        APT_DIR,
        "dists",
        "stable",
        "main",
        "binary-arm64",
        "Packages"
      ),
      "utf-8"
    );
    const filenameMatch = packages.match(/^Filename:\s*(.+)$/m);
    expect(filenameMatch).not.toBeNull();
    const filename = filenameMatch![1].trim();
    // Filename should be a relative path under apt/
    expect(filename).toMatch(/^pool\/main\//);
    // The actual file should exist
    expect(fs.existsSync(path.join(APT_DIR, filename))).toBe(true);
  });
});

// ── Installer script ────────────────────────────────────────────────────

describe("install.sh", () => {
  const installer = fs.readFileSync(INSTALLER, "utf-8");

  it("exists and is non-empty", () => {
    expect(installer.length).toBeGreaterThan(100);
  });

  it("starts with a shebang", () => {
    expect(installer).toMatch(/^#!/);
  });

  it("uses set -euo pipefail", () => {
    expect(installer).toContain("set -euo pipefail");
  });

  it("supports UCONSOLE_URL override for testing", () => {
    expect(installer).toContain("UCONSOLE_URL");
  });

  it("defaults to https://uconsole.cloud", () => {
    expect(installer).toContain("https://uconsole.cloud");
  });

  it("checks for root", () => {
    expect(installer).toContain('$(id -u)');
    expect(installer).toContain("-ne 0");
  });

  it("creates keyrings directory", () => {
    expect(installer).toContain("mkdir -p /etc/apt/keyrings");
  });

  it("downloads GPG key from /apt/uconsole.gpg", () => {
    expect(installer).toContain("/apt/uconsole.gpg");
  });

  it("writes sources list with signed-by", () => {
    expect(installer).toContain("signed-by=");
    expect(installer).toContain("/etc/apt/sources.list.d/uconsole.list");
  });

  it("configures arch=arm64", () => {
    expect(installer).toContain("arch=arm64");
  });

  it("uses stable distribution", () => {
    expect(installer).toContain("stable main");
  });

  it("runs apt-get install uconsole-cloud", () => {
    expect(installer).toContain("apt-get install -y uconsole-cloud");
  });

  it("tells user to run uconsole setup after install", () => {
    expect(installer).toContain("uconsole setup");
  });
});

// ── next.config.ts APT headers ──────────────────────────────────────────

describe("next.config.ts APT headers", () => {
  const config = fs.readFileSync(NEXT_CONFIG, "utf-8");

  it("has headers for /apt/dists/ paths", () => {
    expect(config).toContain("/apt/dists/:path*");
  });

  it("sets text/plain content type for APT metadata", () => {
    expect(config).toContain("text/plain");
  });

  it("has headers for /apt/pool/ paths", () => {
    expect(config).toContain("/apt/pool/:path*");
  });

  it("sets binary content type for .deb packages", () => {
    expect(config).toContain("application/vnd.debian.binary-package");
  });

  it("has headers for GPG key", () => {
    expect(config).toContain("/apt/uconsole.gpg");
    expect(config).toContain("application/pgp-keys");
  });

  it("sets cache headers for repo metadata (short TTL)", () => {
    // Metadata should have short cache (5 min) for freshness
    expect(config).toContain("max-age=300");
  });

  it("sets long cache for .deb packages (immutable)", () => {
    expect(config).toContain("immutable");
  });
});
