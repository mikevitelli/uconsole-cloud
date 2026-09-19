import { describe, it, expect, vi, beforeEach } from "vitest";
import type { NextRequest } from "next/server";
import type { UserSettings } from "@/lib/types";

vi.mock("@/lib/api-helpers", () => ({
  requireAuth: vi.fn(),
}));
vi.mock("@/lib/redis", () => ({
  getUserSettings: vi.fn(),
  setUserSettings: vi.fn(),
}));
vi.mock("@/lib/deviceToken", () => ({
  generateDeviceToken: vi.fn(),
  revokeDeviceTokenValue: vi.fn(),
}));
vi.mock("@/lib/deviceCode", () => ({
  claimDeviceCode: vi.fn(),
  confirmDeviceCode: vi.fn(),
  releaseDeviceCode: vi.fn(),
}));

import { POST } from "@/app/api/device/code/confirm/route";
import { requireAuth } from "@/lib/api-helpers";
import { getUserSettings, setUserSettings } from "@/lib/redis";
import { generateDeviceToken, revokeDeviceTokenValue } from "@/lib/deviceToken";
import {
  claimDeviceCode,
  confirmDeviceCode,
  releaseDeviceCode,
} from "@/lib/deviceCode";

const mockRequireAuth = requireAuth as ReturnType<typeof vi.fn>;
const mockGetUserSettings = getUserSettings as ReturnType<typeof vi.fn>;
const mockSetUserSettings = setUserSettings as ReturnType<typeof vi.fn>;
const mockGenerateDeviceToken = generateDeviceToken as ReturnType<typeof vi.fn>;
const mockRevokeTokenValue = revokeDeviceTokenValue as ReturnType<typeof vi.fn>;
const mockClaimDeviceCode = claimDeviceCode as ReturnType<typeof vi.fn>;
const mockConfirmDeviceCode = confirmDeviceCode as ReturnType<typeof vi.fn>;
const mockReleaseDeviceCode = releaseDeviceCode as ReturnType<typeof vi.fn>;

const CODE = "ABCD-2345";

function request(code: string = CODE) {
  return { json: async () => ({ code }) } as unknown as NextRequest;
}

const BASE: UserSettings = {
  repo: "owner/repo",
  linkedAt: "2026-01-01T00:00:00Z",
  deviceToken: "prior-token",
};

beforeEach(() => {
  vi.clearAllMocks();
  mockRequireAuth.mockResolvedValue({ user: { id: "user123" } });
  mockGetUserSettings.mockResolvedValue({ ...BASE });
  mockGenerateDeviceToken.mockResolvedValue({ token: "new-token", replaced: "prior-token" });
  mockClaimDeviceCode.mockResolvedValue({ success: true });
  mockConfirmDeviceCode.mockResolvedValue({ success: true });
});

