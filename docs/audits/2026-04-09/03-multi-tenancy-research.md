# Multi-Tenancy & Data Efficiency Research

*Generated: 2026-04-09*

Now I have all the information I need. Let me compile the complete research report.

---

## Multi-Device/Multi-User Research Report for uconsole-cloud

### Current Architecture Summary

The existing system uses a straightforward single-device model with these Redis keys:

| Key pattern | Purpose | TTL |
|---|---|---|
| `user:{githubId}` | User settings (repo, linkedAt, deviceToken) | 90 days |
| `devicetoken:{uuid}` | Maps token to userId+repo | 90 days |
| `device:{owner/repo}:status` | Latest full status payload | None (overwrites each push) |
| `device:{owner/repo}:fallback` | WiFi fallback status | 24 hours |
| `devicecode:{CODE}` | Device linking code (pairing flow) | 10 minutes |
| `devicepoll:{secret}` | Device linking poll (pairing flow) | 10 minutes |
| `ratelimit:{key}` | Sliding-window rate limiter | Variable |

The device pushes a ~1.0-1.5 KB JSON payload every 5 minutes via `push-status.sh`. The cloud stores only the latest status -- no history. The repo string (e.g., `mikevitelli/uconsole`) serves as the device identifier, which means the current model is implicitly one-device-per-repo, one-repo-per-user.

---

### 1. Multi-Tenancy Patterns

**How similar IoT dashboards handle this:**

- **ThingsBoard** uses a hierarchical tenant model: Tenant -> Customer -> Device. Each tenant is fully isolated. Devices belong to a customer within a tenant. Telemetry is stored per-device with a compound key of `{tenantId}:{deviceId}`.

- **Balena** uses a fleet model: Organization -> Fleet -> Device. A fleet is a group of devices running the same application. Devices self-register using a provisioning key baked into the OS image.

- **Netdata** uses a space/room model: Space (org) -> Rooms (groupings) -> Nodes (devices). Each node runs an autonomous agent that streams to the cloud parent.

**Recommended model for uconsole-cloud:**

The natural fit is: **User -> Devices** (flat, no hierarchy needed at this scale). Each user can link multiple devices, each identified by a unique device ID (not repo -- a device should be independent of its backup repo).

**Proposed data model:**

```
user:{userId}                    -> { devices: ["dev_abc123", "dev_def456"], defaultDevice: "dev_abc123", linkedAt: "..." }
device:{deviceId}:meta           -> { name: "uconsole-desk", repo: "owner/repo", userId: "gh_12345", linkedAt: "..." }
device:{deviceId}:status         -> { ...full status payload... }
device:{deviceId}:token          -> { token: "uuid", createdAt: "..." }
devicetoken:{uuid}               -> { deviceId: "dev_abc123", userId: "gh_12345" }
```

Key changes from current model:
- Device identity is decoupled from the repo. A device ID (e.g., `dev_` prefix + 8-char random) is assigned during `uconsole setup`.
- `user:{userId}` stores an array of device IDs, not a single repo string.
- The dashboard lists all devices for the user, with a selector to switch between them.
- The `devicetoken` reverse-lookup now maps to a `deviceId` instead of a repo.

This is backward-compatible: existing single-device users just have a one-element `devices` array.

---

### 2. Data Efficiency

#### Payload size analysis

The current full push payload is:
- **Without** hardware manifest: ~927 bytes (compact JSON)
- **With** hardware manifest: ~1,458 bytes (compact JSON)
- With Redis key overhead: ~1.5-1.9 KB per device total

#### Delta compression: worth it?

At 1-1.5 KB per push, the payload is already tiny. Fields that rarely change (hostname, kernel, disk total, cores, hardware manifest) account for roughly 40% of the payload. Fields that change every push (battery, cpu temp, load, memory, wifi signal, collectedAt) account for 60%.

**Recommendation: Not worth the complexity.** The savings would be ~400-600 bytes per push. At 8,640 pushes/month, that is ~4 MB saved per device per month -- negligible versus the Upstash free tier limits. The implementation cost (tracking last-sent state on the device, merging deltas on the server) adds fragility to a system that runs on battery-powered embedded hardware. The current full-push-overwrite model is correct for this scale.

