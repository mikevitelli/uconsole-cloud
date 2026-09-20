import { describe, it, expect, vi, beforeEach } from "vitest";
import type { NextRequest } from "next/server";
import type { UserSettings } from "@/lib/types";

vi.mock("@/lib/api-helpers", () => ({
  requireAuth: vi.fn(),
  requireAuthWithToken: vi.fn(),
}));
vi.mock("@/lib/redis", () => ({
  getUserSettings: vi.fn(),
  setUserSettings: vi.fn(),
  deleteUserSettings: vi.fn(),
}));
vi.mock("@/lib/deviceToken", () => ({
  generateDeviceToken: vi.fn(),
  revokeDeviceToken: vi.fn(),
  revokeOtherDeviceTokens: vi.fn(),
  withDeviceTokenLock: vi.fn(async (_userId: string, fn: () => Promise<unknown>) => fn()),
  DeviceTokenBusyError: class DeviceTokenBusyError extends Error {},
}));
vi.mock("@/lib/github", () => ({
  validateUconsoleRepo: vi.fn(),
}));

import { POST, DELETE } from "@/app/api/settings/route";
import { requireAuth, requireAuthWithToken } from "@/lib/api-helpers";
import {
  getUserSettings,
  setUserSettings,
  deleteUserSettings,
} from "@/lib/redis";
import {
  generateDeviceToken,
  revokeDeviceToken,
  revokeOtherDeviceTokens,
  withDeviceTokenLock,
  DeviceTokenBusyError,
} from "@/lib/deviceToken";
import { validateUconsoleRepo } from "@/lib/github";

const mockAuth = requireAuthWithToken as ReturnType<typeof vi.fn>;
const mockRequireAuth = requireAuth as ReturnType<typeof vi.fn>;
const mockGetUserSettings = getUserSettings as ReturnType<typeof vi.fn>;
const mockSetUserSettings = setUserSettings as ReturnType<typeof vi.fn>;
const mockGenerate = generateDeviceToken as ReturnType<typeof vi.fn>;
const mockRevokeAll = revokeDeviceToken as ReturnType<typeof vi.fn>;
const mockSweep = revokeOtherDeviceTokens as ReturnType<typeof vi.fn>;
const mockValidateRepo = validateUconsoleRepo as ReturnType<typeof vi.fn>;
const mockLock = withDeviceTokenLock as ReturnType<typeof vi.fn>;
const mockDeleteUserSettings = deleteUserSettings as ReturnType<typeof vi.fn>;

const BASE: UserSettings = {
  repo: "owner/old-repo",
  linkedAt: "2026-01-01T00:00:00Z",
  deviceToken: "working-token",
};

function request(repo = "owner/new-repo") {
  return { json: async () => ({ repo }) } as unknown as NextRequest;
}

beforeEach(() => {
  // resetAllMocks, not clearAllMocks: a mockRejectedValue set by one case
  // otherwise leaks into every case after it.
  vi.resetAllMocks();
  mockLock.mockImplementation(async (_userId: string, fn: () => Promise<unknown>) => fn());
  mockSetUserSettings.mockResolvedValue(undefined);
  mockDeleteUserSettings.mockResolvedValue(undefined);
  mockRequireAuth.mockResolvedValue({ user: { id: "user123" } });
  mockSweep.mockResolvedValue(undefined);
  mockRevokeAll.mockResolvedValue(undefined);
  mockAuth.mockResolvedValue({
    user: { id: "user123" },
    accessToken: "gh-token",
  });
  mockGetUserSettings.mockResolvedValue({ ...BASE });
  mockValidateRepo.mockResolvedValue(true);
  mockGenerate.mockResolvedValue({ token: "new-token" });
});

