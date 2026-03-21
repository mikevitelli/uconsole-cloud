import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock Redis
const mockGet = vi.fn();
const mockSet = vi.fn();
const mockDel = vi.fn();

vi.mock("@/lib/redis", () => ({
  redis: {
    get: (...args: unknown[]) => mockGet(...args),
    set: (...args: unknown[]) => mockSet(...args),
    del: (...args: unknown[]) => mockDel(...args),
  },
  getUserSettings: vi.fn(),
  setUserSettings: vi.fn(),
}));

import {
  generateDeviceCode,
  confirmDeviceCode,
  pollDeviceCode,
} from "@/lib/deviceCode";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("generateDeviceCode", () => {
  it("returns a code in XXXX-XXXX format", async () => {
    const result = await generateDeviceCode();
    expect(result.code).toMatch(/^[A-Z0-9]{4}-[A-Z0-9]{4}$/);
  });

  it("returns a UUID secret", async () => {
    const result = await generateDeviceCode();
    expect(result.secret).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    );
  });

  it("returns 600 second expiry", async () => {
    const result = await generateDeviceCode();
    expect(result.expiresIn).toBe(600);
  });

  it("stores code data in Redis with 600s TTL", async () => {
    const result = await generateDeviceCode();
    expect(mockSet).toHaveBeenCalledWith(
      `devicecode:${result.code}`,
      expect.objectContaining({
        secret: result.secret,
        status: "pending",
        createdAt: expect.any(String),
      }),
      { ex: 600 }
    );
  });

  it("stores poll data in Redis with 600s TTL", async () => {
    const result = await generateDeviceCode();
    expect(mockSet).toHaveBeenCalledWith(
      `devicepoll:${result.secret}`,
      expect.objectContaining({
        status: "pending",
        code: result.code,
      }),
      { ex: 600 }
    );
  });

  it("excludes ambiguous characters (I, O, 0, 1)", async () => {
    // Generate many codes to check character set
    for (let i = 0; i < 20; i++) {
      const result = await generateDeviceCode();
      const raw = result.code.replace("-", "");
      expect(raw).not.toMatch(/[IO01]/);
    }
  });
});

describe("confirmDeviceCode", () => {
  it("confirms a pending code", async () => {
    mockGet.mockResolvedValue({
      secret: "test-secret",
      status: "pending",
      createdAt: "2026-01-01T00:00:00Z",
    });

    const result = await confirmDeviceCode("AB12-CD34", "token-123", "owner/repo");
    expect(result.success).toBe(true);
  });

  it("updates both Redis keys on confirm", async () => {
    mockGet.mockResolvedValue({
      secret: "test-secret",
      status: "pending",
      createdAt: "2026-01-01T00:00:00Z",
    });

    await confirmDeviceCode("AB12-CD34", "token-123", "owner/repo");

    // Should update code key
    expect(mockSet).toHaveBeenCalledWith(
      "devicecode:AB12-CD34",
      expect.objectContaining({ status: "confirmed" }),
      { ex: 600 }
    );

    // Should update poll key with token and repo
    expect(mockSet).toHaveBeenCalledWith(
      "devicepoll:test-secret",
      expect.objectContaining({
        status: "confirmed",
        deviceToken: "token-123",
        repo: "owner/repo",
      }),
      { ex: 600 }
    );
  });

  it("rejects expired/missing code", async () => {
    mockGet.mockResolvedValue(null);

    const result = await confirmDeviceCode("AB12-CD34", "token", "repo");
    expect(result.success).toBe(false);
    expect(result.error).toContain("not found or expired");
  });

  it("rejects already-used code", async () => {
    mockGet.mockResolvedValue({
      secret: "test-secret",
      status: "confirmed",
      createdAt: "2026-01-01T00:00:00Z",
    });

    const result = await confirmDeviceCode("AB12-CD34", "token", "repo");
    expect(result.success).toBe(false);
    expect(result.error).toContain("already used");
  });
});

describe("pollDeviceCode", () => {
  it("returns pending status", async () => {
    mockGet.mockResolvedValue({ status: "pending", code: "AB12-CD34" });

    const result = await pollDeviceCode("test-secret");
    expect(result).toEqual({ status: "pending", code: "AB12-CD34" });
  });

  it("returns confirmed status with token and repo", async () => {
    mockGet.mockResolvedValue({
      status: "confirmed",
      code: "AB12-CD34",
      deviceToken: "token-123",
      repo: "owner/repo",
    });

    const result = await pollDeviceCode("test-secret");
    expect(result?.status).toBe("confirmed");
    expect(result?.deviceToken).toBe("token-123");
    expect(result?.repo).toBe("owner/repo");
  });

  it("deletes both keys on confirmed poll (single-use)", async () => {
    mockGet.mockResolvedValue({
      status: "confirmed",
      code: "AB12-CD34",
      deviceToken: "token-123",
      repo: "owner/repo",
    });

    await pollDeviceCode("test-secret");
    expect(mockDel).toHaveBeenCalledWith("devicepoll:test-secret");
    expect(mockDel).toHaveBeenCalledWith("devicecode:AB12-CD34");
  });

  it("does not delete keys on pending poll", async () => {
    mockGet.mockResolvedValue({ status: "pending", code: "AB12-CD34" });

    await pollDeviceCode("test-secret");
    expect(mockDel).not.toHaveBeenCalled();
  });

  it("returns null for unknown secret", async () => {
    mockGet.mockResolvedValue(null);

    const result = await pollDeviceCode("bad-secret");
    expect(result).toBeNull();
  });
});

describe("full flow: generate → confirm → poll", () => {
  it("completes the device code auth flow", async () => {
    // Step 1: Generate
    const generated = await generateDeviceCode();
    expect(generated.code).toMatch(/^[A-Z0-9]{4}-[A-Z0-9]{4}$/);

    // Step 2: Simulate that code is stored
    mockGet.mockResolvedValueOnce({
      secret: generated.secret,
      status: "pending",
      createdAt: new Date().toISOString(),
    });

    // Step 3: Confirm
    const confirmed = await confirmDeviceCode(
      generated.code,
      "device-token-uuid",
      "mikevitelli/uconsole"
    );
    expect(confirmed.success).toBe(true);

    // Step 4: Poll returns confirmed
    mockGet.mockResolvedValueOnce({
      status: "confirmed",
      code: generated.code,
      deviceToken: "device-token-uuid",
      repo: "mikevitelli/uconsole",
    });

    const polled = await pollDeviceCode(generated.secret);
    expect(polled?.status).toBe("confirmed");
    expect(polled?.deviceToken).toBe("device-token-uuid");
    expect(polled?.repo).toBe("mikevitelli/uconsole");
  });
});
