import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock Redis
const mockGet = vi.fn();
const mockSet = vi.fn();
const mockDel = vi.fn();
const mockExpire = vi.fn();
const mockSadd = vi.fn();
const mockSrem = vi.fn();
const mockSmembers = vi.fn();
const mockEval = vi.fn();

vi.mock("@/lib/redis", () => ({
  redis: {
    get: (...args: unknown[]) => mockGet(...args),
    set: (...args: unknown[]) => mockSet(...args),
    del: (...args: unknown[]) => mockDel(...args),
    expire: (...args: unknown[]) => mockExpire(...args),
    sadd: (...args: unknown[]) => mockSadd(...args),
    srem: (...args: unknown[]) => mockSrem(...args),
    smembers: (...args: unknown[]) => mockSmembers(...args),
    eval: (...args: unknown[]) => mockEval(...args),
  },
  getUserSettings: vi.fn(),
  setUserSettings: vi.fn(),
  deleteUserSettings: vi.fn(),
}));

import {
  generateDeviceToken,
  validateDeviceToken,
  revokeDeviceToken,
  revokeDeviceTokenValue,
  revokeOtherDeviceTokens,
  regenerateDeviceToken,
  withDeviceTokenLock,
  DeviceTokenBusyError,
} from "@/lib/deviceToken";
import { getUserSettings, setUserSettings } from "@/lib/redis";

const mockGetUserSettings = getUserSettings as ReturnType<typeof vi.fn>;
const mockSetUserSettings = setUserSettings as ReturnType<typeof vi.fn>;

const TTL = 60 * 60 * 24 * 90;

beforeEach(() => {
  vi.clearAllMocks();
  // "OK" is what SET NX returns when it takes the lock; the token writes
  // ignore the return value.
  mockSet.mockResolvedValue("OK");
  mockEval.mockResolvedValue(1);
  mockSmembers.mockResolvedValue([]);
  mockGetUserSettings.mockResolvedValue({
    repo: "owner/repo",
    linkedAt: "2026-01-01T00:00:00Z",
  });
});

describe("generateDeviceToken", () => {
  it("returns a UUID", async () => {
    const { token } = await generateDeviceToken("user123", "owner/repo");
    expect(token).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    );
  });

  it("stores token in Redis with 90-day TTL", async () => {
    await generateDeviceToken("user123", "owner/repo");
    expect(mockSet).toHaveBeenCalledWith(
      expect.stringMatching(/^devicetoken:/),
      expect.objectContaining({
        userId: "user123",
        repo: "owner/repo",
        createdAt: expect.any(String),
      }),
      { ex: TTL }
    );
  });

  it("indexes the token so revocation can always reach it", async () => {
    const { token } = await generateDeviceToken("user123", "owner/repo");
    expect(mockSadd).toHaveBeenCalledWith("usertokens:user123", token);
    expect(mockExpire).toHaveBeenCalledWith("usertokens:user123", TTL);
  });

  it("points user settings at the new token", async () => {
    const { token } = await generateDeviceToken("user123", "owner/repo");
    expect(mockSetUserSettings).toHaveBeenCalledWith(
      "user123",
      expect.objectContaining({ deviceToken: token })
    );
  });

  it("reports the token it actually displaced", async () => {
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
      deviceToken: "superseded",
    });

    const { replaced } = await generateDeviceToken("user123", "owner/repo");

    // Read at swap time, not from a caller's earlier snapshot — that is what
    // lets the caller revoke the value it really replaced.
    expect(replaced).toBe("superseded");
  });

  it("reports no displacement when there was no prior token", async () => {
    const { replaced } = await generateDeviceToken("user123", "owner/repo");
    expect(replaced).toBeUndefined();
  });
});

describe("validateDeviceToken", () => {
  it("resolves a live token to its user and repo", async () => {
    mockGet.mockResolvedValue({
      userId: "user123",
      repo: "owner/repo",
      createdAt: "2026-01-01T00:00:00Z",
    });

    await expect(validateDeviceToken("tok")).resolves.toEqual({
      userId: "user123",
      repo: "owner/repo",
    });
  });

  it("returns null for an unknown token", async () => {
    mockGet.mockResolvedValue(null);
    await expect(validateDeviceToken("tok")).resolves.toBeNull();
  });
});

