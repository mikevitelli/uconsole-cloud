import { describe, it, expect } from "vitest";
import * as o from "oauth4webapi";
import fs from "fs";

// GitHub sends an RFC 9207 `iss` parameter on the OAuth callback. Auth.js only
// compares it against `provider.issuer`, falling back to its "https://authjs.dev"
// placeholder when none is configured -- which made every sign-in fail with
// CallbackRouteError: unexpected "iss" (issuer) response parameter value.

const client = { client_id: "test-client-id" };
const state = "test-state";

function callbackParams() {
  return new URLSearchParams({
    code: "test-code",
    state,
    iss: "https://github.com",
  });
}

describe("GitHub provider issuer", () => {
  it("is pinned to https://github.com in the auth config", () => {
    const source = fs.readFileSync("src/lib/auth.ts", "utf-8");
    expect(source).toMatch(/issuer:\s*"https:\/\/github\.com"/);
  });

  it("accepts the iss parameter GitHub returns", () => {
    const as = {
      issuer: "https://github.com",
      token_endpoint: "https://github.com/login/oauth/access_token",
      userinfo_endpoint: "https://api.github.com/user",
    };

    expect(() =>
      o.validateAuthResponse(as, client, callbackParams(), state)
    ).not.toThrow();
  });

  it("rejects it under the Auth.js placeholder issuer", () => {
    const as = {
      issuer: "https://authjs.dev",
      token_endpoint: "https://github.com/login/oauth/access_token",
      userinfo_endpoint: "https://api.github.com/user",
    };

    expect(() =>
      o.validateAuthResponse(as, client, callbackParams(), state)
    ).toThrow(/"iss" \(issuer\) response parameter value/);
  });
});
