"""uconsole-ai — local CLI agent for the uConsole.

Talks to the local ollama daemon. Stdlib only.

Tools: run_bash (with confirmation on mutating commands), read_file,
write_file, list_dir. System prompt is built from CLAUDE.md so the
model has the device's full context.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("UCONSOLE_AI_MODEL", "qwen2.5:7b")
MAX_HOPS = int(os.environ.get("UCONSOLE_AI_MAX_HOPS", "10"))
CMD_TIMEOUT = int(os.environ.get("UCONSOLE_AI_CMD_TIMEOUT", "120"))
OUTPUT_LIMIT = 8000

KB_DIR = Path(os.environ.get("UCONSOLE_AI_KB", str(Path.home() / ".config" / "uconsole-ai")))

CLAUDE_MD_PATHS = [
    Path("/home/mikevitelli/CLAUDE.md"),
    Path.home() / "CLAUDE.md",
    Path("/etc/uconsole/CLAUDE.md"),
]

SYSTEM_PROMPT_BASE_FALLBACK = """You are uconsole-ai, an offline expert on a Clockwork Pi uConsole (CM5 Lite, Debian Bookworm). User: mikevitelli.

Tools: run_bash, read_file, write_file, list_dir, list_topics, recall.

Rules:
- Run commands; don't guess. Default read-only.
- Mutating commands (sudo, rm, systemctl restart, apt install, git push, etc.) prompt the user for confirmation.
- Reply tightly: command output + 1-line summary.
- If a command fails, read the error and adjust. Don't repeat failures.