describe("revokeDeviceTokenValue", () => {
  it("deletes the token it is handed and drops it from the index", async () => {
    await revokeDeviceTokenValue("user123", "orphaned-token");

    expect(mockDel).toHaveBeenCalledWith("devicetoken:orphaned-token");
    expect(mockSrem).toHaveBeenCalledWith("usertokens:user123", "orphaned-token");
  });

  it("reaches a token that settings no longer point at", async () => {
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
      deviceToken: "replacement",
    });

    await revokeDeviceTokenValue("user123", "superseded");
    expect(mockDel).toHaveBeenCalledWith("devicetoken:superseded");
  });
});

describe("revokeDeviceToken", () => {
  it("revokes every token the user holds, not just the referenced one", async () => {
    // The exact shape behind "seven valid tokens for a single device": the
    // pointer reaches one, the index reaches all of them.
    mockSmembers.mockResolvedValue(["tok-a", "tok-b", "tok-c"]);
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
      deviceToken: "tok-c",
    });

    await revokeDeviceToken("user123");

    expect(mockDel).toHaveBeenCalledWith(
      "devicetoken:tok-a",
      "devicetoken:tok-b",
      "devicetoken:tok-c"
    );
    // Snapshotted members are removed individually. Deleting the index key
    // wholesale would drop a token a concurrent mint added after the snapshot.
    expect(mockSrem).toHaveBeenCalledWith(
      "usertokens:user123",
      "tok-a",
      "tok-b",
      "tok-c"
    );
  });

  it("still revokes a token minted before the index existed", async () => {
    mockSmembers.mockResolvedValue([]);
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
      deviceToken: "legacy-token",
    });

    await revokeDeviceToken("user123");

    expect(mockDel).toHaveBeenCalledWith("devicetoken:legacy-token");
  });

  it("leaves settings to the caller", async () => {
    // Both callers (unlink, settings DELETE) delete settings straight after.
    // Clearing the pointer here bought nothing and raced concurrent mints.
    mockSmembers.mockResolvedValue(["tok-a"]);
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
      deviceToken: "tok-a",
    });

    await revokeDeviceToken("user123");

    expect(mockDel).toHaveBeenCalledWith("devicetoken:tok-a");
    expect(mockSetUserSettings).not.toHaveBeenCalled();
  });

  it("does nothing if no token exists", async () => {
    mockSmembers.mockResolvedValue([]);
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
    });

    await revokeDeviceToken("user123");
    expect(mockDel).not.toHaveBeenCalledWith(
      expect.stringMatching(/^devicetoken:/)
    );
  });
});

describe("regenerateDeviceToken", () => {
  it("revokes old tokens and generates a new one", async () => {
    mockSmembers.mockResolvedValue(["old-token"]);
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
      deviceToken: "old-token",
    });

    const newToken = await regenerateDeviceToken("user123", "owner/repo");

    expect(newToken).toMatch(/^[0-9a-f]{8}-/);
    expect(mockDel).toHaveBeenCalledWith("devicetoken:old-token");
  });
});

// ── Greptile P1 follow-ups on #58 ────────────────────────────────

describe("generateDeviceToken partial-mint cleanup", () => {
  it("deletes the token when indexing fails", async () => {
    // The token key is written first. A throw after that point leaves a live
    // 90-day credential with nothing referencing it and nothing able to reach
    // it — the orphan this module exists to prevent.
    mockSadd.mockRejectedValueOnce(new Error("redis down"));

    await expect(
      generateDeviceToken("user123", "owner/repo")
    ).rejects.toThrow("redis down");

    expect(mockDel).toHaveBeenCalledWith(
      expect.stringMatching(/^devicetoken:/)
    );
  });

  it("deletes the token when the settings write fails", async () => {
    mockSetUserSettings.mockRejectedValueOnce(new Error("settings write failed"));

    await expect(
      generateDeviceToken("user123", "owner/repo")
    ).rejects.toThrow("settings write failed");

    expect(mockDel).toHaveBeenCalledWith(
      expect.stringMatching(/^devicetoken:/)
    );
  });

  it("surfaces the original error even if cleanup itself fails", async () => {
    mockSadd.mockRejectedValueOnce(new Error("redis down"));
    mockDel.mockRejectedValueOnce(new Error("cleanup also failed"));

    await expect(
      generateDeviceToken("user123", "owner/repo")
    ).rejects.toThrow("redis down");
  });
});

