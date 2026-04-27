// Polyfill globalThis.crypto from node:crypto.webcrypto for Node 18.
// Node 20+ exposes WebCrypto as a native global; Node 18 ships it as a
// module export only. CI (Node 22) and Vercel runtime (Node 20+) don't
// need this — it's purely a local-dev convenience for contributors who
// haven't bumped their toolchain yet.
import { webcrypto } from "node:crypto";

if (!globalThis.crypto) {
  globalThis.crypto = webcrypto;
}