Knowledge: call list_topics() then recall("topic") for command syntax and conventions on a specific area (network, power, services, filesystem, etc.). Do this *first* whenever the question is topic-specific."""


# ── Confirmation classifier ────────────────────────────────────────────

_DESTRUCTIVE_PATTERNS = [
    r"\bsudo\b",
    r"\brm\b",
    r"\bmv\b",
    r"\bcp\b",
    r"\bdd\b",
    r"\bmkfs\b",
    r"\bchmod\b",
    r"\bchown\b",
    r"\bkill(all)?\b",
    r"\bpkill\b",
    r"\bsystemctl\s+(start|stop|restart|enable|disable|mask|unmask|reload)\b",
    r"\bservice\s+\S+\s+(start|stop|restart|reload)\b",
    r"\bapt(?:-get)?\s+(install|remove|purge|update|upgrade|autoremove|dist-upgrade)\b",
    r"\bdpkg\s+-(i|r|P)\b",
    r"\bpip\s+install\b",
    r"\bnpm\s+(install|i|uninstall|remove)\b",
    r"\bgit\s+(commit|push|reset|checkout|rm|clean|merge|rebase)\b",
    r"\btee\b",
    r"\btruncate\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\bpoweroff\b",
    r"\bcrontab\b",
    r"\bnmcli\s+(connection|c)\s+(add|delete|modify|up|down)\b",
    r"\biwconfig\b",
    r"\bip\s+link\s+set\b",
]
_DESTRUCTIVE_RE = re.compile("|".join(_DESTRUCTIVE_PATTERNS))
_REDIRECT_RE = re.compile(r"(?:^|[^>])>{1,2}(?!=)|(?<!\d)>>(?!=)")


def needs_confirm(cmd: str) -> bool:
    if _REDIRECT_RE.search(cmd):
        return True
    return bool(_DESTRUCTIVE_RE.search(cmd))


# ── Tools ──────────────────────────────────────────────────────────────

def _truncate(s: str, n: int = OUTPUT_LIMIT) -> str:
    if len(s) <= n:
        return s
    return s[:n] + f"\n…(truncated, {len(s) - n} more bytes)"


def tool_run_bash(command, *, auto_confirm: bool = False) -> dict:
    # Some models emit the command as a list of argv tokens. Normalize.
    if isinstance(command, (list, tuple)):
        command = " ".join(shlex.quote(str(x)) for x in command)
    elif not isinstance(command, str):
        command = str(command)
    if needs_confirm(command) and not auto_confirm:
        print(f"\n  \033[33m![\033[0m \033[1m{command}\033[0m")
        print("    \033[2mThis looks mutating. Run it? [y/N/e=edit]\033[0m ", end="", flush=True)
        try:
            ans = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "n"
        if ans == "e":
            print("    new command: ", end="", flush=True)
            try:
                new = input().strip()
            except (EOFError, KeyboardInterrupt):
                return {"output": "(cancelled)", "exit_code": -1}
            if new:
                command = new
            else:
                return {"output": "(cancelled)", "exit_code": -1}
        elif ans not in ("y", "yes"):
            return {"output": "(user declined)", "exit_code": -1}
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=CMD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"output": f"(timeout after {CMD_TIMEOUT}s)", "exit_code": -2}
    out = (proc.stdout or "") + (proc.stderr or "")
    return {"output": _truncate(out), "exit_code": proc.returncode}


def _to_int(v, default: int) -> int:
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def tool_read_file(path: str, max_bytes=20000) -> dict:
    n = _to_int(max_bytes, 20000)
    p = Path(path).expanduser()
    if not p.exists():
        return {"error": f"not found: {p}"}
    if not p.is_file():
        return {"error": f"not a regular file: {p}"}
    try:
        data = p.read_text(errors="replace")
    except PermissionError as e:
        return {"error": str(e)}
    return {"content": _truncate(data, n), "size_bytes": p.stat().st_size}


def tool_write_file(path: str, content: str, *, auto_confirm: bool = False) -> dict:
    p = Path(path).expanduser()
    action = "overwrite" if p.exists() else "create"
    if not auto_confirm:
        print(f"\n  \033[33m![\033[0m {action} {p} ({len(content)} bytes)")
        print("    \033[2mProceed? [y/N]\033[0m ", end="", flush=True)
        try:
            ans = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "n"
        if ans not in ("y", "yes"):
            return {"error": "(user declined)"}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    except PermissionError as e:
        return {"error": str(e)}
    return {"ok": True, "path": str(p), "bytes_written": len(content)}


def _topic_dir() -> Path:
    return KB_DIR / "topics"


def _first_h1_or_blurb(md: str) -> str:
    """Extract the first '# heading' or fallback to the first line as a one-line description."""
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s:
            return s[:120]
    return ""


def tool_list_topics() -> dict:
    """List available knowledge topics with one-line descriptions."""
    d = _topic_dir()
    if not d.is_dir():
        return {"error": f"no topics dir at {d}", "topics": []}
    out = []
    for p in sorted(d.glob("*.md")):
        try:
            blurb = _first_h1_or_blurb(p.read_text(errors="replace"))
        except Exception:
            blurb = ""
        out.append({"topic": p.stem, "description": blurb})
    return {"kb_dir": str(d), "topics": out}


def tool_recall(topic: str) -> dict:
    """Return the contents of a knowledge topic file (markdown)."""
    if not topic or not isinstance(topic, str):
        return {"error": "topic must be a non-empty string"}
    # sanitize: only allow word chars + dash to avoid path traversal
    if not re.fullmatch(r"[A-Za-z0-9_-]+", topic):
        return {"error": f"invalid topic name: {topic!r}"}
    p = _topic_dir() / f"{topic}.md"
    if not p.exists():
        return {"error": f"no such topic: {topic}"}
    try:
        content = p.read_text(errors="replace")
    except Exception as e:
        return {"error": str(e)}
    return {"topic": topic, "content": content}


def tool_list_dir(path: str = ".") -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        return {"error": f"not found: {p}"}
    if not p.is_dir():
        return {"error": f"not a directory: {p}"}
    entries = []
    for child in sorted(p.iterdir()):
        try:
            st = child.stat()
            entries.append({
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "size": st.st_size,
            })
        except OSError:
            entries.append({"name": child.name, "type": "?"})
    return {"path": str(p), "entries": entries[:200]}


TOOL_FNS = {
    "run_bash": tool_run_bash,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "list_dir": tool_list_dir,
    "list_topics": tool_list_topics,
    "recall": tool_recall,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute a bash command on the uConsole. Mutating commands prompt the user for confirmation. Returns combined stdout+stderr (truncated) and exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Single bash command line. Pipes and quoting are fine."}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file from disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_bytes": {"type": "integer", "description": "Cap bytes returned (default 20000)."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file. Always prompts for confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List entries in a directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_topics",
            "description": "List available uConsole knowledge-base topics with a one-line description of each. Call this first when the user's question is topic-specific (network, power, services, filesystem, webdash, cloud, lora, esp32, audio, display) so you can find the right topic to recall.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Return the full markdown content of a knowledge-base topic. Use the topic names from list_topics() — typically one of: network, power, services, filesystem, webdash, cloud, lora, esp32, audio, display. Each topic contains the canonical commands and conventions for that area on this specific device.",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string", "description": "Topic name (e.g. \"network\")."}},
                "required": ["topic"],
            },
        },
    },
]


# ── Ollama client ──────────────────────────────────────────────────────

def ollama_chat(model: str, messages: list, *, tools: list | None = None, timeout: int = 600) -> dict:
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def ollama_unload(model: str) -> None:
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"{OLLAMA_URL}/api/generate",
                data=json.dumps({"model": model, "keep_alive": 0}).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=10,
        )
    except Exception:
        pass


# ── System prompt ──────────────────────────────────────────────────────

def build_system_prompt(*, embed_claude_md: bool = False) -> str:
    """Build the system prompt.

    Layered:
      1. KB base.md (if present) — curated essentials
      2. Otherwise SYSTEM_PROMPT_BASE_FALLBACK
      3. Optional: CLAUDE.md inlined (--full-context, slow on this hardware)
    """
    base = KB_DIR / "base.md"
    if base.exists():
        try:
            prompt = base.read_text(errors="replace")
        except Exception:
            prompt = SYSTEM_PROMPT_BASE_FALLBACK
    else:
        prompt = SYSTEM_PROMPT_BASE_FALLBACK

    if embed_claude_md:
        for p in CLAUDE_MD_PATHS:
            if p.exists():
                try:
                    prompt += "\n\n# uConsole context (from CLAUDE.md)\n\n" + p.read_text()
                    break
                except Exception:
                    pass
    return prompt


# ── Agent loop ─────────────────────────────────────────────────────────

def _coerce_args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"command": raw}
    return {}


def step(model: str, messages: list, *, auto_confirm: bool, verbose: bool, stats: dict | None = None) -> str:
    """Run a single user-turn → model-turn cycle (with tool hops). Returns final assistant text."""
    final_text = ""
    for hop in range(MAX_HOPS):
        t0 = time.monotonic()
        try:
            resp = ollama_chat(model, messages, tools=TOOL_SCHEMAS)
        except urllib.error.URLError as e:
            return f"[ollama unreachable: {e}]"
        elapsed = time.monotonic() - t0

        if stats is not None:
            stats.setdefault("hops", 0)
            stats["hops"] += 1
            stats.setdefault("model_seconds", 0.0)
            stats["model_seconds"] += elapsed
            for k in ("eval_count", "eval_duration", "prompt_eval_count", "prompt_eval_duration", "load_duration"):
                if k in resp:
                    stats.setdefault(k, 0)
                    stats[k] += resp[k] or 0

        msg = resp.get("message") or {}
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []
        messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})

        if content:
            print(content)
            final_text = content

        if not tool_calls:
            return final_text

        for tc in tool_calls:
            fn_block = tc.get("function") or {}
            name = fn_block.get("name") or ""
            args = _coerce_args(fn_block.get("arguments"))
            if verbose:
                print(f"  \033[2m· {name}({json.dumps(args)[:160]})\033[0m")
            if name not in TOOL_FNS:
                result = {"error": f"unknown tool: {name}"}
            else:
                fn = TOOL_FNS[name]
                kwargs = dict(args)
                if name in ("run_bash", "write_file"):
                    kwargs["auto_confirm"] = auto_confirm
                try:
                    result = fn(**kwargs)
                except TypeError as e:
                    result = {"error": f"bad args: {e}"}
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}
            if verbose:
                preview = json.dumps(result)[:240]
                print(f"  \033[2m  → {preview}\033[0m")
            messages.append({"role": "tool", "content": json.dumps(result)})
    return final_text or "(reached max hops)"


def repl(model: str, *, auto_confirm: bool, verbose: bool, embed_claude_md: bool = False) -> int:
    print(f"\033[1muconsole-ai\033[0m  · model: \033[36m{model}\033[0m  · /exit to quit, /reset to clear context")
    if auto_confirm:
        print("\033[33m  ⚠ auto-confirm ON — mutating commands run without prompts\033[0m")
    messages = [{"role": "system", "content": build_system_prompt(embed_claude_md=embed_claude_md)}]
    while True:
        try:
            line = input("\n\033[1;32m>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/exit", "/quit"):
            break
        if line == "/reset":
            messages = [{"role": "system", "content": build_system_prompt(embed_claude_md=embed_claude_md)}]
            print("(context cleared)")
            continue
        if line == "/model":
            print(f"current model: {model}")
            continue
        if line.startswith("/model "):
            model = line.split(None, 1)[1].strip()
            print(f"switched to: {model}")
            continue
        messages.append({"role": "user", "content": line})
        step(model, messages, auto_confirm=auto_confirm, verbose=verbose)
    return 0


def one_shot(model: str, query: str, *, auto_confirm: bool, verbose: bool, embed_claude_md: bool = False, stats: dict | None = None) -> int:
    messages = [
        {"role": "system", "content": build_system_prompt(embed_claude_md=embed_claude_md)},
        {"role": "user", "content": query},
    ]
    step(model, messages, auto_confirm=auto_confirm, verbose=verbose, stats=stats)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="uconsole-ai", description="Local AI agent for uConsole.")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"ollama model tag (default: {DEFAULT_MODEL})")
    ap.add_argument("-y", "--yes", action="store_true", help="auto-confirm mutating commands (dangerous)")
    ap.add_argument("-q", "--quiet", action="store_true", help="hide tool-call traces")
    ap.add_argument("--full-context", action="store_true", help="embed CLAUDE.md inline in system prompt (slower; better for complex questions)")
    ap.add_argument("--list-models", action="store_true", help="list installed ollama models and exit")
    ap.add_argument("--bench", action="store_true", help="(internal) emit JSON stats to stderr after one-shot")
    ap.add_argument("query", nargs="*", help="one-shot query (no args → REPL)")
    args = ap.parse_args(argv)

    if args.list_models:
        try:
            with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
                data = json.load(r)
            for m in data.get("models", []):
                print(f"  {m.get('name'):<35} {m.get('size', 0) // 1_000_000:>6} MB")
            return 0
        except Exception as e:
            print(f"[error] {e}", file=sys.stderr)
            return 1

    if args.query:
        query = " ".join(args.query)
        stats: dict = {} if args.bench else None
        rc = one_shot(args.model, query, auto_confirm=args.yes, verbose=not args.quiet,
                      embed_claude_md=args.full_context, stats=stats)
        if args.bench and stats is not None:
            print(json.dumps(stats), file=sys.stderr)
        return rc
    return repl(args.model, auto_confirm=args.yes, verbose=not args.quiet, embed_claude_md=args.full_context)


if __name__ == "__main__":
    sys.exit(main())
