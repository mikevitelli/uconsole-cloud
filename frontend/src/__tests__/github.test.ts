import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  GitHubError,
  fetchRepoInfo,
  fetchCommits,
  fetchRawFile,
  fetchCommitDetail,
  validateUconsoleRepo,
} from "@/lib/github";

// Mock global fetch
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

beforeEach(() => {
  mockFetch.mockReset();
});

function mockResponse(status: number, body: unknown = null) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(typeof body === "string" ? body : JSON.stringify(body)),
  };
}

describe("GitHubError", () => {
  it("has correct name and status", () => {
    const err = new GitHubError(401, "token expired");
    expect(err.name).toBe("GitHubError");
    expect(err.status).toBe(401);
    expect(err.message).toBe("token expired");
    expect(err instanceof Error).toBe(true);
  });
});

describe("githubFetch (via fetchRepoInfo)", () => {
  it("throws GitHubError on 401", async () => {
    mockFetch.mockResolvedValue(mockResponse(401));
    await expect(fetchRepoInfo("tok", "owner/repo")).rejects.toThrow(GitHubError);
    await expect(fetchRepoInfo("tok", "owner/repo")).rejects.toThrow("GitHub token expired");
  });

  it("throws GitHubError on 403", async () => {
    mockFetch.mockResolvedValue(mockResponse(403));
    await expect(fetchRepoInfo("tok", "owner/repo")).rejects.toThrow(GitHubError);
    await expect(fetchRepoInfo("tok", "owner/repo")).rejects.toThrow("GitHub rate limit exceeded");
  });

  it("returns null on 404", async () => {
    mockFetch.mockResolvedValue(mockResponse(404));
    const result = await fetchRepoInfo("tok", "owner/repo");
    expect(result).toBeNull();
  });

  it("returns parsed JSON on 200", async () => {
    const data = { full_name: "owner/repo", private: false };
    mockFetch.mockResolvedValue(mockResponse(200, data));
    const result = await fetchRepoInfo("tok", "owner/repo");
    expect(result).toEqual(data);
  });

  it("sends correct Authorization header", async () => {
    mockFetch.mockResolvedValue(mockResponse(200, {}));
    await fetchRepoInfo("my-token", "owner/repo");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("repos/owner/repo"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "token my-token",
        }),
      })
    );
  });
});

describe("fetchRawFile", () => {
  it("throws GitHubError on 401", async () => {
    mockFetch.mockResolvedValue(mockResponse(401));
    await expect(fetchRawFile("tok", "owner/repo", "file.txt")).rejects.toThrow(
      "GitHub token expired"
    );
  });

  it("throws GitHubError on 403", async () => {
    mockFetch.mockResolvedValue(mockResponse(403));
    await expect(fetchRawFile("tok", "owner/repo", "file.txt")).rejects.toThrow(
      "GitHub rate limit exceeded"
    );
  });

  it("returns null on 404", async () => {
    mockFetch.mockResolvedValue(mockResponse(404));
    const result = await fetchRawFile("tok", "owner/repo", "missing.txt");
    expect(result).toBeNull();
  });

  it("returns text content on 200", async () => {
    mockFetch.mockResolvedValue(mockResponse(200, "file contents here"));
    const result = await fetchRawFile("tok", "owner/repo", "readme.md");
    expect(result).toBe("file contents here");
  });

  it("uses correct raw.githubusercontent.com URL", async () => {
    mockFetch.mockResolvedValue(mockResponse(200, ""));
    await fetchRawFile("tok", "owner/repo", "packages/apt.txt", "main");
    expect(mockFetch).toHaveBeenCalledWith(
      "https://raw.githubusercontent.com/owner/repo/main/packages/apt.txt",
      expect.any(Object)
    );
  });
});

describe("fetchCommitDetail", () => {
  it("returns commit with files", async () => {
    const data = {
      sha: "abc123",
      stats: { total: 10, additions: 7, deletions: 3 },
      files: [
        { filename: "a.txt", status: "modified", additions: 5, deletions: 2 },
        { filename: "b.txt", status: "added", additions: 2, deletions: 1 },
      ],
    };
    mockFetch.mockResolvedValue(mockResponse(200, data));
    const result = await fetchCommitDetail("tok", "owner/repo", "abc123");
    expect(result).toEqual(data);
  });

  it("handles merge commits with no files array", async () => {
    const data = {
      sha: "merge123",
      stats: { total: 0, additions: 0, deletions: 0 },
      // no files key — merge commits can omit this
    };
    mockFetch.mockResolvedValue(mockResponse(200, data));
    const result = await fetchCommitDetail("tok", "owner/repo", "merge123");
    expect(result).not.toBeNull();
    expect(result!.files).toEqual([]);
  });

  it("handles files being null", async () => {
    const data = {
      sha: "abc",
      stats: { total: 0, additions: 0, deletions: 0 },
      files: null,
    };
    mockFetch.mockResolvedValue(mockResponse(200, data));
    const result = await fetchCommitDetail("tok", "owner/repo", "abc");
    expect(result!.files).toEqual([]);
  });

  it("returns null on 404", async () => {
    mockFetch.mockResolvedValue(mockResponse(404));
    const result = await fetchCommitDetail("tok", "owner/repo", "bad-sha");
    expect(result).toBeNull();
  });

  it("throws on 401", async () => {
    mockFetch.mockResolvedValue(mockResponse(401));
    await expect(
      fetchCommitDetail("tok", "owner/repo", "abc")
    ).rejects.toThrow(GitHubError);
  });
});

describe("fetchCommits", () => {
  it("fetches commits with default perPage", async () => {
    mockFetch.mockResolvedValue(mockResponse(200, []));
    await fetchCommits("tok", "owner/repo");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("per_page=50"),
      expect.any(Object)
    );
  });

  it("fetches commits with custom perPage", async () => {
    mockFetch.mockResolvedValue(mockResponse(200, []));
    await fetchCommits("tok", "owner/repo", 10);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("per_page=10"),
      expect.any(Object)
    );
  });
});

describe("validateUconsoleRepo", () => {
  it("returns true when apt-manual.txt exists", async () => {
    mockFetch.mockResolvedValue(mockResponse(200, "vim\ngit\ncurl"));
    const result = await validateUconsoleRepo("tok", "owner/repo");
    expect(result).toBe(true);
  });

  it("returns false when apt-manual.txt is missing", async () => {
    mockFetch.mockResolvedValue(mockResponse(404));
    const result = await validateUconsoleRepo("tok", "owner/repo");
    expect(result).toBe(false);
  });
});
