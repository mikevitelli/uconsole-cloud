import { describe, it, expect } from "vitest";
import * as o from "oauth4webapi";
import GitHub from "next-auth/providers/github";
import fs from "fs";

// GitHub sends an RFC 9207 `iss` parameter on the OAuth callback. Auth.js
// compares it against `provider.issuer`, and @auth/core below 0.41.3 shipped
// the GitHub provider without one — so it fell back to the "https://authjs.dev"
// placeholder and every sign-in failed with:
//
//   CallbackRouteError: unexpected "iss" (issuer) response parameter value
//
// The value GitHub actually sends is "https://github.com/login/oauth", not
// "https://github.com". Overriding `issuer` with the wrong string fails exactly
// the same way, so these tests pin the effective value rather than the config.

const ISSUER = "https://github.com/login/oauth";
const client = { client_id: "test-client-id" };
const state = "test-state";

function callbackParams() {
  return new URLSearchParams({ code: "test-code", state, iss: ISSUER });
}

function as(issuer: string) {
  return {
    issuer,
    token_endpoint: "https://github.com/login/oauth/access_token",
    userinfo_endpoint: "https://api.github.com/user",
  };
}

describe("GitHub provider issuer", () => {
  it("resolves to the value GitHub actually sends", () => {
    const provider = GitHub({
      clientId: "id",
      clientSecret: "secret",
      authorization: { params: { scope: "repo read:user" } },
    });

    expect(provider.issuer).toBe(ISSUER);
  });

  it("is not overridden in the auth config", () => {
    // The provider default is correct and enterprise-aware; a hardcoded
    // override here silently wins over it and broke production once already.
    const source = fs.readFileSync("src/lib/auth.ts", "utf-8");
    expect(source).not.toMatch(/issuer:/);
  });

  it("accepts the iss parameter GitHub returns", () => {
    expect(() =>
      o.validateAuthResponse(as(ISSUER), client, callbackParams(), state)
    ).not.toThrow();
  });

  it("rejects it under the Auth.js placeholder issuer", () => {
    expect(() =>
      o.validateAuthResponse(
        as("https://authjs.dev"),
        client,
        callbackParams(),
        state
      )
    ).toThrow(/"iss" \(issuer\) response parameter value/);
  });

  it("rejects it under the bare github.com origin", () => {
    // The shape of the first attempted fix. Same failure, different expected
    // value — which is why the assertion above pins the exact string.
    expect(() =>
      o.validateAuthResponse(
        as("https://github.com"),
        client,
        callbackParams(),
        state
      )
    ).toThrow(/"iss" \(issuer\) response parameter value/);
  });
});
