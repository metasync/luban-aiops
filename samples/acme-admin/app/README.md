# `acme-admin` — the application

A small FastAPI user-administration console: the tutorial target the
`samples/acme-admin/` skill suite is written against (SPEC-059). It exists so the
samples have something real to check — state that persists between calls, a
login that validates, and mutations that can be refused.

State is **in memory**. There is no database, no PVC and no external dependency,
because a tutorial target that needs provisioning stops being a tutorial target.
The consequence is `replicas: 1` in the Deployment: two replicas would be two
independent consoles that disagree.

The operator-facing document — endpoints, seed data, the credential arrangement,
how to deploy it and how to write a walkthrough against it — is
[`../README.md`](../README.md). This file covers working on the app itself.

## Two surfaces, one store

`store.STORE` holds the users, a monotonic `revision` and the last reset record.
Two routers sit over it:

| module | surface | auth |
|---|---|---|
| `api.py` | JSON: `/healthz`, `/api/hello`, `/api/users*`, `/internal/reset-demo` | HTTP Basic (`admin`) on `/api/users*`; none on `/healthz` and `/api/hello` |
| `pages.py` | HTML: `/`, `/status`, `/admin/`, `/admin/users/`, `/admin/users/reset/`, `/admin/users/reset/done/` | an opaque session token in an `HttpOnly`/`SameSite=Lax` cookie |

Both authenticate against the one value in `ACME_ADMIN_PASSWORD`, so the browser
surface, the HTTP surface and the application cannot disagree about the password.
There is no default: with the variable absent or empty the app **refuses to
start** and names the secret and the sync script that produce it.

Templates are `string.Template` module constants in `pages.py`, not files — the
Dockerfile copies one tree and there is no template-search path to configure.

## Working on it

```sh
cd samples/acme-admin/app
make sync      # uv sync --frozen
make test      # uv run pytest (the R-1 store/API, R-2 page-id and R-4 packaging suites)
make build     # docker build on the shared base-uv image
make lint      # hadolint on the Dockerfile
```

Run it locally against a throwaway password:

```sh
cd samples/acme-admin/app
ACME_ADMIN_PASSWORD="$(openssl rand -hex 16)" uv run acme-admin
# then: curl -s localhost:8080/healthz
```

`uv.lock` is committed and every sync is `--frozen`; regenerate it with
`uv lock` and commit the result rather than editing it.

## Deliberate boundaries

- **No OpenAPI document and no `/docs`.** Both are unauthenticated by nature and
  would publish `/internal/reset-demo` — the header-gated reseed no skill
  document names — to anything that can reach the pod.
- **`/internal/reset-demo` requires the `X-Luban-Demo-Reset` header**, which
  `http.post` has no way to send (SPEC-058 ships no `headers` parameter). The
  agent therefore cannot reset demo state mid-run even on an allowlisted origin.
- **No password is ever stored.** A reset records *when* it happened and which
  revision it produced; the value is discarded. The seeded users (`alice`, `bob`,
  `carol`, `dave`, one of them pre-locked) are records, not accounts.
- **No template engine, no ORM, no JWT.** The session is a token the server
  handed out and can revoke by forgetting it — a tutorial target that signs
  tokens teaches the wrong thing about where authority comes from.
