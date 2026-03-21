"use server";

import { auth, signIn, signOut } from "@/lib/auth";
import { deleteUserSettings } from "@/lib/redis";
import { revokeDeviceToken } from "@/lib/deviceToken";
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
  await revokeDeviceToken(session.user.id);
  await deleteUserSettings(session.user.id);
  redirect("/");
}
