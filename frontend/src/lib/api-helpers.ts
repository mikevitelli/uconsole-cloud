import { Session } from "next-auth";
import { auth } from "@/lib/auth";

/**
 * Calls auth() and returns the session only if the user is authenticated
 * (session.user.id exists). Returns null otherwise.
 */
export async function requireAuth(): Promise<Session | null> {
  const session = await auth();
  if (!session?.user?.id) return null;
  return session;
}

/**
 * Like requireAuth(), but also requires session.accessToken to be present.
 * Returns a session with accessToken narrowed to string (non-optional).
 */
export async function requireAuthWithToken(): Promise<
  (Session & { accessToken: string }) | null
> {
  const session = await auth();
  if (!session?.accessToken || !session?.user?.id) return null;
  return session as Session & { accessToken: string };
}
