from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app.db import models
from app.db.base import Base
from app.db.session import SessionLocal, engine


def claim_job(db, worker_id: str) -> models.Job | None:
    now = datetime.now(timezone.utc)
    job = db.execute(
        select(models.Job)
        .where(
            (models.Job.status == "queued")
            | (
                (models.Job.status == "running")
                & (models.Job.lease_expires_at < now)
            )
        )
        .order_by(models.Job.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if not job:
        return None
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.error = "max_attempts_exceeded"
        db.commit()
        return None
    job.status = "running"
    job.lease_owner = worker_id
    job.lease_expires_at = now + timedelta(minutes=5)
    job.attempts += 1
    db.commit()
    return job


def process_job(db, job: models.Job) -> None:
    # Process outbox-linked lightweight jobs
    if job.kind == "process_outbox":
        events = db.execute(
            select(models.OutboxEvent).where(models.OutboxEvent.status == "pending").limit(20)
        ).scalars().all()
        for ev in events:
            ev.status = "processed"
        job.status = "succeeded"
    else:
        job.status = "succeeded"
    db.commit()


def main() -> None:
    Base.metadata.create_all(bind=engine)
    worker_id = f"worker-{uuid.uuid4().hex[:8]}"
    print(f"FieldSense worker started: {worker_id}")
    while True:
        with SessionLocal() as db:
            # enqueue a heartbeat outbox processor if idle
            pending = db.execute(
                select(models.OutboxEvent).where(models.OutboxEvent.status == "pending").limit(1)
            ).scalar_one_or_none()
            if pending:
                existing = db.execute(
                    select(models.Job).where(
                        models.Job.kind == "process_outbox",
                        models.Job.status.in_(["queued", "running"]),
                    )
                ).scalar_one_or_none()
                if not existing:
                    db.add(
                        models.Job(
                            kind="process_outbox",
                            payload={},
                            idempotency_key=f"outbox-{uuid.uuid4().hex}",
                        )
                    )
                    db.commit()
            job = claim_job(db, worker_id)
            if job:
                try:
                    process_job(db, job)
                    print(f"processed {job.id} ({job.kind})")
                except Exception as exc:  # noqa: BLE001
                    job.status = "failed"
                    job.error = str(exc)
                    db.commit()
                    print(f"failed {job.id}: {exc}")
            else:
                time.sleep(2)


if __name__ == "__main__":
    main()
