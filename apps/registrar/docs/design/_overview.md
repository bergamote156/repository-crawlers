---
title: "Registrar: Design Overview"
description: >
  How the registrar bridges crawled dataset metadata and Onedata infrastructure —
  resolving target spaces, creating resources, and registering files in bulk.
audience: internal-developer
source_modules:
  - apps/registrar/src/registrar/register/command.py
  - apps/registrar/src/registrar/register/planner.py
  - apps/registrar/src/registrar/register/lookups.py
  - apps/registrar/src/registrar/register/registration.py
  - apps/registrar/src/registrar/register/types.py
  - apps/registrar/src/registrar/register/datasets.py
  - apps/registrar/src/registrar/api/onepanel.py
  - apps/registrar/src/registrar/api/onezone.py
  - apps/registrar/src/registrar/api/oneprovider.py
  - apps/registrar/src/registrar/config.py
source_commits:
  public-data-crawlers: b5b9c82
---

The registrar takes a file of crawled dataset metadata and turns it into
registered Onedata resources — files, shares, and optionally public data
records. You point it at a JSON or JSONL file produced by a crawler, it
figures out which Onedata space and storage to use (or creates them), asks
you to confirm, and then registers every dataset in a single batch run.

The `register` command is the only command with significant logic; the
companion `list-spaces` and `list-storages` commands are simple query
wrappers for operator convenience. The entry point is
`register/command.py:run()` — a linear 90-line sequencer that reads
top-to-bottom.

## Design Principles

The `register` command splits its work into three distinct phases — plan,
apply, register — so the operator always sees what will happen before
anything changes. The planner resolves the target space and storage without
creating resources, the confirmation gate lets the operator inspect and
abort, and only then does the applier materialize missing infrastructure.
This design means you can run `registrar register datasets.jsonl` against
a production cluster and review the resolved plan before a single API call
mutates state.

Three more properties shape the design:

- **Per-dataset error isolation.** If one dataset fails to register (bad
  file URL, share conflict, missing metadata), the loop records the failure
  and moves on. The operator gets a full summary at the end rather than a
  partial run that stopped at the first error.

- **Idempotent re-runs.** Every step checks before creating: files are
  looked up by path before registration, shares are matched by name +
  description, handles are checked for existing `handleId`. A run
  interrupted halfway can be re-run with the same input — already-completed
  work is skipped automatically.

- **No rollback, by design.** If the space is created but support fails,
  the operator re-runs the command — the planner will find the existing
  space by name and pick up where it left off. This is simpler and more
  reliable than partial undo logic.

## Space Resolution

The planner resolves *which space* should hold the datasets. It follows
a cascade: explicit ID → name lookup → inference from file URLs, and
either produces a single unambiguous result or fails with a clear error.
It never silently picks one candidate over another.

```mermaid
flowchart TD
    START([space resolution]) --> A{space.id\nprovided?}

    A -- yes --> B[lookup_space_by_id\nOnepanelClient]
    B -- found --> E1["_PlannedSpace\n(id=existing, current_storage_id=id)"]
    B -- not found --> ERR1([TargetResolutionError])

    A -- no --> C{space.name\nprovided?}

    C -- yes --> D[find_spaces_by_name\nOnepanelClient, exact match]
    D -- 0 matches --> E2["_PlannedSpace\n(id=None, current_storage_id=None)"]
    D -- 1 match --> E3["_PlannedSpace\n(id=existing, current_storage_id=id)"]
    D -- 2+ matches --> ERR2([AmbiguityError\nwith candidate IDs])

    C -- no --> F["infer_domain\n(first_file_url)"]
    F -- domain found --> G[use domain as name]
    G --> D
    F -- no usable URL --> ERR3([TargetResolutionError])

    style E1 fill:#d4edda,stroke:#28a745,color:#000
    style E2 fill:#d4edda,stroke:#28a745,color:#000
    style E3 fill:#d4edda,stroke:#28a745,color:#000
    style ERR1 fill:#f8d7da,stroke:#dc3545,color:#000
    style ERR2 fill:#fff3cd,stroke:#ffc107,color:#000
    style ERR3 fill:#f8d7da,stroke:#dc3545,color:#000
```

The config layer enforces mutual exclusion between `space.id` and
`space.name`, so only one path can be active. When a name is inferred
from file URLs, the plan records `space_inferred=True` so the confirmation
display can highlight the guess before the operator commits.

## Storage Resolution

Storage resolution is more complex than space resolution because it must
satisfy two additional constraints:

- **Compatibility** — a storage must be HTTP readonly imported (the only
  type that supports file registration from external URLs). Incompatible
  types (POSIX, HTTP non-readonly) are rejected with a clear error.

- **Single-support invariant** — a space on a given provider can be
  supported by only one storage. The planner refuses to plan a switch
  rather than risk data split across storages or an API error at apply
  time.

