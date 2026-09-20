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
  revokeDeviceTokenValue: vi.fn(),
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
  revokeDeviceTokenValue,
} from "@/lib/deviceToken";
import { validateUconsoleRepo } from "@/lib/github";

const mockAuth = requireAuthWithToken as ReturnType<typeof vi.fn>;
const mockGetUserSettings = getUserSettings as ReturnType<typeof vi.fn>;
const mockSetUserSettings = setUserSettings as ReturnType<typeof vi.fn>;
const mockGenerate = generateDeviceToken as ReturnType<typeof vi.fn>;
const mockRevokeAll = revokeDeviceToken as ReturnType<typeof vi.fn>;
const mockRevokeValue = revokeDeviceTokenValue as ReturnType<typeof vi.fn>;
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
  mockRevokeValue.mockResolvedValue(undefined);
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
  it("commits the replacement before retiring the old credential", async () => {
    const order: string[] = [];
    mockSetUserSettings.mockImplementation(async () => {
      order.push("settings");
    });
    mockGenerate.mockImplementation(async () => {
      order.push("mint");
      return { token: "new-token" };
    });
    mockRevokeValue.mockImplementation(async () => {
      order.push("revoke");
    });

    await POST(request());

    // Revoking first disconnects a working device and leaves nothing in its
    // place if either later step fails.
    expect(order).toEqual(["settings", "mint", "revoke"]);
  });

  it("revokes the token the settings pointer held before it was wiped", async () => {
    await POST(request());

    // The settings write drops the deviceToken field, so the outgoing value
    // has to be captured up front or nothing can name it afterwards.
    expect(mockRevokeValue).toHaveBeenCalledWith("user123", "working-token");
    expect(mockRevokeAll).not.toHaveBeenCalled();
  });

  it("leaves the device connected when the settings write fails", async () => {
    mockSetUserSettings.mockRejectedValue(new Error("redis down"));

    await expect(POST(request())).rejects.toThrow("redis down");

    // Nothing was revoked, so the existing device still works.
    expect(mockRevokeValue).not.toHaveBeenCalled();
    expect(mockRevokeAll).not.toHaveBeenCalled();
  });

  it("leaves the device connected when minting fails", async () => {
    mockGenerate.mockRejectedValue(new Error("mint failed"));

    await expect(POST(request())).rejects.toThrow("mint failed");

    expect(mockRevokeValue).not.toHaveBeenCalled();
  });

  it("still succeeds when retiring the old credential fails", async () => {
    mockRevokeValue.mockRejectedValue(new Error("redis down"));

    const res = await POST(request());

    expect(res.status).toBe(200);
    await expect(res.json()).resolves.toMatchObject({ deviceToken: "new-token" });
  });

  it("does nothing to revoke when there was no prior token", async () => {
    mockGetUserSettings.mockResolvedValue({
      repo: "owner/old-repo",
      linkedAt: "2026-01-01T00:00:00Z",
    });

    await POST(request());

    expect(mockRevokeValue).not.toHaveBeenCalled();
  });
});
