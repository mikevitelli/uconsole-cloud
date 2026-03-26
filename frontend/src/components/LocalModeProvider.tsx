"use client";

import { createContext, useContext } from "react";
import { useLocalDevice, type LocalDeviceState } from "@/hooks/useLocalDevice";

const LocalModeContext = createContext<LocalDeviceState>({
  isLocal: false,
  stats: null,
  baseUrl: null,
  probing: true,
});

export function useLocalMode() {
  return useContext(LocalModeContext);
}

interface LocalModeProviderProps {
  deviceIp: string | null;
  children: React.ReactNode;
}

export function LocalModeProvider({ deviceIp, children }: LocalModeProviderProps) {
  const state = useLocalDevice(deviceIp);

  return (
    <LocalModeContext value={state}>
      {children}
    </LocalModeContext>
  );
}
