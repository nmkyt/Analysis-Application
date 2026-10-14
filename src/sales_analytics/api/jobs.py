"""Фоновые задачи: обучение и выгрузка идут минутами, HTTP-запрос их не ждёт.

Задача выполняется в отдельном потоке, статус хранится в памяти процесса
и пропадает при перезапуске API. Одновременно идёт не больше одной задачи каждого вида.
"""
import threading
import uuid
from datetime import datetime

from .schemas import Job, JobStatus


class JobConflict(Exception):
    """Задача этого вида уже выполняется."""


class JobRegistry:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, func) -> Job:
        """Запускает func() в отдельном потоке; результат func (словарь) попадает в Job.result."""
        with self._lock:
            running = [job for job in self._jobs.values() if job.kind == kind and job.status is JobStatus.running]
            if running:
                raise JobConflict(f'Задача {kind} уже выполняется: {running[0].id}')
            job = Job(id=uuid.uuid4().hex[:12], kind=kind, started_at=datetime.now())
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job, func), daemon=True).start()
        return job.model_copy()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy() if job else None

    def list(self) -> list[Job]:
        with self._lock:
            return [job.model_copy() for job in sorted(self._jobs.values(), key=lambda job: job.started_at)]

    def _run(self, job: Job, func):
        try:
            result, error, status = func(), None, JobStatus.done
        except Exception as e:  # ошибка задачи не должна останавливать API, она попадает в статус
            result, error, status = None, str(e) or type(e).__name__, JobStatus.failed
        with self._lock:
            job.result, job.error, job.status, job.finished_at = result, error, status, datetime.now()
