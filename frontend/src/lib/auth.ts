import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    GitHub({
      clientId: process.env.GITHUB_ID,
      clientSecret: process.env.GITHUB_SECRET,
      // GitHub returns an RFC 9207 `iss` parameter on the authorization
      // callback. Auth.js otherwise falls back to its "https://authjs.dev"
      // placeholder issuer, and oauth4webapi rejects the mismatch with
      // CallbackRouteError. GitHub ships explicit token/userinfo URLs, so
      // setting issuer here is only used for that comparison -- it does not
      // trigger OIDC discovery.
      issuer: "https://github.com",
      // "repo" scope required for private repo access (read commits, files, tree).
      // Cannot use narrower "public_repo" since backup repos may be private.
      authorization: { params: { scope: "repo read:user" } },
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        token.accessToken = account.access_token;
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string | undefined;
      if (token.sub) session.user.id = token.sub;
      return session;
    },
  },
});
