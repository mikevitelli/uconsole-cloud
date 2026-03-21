import { describe, it, expect } from "vitest";
import {
  parseLines,
  fmtSize,
  categoryLabel,
  parseScriptsManifest,
} from "@/lib/utils";

describe("parseLines", () => {
  it("returns empty array for null", () => {
    expect(parseLines(null)).toEqual([]);
  });

  it("returns empty array for empty string", () => {
    expect(parseLines("")).toEqual([]);
  });

  it("splits lines and trims whitespace", () => {
    expect(parseLines("  foo  \n  bar  ")).toEqual(["foo", "bar"]);
  });

  it("filters out comments", () => {
    expect(parseLines("# comment\nfoo\n# another\nbar")).toEqual(["foo", "bar"]);
  });

  it("filters out empty lines", () => {
    expect(parseLines("foo\n\n\nbar\n")).toEqual(["foo", "bar"]);
  });
});

describe("fmtSize", () => {
  it("formats KB values", () => {
    expect(fmtSize(512)).toBe("512 KB");
  });

  it("formats MB values", () => {
    expect(fmtSize(2048)).toBe("2.0 MB");
  });

  it("formats exact 1024 as MB", () => {
    expect(fmtSize(1025)).toBe("1.0 MB");
  });
});

describe("categoryLabel", () => {
  it("returns known labels", () => {
    expect(categoryLabel("packages")).toBe("packages");
    expect(categoryLabel("gh")).toBe("GitHub CLI");
    expect(categoryLabel("retropie")).toBe("RetroPie");
  });

  it("returns key for unknown categories", () => {
    expect(categoryLabel("custom")).toBe("custom");
  });
});

describe("parseScriptsManifest", () => {
  it("returns empty for null", () => {
    expect(parseScriptsManifest(null)).toEqual({ columns: [], rows: [] });
  });

  it("returns empty for empty string", () => {
    expect(parseScriptsManifest("")).toEqual({ columns: [], rows: [] });
  });

  it("parses tab-delimited manifest", () => {
    const text = "Name\tSize\tPath\nbackup.sh\t2KB\t~/scripts/\nrestore.sh\t1KB\t~/";
    const result = parseScriptsManifest(text);
    expect(result.columns).toEqual(["Name", "Size", "Path"]);
    expect(result.rows).toHaveLength(2);
    expect(result.rows[0]).toEqual(["backup.sh", "2KB", "~/scripts/"]);
  });

  it("skips separator lines", () => {
    const text = "Name\tSize\n────\t────\nfoo\t1KB";
    const result = parseScriptsManifest(text);
    expect(result.rows).toHaveLength(1);
    expect(result.rows[0]).toEqual(["foo", "1KB"]);
  });

  it("filters comment lines", () => {
    const text = "# header comment\nName\tSize\nfoo\t1KB";
    const result = parseScriptsManifest(text);
    expect(result.columns).toEqual(["Name", "Size"]);
    expect(result.rows).toHaveLength(1);
  });
});