However, a simple optimization is available: **split static vs. dynamic data.** The hardware manifest, hostname, kernel, and disk totals change only on reboot or hardware scan. These could be pushed only on change (or once per hour), reducing every-5-min payload to ~600 bytes. This is worth doing only if bandwidth becomes a concern on metered mobile connections.

#### TTL strategies

The current model stores `device:{repo}:status` with **no TTL**, relying on `collectedAt` age for staleness. This is problematic for multi-device -- abandoned devices accumulate forever.

**Recommended TTLs:**

| Key | TTL | Rationale |
|---|---|---|
| `device:{id}:status` (latest) | 24 hours | If a device hasn't pushed in 24h, it's off. The dashboard already shows "offline" after 15 min. Stale data older than 24h is misleading. |
| `device:{id}:history:raw` (stream) | 24 hours (XTRIM by time) | Raw 5-min data is only useful for recent troubleshooting. |
| `device:{id}:history:hourly` (stream) | 30 days | Useful for trend analysis. |
| `device:{id}:history:daily` (sorted set) | 365 days | Long-term capacity planning. |
| `device:{id}:meta` | 90 days (renewed on push) | Matches user session TTL. |
| `devicetoken:{uuid}` | 90 days (current, correct) | |
| `user:{userId}` | 90 days (current, correct) | |

#### Aggregation strategy

A three-tier rollup model:

1. **Raw** (every 5 min, keep 24h): Full status payload stored via `XADD`. Device pushes status; server writes to both `device:{id}:status` (latest, SET) and `device:{id}:history:raw` (XADD).

2. **Hourly** (computed server-side, keep 30d): Every hour, a scheduled function (Vercel cron or on-push check) reads the last 12 raw entries and writes an aggregate: avg CPU temp, avg battery %, min/max battery voltage, avg memory used, avg wifi quality.

3. **Daily** (keep 365d): Same pattern, aggregating from hourly data. Stored in a sorted set with score = epoch day, member = JSON summary.

The aggregation can be triggered lazily: on each push, check if the last hourly rollup is >60 minutes old and compute it then. This avoids needing a separate cron job.

#### Storage cost projections

**Current model (latest-only, no history):**

| Devices | Storage | Commands/month | Fits free tier? |
|---|---|---|---|
| 1 | ~1.9 KB | ~18,180 | Yes (3.6% of commands) |
| 10 | ~19 KB | ~181,800 | Yes (36% of commands) |
| 27 | ~52 KB | ~490,860 | Barely (98% of commands) |
| 50 | ~96 KB | ~909,000 | No (182% of commands) |

**The bottleneck is commands, not storage.** Each 5-min push costs 2 Redis commands (GET token + SET status). At 27 devices the free tier (500K commands/month) is exhausted.

**With time-series history (raw 24h + hourly 30d + daily 365d):**

| Devices | Storage | Commands/month | Fits free tier? |
|---|---|---|---|
| 1 | ~199 KB | ~35,460 | Yes |
| 5 | ~997 KB | ~177,300 | Yes (35%) |
| 14 | ~2.8 MB | ~496,440 | Barely |

**Optimization to extend command budget:**
- Cache the device token validation. Use a hash `tokencache:{token}` with a 5-min TTL so repeated pushes from the same device skip the token lookup. Saves 1 command per push, effectively doubling device capacity to ~27 with history.
- Batch the XADD + SET into a pipeline (Upstash supports pipelining via the REST SDK). Saves 1 round-trip per push.

**Upstash Pay-As-You-Go escape hatch:** At $0.20/100K commands, 50 devices with history would cost ~$3.55/month. Very manageable if the free tier is outgrown.

---

### 3. Docker for Testing Multi-Device Scenarios

The existing `Dockerfile.test` already validates the .deb installation. Extending it for multi-device simulation is straightforward.

**Proposed approach: `docker-compose.multi-device.yml`**

```yaml
# Spins up N simulated devices, each pushing to the real or local API
services:
  device-sim:
    build:
      context: .
      dockerfile: Dockerfile.device-sim
    deploy:
      replicas: 5  # simulate 5 devices
    environment:
      - DEVICE_API_URL=https://uconsole.cloud/api/device/push
      - DEVICE_TOKEN=${DEVICE_TOKEN_POOL}  # injected per replica
      - PUSH_INTERVAL=10  # seconds, faster than real for testing
      - DEVICE_NAME=sim-${HOSTNAME}
```

