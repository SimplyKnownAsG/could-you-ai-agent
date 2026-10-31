"""In-process jobs shared by an agent and all of its descendants."""

import asyncio
import uuid
from collections.abc import Awaitable

from .cy_error import CYError, FaultOwner
from .logging_config import LOGGER


class SubagentJobs:
    def __init__(self):
        self.tasks: dict[str, asyncio.Task[str]] = {}
        self.closed = False

    def start(self, work: Awaitable[str]) -> str:
        if self.closed:
            work.close()
            raise CYError(message="Sub-agent jobs are closing", retriable=False, fault_owner=FaultOwner.INTERNAL)
        job_id = uuid.uuid4().hex
        task = asyncio.create_task(work)
        self.tasks[job_id] = task
        return job_id

    def poll(self, job_id: str) -> dict[str, str]:
        if not isinstance(job_id, str) or not job_id:
            raise CYError(message="Expected nonempty string 'job_id'", retriable=False, fault_owner=FaultOwner.LLM)
        task = self.tasks.get(job_id)
        if task is None:
            return {"status": "failed", "text": f"Unknown sub-agent job id: {job_id}"}
        if not task.done():
            return {"status": "pending"}
        try:
            return {"status": "succeeded", "text": task.result()}
        except asyncio.CancelledError:
            return {"status": "failed", "error": "Sub-agent job was cancelled"}
        except Exception as err:
            return {"status": "failed", "error": str(err)}

    async def close(self):
        self.closed = True
        # Cancelling a parent can start a descendant in its cancellation handler.
        # Repeat until every task in the shared registry has finished.
        while pending := [task for task in self.tasks.values() if not task.done()]:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        # Retrieve failures even when nobody polled the job.
        for job_id, task in self.tasks.items():
            if task.cancelled():
                continue
            error = task.exception()
            if error is not None:
                LOGGER.warning("Sub-agent job %s failed: %s", job_id, error)
