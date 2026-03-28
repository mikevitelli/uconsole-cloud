import { DeviceOffline } from "@/components/dashboard/DeviceOffline";
import { DeviceOnline } from "@/components/dashboard/DeviceOnline";
import type {
  DeviceStatusPayload,
  WifiFallbackStatus,
} from "@/lib/deviceStatus";

interface DeviceStatusContent {
  heading?: string;
  offlineMessage?: string;
}

interface DeviceStatusProps {
  status: DeviceStatusPayload | null;
  ageMinutes: number;
  lastKnownFallback?: WifiFallbackStatus | null;
  content?: DeviceStatusContent;
  /** When true, the same-network banner is already showing the webdash link */
  isSameNetwork?: boolean;
  deviceLocalIp?: string | null;
}

export function DeviceStatus({
  status,
  ageMinutes,
  lastKnownFallback,
  content,
  isSameNetwork = false,
}: DeviceStatusProps) {
  const heading = content?.heading ?? "Device Status";

  if (!status) {
    return (
      <DeviceOffline
        heading={heading}
        offlineMessage={content?.offlineMessage}
        lastKnownFallback={lastKnownFallback}
      />
    );
  }

  return (
    <DeviceOnline
      status={status}
      ageMinutes={ageMinutes}
      heading={heading}
      isSameNetwork={isSameNetwork}
    />
  );
}