**The simulation script (`device-sim.sh`):**
A simplified version of `push-status.sh` that generates randomized but realistic telemetry:
- Battery capacity: random walk between 15-100%
- CPU temp: random between 40-75C
- Memory: random between 50-80% used
- WiFi signal: random between -30 and -80 dBm
- Occasional "offline" gaps (skip a push)

**How to provision test tokens:**
1. Create a `/api/device/test/provision` endpoint (dev-only, behind env flag) that bulk-generates device tokens for a test user.
2. Or: use a script that calls the existing device code flow N times programmatically.

**What this tests:**
- Redis command consumption at scale (measure actual commands via Upstash dashboard)
- Dashboard rendering with multiple devices
- Token validation performance under concurrent pushes
- Aggregation correctness across multiple devices

This approach is more useful than simulating on the real device because you can dial up to 100 simulated devices in seconds and measure the actual Upstash impact.

---

### 4. Redis Data Structures for Time-Series Telemetry

#### Options evaluated

**A. Sorted sets (ZADD/ZRANGEBYSCORE)**
- Score = Unix timestamp, member = JSON payload
- Pros: Simple queries, range queries by time, Upstash supports fully
- Cons: Entire set loaded to memory for operations; duplicate timestamps cause upsert (data loss); no built-in trimming by time
- Memory: ~64 bytes overhead per entry + payload size

**B. Redis Streams (XADD/XRANGE/XTRIM)**
- Auto-generated time-ordered IDs, multiple fields per entry
- Pros: Disk-backed on Upstash (entries stored on disk, only queried data loaded to memory); natural time ordering; XTRIM by MAXLEN or MINID for automatic cleanup; built-in range queries
- Cons: No native aggregation; slightly more complex API
- Memory: On Upstash, streams are stored on disk and do not count against the 256MB memory limit (this is a major advantage)

**C. Hash-per-timestamp (HSET `ts:1712345678` field value)**
- One hash per data point
- Pros: Very flexible field access
- Cons: Massive key proliferation (288 keys/day/device); no range queries without maintaining a separate index; worst memory efficiency due to per-key overhead

**D. RedisTimeSeries module**
- Purpose-built for this exact use case with built-in downsampling
- Cons: Not available on Upstash. Only available on Redis Stack / Redis Cloud.

#### Recommendation: Redis Streams

Streams are the clear winner for uconsole-cloud on Upstash:

1. **Disk-backed storage**: Upstash streams store entries on disk, not in memory. This means time-series history does not count against the 256MB free tier limit. This single fact changes the math entirely -- you could store months of raw data without hitting storage limits.

2. **Natural time ordering**: Entries are automatically ordered by timestamp ID.

3. **XTRIM**: `XTRIM device:{id}:history:raw MINID <24h-ago-timestamp>` cleanly evicts old data.

4. **XRANGE**: `XRANGE device:{id}:history:raw <start> <end>` for dashboard time-range queries.

**Proposed key schema with streams:**

```
# Latest status (SET, overwrites each push) -- used by dashboard for real-time display
device:{deviceId}:status           -> JSON blob (~1KB)

# Raw 5-min history (STREAM, XTRIM to 24h)
device:{deviceId}:ts:raw           -> Stream entries, each with fields:
                                       bat_cap, bat_v, bat_i, bat_status,
                                       cpu_temp, load1, load5, load15,
                                       mem_used, mem_total,
                                       wifi_signal, wifi_quality, wifi_ssid,
                                       disk_pct, screen_bright, uptime_s

# Hourly aggregates (STREAM, XTRIM to 30 days = 720 entries max)
device:{deviceId}:ts:hourly        -> Stream entries with fields:
                                       bat_cap_avg, bat_cap_min, bat_cap_max,
                                       cpu_temp_avg, cpu_temp_max,
                                       mem_pct_avg, wifi_quality_avg

# Daily aggregates (SORTED SET, score=epoch day, TTL 365d via periodic cleanup)
device:{deviceId}:ts:daily         -> Sorted set members are compact JSON summaries
```

Note the stream field names are abbreviated to save bytes. The raw stream stores a flattened subset of the full payload (no need to duplicate hostname/kernel/hardware every 5 minutes).

---

### 5. Similar Open-Source Projects

