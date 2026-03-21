import { describe, it, expect } from "vitest";

// Test the path validation regex used in /api/github and /api/raw routes
const PATH_REGEX = /^[\w\-./]+$/;

function isValidPath(path: string): boolean {
  if (!PATH_REGEX.test(path)) return false;
  if (path.includes("..")) return false;
  return true;
}

describe("path validation", () => {
  // ── Valid paths ───────────────────────────────────────

  it("allows simple filenames", () => {
    expect(isValidPath("readme.md")).toBe(true);
  });

  it("allows nested paths", () => {
    expect(isValidPath("packages/apt-manual.txt")).toBe(true);
  });

  it("allows deeply nested paths", () => {
    expect(isValidPath("config/systemd/user/webdash.service")).toBe(true);
  });

  it("allows paths with hyphens and underscores", () => {
    expect(isValidPath("my-file_name.txt")).toBe(true);
  });

  it("allows paths with dots", () => {
    expect(isValidPath(".bashrc")).toBe(true);
  });

  // ── Blocked traversal paths ───────────────────────────

  it("blocks parent directory traversal", () => {
    expect(isValidPath("../etc/passwd")).toBe(false);
  });

  it("blocks mid-path traversal", () => {
    expect(isValidPath("packages/../../etc/shadow")).toBe(false);
  });

  it("blocks double-dot only", () => {
    expect(isValidPath("..")).toBe(false);
  });

  // ── Blocked special characters ────────────────────────

  it("blocks spaces", () => {
    expect(isValidPath("my file.txt")).toBe(false);
  });

  it("blocks query strings", () => {
    expect(isValidPath("file.txt?foo=bar")).toBe(false);
  });

  it("blocks hash fragments", () => {
    expect(isValidPath("file.txt#section")).toBe(false);
  });

  it("blocks null bytes", () => {
    expect(isValidPath("file\0.txt")).toBe(false);
  });

  it("blocks semicolons", () => {
    expect(isValidPath("file;rm -rf")).toBe(false);
  });

  it("blocks backticks", () => {
    expect(isValidPath("`whoami`")).toBe(false);
  });

  it("blocks dollar signs", () => {
    expect(isValidPath("${HOME}/secret")).toBe(false);
  });
});

// Test the repo format validation regex from /api/settings
const REPO_REGEX = /^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/;

describe("repo format validation", () => {
  // ── Valid repos ───────────────────────────────────────

  it("allows standard owner/repo", () => {
    expect(REPO_REGEX.test("mikevitelli/uconsole")).toBe(true);
  });

  it("allows repos with dots", () => {
    expect(REPO_REGEX.test("owner/my.repo")).toBe(true);
  });

  it("allows repos with hyphens", () => {
    expect(REPO_REGEX.test("my-org/my-repo")).toBe(true);
  });

  it("allows repos with underscores", () => {
    expect(REPO_REGEX.test("my_org/my_repo")).toBe(true);
  });

  // ── Blocked formats ──────────────────────────────────

  it("blocks traversal in repo name", () => {
    expect(REPO_REGEX.test("../../etc")).toBe(false);
  });

  it("blocks extra slashes", () => {
    expect(REPO_REGEX.test("owner/repo/extra")).toBe(false);
  });

  it("blocks spaces", () => {
    expect(REPO_REGEX.test("owner/my repo")).toBe(false);
  });

  it("blocks special characters", () => {
    expect(REPO_REGEX.test("owner/repo;rm")).toBe(false);
  });

  it("blocks empty owner", () => {
    expect(REPO_REGEX.test("/repo")).toBe(false);
  });

  it("blocks empty repo", () => {
    expect(REPO_REGEX.test("owner/")).toBe(false);
  });

  it("blocks no slash", () => {
    expect(REPO_REGEX.test("justrepo")).toBe(false);
  });

  it("blocks query params", () => {
    expect(REPO_REGEX.test("owner/repo?admin=true")).toBe(false);
  });
});

// Test SHA validation regex from /api/github/commits/[sha]
const SHA_REGEX = /^[0-9a-f]{7,40}$/i;

describe("SHA validation", () => {
  it("allows full 40-char SHA", () => {
    expect(SHA_REGEX.test("1a83d5a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6")).toBe(true);
  });

  it("allows short 7-char SHA", () => {
    expect(SHA_REGEX.test("1a83d5a")).toBe(true);
  });

  it("allows mixed case hex", () => {
    expect(SHA_REGEX.test("AbCdEf1234567")).toBe(true);
  });

  it("blocks too-short SHA (6 chars)", () => {
    expect(SHA_REGEX.test("1a83d5")).toBe(false);
  });

  it("blocks too-long SHA (41 chars)", () => {
    expect(SHA_REGEX.test("1a83d5a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6a")).toBe(false);
  });

  it("blocks non-hex characters", () => {
    expect(SHA_REGEX.test("1a83d5g")).toBe(false);
  });

  it("blocks path traversal as SHA", () => {
    expect(SHA_REGEX.test("../branches")).toBe(false);
  });

  it("blocks branch name as SHA", () => {
    expect(SHA_REGEX.test("main")).toBe(false);
  });

  it("blocks empty string", () => {
    expect(SHA_REGEX.test("")).toBe(false);
  });
});
