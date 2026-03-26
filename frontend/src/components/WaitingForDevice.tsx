"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CopyCommand } from "@/components/CopyCommand";

export function WaitingForDevice() {
  const router = useRouter();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch("/api/device/status");
        if (res.ok) {
          const data = await res.json();
          if (data && data.collectedAt) {
            setConnected(true);
            clearInterval(interval);
            setTimeout(() => router.refresh(), 1500);
          }
        }
      } catch {
        // ignore fetch errors, keep polling
      }
    }, 10_000);

    return () => clearInterval(interval);
  }, [router]);

  if (connected) {
    return (
      <section className="bg-card border border-border rounded-xl p-4">
        <div className="flex items-center gap-2">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--green)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
          <h2 className="text-sm font-semibold text-bright">
            Device connected!
          </h2>
        </div>
      </section>
    );
  }

  return (
    <section className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <span
          className="w-2 h-2 rounded-full shrink-0 animate-pulse"
          style={{ background: "var(--yellow)" }}
        />
        <h2 className="text-sm font-semibold text-bright">
          Waiting for device
        </h2>
      </div>
      <p className="text-xs text-sub mb-3">
        Run these commands on your uConsole to start sending data:
      </p>
      <ol className="space-y-2 list-none">
        <li className="flex items-start gap-2">
          <span className="text-xs font-mono text-accent bg-accent/10 border border-accent/20 rounded px-1.5 py-0.5 shrink-0">1</span>
          <div className="flex-1">
            <CopyCommand command="curl -fsSL https://uconsole.cloud/install | bash" />
          </div>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-xs font-mono text-accent bg-accent/10 border border-accent/20 rounded px-1.5 py-0.5 shrink-0">2</span>
          <div className="flex-1">
            <CopyCommand command="uconsole setup" />
          </div>
        </li>
        <li className="flex items-start gap-2">
          <span className="text-xs font-mono text-accent bg-accent/10 border border-accent/20 rounded px-1.5 py-0.5 shrink-0">3</span>
          <p className="text-xs text-sub py-1">
            Enter the code at{" "}
            <a href="/link" className="text-accent hover:underline">
              uconsole.cloud/link
            </a>
          </p>
        </li>
      </ol>
      <p className="text-[11px] text-dim mt-3 animate-pulse">
        Checking for device data every 10 seconds...
      </p>
    </section>
  );
}
