"use server";

import { auth, signIn, signOut } from "@/lib/auth";
import { deleteUserSettings } from "@/lib/redis";
import { revokeDeviceToken, withDeviceTokenLock } from "@/lib/deviceToken";
import { redirect } from "next/navigation";

export async function signInAction() {
  await signIn("github");
}

export async function signOutAction() {
  await signOut({ redirectTo: "/" });
}

export async function unlinkAction() {
  const session = await auth();
  if (!session?.user?.id) {
    await signOut();
    return;
  }
  // Same lock the replacement flows take. Without it an unlink can delete a
  // token a relink has already indexed, and that relink's settings write then
  // lands afterwards, leaving the dashboard reading as linked against a
  // credential that no longer exists.
  //
  // redirect() throws a control-flow signal that Next catches, so it stays
  // outside the callback where it cannot be mistaken for a failure.
  await withDeviceTokenLock(session.user.id, async () => {
    await revokeDeviceToken(session.user.id);
    await deleteUserSettings(session.user.id);
  });
  redirect("/");
}
