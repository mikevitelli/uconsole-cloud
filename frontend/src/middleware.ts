export { auth as middleware } from "@/lib/auth";

export const config = {
  matcher: [
    // Protect all API routes except auth callbacks, health check, device push,
    // device code generation, device poll, and script serving
    "/api/((?!auth|health|device/push|device/code$|device/poll|scripts).*)",
  ],
};
