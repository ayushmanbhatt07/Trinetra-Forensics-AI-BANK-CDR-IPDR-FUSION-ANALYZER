import threading
import time
import logging
import uuid
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from backend import store
from backend import config

import logging

_log = logging.getLogger(__name__)

class PipelineOrchestrator:
    def __init__(self):
        self._lock = threading.Lock()
        # Single bounded executor to prevent spawning multiple threads or processing simultaneously.
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._active_job = None
        self._load_active_job()

    def _load_active_job(self):
        job = store.get_active_pipeline_job()
        if job and job["status"] not in ("READY", "ERROR", "CANCELLED"):
            # If the server restarted during processing, transition it to ERROR or CANCELLED
            # because we cannot magically resume ThreadPoolExecutor jobs after a crash.
            job["status"] = "ERROR"
            job["error_message"] = "Server restarted during processing. Job cancelled."
            store.save_pipeline_job(job)
            self._active_job = job
        else:
            self._active_job = job

    def start_pipeline(self, bundle: dict) -> dict:
        """Initialize the pipeline job, persist it, and submit the background task."""
        with self._lock:
            # Check if there's already an active job running to prevent concurrent dupes
            if self._active_job and self._active_job["status"] not in ("READY", "ERROR", "CANCELLED"):
                return self._active_job

            dataset_id = str(uuid.uuid4())
            job_id = f"job-{dataset_id}"
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            job = {
                "job_id": job_id,
                "dataset_id": dataset_id,
                "status": "PARSING",
                "stage": "PARSING",
                "progress": 10,
                "started_at": now,
                "updated_at": now,
                "completed_at": None,
                "error_message": None,
                "fused_ready": False,
                "anomalies_ready": False,
                "graphs_ready": False
            }
            self._active_job = job
            store.save_pipeline_job(job)
            self._executor.submit(self._run_pipeline, bundle, job_id)
            return job
            
    def reset(self):
        with self._lock:
            if self._active_job and self._active_job["status"] not in ("READY", "ERROR", "CANCELLED"):
                self._active_job["status"] = "CANCELLED"
                self._active_job["error_message"] = "Job cancelled due to session reset."
                store.save_pipeline_job(self._active_job)
            self._active_job = None

    def get_status(self) -> dict:
        """Returns the current pipeline status with per-stage result availability."""
        from .api import _state
        b = _state.get("bundle")
        has_bundle = b is not None and bool(b.get("bank") or b.get("cdr") or b.get("ipdr"))
        
        with self._lock:
            if not self._active_job:
                return {
                    "job_id": None,
                    "dataset_id": "restored_session" if has_bundle else None,
                    "status": "READY" if has_bundle else "IDLE",
                    "stage": "READY" if has_bundle else "IDLE",
                    "progress": 100 if has_bundle else 0,
                    "fused_ready": has_bundle,
                    "anomalies_ready": has_bundle,
                    "graphs_ready": has_bundle,
                    "ready": has_bundle,
                    "error": None,
                    # Per-stage result availability for the frontend
                    "stages": {
                        "ingestion": {"status": "completed" if has_bundle else "pending", "result_available": has_bundle},
                        "fusion": {"status": "completed" if has_bundle else "pending", "result_available": has_bundle},
                        "scoring": {"status": "completed" if has_bundle else "pending", "result_available": has_bundle},
                        "anomalies": {"status": "completed" if has_bundle else "pending", "result_available": has_bundle},
                        "graphs": {"status": "completed" if has_bundle else "pending", "result_available": has_bundle},
                    }
                }
            
            job = self._active_job.copy()
            
            # If a bundle is successfully loaded into memory, the data is available for the UI
            # even if the last tracked pipeline job was cancelled or errored out.
            if has_bundle and job["status"] in ("READY", "ERROR", "CANCELLED"):
                job["fused_ready"] = True
                job["anomalies_ready"] = True
                job["graphs_ready"] = True
                job["ready"] = True

            fused_ready = job["fused_ready"]
            anomalies_ready = job["anomalies_ready"]
            graphs_ready = job["graphs_ready"]
            is_ready = job.get("ready", job["status"] == "READY")
            stage = job["status"]

            def _stage_status(completed: bool, active_stages: list) -> str:
                if completed: return "completed"
                if stage in active_stages: return "running"
                return "pending"

            return {
                "job_id": job["job_id"],
                "dataset_id": job["dataset_id"],
                "status": stage,
                "stage": job["stage"],
                "progress": job["progress"],
                "fused_ready": fused_ready,
                "anomalies_ready": anomalies_ready,
                "graphs_ready": graphs_ready,
                "ready": is_ready,
                "error": job["error_message"],
                # Per-stage result availability for frontend stage-aware queries
                "stages": {
                    "ingestion": {
                        "status": "completed",
                        "result_available": has_bundle,
                    },
                    "fusion": {
                        "status": _stage_status(fused_ready, ["FUSING"]),
                        "result_available": fused_ready,
                    },
                    "scoring": {
                        "status": _stage_status(anomalies_ready, ["SCORING"]),
                        "result_available": anomalies_ready,
                    },
                    "anomalies": {
                        "status": _stage_status(anomalies_ready, ["SCORING"]),
                        "result_available": anomalies_ready,
                    },
                    "graphs": {
                        "status": _stage_status(graphs_ready, ["GRAPHS"]),
                        "result_available": graphs_ready,
                    },
                }
            }


    def _update_job(self, job_id: str, updates: dict):
        with self._lock:
            if self._active_job and self._active_job["job_id"] == job_id:
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                self._active_job.update(updates)
                self._active_job["updated_at"] = now
                store.save_pipeline_job(self._active_job)

    def _run_pipeline(self, bundle: dict, job_id: str):
        """The actual background processing stage machine."""
        t0 = time.time()
        try:
            # We must import these here to avoid circular imports during init
            from backend.fusion import cached_fused_base, cached_build_timeline
            from backend.graphs import cached_money_graph, cached_account_phone_graph, cached_phone_call_graph
            import backend.risk.hybrid as hybrid
            
            self._update_job(job_id, {
                "status": "FUSING",
                "stage": "FUSING",
                "progress": 25
            })
            _log.info(f"[PIPELINE] job={job_id} stage=FUSING")
            
            # Step 1: Fusion
            cached_fused_base(bundle)
            cached_build_timeline(bundle)
            
            self._update_job(job_id, {
                "status": "FUSED_READY",
                "stage": "FUSED_READY",
                "progress": 40,
                "fused_ready": True
            })
            _log.info(f"[PIPELINE] job={job_id} stage=FUSED_READY elapsed={time.time() - t0:.2f}s")
            
            # Step 2: Scoring
            self._update_job(job_id, {
                "status": "SCORING",
                "stage": "SCORING",
                "progress": 50
            })
            _log.info(f"[PIPELINE] job={job_id} stage=SCORING")
            
            hybrid.hybrid_analyze(bundle)
            
            self._update_job(job_id, {
                "status": "ANOMALIES_READY",
                "stage": "ANOMALIES_READY",
                "progress": 75,
                "anomalies_ready": True
            })
            _log.info(f"[PIPELINE] job={job_id} stage=ANOMALIES_READY elapsed={time.time() - t0:.2f}s")
            
            # Step 3: Graphs
            self._update_job(job_id, {
                "status": "GRAPHS",
                "stage": "GRAPHS",
                "progress": 85
            })
            _log.info(f"[PIPELINE] job={job_id} stage=GRAPHS")
            
            cached_money_graph(bundle)
            cached_account_phone_graph(bundle)
            cached_phone_call_graph(bundle)
            
            # Final Step: Ready
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._update_job(job_id, {
                "status": "READY",
                "stage": "READY",
                "progress": 100,
                "graphs_ready": True,
                "completed_at": now
            })
            _log.info(f"[PIPELINE] job={job_id} stage=READY total_elapsed={time.time() - t0:.2f}s")
            
        except Exception as e:
            _log.exception(f"[PIPELINE] job={job_id} ERROR: {e}")
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._update_job(job_id, {
                "status": "ERROR",
                "stage": "ERROR",
                "error_message": str(e),
                "completed_at": now
            })

orchestrator = PipelineOrchestrator()