describe("revokeDeviceToken concurrency", () => {
  it("removes only the tokens it snapshotted, not the whole index", async () => {
    // Deleting the index key would drop a token a concurrent mint added after
    // the snapshot, stranding a live credential outside the index.
    mockSmembers.mockResolvedValue(["tok-a", "tok-b"]);
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
      deviceToken: "tok-b",
    });

    await revokeDeviceToken("user123");

    expect(mockSrem).toHaveBeenCalledWith("usertokens:user123", "tok-a", "tok-b");
    expect(mockDel).not.toHaveBeenCalledWith("usertokens:user123");
  });

  it("never writes settings, so a concurrent mint cannot lose its pointer", async () => {
    // Read the pointer, compare it, write it back and a mint landing inside
    // that window has its pointer overwritten: the replacement stays live and
    // indexed with nothing in settings naming it. Settings belong to the
    // callers, both of which delete them outright straight after.
    mockSmembers.mockResolvedValue(["tok-a"]);
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
      deviceToken: "tok-a",
    });

    await revokeDeviceToken("user123");

    expect(mockSetUserSettings).not.toHaveBeenCalled();
  });

  it("still revokes a pointer token that predates the index", async () => {
    mockSmembers.mockResolvedValue([]);
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
      deviceToken: "pre-index",
    });

    await revokeDeviceToken("user123");

    expect(mockDel).toHaveBeenCalledWith("devicetoken:pre-index");
    expect(mockSrem).toHaveBeenCalledWith("usertokens:user123", "pre-index");
  });
});

describe("generateDeviceToken indexes what it displaces", () => {
  it("indexes a pointer-only token as it is superseded", async () => {
    // Tokens minted before the index existed are known only to the pointer,
    // and the mint is the last moment anything names them. Missing this leaves
    // them invisible to the sweep and live for the rest of their 90 days.
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
      deviceToken: "legacy-pointer-only",
    });

    const { token } = await generateDeviceToken("user123", "owner/repo");

    expect(mockSadd).toHaveBeenCalledWith("usertokens:user123", token);
    expect(mockSadd).toHaveBeenCalledWith(
      "usertokens:user123",
      "legacy-pointer-only"
    );
  });

  it("indexes only the new token on a first link", async () => {
    mockGetUserSettings.mockResolvedValue(null);

    await generateDeviceToken("user123", "owner/repo");

    expect(mockSadd).toHaveBeenCalledTimes(1);
  });
});

describe("revokeOtherDeviceTokens", () => {
  it("revokes every indexed token but the one it is told to keep", async () => {
    mockSmembers.mockResolvedValue(["stale-a", "keep-me", "stale-b"]);

    await revokeOtherDeviceTokens("user123", "keep-me");

    expect(mockDel).toHaveBeenCalledWith(
      "devicetoken:stale-a",
      "devicetoken:stale-b"
    );
    expect(mockSrem).toHaveBeenCalledWith(
      "usertokens:user123",
      "stale-a",
      "stale-b"
    );
  });

  it("retries a credential an earlier cleanup failed to delete", async () => {
    // The point of sweeping the index instead of the single value a request
    // displaced: a revoke that failed on a previous relink left that token
    // indexed, so this call picks it up rather than leaving it live for the
    // rest of its 90 days.
    mockSmembers.mockResolvedValue(["missed-last-time", "current"]);

    await revokeOtherDeviceTokens("user123", "current");

    expect(mockDel).toHaveBeenCalledWith("devicetoken:missed-last-time");
  });

  it("touches nothing when the kept token is the only one", async () => {
    mockSmembers.mockResolvedValue(["current"]);

    await revokeOtherDeviceTokens("user123", "current");

    expect(mockDel).not.toHaveBeenCalled();
    expect(mockSrem).not.toHaveBeenCalled();
  });
});

