"""Ports for durable jobs; no in-process function is advertised as durable work."""

from dataclasses import dataclass
from typing import Protocol

from python_foundation.security import Actor


@dataclass(frozen=True)
class JobReceipt:
    id: str
    status: str


class DurableJobs(Protocol):
    """Consumer-supplied durable adapter.

    Implementations must persist before returning, bound queued/running capacity,
    scope idempotency keys by actor/operation, reject payload changes for reused keys,
    and define replay/fencing/retry policy. Never persist access tokens.
    Submission alone is not atomic with the caller's transaction: use an outbox when needed.
    """

    def submit(self, kind: str, payload: str, *, key: str, actor: Actor) -> JobReceipt: ...
    def find(self, job_id: str, *, actor: Actor) -> JobReceipt | None: ...
