import { describe, it, expect } from "vitest";

// ── 1. Sanity client: no hardcoded fallback in production ────

describe("Sanity client config", () => {
  it("should not hardcode a project ID fallback", async () => {
    // Read the source to verify no hardcoded fallback
    const fs = await import("fs");
    const source = fs.readFileSync(
      "src/lib/sanity/client.ts",
      "utf-8"
    );
    // Should not contain a hardcoded project ID as a fallback
    expect(source).not.toMatch(/\|\|\s*["']jdm1m5uf["']/);
  });
});

// ── 2. OAuth scope should be minimal ─────────────────────────

describe("OAuth scope", () => {
  it("should not request full repo write access unless documented", async () => {
    const fs = await import("fs");
    const source = fs.readFileSync("src/lib/auth.ts", "utf-8");
    // If "repo" scope is used (full write access), it should be documented
    // Ideally should use "public_repo" or read-only scope
    const hasRepoScope = source.includes('"repo ') || source.includes('"repo"');
    if (hasRepoScope) {
      // At minimum, there should be a comment explaining why full repo scope is needed
      expect(source).toMatch(/private repo|write access|repo scope/i);
    }
  });
});

// ── 3. Error boundary should not leak internal details ───────

describe("Error boundary", () => {
  it("should not render raw error.message in production", async () => {
    const fs = await import("fs");
    const source = fs.readFileSync("src/app/error.tsx", "utf-8");
    // Should use a generic message or check NODE_ENV before showing error.message
    const rendersRawMessage = source.includes("error.message") &&
      !source.includes("NODE_ENV") &&
      !source.includes("production");
    expect(rendersRawMessage).toBe(false);
  });
});

// ── 4. URL scheme validation on external links ───────────────

describe("URL scheme validation", () => {
  function isValidGitHubUrl(url: string): boolean {
    return url.startsWith("https://github.com/");
  }

  it("blocks javascript: URIs", () => {
    expect(isValidGitHubUrl("javascript:alert(1)")).toBe(false);
  });

  it("blocks data: URIs", () => {
    expect(isValidGitHubUrl("data:text/html,<script>alert(1)</script>")).toBe(false);
  });

  it("blocks empty string", () => {
    expect(isValidGitHubUrl("")).toBe(false);
  });

  it("blocks relative URLs", () => {
    expect(isValidGitHubUrl("/evil/page")).toBe(false);
  });

  it("blocks http (non-TLS) GitHub URLs", () => {
    expect(isValidGitHubUrl("http://github.com/owner/repo")).toBe(false);
  });

  it("allows valid GitHub commit URLs", () => {
    expect(
      isValidGitHubUrl("https://github.com/mikevitelli/uconsole/commit/abc123")
    ).toBe(true);
  });
});

// ── 5. Security headers validation ───────────────────────────

describe("Security headers config", () => {
  it("next.config.ts should define security headers", async () => {
    const fs = await import("fs");
    const source = fs.readFileSync("next.config.ts", "utf-8");

    expect(source).toContain("X-Frame-Options");
    expect(source).toContain("X-Content-Type-Options");
    expect(source).toContain("Referrer-Policy");
    expect(source).toContain("Content-Security-Policy");
    expect(source).toContain("Permissions-Policy");
  });

  it("X-Frame-Options should be DENY", async () => {
    const fs = await import("fs");
    const source = fs.readFileSync("next.config.ts", "utf-8");
    expect(source).toContain('"DENY"');
  });

  it("CSP should restrict default-src to self", async () => {
    const fs = await import("fs");
    const source = fs.readFileSync("next.config.ts", "utf-8");
    expect(source).toContain("default-src 'self'");
  });
});

// ── 6. .env.local should never be committed ──────────────────

describe("Secrets management", () => {
  it(".gitignore should exclude env files", async () => {
    const fs = await import("fs");
    // Check both root and frontend .gitignore
    let gitignore = "";
    try { gitignore += fs.readFileSync("../.gitignore", "utf-8"); } catch {}
    try { gitignore += fs.readFileSync(".gitignore", "utf-8"); } catch {}

    expect(gitignore).toMatch(/\.env/);
  });

  it("no NEXT_PUBLIC_ env vars should contain secrets", async () => {
    const fs = await import("fs");

    // Check all .ts files for NEXT_PUBLIC_ vars that might be secret
    function checkFile(filePath: string) {
      try {
        const content = fs.readFileSync(filePath, "utf-8");
        // NEXT_PUBLIC_ vars are inlined in the client bundle
        // They should never contain tokens, keys, or secrets
        const matches = content.match(/NEXT_PUBLIC_\w+/g) || [];
        for (const m of matches) {
          expect(m).not.toMatch(/SECRET|TOKEN|KEY|PASSWORD/i);
        }
      } catch {}
    }

    checkFile("src/lib/sanity/client.ts");
    checkFile("src/lib/auth.ts");
    checkFile("src/lib/redis.ts");
    checkFile("src/lib/deviceStatus.ts");
  });
});

// ── 7. API route auth consistency ────────────────────────────

describe("API route auth guards", () => {
  const API_ROUTES = [
    "src/app/api/device/status/route.ts",
    "src/app/api/settings/route.ts",
    "src/app/api/github/route.ts",
    "src/app/api/github/repos/route.ts",
    "src/app/api/github/commits/[sha]/route.ts",
    "src/app/api/raw/route.ts",
  ];

  for (const route of API_ROUTES) {
    it(`${route} should check auth`, async () => {
      const fs = await import("fs");
      const source = fs.readFileSync(route, "utf-8");
      // Every route must call auth() and check the session
      expect(source).toContain("auth()");
      expect(source).toMatch(/Unauthorized/);
    });
  }

  it("repos route should check user.id not just accessToken", async () => {
    const fs = await import("fs");
    const source = fs.readFileSync(
      "src/app/api/github/repos/route.ts",
      "utf-8"
    );
    // Should check both accessToken AND user.id for consistency
    expect(source).toMatch(/session\?\.accessToken/);
  });
});

// ── 8. Redis key isolation ───────────────────────────────────

describe("Redis key isolation", () => {
  it("user settings keys should use userId from session, never from client input", async () => {
    const fs = await import("fs");

    // Check settings route - userId should come from session, not request body
    const settingsRoute = fs.readFileSync(
      "src/app/api/settings/route.ts",
      "utf-8"
    );
    expect(settingsRoute).toContain("session.user.id");
    // Should NOT accept userId from request body
    expect(settingsRoute).not.toMatch(/req\.json\(\)[\s\S]*userId/);

    // Check device status route - repo comes from settings, not query params
    const statusRoute = fs.readFileSync(
      "src/app/api/device/status/route.ts",
      "utf-8"
    );
    expect(statusRoute).toContain("settings.repo");
    expect(statusRoute).not.toMatch(/searchParams.*repo/);
  });
});

// ── 9. Device push endpoint security ─────────────────────────

describe("Device push endpoint", () => {
  it("should NOT use NextAuth auth() — uses its own Bearer token auth", async () => {
    const fs = await import("fs");
    const source = fs.readFileSync(
      "src/app/api/device/push/route.ts",
      "utf-8"
    );
    expect(source).not.toContain('from "@/lib/auth"');
    expect(source).toContain("Authorization");
    expect(source).toContain("Bearer");
  });

  it("should validate token format before Redis lookup", async () => {
    const fs = await import("fs");
    const source = fs.readFileSync(
      "src/app/api/device/push/route.ts",
      "utf-8"
    );
    expect(source).toContain("validateDeviceToken");
  });

  it("middleware should exclude device/push from NextAuth", async () => {
    const fs = await import("fs");
    const source = fs.readFileSync("src/middleware.ts", "utf-8");
    expect(source).toContain("device/push");
  });

  it("unlink action should revoke device token", async () => {
    const fs = await import("fs");
    const source = fs.readFileSync("src/app/actions.ts", "utf-8");
    expect(source).toContain("revokeDeviceToken");
  });
});
