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

/**
 * Validate a string as a literal IPv4 or IPv6 address.
 *
 * The cloud dashboard interpolates the device-reported `wifi.ip` into
 * `https://${ip}` `href` attributes (LocalModeShell, DeviceOnline,
 * QuickActions). The value is push-supplied by the device — a
 * compromised device token could push `evil.com` (phishing) or a
 * fragment containing characters that escape the URL.
 *
 * Allowing only literal IP addresses keeps the same-network bridge
 * working while making the click target unspoofable.
 */
const IPV4_RE = /^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$/;
// Permissive IPv6: hex-and-colons only, between 2 and 39 chars. Browsers
// parse the canonical form; we only need to gate on character class so
// nothing weird leaks into the href.
const IPV6_RE = /^[0-9a-fA-F:]{2,39}$/;

export function isValidIp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  if (!value) return false;
  if (IPV4_RE.test(value)) return true;
  if (value.includes(":") && IPV6_RE.test(value)) return true;
  return false;
}

/**
 * Build an `https://<ip>` URL only when the value is a literal IP.
 * Returns null otherwise — caller should render text without a link.
 *
 * IPv6 hosts must be bracketed in URLs.
 */
export function buildLocalDashboardUrl(ip: unknown): string | null {
  if (!isValidIp(ip)) return null;
  const ipStr = ip as string;
  return ipStr.includes(":") ? `https://[${ipStr}]` : `https://${ipStr}`;
}
