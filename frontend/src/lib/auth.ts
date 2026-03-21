import NextAuth from "next-auth";
import GitHub from "next-auth/providers/github";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    GitHub({
      clientId: process.env.GITHUB_ID,
      clientSecret: process.env.GITHUB_SECRET,
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