```mermaid
flowchart TD
    START([resolve_storage]) --> Q_ID{storage.id\nprovided?}

    Q_ID -- yes --> LOOKUP_ID[lookup_storage_by_id]
    LOOKUP_ID -- not found --> ERR1([TargetResolutionError])
    LOOKUP_ID -- found --> COMPAT_ID{is_storage_compatible?\nHTTP readonly imported}
    COMPAT_ID -- no --> ERR2([TargetResolutionError])
    COMPAT_ID -- yes --> SINGLE_ID{storage == space's\ncurrent storage?}
    SINGLE_ID -- "yes, or space has\nno current storage" --> USE_ID([use this storage])
    SINGLE_ID -- "no — different storage" --> ERR3([TargetResolutionError])

    Q_ID -- no --> Q_NAME{storage.name\nprovided?}
    Q_NAME -- yes --> FIND[find_storages_by_name\nexact match]
    FIND -- "2+ matches" --> ERR4([AmbiguityError])
    FIND -- "1 match" --> COMPAT_NAME{is_storage_compatible?}
    COMPAT_NAME -- no --> ERR5([TargetResolutionError])
    COMPAT_NAME -- yes --> SINGLE_NAME{storage == space's\ncurrent storage?}
    SINGLE_NAME -- pass --> USE_NAME([use this storage])
    SINGLE_NAME -- fail --> ERR6([TargetResolutionError])

    FIND -- "0 matches" --> Q_CURRENT_NAME{space has\ncurrent storage?}
    Q_CURRENT_NAME -- yes --> ERR7([TargetResolutionError\ncannot add second support])
    Q_CURRENT_NAME -- no --> ENDPOINT[choose_endpoint\nexplicit or inferred\nfrom file URL]
    ENDPOINT -- no endpoint --> ERR8([TargetResolutionError])
    ENDPOINT -- got endpoint --> CREATE([plan: create new storage\nid = None])

    Q_NAME -- no --> Q_CURRENT_AUTO{space has\ncurrent_storage_id?}
    Q_CURRENT_AUTO -- yes --> LOOKUP_AUTO[lookup current storage]
    LOOKUP_AUTO --> COMPAT_AUTO{is_storage_compatible?}
    COMPAT_AUTO -- yes --> REUSE([reuse current storage])
    COMPAT_AUTO -- no --> ERR9([TargetResolutionError\ncannot add second support])
    Q_CURRENT_AUTO -- no --> USE_SPACE_NAME[use space.name\nas storage name]
    USE_SPACE_NAME --> ENDPOINT

    classDef error fill:#fde8e8,stroke:#c0392b,color:#7b0000
    classDef success fill:#e8f5e9,stroke:#27ae60,color:#145a32
    classDef decision fill:#fff8e1,stroke:#f39c12,color:#6d4c00
    classDef op fill:#e8f0fe,stroke:#3f51b5,color:#1a237e

    class ERR1,ERR2,ERR3,ERR4,ERR5,ERR6,ERR7,ERR8,ERR9 error
    class USE_ID,USE_NAME,REUSE,CREATE success
    class Q_ID,Q_NAME,Q_CURRENT_NAME,Q_CURRENT_AUTO,COMPAT_ID,COMPAT_NAME,COMPAT_AUTO,SINGLE_ID,SINGLE_NAME decision
    class LOOKUP_ID,FIND,LOOKUP_AUTO,ENDPOINT,USE_SPACE_NAME op
```

When neither ID nor name is provided and the space already has a compatible
storage, the planner reuses it. When the space is new, the planner uses
the space name as the storage name — keeping them aligned by convention.

## Public Data Records

After files and shares are in place, the registrar can optionally mint a
public identifier for each dataset's share. Both identifier types go
through `register_handle`; the behavior branches on two config values:
`public_identifier_type` (controls `requestPublicHandle`) and
`identifier_policy` (controls `publicHandleToReuse`).

- **`onedata-url`** (default) — registers the handle with
  `requestPublicHandle=false`. No public handle is minted by the service.
- **`pid`** — registers the handle with `requestPublicHandle=true`,
  asking the handle service (e.g. DOI or ePIC) to mint a public handle.

Both types require `metadata_xml` on the dataset and `handle_service_id`
in config.

```mermaid
flowchart TD
    START([public_data_records.register?])
    START -- NO --> SKIP([skip record phase])
    START -- YES --> XML{dataset.metadata_xml\npresent?}

    XML -- NO --> XML_ERR([RecordRequirementError])
    XML -- YES --> HANDLE{handleId already\non share?}

    HANDLE -- YES --> HANDLE_RET([return handleId\nidempotent])
    HANDLE -- NO --> TYPE{public_identifier_type}

    TYPE -- onedata-url --> TYPE_URL[requestPublicHandle = false]
    TYPE -- pid --> TYPE_PID[requestPublicHandle = true]

    TYPE_URL --> POL{identifier_policy}
    TYPE_PID --> POL

    POL -- always-reuse-existing --> AR_PID{dataset.pid\npresent?}
    AR_PID -- YES --> AR_SET[publicHandleToReuse = pid]
    AR_PID -- NO --> AR_ERR([RecordRequirementError])

    POL -- generate-new-if-missing --> GN_PID{dataset.pid\npresent?}
    GN_PID -- YES --> GN_SET[publicHandleToReuse = pid]
    GN_PID -- NO --> GN_NONE[publicHandleToReuse omitted]

    POL -- always-generate-new --> AG_NONE[publicHandleToReuse omitted]

    AR_SET --> REG
    GN_SET --> REG
    GN_NONE --> REG
    AG_NONE --> REG

    REG[register_handle\nhandle_service_id, share_id,\nmetadata_xml, requestPublicHandle,\npublicHandleToReuse]
    REG --> RET([return handle identifier])
```

### Identifier Policy

The `identifier_policy` controls `publicHandleToReuse` identically for
both `onedata-url` and `pid` types:

| Policy | `pid` present | `pid` absent |
|--------|---------------|--------------|
| `always-reuse-existing` | `publicHandleToReuse = pid` | Fail with `RecordRequirementError` |
| `generate-new-if-missing` | `publicHandleToReuse = pid` | Omit `publicHandleToReuse` |
| `always-generate-new` | Ignore the PID | Omit `publicHandleToReuse` |

The default is `generate-new-if-missing` — the safest option for batch
runs where some datasets carry PIDs from previous systems and others
are new.
