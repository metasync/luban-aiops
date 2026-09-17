"""`acme-admin` — the tutorial target for the SPEC-059 sample suite.

A small FastAPI user-administration console: a health API, a service API, an
operator login, a user list carrying real status and modification state, and
real lock/unlock and password-reset mutations. State is in memory
(`store.STORE`) so nothing needs provisioning.
"""

__version__ = "0.1.0"

SERVICE_NAME = "acme-admin"