#### 1. ThingsBoard (github.com/thingsboard/thingsboard)
- **What it does**: Full IoT platform with device management, data collection, rule engine, and dashboards. Supports MQTT, CoAP, HTTP.
- **Data model**: Entities (tenants, customers, devices) in PostgreSQL. Time-series in Cassandra or TimescaleDB. Redis for caching only.
- **Telemetry flow**: Device -> Transport layer -> Kafka queue -> Rule engine -> Database. Telemetry is key-value pairs with timestamps, not monolithic JSON blobs.
- **What uconsole-cloud can learn**: Separate entity metadata from time-series data. ThingsBoard's approach of storing telemetry as individual key-value pairs (e.g., `temperature=52.3` at timestamp X) rather than full JSON payloads enables much more efficient aggregation and querying.

#### 2. Netdata (github.com/netdata/netdata)
- **What it does**: Real-time per-second monitoring for Linux. Agent runs on-device, streams to Netdata Cloud or a parent node.
- **Data model**: Each agent stores metrics locally in a custom time-series database (DBENGINE) with tiered storage: hot (RAM) -> warm (disk page cache) -> cold (disk). Cloud receives only metadata and query routing.
- **Telemetry flow**: Agent collects metrics locally at 1s resolution. Cloud does not store raw metrics -- it queries agents on-demand.
- **What uconsole-cloud can learn**: The "query the device, don't store everything in the cloud" model is compelling. Since uconsole devices already run webdash on the local network, the cloud dashboard could proxy real-time queries to the device when it is reachable (same-network detection already exists), and fall back to stored snapshots when the device is offline.

#### 3. Balena Cloud (github.com/balena-io)
- **What it does**: Fleet management for container-based embedded Linux devices. Deploys apps via Docker to fleets of devices.
- **Data model**: Devices self-register with a provisioning key. Each device gets a unique UUID. Device state (online/offline, OS version, IP, CPU/memory) is stored server-side. Telemetry is separate from device management.
- **What uconsole-cloud can learn**: The device provisioning flow (`uconsole setup` generating a code, confirmed at uconsole.cloud/link) is already very similar to Balena's model. Balena's fleet concept maps naturally to "all devices belonging to a user." The key insight is that Balena keeps device state minimal on the server and pushes application management to the device.

#### 4. Pantavisor + InfluxDB (pantacor.com)
- **What it does**: Embedded Linux device lifecycle management with container-based firmware. Uses InfluxDB for telemetry storage.
- **Data model**: Devices push telemetry to Pantacor Hub API. InfluxDB stores time-series with tags (device_id, region) and fields (cpu, memory, etc.). Retention policies auto-expire old data.
- **What uconsole-cloud can learn**: InfluxDB's retention policy concept maps directly to the TTL tiers proposed above. The tag-based model (where device_id is a tag, not part of the key name) is more query-friendly when you want cross-device aggregation ("average battery across all my devices").

#### 5. Home Assistant (github.com/home-assistant/core)
- **What it does**: Home automation platform. Not exactly device-to-cloud, but manages hundreds of entities (sensors, switches) with state tracking and history.
- **Data model**: Each entity has a current state (like `device:status`) and a state history stored in SQLite/PostgreSQL with automatic purge after a configurable retention period (default 10 days).
- **What uconsole-cloud can learn**: Home Assistant's "recorder" component is essentially what uconsole-cloud needs: store current state for real-time display, record history with automatic purge, and provide statistics (hourly/daily/monthly aggregates) computed from history. Their statistics tables store min/max/mean/sum per hour -- almost exactly the hourly rollup proposed above.

---

### Concrete Recommendations (Prioritized)

**Phase 1 -- Quick wins (no schema change needed):**

1. **Add TTL to `device:{repo}:status`**: Set `ex: 86400` (24h) on the SET in `push/route.ts` line 61. One-line change. Prevents abandoned device data from persisting forever.

2. **Pipeline the push commands**: Use Upstash's `redis.pipeline()` to batch the token validation GET and status SET into a single HTTP round-trip. Cuts push latency in half and reduces effective command count.

**Phase 2 -- Multi-device support:**

3. **Introduce device IDs**: Generate a `dev_` prefixed ID during `uconsole setup` instead of using the repo as the device identifier. Store a `devices[]` array in user settings. Update the dashboard to show a device selector.

