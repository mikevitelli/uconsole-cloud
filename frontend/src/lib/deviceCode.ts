import { randomUUID } from "crypto";
import { redis } from "./redis";

const CODE_TTL = 600; // 10 minutes

interface DeviceCodeData {
  secret: string;
  status: "pending" | "confirmed";
  createdAt: string;
}

interface DevicePollData {
  status: "pending" | "confirmed";
  code: string;
  deviceToken?: string;
  repo?: string;
}

function generateCodeString(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // no I/O/0/1
  let code = "";
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  for (let i = 0; i < 8; i++) {
    code += chars[bytes[i] % chars.length];
  }
  return code.slice(0, 4) + "-" + code.slice(4);
}

export async function generateDeviceCode(): Promise<{
  code: string;
  secret: string;
  expiresIn: number;
}> {
  const code = generateCodeString();
  const secret = randomUUID();

  const codeData: DeviceCodeData = {
    secret,
    status: "pending",
    createdAt: new Date().toISOString(),
  };

  const pollData: DevicePollData = {
    status: "pending",
    code,
  };

  await Promise.all([
    redis.set(`devicecode:${code}`, codeData, { ex: CODE_TTL }),
    redis.set(`devicepoll:${secret}`, pollData, { ex: CODE_TTL }),
  ]);

  return { code, secret, expiresIn: CODE_TTL };
}

/**
 * Atomically reserve a pending code for exactly one caller.
 *
 * Lets callers reject a bad code *before* minting a device token. Confirming
 * mints first and validates second, so every mistyped or expired code left a
 * live 90-day credential behind that never reached a device.
 *
 * The status read alone is not enough: confirmDeviceCode is a read-then-write,
 * so two simultaneous confirmations of the same code both observe "pending",
 * both pass, and both mint a token. Only the last one is referenced by user
 * settings — the other stays valid and unreachable. The SET NX below is the
 * actual gate; the read only supplies the accurate error message.
 *
 * Callers that do not go on to confirm must releaseDeviceCode(), or a
 * transient failure locks the code out for the rest of its TTL.
 */
export async function claimDeviceCode(
  code: string
): Promise<{ success: boolean; error?: string }> {
  const codeData = await redis.get<DeviceCodeData>(`devicecode:${code}`);
  if (!codeData) {
    return { success: false, error: "Code not found or expired" };
  }
  if (codeData.status !== "pending") {
    return { success: false, error: "Code already used" };
  }

  const claimed = await redis.set(`deviceclaim:${code}`, "1", {
    ex: CODE_TTL,
    nx: true,
  });
  if (claimed !== "OK") {
    return { success: false, error: "Code already used" };
  }

  return { success: true };
}

/** Release a claim so a legitimate retry can take it. */
export async function releaseDeviceCode(code: string): Promise<void> {
  await redis.del(`deviceclaim:${code}`);
}

export async function confirmDeviceCode(
  code: string,
  deviceToken: string,
  repo: string
): Promise<{ success: boolean; error?: string }> {
  const codeData = await redis.get<DeviceCodeData>(`devicecode:${code}`);
  if (!codeData) {
    return { success: false, error: "Code not found or expired" };
  }
  if (codeData.status !== "pending") {
    return { success: false, error: "Code already used" };
  }

  const pollData: DevicePollData = {
    status: "confirmed",
    code,
    deviceToken,
    repo,
  };

  await Promise.all([
    redis.set(`devicecode:${code}`, { ...codeData, status: "confirmed" }, { ex: CODE_TTL }),
    redis.set(`devicepoll:${codeData.secret}`, pollData, { ex: CODE_TTL }),
  ]);

  return { success: true };
}

export async function pollDeviceCode(
  secret: string
): Promise<DevicePollData | null> {
  const data = await redis.get<DevicePollData>(`devicepoll:${secret}`);
  if (!data) return null;

  // If confirmed, clean up both keys (single-use)
  if (data.status === "confirmed") {
    await Promise.all([
      redis.del(`devicepoll:${secret}`),
      redis.del(`devicecode:${data.code}`),
      redis.del(`deviceclaim:${data.code}`),
    ]);
  }

  return data;
}
