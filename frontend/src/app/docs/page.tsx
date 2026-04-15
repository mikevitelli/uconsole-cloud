import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Documentation — uConsole Cloud",
  description:
    "Installation guide, CLI reference, and architecture docs for uconsole-cloud.",
};

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <h2 className="text-xl font-bold text-bright mb-3 flex items-center gap-2">
        <a href={`#${id}`} className="text-dim hover:text-accent">
          #
        </a>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <pre className="bg-card border border-border rounded-lg p-4 text-sm font-mono text-foreground overflow-x-auto">
      {children}
    </pre>
  );
}

function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="bg-card border border-border rounded px-1.5 py-0.5 text-xs font-mono text-accent">
      {children}
    </code>
  );
}

export default function DocsPage() {
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md px-4 py-3">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <Link
            href="/"
            className="text-sm font-bold text-bright hover:text-accent transition-colors no-underline"
          >
            uConsole Cloud
          </Link>
          <span className="text-xs text-sub font-mono">docs</span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 sm:px-6 py-10 space-y-12">
        {/* Title */}
        <div>
          <h1 className="text-3xl font-bold text-bright mb-2">
            Documentation
          </h1>
          <p className="text-sub">
            Everything you need to install, configure, and manage the uConsole
            with uconsole-cloud.
          </p>
        </div>

        {/* Table of contents */}
        <nav className="bg-card border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-bright mb-2">
            On this page
          </h2>
          <ul className="space-y-1 text-sm">
            {[
              ["install", "Installation"],
              ["setup", "Setup Wizard"],
              ["cli", "CLI Reference"],
              ["architecture", "Architecture"],
              ["telemetry", "Telemetry"],
              ["webdash", "Local Web Dashboard"],
              ["cloud", "Cloud Dashboard"],
              ["scripts", "Scripts"],
              ["tui", "TUI Modules"],
              ["webdash-api", "Webdash API"],
              ["services", "Services"],
              ["security", "Security"],
              ["troubleshooting", "Troubleshooting"],
              ["contributing", "Contributing"],
            ].map(([id, label]) => (
              <li key={id}>
                <a
                  href={`#${id}`}
                  className="text-sub hover:text-accent transition-colors"
                >
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        {/* Install */}
        <Section id="install" title="Installation">
          <p className="text-sub mb-3">
            On your uConsole (arm64 Debian Bookworm):
          </p>
          <Code>curl -s https://uconsole.cloud/install | sudo bash</Code>
          <p className="text-sub mt-3 mb-3">
            This adds the GPG-signed APT repository and installs the{" "}
            <InlineCode>uconsole-cloud</InlineCode> package. Then run the setup
            wizard:
          </p>
          <Code>uconsole setup</Code>
          <p className="text-sub mt-3">
            Future updates arrive automatically via{" "}
            <InlineCode>sudo apt upgrade</InlineCode>.
          </p>
          <div className="mt-4 bg-card border border-border rounded-lg p-4 text-sm">
            <p className="text-bright font-medium mb-1">What gets installed</p>
            <ul className="text-sub space-y-1 list-disc list-inside">
              <li>
                <InlineCode>uconsole</InlineCode> CLI at{" "}
                <InlineCode>/usr/bin/uconsole</InlineCode>
              </li>
              <li>
                46 management scripts in{" "}
                <InlineCode>/opt/uconsole/scripts/</InlineCode>
              </li>
              <li>
                Curses TUI at <InlineCode>/usr/bin/console</InlineCode>
              </li>
              <li>
                Flask web dashboard at{" "}
                <InlineCode>/opt/uconsole/webdash/</InlineCode>
              </li>
              <li>
                Systemd services and timers (enabled by setup wizard)
              </li>
              <li>
                Nginx HTTPS reverse proxy config for{" "}
                <InlineCode>uconsole.local</InlineCode>
              </li>
              <li>Avahi mDNS advertisement</li>
            </ul>
          </div>
        </Section>

        {/* Setup */}
        <Section id="setup" title="Setup Wizard">
          <p className="text-sub mb-3">
            <InlineCode>uconsole setup</InlineCode> walks through 9 steps:
          </p>
          <div className="space-y-2">
            {[
              [
                "Hardware Detection",
                "Scans for AIO expansion board (SDR, LoRa, GPS, RTC), WiFi method, compute module",
              ],
              [
                "System Configuration",
                "CPU frequency cap, low battery shutdown voltage",
              ],
              [
                "Webdash Password",
                "Sets a bcrypt-hashed password for the local web dashboard",
              ],
              [
                "Hotspot Configuration",
                "WiFi fallback AP SSID (default: uConsole)",
              ],
              [
                "Cloud Link",
                "Optional — generates a device code to link with uconsole.cloud",
              ],
              [
                "Backup Configuration",
                "Schedule for automated backups (daily/weekly/manual)",
              ],
              [
                "Enable Services",
                "Starts webdash, status timer, backup timer, update timer",
              ],
              [
                "SSL Certificate",
                "Generates a self-signed cert with SANs for uconsole.local",
              ],
              [
                "Summary",
                "Shows what was configured and how to access everything",
              ],
            ].map(([step, desc], i) => (
              <div
                key={i}
                className="flex gap-3 bg-card border border-border rounded-lg px-3 py-2 text-sm"
              >
                <span className="text-accent font-mono font-bold shrink-0 w-5 text-right">
                  {i + 1}
                </span>
                <div>
                  <span className="text-bright font-medium">{step}</span>
                  <span className="text-dim"> — </span>
                  <span className="text-sub">{desc}</span>
                </div>
              </div>
            ))}
          </div>
          <p className="text-sub mt-3 text-sm">
            The wizard is re-runnable. Existing config values are preserved —
            just hit Enter to keep them.
          </p>
        </Section>

        {/* CLI */}
        <Section id="cli" title="CLI Reference">
          <div className="space-y-2">
            {[
              [
                "uconsole setup",
                "Run the interactive setup wizard (hardware detect, passwords, services, cloud link)",
              ],
              [
                "uconsole link",
                "Link device to uconsole.cloud via code auth (cloud-only, no wizard)",
              ],
              ["uconsole push", "Push device status to the cloud now"],
              [
                "uconsole status",
                "Show current config, timer status, last push time",
              ],
              [
                "uconsole doctor",
                "Diagnose services, SSL, nginx, connectivity — reports pass/fail",
              ],
              [
                "uconsole restore",
                "Run restore.sh from your backup repo to rebuild the device",
              ],
              [
                "uconsole unlink",
                "Remove cloud config (keeps services installed)",
              ],
              [
                "uconsole update",
                "Update via APT (package mode) or re-download scripts (standalone)",
              ],
              ["uconsole version", "Show installed version"],
              ["uconsole help", "Show all commands"],
            ].map(([cmd, desc]) => (
              <div
                key={cmd}
                className="flex gap-3 bg-card border border-border rounded-lg px-3 py-2 text-sm"
              >
                <code className="text-accent font-mono shrink-0 min-w-[170px]">
                  {cmd}
                </code>
                <span className="text-sub">{desc}</span>
              </div>
            ))}
          </div>
        </Section>

        {/* Architecture */}
        <Section id="architecture" title="Architecture">
          <Code>{`uConsole (arm64, Debian)              Cloud (Vercel)
┌─────────────────────────┐       ┌─────────────────────────┐
│                         │       │                         │
│  /opt/uconsole/         │       │  uconsole.cloud         │
│  ├── bin/               │       │                         │
│  │   ├── uconsole  CLI  │       │  Upstash Redis          │
│  │   └── console   TUI  │       │  (device telemetry)     │
│  ├── scripts/           │       │         │               │
│  │   └── system/        │       │         ▼               │
│  │       └── push ──────────→   │  Next.js 16 SSR         │
│  ├── webdash/      POST │       │  (Server Components)    │
│  │   └── app.py ◄─┐    │       │         │               │
│  └── lib/          │    │       │         ▼               │
│               nginx │    │       │    Dashboard            │
│               :443  │    │       │                         │
│                     │    │       │  /apt/ (package repo)   │
└─────────────────────┘    │       └─────────────────────────┘
                           │
Phone / Browser            │
┌─────────────────┐        │
│ uconsole.cloud  │ ◄──────── Vercel CDN
│ uconsole.local  │ ◄──┘
└─────────────────┘`}</Code>
          <div className="mt-4 space-y-2 text-sm text-sub">
            <p>
              <span className="text-bright font-medium">Device → Redis → Dashboard.</span>{" "}
              The device pushes telemetry every 5 minutes. The cloud dashboard
              reads it on page load. No browser polling. Data persists
              indefinitely.
            </p>
            <p>
              <span className="text-bright font-medium">Cloud is optional.</span>{" "}
              Everything works offline — the local webdash, TUI, and all
              management scripts run without internet.
            </p>
          </div>
        </Section>

        {/* Telemetry */}
        <Section id="telemetry" title="Telemetry">
          <p className="text-sub mb-3">
            <InlineCode>push-status.sh</InlineCode> collects from sysfs and
            procfs every 5 minutes:
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-bright font-medium py-2 pr-4">
                    Category
                  </th>
                  <th className="text-left text-bright font-medium py-2 pr-4">
                    Metrics
                  </th>
                </tr>
              </thead>
              <tbody className="text-sub">
                {[
                  ["Battery", "capacity, voltage, current, status, health"],
                  ["CPU", "temperature, load average, core count"],
                  ["Memory", "total, used, available"],
                  ["Disk", "total, used, available, percent"],
                  ["WiFi", "SSID, signal dBm, quality, bitrate, IP"],
                  ["Screen", "brightness, max brightness"],
                  ["AIO Board", "SDR, LoRa, GPS fix, RTC sync"],
                  ["Hardware", "expansion module, component detection"],
                  ["Webdash", "running, port"],
                  ["System", "hostname, kernel, uptime"],
                ].map(([cat, metrics]) => (
                  <tr key={cat} className="border-b border-border/50">
                    <td className="py-2 pr-4 font-mono text-accent text-xs">
                      {cat}
                    </td>
                    <td className="py-2">{metrics}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        {/* Webdash */}
        <Section id="webdash" title="Local Web Dashboard">
          <p className="text-sub mb-3">
            The Flask web dashboard runs at{" "}
            <InlineCode>https://uconsole.local</InlineCode> (mDNS) or your
            device&apos;s IP. It provides:
          </p>
          <ul className="text-sub space-y-1 list-disc list-inside text-sm mb-3">
            <li>Live system stats via SSE (Server-Sent Events)</li>
            <li>Browser-based terminal (xterm.js + PTY)</li>
            <li>Script execution dashboard (60+ scripts)</li>
            <li>System management panels</li>
            <li>PWA — installable on phone</li>
          </ul>
          <p className="text-sub text-sm">
            HTTPS uses a self-signed certificate with SANs. On first visit, accept
            the certificate warning or install the cert as a trusted profile on
            your phone/laptop.
          </p>
          <div className="mt-3 bg-card border border-border rounded-lg p-4 text-sm">
            <p className="text-bright font-medium mb-1">WiFi Fallback AP</p>
            <p className="text-sub">
              When no known WiFi network is available, the device creates a
              fallback access point (default SSID: &quot;uConsole&quot;). Connect your
              phone to this AP to access the webdash at{" "}
              <InlineCode>https://10.42.0.1</InlineCode> — no internet required.
            </p>
          </div>
        </Section>

        {/* Cloud */}
        <Section id="cloud" title="Cloud Dashboard">
          <p className="text-sub mb-3">
            <a href="https://uconsole.cloud">uconsole.cloud</a> shows your
            device status from anywhere. Sign in with GitHub, link your device
            with a code, and get:
          </p>
          <ul className="text-sub space-y-1 list-disc list-inside text-sm mb-3">
            <li>Live device telemetry (battery, CPU, memory, WiFi, AIO board)</li>
            <li>Persistent status — survives reboots, shows staleness</li>
            <li>Backup coverage across 9 categories with sparklines</li>
            <li>Package inventory, browser extensions, scripts</li>
            <li>Hardware manifest (expansion module detection)</li>
            <li>Same-network detection — direct link to local webdash</li>
          </ul>
          <div className="bg-card border border-border rounded-lg p-4 text-sm">
            <p className="text-bright font-medium mb-1">Device Code Auth</p>
            <p className="text-sub">
              Run <InlineCode>uconsole link</InlineCode> on the device. It shows
              an 8-character code and QR code. Enter the code at{" "}
              <a href="/link">uconsole.cloud/link</a> to connect. No passwords
              to type on a tiny keyboard.
            </p>
          </div>
        </Section>

        {/* Scripts */}
        <Section id="scripts" title="Scripts">
          <p className="text-sub mb-3 text-sm">
            46 management scripts organized in 5 categories under{" "}
            <InlineCode>/opt/uconsole/scripts/</InlineCode>.
          </p>
          <div className="space-y-4">
            {[
              {
                name: "network/",
                count: 5,
                scripts: "hotspot.sh, network.sh, wifi-fallback.sh, wifi.sh, lib.sh",
              },
              {
                name: "power/",
                count: 11,
                scripts:
                  "battery.sh, battery-test.sh, cellhealth.sh, charge.sh, cpu-freq-cap.sh, fix-battery-boot.sh, fix-voltage-cutoff.sh, low-battery-shutdown.sh, pmu-voltage-min.sh, power.sh, lib.sh",
              },
              {
                name: "radio/",
                count: 8,
                scripts:
                  "aio-check.sh, esp32.sh, esp32-marauder.sh, gps.sh, lora.sh, lora_helper.py, sdr.sh, lib.sh",
              },
              {
                name: "system/",
                count: 5,
                scripts: "backup.sh, push-status.sh, restore.sh, update.sh, lib.sh",
              },
              {
                name: "util/",
                count: 18,
                scripts:
                  "audit.sh, boot-check.sh, config.py, config.sh, console.sh, crash-log.sh, dashboard.sh, discharge-test.sh, diskusage.sh, hardware-detect.sh, integration-test.sh, smoke-test.sh, storage.sh, trackball-scroll.py, webdash-ctl.sh, webdash-info.sh, webdash.sh, lib.sh",
              },
            ].map(({ name, count, scripts }) => (
              <div
                key={name}
                className="bg-card border border-border rounded-lg px-3 py-2 text-sm"
              >
                <div className="flex items-center gap-2 mb-1">
                  <code className="text-accent font-mono">{name}</code>
                  <span className="text-dim text-xs">({count} files)</span>
                </div>
                <p className="text-sub text-xs">{scripts}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* TUI */}
        <Section id="tui" title="TUI Modules">
          <p className="text-sub mb-3 text-sm">
            Curses-based terminal interface launched via{" "}
            <InlineCode>console</InlineCode>. 9 category tabs, 53 native
            tools. Supports keyboard (arrows, vim keys) and gamepad input.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {[
              ["framework", "Main loop, menus, rendering"],
              ["monitor", "Real-time CPU, RAM, temp gauges"],
              ["network", "WiFi switcher, hotspot, fallback"],
              ["radio", "GPS globe, FM radio"],
              ["adsb", "Global ADS-B map, layers, hi-res fetch"],
              ["marauder", "ESP32 Marauder WiFi/BLE toolkit"],
              ["telegram", "Terminal Telegram client (tg + tdlib)"],
              ["services", "Timer config, push interval"],
              ["tools", "Git panel, notes, calculator, stopwatch"],
              ["games", "Watch Dogs Go, minesweeper, snake, tetris, 2048, ROMs"],
              ["watchdogs", "Watch Dogs Go launcher with auto-install"],
              ["launcher", "Shared detached-spawn helper"],
              ["files", "File browser"],
              ["config_ui", "Theme picker, view mode"],
              ["workspace-monitor", "Labwc workspace detection"],
            ].map(([mod, desc]) => (
              <div
                key={mod}
                className="bg-card border border-border rounded-lg px-3 py-2 text-sm"
              >
                <code className="text-accent font-mono text-xs">{mod}</code>
                <p className="text-sub text-xs mt-0.5">{desc}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* Webdash API */}
        <Section id="webdash-api" title="Webdash API">
          <p className="text-sub mb-3 text-sm">
            46 routes served by the Flask webdash at{" "}
            <InlineCode>https://uconsole.local</InlineCode>.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-bright font-medium py-2 pr-4">
                    Category
                  </th>
                  <th className="text-left text-bright font-medium py-2">
                    Endpoints
                  </th>
                </tr>
              </thead>
              <tbody className="text-sub">
                {[
                  ["Auth", "/login, /setup-password, /api/set-password, /logout"],
                  ["Dashboard", "/, /api/logo, /api/stats, /api/public/stats"],
                  [
                    "Config",
                    "/api/config, /api/config/brightness, /api/config/git-remote, /api/config/timezone",
                  ],
                  ["Timers", "/api/timers, /api/timer-schedule/<name>"],
                  [
                    "Monitoring",
                    "/api/processes, /api/logs/<source>, /api/connections, /api/services",
                  ],
                  ["Wiki", "/api/wiki (GET/POST/DELETE)"],
                  ["WiFi", "/api/wifi/scan, /api/wifi/connect, /api/wifi/disconnect"],
                  [
                    "Scripts",
                    "/api/run/<script> (POST), /api/stream/<script> (SSE)",
                  ],
                  [
                    "Battery",
                    "/api/battery-test/chart, /api/battery-test/start",
                  ],
                  [
                    "Hardware",
                    "/api/esp32, /api/gps, /api/sdr, /api/lora (GET + push POST)",
                  ],
                  [
                    "Terminal",
                    "SocketIO: pty-spawn, pty-input, pty-resize, pty-output, pty-exit",
                  ],
                  [
                    "Static",
                    "/favicon.png, /uconsole.crt, /manifest.json, /sw.js",
                  ],
                ].map(([cat, endpoints]) => (
                  <tr key={cat} className="border-b border-border/50">
                    <td className="py-2 pr-4 font-mono text-accent text-xs">
                      {cat}
                    </td>
                    <td className="py-2 text-xs">{endpoints}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        {/* Services */}
        <Section id="services" title="Services">
          <p className="text-sub mb-3 text-sm">
            4 systemd services and 3 timers, managed by the setup wizard.
          </p>
          <div className="space-y-2">
            {[
              [
                "uconsole-webdash.service",
                "Flask dashboard on :8080, Restart=always",
              ],
              [
                "uconsole-status.service + timer",
                "Push telemetry every 5 minutes",
              ],
              [
                "uconsole-backup.service + timer",
                "Daily backup at 3:00 AM",
              ],
              [
                "uconsole-update.service + timer",
                "Weekly update check, Sunday 4:00 AM",
              ],
              [
                "nginx",
                "HTTPS reverse proxy on :443, self-signed cert, CORS for uconsole.cloud",
              ],
            ].map(([svc, desc]) => (
              <div
                key={svc}
                className="flex gap-3 bg-card border border-border rounded-lg px-3 py-2 text-sm"
              >
                <code className="text-accent font-mono shrink-0 text-xs">
                  {svc}
                </code>
                <span className="text-sub text-xs">{desc}</span>
              </div>
            ))}
          </div>
        </Section>

        {/* Security */}
        <Section id="security" title="Security">
          <div className="space-y-2 text-sm">
            {[
              [
                "Authentication",
                "NextAuth v5 + GitHub OAuth on the cloud side. bcrypt-hashed passwords on the local webdash.",
              ],
              [
                "Device tokens",
                "90-day UUID v4 tokens stored at /etc/uconsole/status.env (chmod 600, owned by device user).",
              ],
              [
                "Sessions",
                "Cryptographically random session tokens (secrets.token_hex), server-side session store with 30-day TTL.",
              ],
              [
                "Local TLS",
                "Self-signed cert with SANs (DNS:uconsole.local, DNS:uconsole, IP:127.0.0.1). Key readable by nginx (640 root:www-data).",
              ],
              [
                "Rate limiting",
                "Device code generation limited to 5 requests per minute per IP.",
              ],
              [
                "Input validation",
                "Path traversal blocks, SHA regex, strict repo format validation on all API routes.",
              ],
              [
                "Headers",
                "CSP, X-Frame-Options DENY, nosniff, strict Referrer-Policy, restrictive Permissions-Policy.",
              ],
              [
                "Process safety",
                "PID range guard (2-4194304) in TUI process manager. AST-based calculator prevents code injection.",
              ],
              [
                "Network isolation",
                "Webdash binds 127.0.0.1 only (nginx proxies). CORS whitelist: uconsole.local, uconsole.cloud. PTY auth gate on terminal sessions.",
              ],
              [
                "Systemd hardening",
                "PrivateTmp, ProtectSystem=strict, NoNewPrivileges on all service units.",
              ],
            ].map(([title, desc]) => (
              <div
                key={title}
                className="bg-card border border-border rounded-lg px-3 py-2"
              >
                <span className="text-bright font-medium">{title}:</span>{" "}
                <span className="text-sub">{desc}</span>
              </div>
            ))}
          </div>
        </Section>

        {/* Troubleshooting */}
        <Section id="troubleshooting" title="Troubleshooting">
          <div className="space-y-4">
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                Run the doctor
              </p>
              <Code>uconsole doctor</Code>
              <p className="text-sub text-sm mt-2">
                Reports pass/fail for config, services, nginx, SSL, connectivity.
                Fix what it flags.
              </p>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                Webdash not loading
              </p>
              <Code>{`sudo systemctl status uconsole-webdash
sudo systemctl restart uconsole-webdash
journalctl -u uconsole-webdash -f`}</Code>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                Status not pushing to cloud
              </p>
              <Code>{`uconsole status          # check config
uconsole push            # manual push
journalctl -u uconsole-status -n 20`}</Code>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                Certificate warnings in Chrome
              </p>
              <p className="text-sub text-sm">
                Chrome requires Subject Alternative Names (SANs). Regenerate
                the cert by running <InlineCode>uconsole setup</InlineCode>{" "}
                (Step 8 will regenerate if you delete the old cert first):
              </p>
              <Code>{`sudo rm /etc/uconsole/ssl/uconsole.*
uconsole setup`}</Code>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                iOS PWA icon shows letter instead of logo
              </p>
              <p className="text-sub text-sm mb-2">
                Safari won&apos;t load the favicon from a self-signed cert it
                doesn&apos;t trust. Fix: go to Settings &gt; General &gt; About
                &gt; Certificate Trust Settings, enable the uconsole.local
                certificate. Then clear Safari website data (Settings &gt;
                Safari &gt; Clear History and Website Data). Delete the old PWA
                from Home Screen and re-add from Safari&apos;s share sheet.
              </p>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                Desktop is bare after reboot
              </p>
              <p className="text-sub text-sm mb-2">
                The labwc autostart file can get overwritten by system updates,
                losing pcmanfm, wf-panel, and kanshi entries. Check{" "}
                <InlineCode>~/.config/labwc/autostart</InlineCode> has all
                required entries. Consider adding it to your backup system.
              </p>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                Console keybind missing after apt upgrade
              </p>
              <p className="text-sub text-sm mb-2">
                The package installs to <InlineCode>/opt/uconsole</InlineCode>{" "}
                but your dev tree at <InlineCode>~/pkg</InlineCode> may have
                newer code. Run <InlineCode>uconsole update</InlineCode> or
                manually copy from your dev tree.
              </p>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                Webdash scripts return empty
              </p>
              <p className="text-sub text-sm mb-2">
                SCRIPTS_DIR resolution may be wrong. Run{" "}
                <InlineCode>uconsole doctor</InlineCode> and verify{" "}
                <InlineCode>/opt/uconsole/scripts/</InlineCode> has the expected
                scripts. Also check that PATH includes{" "}
                <InlineCode>/opt/uconsole/bin</InlineCode>.
              </p>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                uConsole won&apos;t boot on battery
              </p>
              <p className="text-sub text-sm mb-2">
                The AXP228 PMU defaults to a 3.3V undervoltage cutoff. 18650
                cells sag below this during boot inrush. Install the battery
                boot fix from TUI (Power &gt; Power Config &gt; Install Boot
                Fix) or run{" "}
                <InlineCode>
                  sudo bash /opt/uconsole/scripts/power/fix-battery-boot.sh
                  install
                </InlineCode>
                . This sets a 2.9V cutoff via udev rule, initramfs hook, and
                shutdown service.
              </p>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                GPS satellite globe shows &quot;No Signal&quot;
              </p>
              <p className="text-sub text-sm mb-2">
                The u-blox GPS module needs gpsd&apos;s{" "}
                <InlineCode>-b</InlineCode> flag to stay in NMEA mode for
                satellite visibility data. The package adds this automatically
                on install. To fix manually:{" "}
                <InlineCode>
                  sudo sed -i &apos;/^GPSD_OPTIONS=/ s/&quot;$/ -b&quot;/&apos;
                  /etc/default/gpsd &amp;&amp; sudo systemctl restart gpsd
                </InlineCode>
              </p>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                LoRa SX1262 not detected
              </p>
              <p className="text-sub text-sm mb-2">
                The SX1262 is on SPI1 (<InlineCode>/dev/spidev1.0</InlineCode>),
                not SPI4. The <InlineCode>lora.sh</InlineCode> script loads the{" "}
                <InlineCode>spi1-1cs</InlineCode> overlay on demand and unloads
                it after use to avoid audio interference. Do not add{" "}
                <InlineCode>dtoverlay=spi1-1cs</InlineCode> to config.txt
                permanently.
              </p>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                WiFi fallback AP not starting
              </p>
              <p className="text-sub text-sm mb-2">
                NetworkManager connection profile may be missing. Re-run{" "}
                <InlineCode>uconsole setup</InlineCode> to reconfigure hotspot
                settings.
              </p>
            </div>
            <div>
              <p className="text-bright font-medium text-sm mb-1">
                Reset everything
              </p>
              <Code>{`sudo apt remove uconsole-cloud    # remove package
sudo apt purge uconsole-cloud     # remove package + config
curl -s https://uconsole.cloud/install | sudo bash  # reinstall`}</Code>
            </div>
          </div>
        </Section>

        {/* Contributing */}
        <Section id="contributing" title="Contributing">
          <p className="text-sub mb-3 text-sm">
            Issues and PRs welcome — especially from uConsole owners who can
            test on real hardware.
          </p>
          <Code>{`git clone https://github.com/mikevitelli/uconsole-cloud.git
cd uconsole-cloud
npm install
cp frontend/.env.example frontend/.env.local
# Fill in your credentials
npm run dev    # frontend :3000, studio :3333
npm test       # 1,024 tests (211 vitest + 813 pytest)`}</Code>
          <p className="text-sub mt-3 text-sm">
            See{" "}
            <a href="https://github.com/mikevitelli/uconsole-cloud/blob/main/CONTRIBUTING.md">
              CONTRIBUTING.md
            </a>{" "}
            for details. Power scripts are safety-critical — changes to
            battery/charge logic require extra review.
          </p>
        </Section>

        {/* Footer */}
        <div className="border-t border-border pt-8 text-center">
          <p className="text-dim text-xs">
            Built for the{" "}
            <a href="https://www.clockworkpi.com/uconsole">
              ClockworkPi uConsole
            </a>
            .
          </p>
          <p className="text-dim text-xs mt-1">
            <a href="https://github.com/mikevitelli/uconsole-cloud">
              GitHub
            </a>
            {" · "}
            <Link href="/">Dashboard</Link>
            {" · "}
            <Link href="/link">Link Device</Link>
            {" · "}
            <a href="https://github.com/mikevitelli/uconsole-cloud/blob/main/docs/DEVICE-LINKING.md">
              Device Linking Flow
            </a>
          </p>
        </div>
      </main>
    </div>
  );
}
