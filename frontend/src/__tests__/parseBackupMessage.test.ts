import { describe, it, expect } from "vitest";
import { parseBackupMessage } from "@/lib/utils";

describe("parseBackupMessage", () => {
  // ── Plain backup format: backup: DATE — N file(s) ──────

  it("parses plain backup format with file count", () => {
    const result = parseBackupMessage("backup: 2026-03-14 23:57 — 7 file(s)");
    expect(result.categories).toEqual(["all"]);
    expect(result.fileCount).toBe(7);
  });

  it("parses plain backup with large file count", () => {
    const result = parseBackupMessage("backup: 2026-03-15 00:56 — 10 file(s)");
    expect(result.categories).toEqual(["all"]);
    expect(result.fileCount).toBe(10);
  });

  it("parses plain backup with 1 file", () => {
    const result = parseBackupMessage("backup: 2026-03-14 18:32 — 1 file(s)");
    expect(result.categories).toEqual(["all"]);
    expect(result.fileCount).toBe(1);
  });

  it("parses plain backup without file count", () => {
    const result = parseBackupMessage("backup: 2026-03-14 20:00");
    expect(result.categories).toEqual(["all"]);
    expect(result.fileCount).toBeNull();
  });

  // ── Category backup format: backup(cat1, cat2) N file(s) ──

  it("parses single category backup", () => {
    const result = parseBackupMessage("backup(packages) 15 file(s)");
    expect(result.categories).toEqual(["packages"]);
    expect(result.fileCount).toBe(15);
  });

  it("parses multi-category backup", () => {
    const result = parseBackupMessage(
      "backup(shell, packages, config) 45 file(s)"
    );
    expect(result.categories).toEqual(["shell", "packages", "config"]);
    expect(result.fileCount).toBe(45);
  });

  it("parses category backup without file count", () => {
    const result = parseBackupMessage("backup(system)");
    expect(result.categories).toEqual(["system"]);
    expect(result.fileCount).toBeNull();
  });

  it("trims whitespace in category names", () => {
    const result = parseBackupMessage("backup( shell , config ) 3 file(s)");
    expect(result.categories).toEqual(["shell", "config"]);
  });

  // ── Non-backup messages ───────────────────────────────

  it("returns empty for non-backup commit messages", () => {
    const result = parseBackupMessage("Fix: replace undefined BRANCH variable");
    expect(result.categories).toEqual([]);
    expect(result.fileCount).toBeNull();
  });

  it("returns empty for empty string", () => {
    const result = parseBackupMessage("");
    expect(result.categories).toEqual([]);
    expect(result.fileCount).toBeNull();
  });

  it("returns empty for random commit message", () => {
    const result = parseBackupMessage(
      "Add comprehensive docs, utility scripts, and fix charging config"
    );
    expect(result.categories).toEqual([]);
    expect(result.fileCount).toBeNull();
  });

  // ── Multi-line messages ───────────────────────────────

  it("only parses first line of multi-line message", () => {
    const result = parseBackupMessage(
      "backup(packages) 5 file(s)\n\nUpdated apt and snap manifests"
    );
    expect(result.categories).toEqual(["packages"]);
    expect(result.fileCount).toBe(5);
  });

  it("only parses first line of plain backup with body", () => {
    const result = parseBackupMessage(
      "backup: 2026-03-14 23:57 — 7 file(s)\n\nSome details here"
    );
    expect(result.categories).toEqual(["all"]);
    expect(result.fileCount).toBe(7);
  });
});