describe("regenerateDeviceToken", () => {
  it("mints before revoking, so a failed mint leaves the device connected", async () => {
    const order: string[] = [];
    mockSet.mockImplementation(async (key: string) => {
      if (!String(key).startsWith("devicetoken:")) return "OK"; // the lock
      order.push("mint");
      throw new Error("redis down");
    });
    mockSmembers.mockImplementation(async () => {
      order.push("sweep");
      return ["live-token"];
    });

    await expect(regenerateDeviceToken("user123", "owner/repo")).rejects.toThrow(
      "redis down"
    );
    expect(order).toEqual(["mint"]);
    expect(mockDel).not.toHaveBeenCalledWith("devicetoken:live-token");
  });

  it("surfaces a failed sweep rather than swallowing it", async () => {
    // Retiring the old credential is the whole point of regenerating, so
    // unlike a relink this one must not report success on a failed cleanup.
    mockSmembers.mockResolvedValue(["old-token"]);
    mockDel.mockRejectedValue(new Error("redis down"));

    await expect(regenerateDeviceToken("user123", "owner/repo")).rejects.toThrow(
      "redis down"
    );
  });
});


describe("withDeviceTokenLock", () => {
  it("runs the callback while holding the lock and releases it after", async () => {
    const result = await withDeviceTokenLock("user123", async () => "done");

    expect(result).toBe("done");
    expect(mockSet).toHaveBeenCalledWith(
      "devicelock:user123",
      expect.any(String),
      { ex: 10, nx: true }
    );
    // Released through a script, not GET-then-DEL: a lock that expired mid-run
    // belongs to someone else by then and must not be deleted.
    expect(mockEval).toHaveBeenCalledWith(
      expect.stringContaining("redis.call(\"DEL\", KEYS[1])"),
      ["devicelock:user123"],
      [expect.any(String)]
    );
  });

  it("releases the lock when the callback throws", async () => {
    await expect(
      withDeviceTokenLock("user123", async () => {
        throw new Error("boom");
      })
    ).rejects.toThrow("boom");

    expect(mockEval).toHaveBeenCalled();
  });

  it("does not let a failed release mask a committed replacement", async () => {
    // By the time the lock is released the work has landed. Throwing here
    // would report a committed relink as a 500, and the retry would meet a
    // consumed device code or an existing repo.
    mockEval.mockRejectedValue(new Error("redis down"));

    await expect(
      withDeviceTokenLock("user123", async () => "committed")
    ).resolves.toBe("committed");
  });

  it("refuses rather than running alongside another change", async () => {
    // SET NX returns null while someone else holds it.
    mockSet.mockResolvedValue(null);
    const ran = vi.fn();

    await expect(withDeviceTokenLock("user123", ran)).rejects.toBeInstanceOf(
      DeviceTokenBusyError
    );
    expect(ran).not.toHaveBeenCalled();
  }, 10000);

  it("serializes two replacements instead of interleaving them", async () => {
    // The race this exists for: A commits, pauses, B commits and sweeps, then
    // A's sweep deletes B's committed token. Under the lock B cannot start
    // until A has finished sweeping.
    const held: string[] = [];
    let locked = false;
    mockSet.mockImplementation(async (key: string) => {
      if (!String(key).startsWith("devicelock:")) return "OK";
      if (locked) return null;
      locked = true;
      return "OK";
    });
    mockEval.mockImplementation(async () => {
      locked = false;
      return 1;
    });

    const flow = (name: string) =>
      withDeviceTokenLock("user123", async () => {
        held.push(`${name}:in`);
        await new Promise((r) => setTimeout(r, 60));
        held.push(`${name}:out`);
      });

    await Promise.all([flow("a"), flow("b")]);

    // Never "a:in, b:in" — one runs to completion before the other starts.
    expect(held).toEqual(
      held[0] === "a:in"
        ? ["a:in", "a:out", "b:in", "b:out"]
        : ["b:in", "b:out", "a:in", "a:out"]
    );
  });
});
