import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock Redis
const mockGet = vi.fn();
const mockSet = vi.fn();
const mockDel = vi.fn();
const mockExpire = vi.fn();

vi.mock("@/lib/redis", () => ({
  redis: {
    get: (...args: unknown[]) => mockGet(...args),
    set: (...args: unknown[]) => mockSet(...args),
    del: (...args: unknown[]) => mockDel(...args),
    expire: (...args: unknown[]) => mockExpire(...args),
  },
  getUserSettings: vi.fn(),
  setUserSettings: vi.fn(),
  deleteUserSettings: vi.fn(),
}));

import {
  generateDeviceToken,
  validateDeviceToken,
  revokeDeviceToken,
  regenerateDeviceToken,
} from "@/lib/deviceToken";
import { getUserSettings, setUserSettings } from "@/lib/redis";

const mockGetUserSettings = getUserSettings as ReturnType<typeof vi.fn>;
const mockSetUserSettings = setUserSettings as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  mockGetUserSettings.mockResolvedValue({
    repo: "owner/repo",
    linkedAt: "2026-01-01T00:00:00Z",
  });
});

describe("generateDeviceToken", () => {
  it("returns a UUID", async () => {
    const token = await generateDeviceToken("user123", "owner/repo");
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
      { ex: 60 * 60 * 24 * 90 }
    );
  });

  it("updates user settings with token", async () => {
    const token = await generateDeviceToken("user123", "owner/repo");
    expect(mockSetUserSettings).toHaveBeenCalledWith(
      "user123",
      expect.objectContaining({ deviceToken: token })
    );
  });
});

describe("validateDeviceToken", () => {
  it("returns userId and repo for valid token", async () => {
    mockGet.mockResolvedValue({
      userId: "user123",
      repo: "owner/repo",
      createdAt: "2026-01-01T00:00:00Z",
    });
    const result = await validateDeviceToken("some-uuid");
    expect(result).toEqual({ userId: "user123", repo: "owner/repo" });
  });

  it("returns null for invalid token", async () => {
    mockGet.mockResolvedValue(null);
    const result = await validateDeviceToken("bad-token");
    expect(result).toBeNull();
  });
});

describe("revokeDeviceToken", () => {
  it("deletes token key and clears from settings", async () => {
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
      deviceToken: "old-token-uuid",
    });

    await revokeDeviceToken("user123");

    expect(mockDel).toHaveBeenCalledWith("devicetoken:old-token-uuid");
    expect(mockSetUserSettings).toHaveBeenCalledWith("user123", {
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
    });
  });

  it("does nothing if no token exists", async () => {
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/repo",
      linkedAt: "2026-01-01T00:00:00Z",
    });

    await revokeDeviceToken("user123");
    expect(mockDel).not.toHaveBeenCalled();
  });
});

describe("regenerateDeviceToken", () => {
  it("revokes old token and generates new one", async () => {
    mockGetUserSettings
      .mockResolvedValueOnce({
        repo: "owner/repo",
        linkedAt: "2026-01-01T00:00:00Z",
        deviceToken: "old-token",
      })
      .mockResolvedValueOnce({
        repo: "owner/repo",
        linkedAt: "2026-01-01T00:00:00Z",
      });

    const newToken = await regenerateDeviceToken("user123", "owner/repo");
    expect(newToken).toMatch(/^[0-9a-f]{8}-/);
    expect(mockDel).toHaveBeenCalledWith("devicetoken:old-token");
  });
});
