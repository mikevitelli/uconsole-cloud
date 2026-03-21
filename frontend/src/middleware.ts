export { auth as middleware } from "@/lib/auth";

export const config = {
  matcher: [
    // Protect all API routes except auth callbacks, health check, and device push
    "/api/((?!auth|health|device/push).*)",
  ],
};
