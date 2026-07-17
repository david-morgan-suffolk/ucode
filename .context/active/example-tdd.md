# TDD: Cache Discovered Models Per Workspace (EXAMPLE)

> **This is an example, not real in-flight work.** It is the `.env.example` of active
> docs: a persistent template that shows the [`../writing-tdds.md`](../writing-tdds.md)
> format in a filled-in, realistic ucode design. Do not implement it. Real TDDs are named
> `YYYYMMDD-<doc-title>.md`, dated the day they are created, and deleted by the PR that
> completes the work — this file has no date and stays committed.

## 1. Context & Problem

Every launch calls the gateway to discover model-serving endpoints before it writes agent
config. Discovery adds a round trip to each `ucode` run even when the model set has not
changed. This TDD adds a per-workspace model cache in `state.py` so a launch reuses a
recent discovery result. The cache is an optimization only; a stale or absent cache never
changes which models a launch can reach.

Glossary:
- **discovery result** — the list of `ProviderService` records `databricks.py` returns for a workspace.
- **workspace key** — the canonical workspace host string used as the state key.
- **cache entry** — one `{workspace_key: {fetched_at, services}}` record in ucode state.
- **TTL** — `MODEL_CACHE_TTL_S` (900 s), the maximum age a cache entry may serve.
- **fresh entry** — a cache entry whose age is below the TTL.

## 2. Goals

- A launch with a fresh entry skips the discovery round trip.
- A launch with a stale or missing entry performs discovery and refreshes the entry.
- `ucode configure` always performs discovery and refreshes the entry, never serving cache.
- A cache read failure falls back to live discovery, never to an error.

## 3. Non-Goals & Forbidden Approaches

Non-goals:
- Caching auth tokens or SQL warehouse discovery (separate lifetimes).
- Cross-workspace cache sharing.
- A user-facing cache-inspection command.

Forbidden approaches:
- Do not cache in a module-level dict. State persists only through `state.py`.
- Do not read the cache inside `databricks.py`; discovery stays a pure gateway call.
- Do not extend the TTL when an entry is read (no sliding expiry — a fixed lifetime keeps
  reasoning simple).

## 4. Requirements

- R1: `state.py` gains `load_model_cache(workspace)` and `save_model_cache(workspace, services)`.
- R2: A cache entry stores `fetched_at` (epoch seconds) and the serialized `services` list.
- R3: `load_model_cache` returns the services only when `now - fetched_at < MODEL_CACHE_TTL_S`.
- R4: The launch path reads the cache first and calls discovery only on a miss.
- R5: The configure path ignores the cache and calls discovery unconditionally, then saves.
- R6: A malformed or unreadable cache entry is treated as a miss, not an error.

## 5. Invariants

- I1: The set of reachable models is identical with and without the cache.
- I2: A served cache entry is always younger than the TTL.
- I3: State written by an older ucode version never crashes a newer read (I6 of state versioning).

## 6. Proposed Architecture

No new modules. One new seam in `state.py`, consumed by `cli.py`.

```
+-----------------------------------------------------------+
|                          cli.py                           |
|   launch path ----read----> state.load_model_cache        |
|        |  miss                     |                       |
|        v                           | hit (fresh)           |
|   databricks.discover_* -----------+                       |
|        |                                                   |
|        +----write----> state.save_model_cache             |
|   configure path ----always----> databricks.discover_*    |
+-----------------------------------------------------------+
```

- `state.py` owns serialization, the TTL check, and the miss-on-error rule.
- `cli.py` owns the read-then-discover order and the configure-bypass rule.

## 7. Key Interactions

Launch, fresh entry (R3, R4):

```
cli            state              gateway
 |--load_model_cache(ws)-->|
 |<--services (age<TTL)----|
 |  (skip discovery)       |
 |--write agent config-------------------->|
```

Launch, stale entry (R3, R4):

```
cli            state              gateway
 |--load_model_cache(ws)-->|
 |<--None (age>=TTL)-------|
 |--discover_* -------------------------->|
 |<--services ---------------------------|
 |--save_model_cache(ws, services)-->|
```

## 8. Data Model

State gains one keyed section (per workspace, versioned with existing state):

```
model_cache:
  <workspace_key>:
    fetched_at: int        # epoch seconds
    services: [ {name, provider_type, base_url}, ... ]
```

## 9. APIs / Interfaces

Pinned contract types (a different shape fails review):

```python
@dataclass(frozen=True, slots=True)
class ProviderService:
    name: str
    provider_type: str
    base_url: str

MODEL_CACHE_TTL_S: int = 900

def load_model_cache(workspace: str) -> list[ProviderService] | None: ...
    # None on miss, stale entry, or any read/parse error (R6). Never raises.

def save_model_cache(workspace: str, services: list[ProviderService]) -> None: ...
```

## 10. Behavior & Domain Rules

**Freshness (R3).** An entry serves only while younger than the TTL.
- `fetched_at` 100 s ago → served.
- `fetched_at` 900 s ago → miss (boundary is exclusive).
- `fetched_at` in the future (clock skew) → miss.

**Configure bypass (R5).** `ucode configure` calls discovery even with a fresh entry, then
overwrites it. A user who just changed gateway models sees them immediately.

**Error tolerance (R6).** A cache entry whose `services` fails to parse is a miss; the
launch discovers live and rewrites the entry.

## 11. Acceptance Criteria

- `test_state.py`: `save_model_cache` then `load_model_cache` round-trips the services;
  an entry aged past the TTL returns `None`; a hand-corrupted entry returns `None`.
- `test_cli.py`: a fresh entry suppresses the discovery call on launch (mock asserts zero
  calls); a stale entry triggers exactly one discovery call and one save.
- `test_cli.py`: `configure` calls discovery once even with a fresh entry.
- Full gate: `uv run pytest` and `uv run ruff check .` stay green.

## 12. Cross-Cutting Concerns

**Observability.** A cache hit prints nothing new; a miss follows the existing discovery
`spinner`. No new user-facing output.

## 13. Reference Implementations

- Versioned state read/write: `load_state` / `save_state` in `src/ucode/state.py`.
- Discovery call shape: `discover_model_services` in `src/ucode/databricks.py`.
- Mock-the-boundary test style: existing discovery tests in `tests/test_cli.py`.

## 14. Alternatives Considered

- Module-level dict cache — rejected; does not survive across `ucode` invocations (chosen: `state.py`).
- Sliding expiry (refresh TTL on read) — rejected; fixed lifetime is simpler to reason about (chosen: R3).
- Caching in `databricks.py` — rejected; keeps discovery a pure gateway call (chosen: seam in `state.py`).

## 15. Halt Conditions

- If `state.py` has no per-workspace keying seam to extend, stop and ask before adding one.
- If a fresh-entry launch still needs a token that only discovery fetched, stop — the cache
  would then change reachability and violate I1.