4. **Proposed key schema migration:**
```
# Old
device:{owner/repo}:status
user:{userId}                   -> { repo, linkedAt, deviceToken }

# New
device:{deviceId}:status        -> latest payload (SET, TTL 24h)
device:{deviceId}:meta          -> { name, repo, userId, linkedAt } (SET, TTL 90d, renewed on push)
user:{userId}                   -> { devices: [...], defaultDevice, linkedAt }
devicetoken:{uuid}              -> { deviceId, userId }
```

**Phase 3 -- Time-series history (using Streams):**

5. **Add raw history**: On each push, also `XADD device:{deviceId}:ts:raw * bat_cap {val} cpu_temp {val} ...` with flattened numeric fields only. `XTRIM` to MAXLEN 288 (24h of 5-min data).

6. **Add hourly rollup**: On push, check if last entry in `device:{deviceId}:ts:hourly` is >60 minutes old. If so, `XRANGE` the raw stream for the last hour, compute min/mean/max, and `XADD` to the hourly stream. XTRIM to MAXLEN 720 (30 days).

7. **Add dashboard history charts**: The frontend can query `XRANGE` for battery trend, CPU temp trend, memory trend over the last 24h/30d.

**Phase 4 -- Testing infrastructure:**

8. **Create `docker-compose.multi-device.yml`** with a lightweight simulation script that generates randomized telemetry and pushes it at configurable intervals. Use this to validate command budgets and dashboard behavior at 10/50/100 devices.

---

### Summary Table: Scaling Limits

| Scenario | Storage | Commands/mo | Free tier? | Monthly cost |
|---|---|---|---|---|
| 1 device, latest only (current) | 1.9 KB | 18K | Yes | $0 |
| 10 devices, latest only | 19 KB | 181K | Yes | $0 |
| 27 devices, latest only | 52 KB | 491K | Barely | $0 |
| 10 devices + stream history | ~10 KB memory (streams on disk) | 354K | Yes | $0 |
| 27 devices + stream history | ~27 KB memory (streams on disk) | 957K | No | ~$0.91/mo |
| 50 devices + stream history | ~50 KB memory (streams on disk) | 1.77M | No | ~$2.55/mo |
| 100 devices + stream history | ~100 KB memory (streams on disk) | 3.55M | No | ~$6.10/mo |

The critical insight: **Upstash Streams are stored on disk, not memory.** This means the 256MB storage limit is effectively irrelevant for time-series history -- only the `device:{id}:status` latest-snapshot keys consume the memory quota. The real constraint is the 500K commands/month free tier, which supports roughly 14-27 devices depending on whether history streams are enabled. Beyond that, pay-as-you-go pricing is extremely affordable for this use case.

Sources:
- [Upstash Redis Pricing & Limits](https://upstash.com/docs/redis/overall/pricing)
- [Storing Time Series Data in Redis (Upstash Blog)](https://upstash.com/blog/redis-timeseries)
- [Upstash Streams Beyond Memory](https://upstash.com/blog/redis-streams-beyond-memory)
- [XADD Documentation (Upstash)](https://upstash.com/docs/redis/sdks/ts/commands/stream/xadd)
- [ThingsBoard Architecture](https://thingsboard.io/docs/reference/)
- [ThingsBoard Telemetry](https://thingsboard.io/docs/user-guide/telemetry/)
- [Netdata Agents](https://www.netdata.cloud/product/netdata-agents/)
- [Netdata IoT Monitoring](https://www.netdata.cloud/solutions/use-cases/iot-monitoring/)
- [Balena Cloud Platform](https://www.balena.io/cloud)
- [Pantavisor + InfluxDB Observability](https://www.influxdata.com/blog/real-time-embedded-linux-observability-pantavisor-influxdb/)
- [Redis Data Isolation for Multi-Tenant SaaS](https://redis.io/blog/data-isolation-multi-tenant-saas/)
- [Redis Key Design and Naming Conventions](https://oneuptime.com/blog/post/2026-01-21-redis-key-design-naming/view)
- [Redis Memory Optimization](https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/)
- [Azure IoT Telemetry Simulator (Docker)](https://github.com/Azure-Samples/Iot-Telemetry-Simulator)
- [Docker Scaling 100K+ IoT Devices](https://www.docker.com/blog/from-edge-to-mainstream-scaling-to-100k-iot-devices/)