describe("POST /api/device/code/confirm", () => {
  it("mints nothing when the code cannot be claimed", async () => {
    mockClaimDeviceCode.mockResolvedValue({
      success: false,
      error: "Code not found or expired",
    });

    const res = await POST(request());

    expect(res.status).toBe(400);
    expect(mockGenerateDeviceToken).not.toHaveBeenCalled();
  });

  it("claims the code before minting a token", async () => {
    const order: string[] = [];
    mockClaimDeviceCode.mockImplementation(async () => {
      order.push("claim");
      return { success: true };
    });
    mockGenerateDeviceToken.mockImplementation(async () => {
      order.push("mint");
      return { token: "new-token", replaced: "prior-token" };
    });

    await POST(request());

    expect(order).toEqual(["claim", "mint"]);
  });

  it("revokes the superseded token once the replacement commits", async () => {
    const res = await POST(request());

    expect(res.status).toBe(200);
    expect(mockRevokeTokenValue).toHaveBeenCalledTimes(1);
    expect(mockRevokeTokenValue).toHaveBeenCalledWith("user123", "prior-token");
    expect(mockRevokeTokenValue).not.toHaveBeenCalledWith("user123", "new-token");
  });

  it("rolls the token back and restores the pointer when confirm fails", async () => {
    mockConfirmDeviceCode.mockResolvedValue({
      success: false,
      error: "Code not found or expired",
    });
    // Nothing else moved: settings still point at this request's token.
    mockGetUserSettings
      .mockResolvedValueOnce({ ...BASE })
      .mockResolvedValueOnce({ ...BASE, deviceToken: "new-token" });

    const res = await POST(request());

    expect(res.status).toBe(400);
    expect(mockRevokeTokenValue).toHaveBeenCalledWith("user123", "new-token");
    expect(mockSetUserSettings).toHaveBeenCalledWith("user123", {
      ...BASE,
      deviceToken: "prior-token",
    });
    expect(mockReleaseDeviceCode).toHaveBeenCalledWith(CODE);
  });

  it("does not clobber settings a concurrent request committed", async () => {
    // A concurrent re-link lands while confirmation is in flight: it changed
    // the repo and installed its own live token. Blindly writing back the
    // opening snapshot would restore the old repo and orphan that token.
    mockConfirmDeviceCode.mockResolvedValue({
      success: false,
      error: "Code not found or expired",
    });
    const concurrent: UserSettings = {
      repo: "owner/other-repo",
      linkedAt: "2026-02-02T00:00:00Z",
      deviceToken: "concurrent-token",
    };
    mockGetUserSettings
      .mockResolvedValueOnce({ ...BASE })
      .mockResolvedValueOnce({ ...concurrent });

    const res = await POST(request());

    expect(res.status).toBe(400);
    // This request's own token is still rolled back...
    expect(mockRevokeTokenValue).toHaveBeenCalledWith("user123", "new-token");
    // ...but the concurrent request's settings and live token survive.
    expect(mockSetUserSettings).not.toHaveBeenCalled();
    expect(mockRevokeTokenValue).not.toHaveBeenCalledWith("user123", "concurrent-token");
  });

  it("revokes the token the pointer actually held, not an earlier snapshot", async () => {
    // A concurrent link superseded the opening snapshot's token before this
    // request swapped the pointer. Revoking "prior-token" would leave the
    // token this request really displaced live and unreferenced.
    mockGenerateDeviceToken.mockResolvedValue({
      token: "new-token",
      replaced: "actually-displaced",
    });

    await POST(request());

    expect(mockRevokeTokenValue).toHaveBeenCalledWith(
      "user123",
      "actually-displaced"
    );
    expect(mockRevokeTokenValue).not.toHaveBeenCalledWith(
      "user123",
      "prior-token"
    );
  });

  it("cleans up when confirmation throws", async () => {
    // A failed Redis write mid-flight must not leave the token live, the
    // pointer moved, and the code claimed until its TTL expires.
    mockConfirmDeviceCode.mockRejectedValue(new Error("redis unavailable"));
    mockGetUserSettings
      .mockResolvedValueOnce({ ...BASE })
      .mockResolvedValueOnce({ ...BASE, deviceToken: "new-token" });

    await expect(POST(request())).rejects.toThrow("redis unavailable");

    expect(mockRevokeTokenValue).toHaveBeenCalledWith("user123", "new-token");
    expect(mockSetUserSettings).toHaveBeenCalledWith("user123", {
      ...BASE,
      deviceToken: "prior-token",
    });
    expect(mockReleaseDeviceCode).toHaveBeenCalledWith(CODE);
  });

  it("releases the claim when minting itself throws", async () => {
    mockGenerateDeviceToken.mockRejectedValue(new Error("mint failed"));

    await expect(POST(request())).rejects.toThrow("mint failed");

    expect(mockReleaseDeviceCode).toHaveBeenCalledWith(CODE);
    expect(mockRevokeTokenValue).not.toHaveBeenCalled();
  });
});
