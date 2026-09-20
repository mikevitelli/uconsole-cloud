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
}));
vi.mock("@/lib/github", () => ({
  validateUconsoleRepo: vi.fn(),
}));

import { POST } from "@/app/api/settings/route";
import { requireAuthWithToken } from "@/lib/api-helpers";
import { getUserSettings, setUserSettings } from "@/lib/redis";
import {
  generateDeviceToken,
  revokeDeviceToken,
  revokeOtherDeviceTokens,
} from "@/lib/deviceToken";
import { validateUconsoleRepo } from "@/lib/github";

const mockAuth = requireAuthWithToken as ReturnType<typeof vi.fn>;
const mockGetUserSettings = getUserSettings as ReturnType<typeof vi.fn>;
const mockSetUserSettings = setUserSettings as ReturnType<typeof vi.fn>;
const mockGenerate = generateDeviceToken as ReturnType<typeof vi.fn>;
const mockRevokeAll = revokeDeviceToken as ReturnType<typeof vi.fn>;
const mockSweep = revokeOtherDeviceTokens as ReturnType<typeof vi.fn>;
const mockValidateRepo = validateUconsoleRepo as ReturnType<typeof vi.fn>;

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
  mockSetUserSettings.mockResolvedValue(undefined);
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

  it("sweeps on a first link too, when there was no prior token", async () => {
    mockGetUserSettings.mockResolvedValue(null);

    await POST(request());

    expect(mockSweep).toHaveBeenCalledWith("user123", "new-token");
  });
});
