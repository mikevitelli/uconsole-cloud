"use client";

import { useState } from "react";

type Status = "idle" | "submitting" | "success" | "error";

export function DeviceCodeForm() {
  const [code, setCode] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const [repo, setRepo] = useState("");

  function handleChange(value: string) {
    // Strip non-alphanumeric, uppercase, auto-insert hyphen
    const raw = value.replace(/[^a-zA-Z0-9]/g, "").toUpperCase().slice(0, 8);
    if (raw.length > 4) {
      setCode(raw.slice(0, 4) + "-" + raw.slice(4));
    } else {
      setCode(raw);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setStatus("submitting");

    try {
      const res = await fetch("/api/device/code/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || "Failed to confirm code");
        setStatus("error");
        return;
      }

      setRepo(data.repo);
      setStatus("success");
    } catch {
      setError("Something went wrong");
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <div className="text-center py-4">
        <div className="text-2xl mb-2">&#10003;</div>
        <p className="text-bright font-semibold">Device linked!</p>
        <p className="text-sub text-sm mt-1">
          Connected to <span className="font-mono text-foreground">{repo}</span>
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="text"
        value={code}
        onChange={(e) => handleChange(e.target.value)}
        placeholder="AB12-CD34"
        maxLength={9}
        autoComplete="off"
        autoFocus
        className="w-full bg-background border border-border rounded-lg px-4 py-3 text-center text-2xl font-mono tracking-[0.3em] text-foreground placeholder:text-dim focus:outline-none focus:border-accent uppercase"
      />
      {error && <p className="text-red text-xs mt-2">{error}</p>}
      <button
        type="submit"
        disabled={status === "submitting" || code.length !== 9}
        className="w-full mt-3 bg-accent text-[#0d1117] font-semibold rounded-lg px-4 py-2.5 text-sm hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {status === "submitting" ? "Confirming..." : "Confirm Code"}
      </button>
    </form>
  );
}
