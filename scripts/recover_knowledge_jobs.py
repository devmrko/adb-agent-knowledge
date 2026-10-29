"""Manual crash recovery. Stop every worker before invoking this operation."""

import argparse

from sqlalchemy import update

from knowledge_app.database import database
from knowledge_app.models import Job
from knowledge_app.settings import Settings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--workers-stopped", action="store_true", required=True)
parser.add_argument("--job-id", required=True)
args = parser.parse_args()
engine = database(Settings())
try:
    with engine.begin() as con:
        result = con.execute(
            update(Job)
            .where(Job.id == args.job_id, Job.status == "RUNNING")
            .values(status="QUEUED", stage="WAITING", error_code=None)
        )
        print("Recovered jobs:", result.rowcount)
finally:
    engine.dispose()
