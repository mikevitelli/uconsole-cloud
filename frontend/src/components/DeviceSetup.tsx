"use client";

import { useState } from "react";

interface DeviceSetupProps {
  deviceToken: string;
  repo: string;
  apiUrl: string;
}

export function DeviceSetup({ deviceToken, repo, apiUrl }: DeviceSetupProps) {
  const [showToken, setShowToken] = useState(false);
  const [copied, setCopied] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [token, setToken] = useState(deviceToken);

  const setupCommand = `mkdir -p ~/.config/uconsole
cat > ~/.config/uconsole/status.env << 'EOF'
DEVICE_API_URL="${apiUrl}/api/device/push"
DEVICE_TOKEN="${token}"
DEVICE_REPO="${repo}"
EOF`;

  async function copySetup() {
    await navigator.clipboard.writeText(setupCommand);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function regenerate() {
    if (!confirm("Regenerate device token? Your device will need to be reconfigured.")) return;
    setRegenerating(true);
    try {
      const res = await fetch("/api/settings/regenerate-token", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setToken(data.deviceToken);
      }
    } finally {
      setRegenerating(false);
    }
  }

  const masked = token.slice(0, 8) + "••••••••••••••••••••••••" + token.slice(-4);

  return (
    <details className="bg-card border border-border rounded-xl p-4">
      <summary className="text-sm font-semibold text-bright cursor-pointer flex items-center gap-2">
        <span>📡</span> Device Setup
      </summary>
      <div className="mt-3 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-sub">Token:</span>
          <code className="text-xs font-mono bg-background border border-border rounded px-2 py-1 flex-1 overflow-hidden">
            {showToken ? token : masked}
          </code>
          <button
            onClick={() => setShowToken(!showToken)}
            className="text-xs text-sub hover:text-foreground cursor-pointer"
          >
            {showToken ? "Hide" : "Show"}
          </button>
          <button
            onClick={regenerate}
            disabled={regenerating}
            className="text-xs text-sub hover:text-foreground cursor-pointer disabled:opacity-50"
          >
            {regenerating ? "..." : "Regenerate"}
          </button>
        </div>

        <div className="relative">
          <pre className="text-xs font-mono bg-background border border-border rounded p-3 overflow-x-auto whitespace-pre text-sub">
            {setupCommand}
          </pre>
          <button
            onClick={copySetup}
            className="absolute top-2 right-2 text-xs bg-card border border-border rounded px-2 py-1 text-sub hover:text-foreground cursor-pointer"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>

        <p className="text-xs text-dim">
          Paste this on your uConsole, then run{" "}
          <code className="bg-background px-1 rounded">bash ~/scripts/push-status.sh</code>{" "}
          to test.
        </p>
      </div>
    </details>
  );
}