describe("POST /api/settings — relink", () => {
  it("mints, then commits, then retires the old credentials", async () => {
    const order: string[] = [];
    mockGenerate.mockImplementation(async () => {
      order.push("mint");
      return { token: "new-token" };
    });
    mockSetUserSettings.mockImplementation(async () => {
      order.push("settings");
    });
    mockSweep.mockImplementation(async () => {
      order.push("sweep");
    });

    await POST(request());

    // Committing before the mint moves the dashboard to a repo no device is
    // pushing to; revoking before the commit disconnects a working device and
    // leaves nothing in its place.
    expect(order).toEqual(["mint", "settings", "sweep"]);
  });

  it("commits the repo and the new pointer in one write", async () => {
    await POST(request());

    // Dropping deviceToken here is what previously left the outgoing
    // credential unnameable from settings.
    expect(mockSetUserSettings).toHaveBeenCalledWith("user123", {
      repo: "owner/new-repo",
      linkedAt: expect.any(String),
      deviceToken: "new-token",
    });
  });

  it("sweeps every stale credential, not just the displaced pointer", async () => {
    await POST(request());

    // Revoking only the value this request displaced never retried a cleanup
    // an earlier relink dropped, leaving that token live for its full 90 days.
    expect(mockSweep).toHaveBeenCalledWith("user123", "new-token");
    expect(mockRevokeAll).not.toHaveBeenCalled();
  });

  it("commits nothing when minting fails", async () => {
    mockGenerate.mockRejectedValue(new Error("mint failed"));

    await expect(POST(request())).rejects.toThrow("mint failed");

    // The old link and its working credential survive untouched.
    expect(mockSetUserSettings).not.toHaveBeenCalled();
    expect(mockSweep).not.toHaveBeenCalled();
  });

  it("leaves the old credential live when the settings write fails", async () => {
    mockSetUserSettings.mockRejectedValue(new Error("redis down"));

    await expect(POST(request())).rejects.toThrow("redis down");

    expect(mockSweep).not.toHaveBeenCalled();
  });

  it("still succeeds when the sweep fails", async () => {
    mockSweep.mockRejectedValue(new Error("redis down"));

    const res = await POST(request());

    expect(res.status).toBe(200);
    await expect(res.json()).resolves.toMatchObject({ deviceToken: "new-token" });
  });

  it("does the whole replacement under the per-user lock", async () => {
    const order: string[] = [];
    mockLock.mockImplementation(async (_userId: string, fn: () => Promise<unknown>) => {
      order.push("lock");
      const out = await fn();
      order.push("unlock");
      return out;
    });
    mockGenerate.mockImplementation(async () => {
      order.push("mint");
      return { token: "new-token" };
    });
    mockSweep.mockImplementation(async () => {
      order.push("sweep");
    });

    await POST(request());

    // A sweep outside the lock can delete a token a concurrent relink just
    // committed, leaving settings naming a credential that no longer works.
    expect(order).toEqual(["lock", "mint", "sweep", "unlock"]);
  });

  it("returns 409 rather than racing another change", async () => {
    mockLock.mockRejectedValue(new DeviceTokenBusyError());

    const res = await POST(request());

    expect(res.status).toBe(409);
  });

  it("sweeps on a first link too, when there was no prior token", async () => {
    mockGetUserSettings.mockResolvedValue(null);

    await POST(request());

    expect(mockSweep).toHaveBeenCalledWith("user123", "new-token");
  });
});

describe("DELETE /api/settings — unlink", () => {
  it("revokes and deletes settings under the replacement lock", async () => {
    // A relink indexes its new token before it writes settings. An unlocked
    // unlink can delete that token and then have the relink's settings write
    // land afterwards, recreating settings that name a credential which no
    // longer exists: the dashboard reads as linked and the device cannot push.
    const order: string[] = [];
    mockLock.mockImplementation(async (_userId: string, fn: () => Promise<unknown>) => {
      order.push("lock");
      const out = await fn();
      order.push("unlock");
      return out;
    });
    mockRevokeAll.mockImplementation(async () => {
      order.push("revoke");
    });
    mockDeleteUserSettings.mockImplementation(async () => {
      order.push("delete-settings");
    });

    await DELETE();

    expect(order).toEqual(["lock", "revoke", "delete-settings", "unlock"]);
  });

  it("returns 409 rather than racing a replacement", async () => {
    mockLock.mockRejectedValue(new DeviceTokenBusyError());

    const res = await DELETE();

    expect(res.status).toBe(409);
    expect(mockRevokeAll).not.toHaveBeenCalled();
  });
});
