/**
 * Same-network detection via public IP comparison.
 *
 * When the device pushes status, the server stores the request's
 * source IP (the device's public/NAT IP). When a user loads the
 * dashboard, we compare their public IP (from x-forwarded-for)
 * with the device's stored public IP. A match means both are
 * behind the same router/NAT — i.e., same network.
 */
export function checkSameNetwork(
  userPublicIp: string | null,
  devicePublicIp: string | null
): boolean {
  if (!userPublicIp || !devicePublicIp) return false;
  return userPublicIp === devicePublicIp;
}
