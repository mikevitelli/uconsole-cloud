/** Pure color-mapping utilities for device status values. */

export function batteryColor(capacity: number): string {
  if (capacity > 50) return "var(--green)";
  if (capacity > 20) return "var(--yellow)";
  return "var(--red)";
}

export function tempColor(tempC: number): string {
  if (tempC < 60) return "var(--green)";
  if (tempC < 75) return "var(--yellow)";
  return "var(--red)";
}

export function stalenessColor(minutes: number): string {
  if (minutes < 10) return "var(--green)";
  if (minutes < 30) return "var(--yellow)";
  return "var(--red)";
}
