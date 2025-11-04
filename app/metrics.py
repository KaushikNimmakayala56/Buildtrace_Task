from datetime import datetime
from typing import Dict, Any, Optional

class Metrics:
    def __init__(self):
        self.jobs = {}
        self.durations = []  # For percentile calculation

    def mark_start(self, job_id: str):
        self.jobs[job_id] = {
            "start_time": datetime.now(),
            "status": "running"
        }

    def mark_end(self, job_id: str, ok: bool, result: Optional[Dict] = None):
        end_time = datetime.now()
        if job_id in self.jobs:
            start_time = self.jobs[job_id]["start_time"]
            duration = (end_time - start_time).total_seconds()
            self.durations.append(duration)
            
            # FIX 4: Prevent memory leak - keep only last 1000
            if len(self.durations) > 1000:
                self.durations = self.durations[-1000:]
            
            self.jobs[job_id].update({
                "end_time": end_time.isoformat(),
                "status": "success" if ok else "failed",
                "duration": duration
            })
            
            if ok and result:
                self.jobs[job_id].update({
                    "added_count": len(result.get("added", [])),
                    "removed_count": len(result.get("removed", [])),
                    "moved_count": len(result.get("moved", []))
                })
        else:
            self.jobs[job_id] = {
                "end_time": end_time.isoformat(),
                "status": "success" if ok else "failed"
            }

    def _percentile(self, p: float, values: list) -> float:
        # FIX 2: Correct percentile calculation (off-by-one fix)
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = max(0, int((p / 100) * len(sorted_vals)) - 1)
        return sorted_vals[idx]

    def snapshot(self) -> Dict[str, Any]:
        success_count = sum(1 for j in self.jobs.values() if j.get("status") == "success")
        failed_count = sum(1 for j in self.jobs.values() if j.get("status") == "failed")
        running_count = sum(1 for j in self.jobs.values() if j.get("status") == "running")
        
        total_added = sum(j.get("added_count", 0) for j in self.jobs.values())
        total_removed = sum(j.get("removed_count", 0) for j in self.jobs.values())
        total_moved = sum(j.get("moved_count", 0) for j in self.jobs.values())
        
        # FIX 3: Better field names
        return {
            "p50": round(self._percentile(50, self.durations), 2),
            "p95": round(self._percentile(95, self.durations), 2),
            "p99": round(self._percentile(99, self.durations), 2),
            "jobs_total": len(self.jobs),
            "jobs_success": success_count,
            "jobs_failed": failed_count,
            "jobs_running": running_count,
            "total_objects_added": total_added,
            "total_objects_removed": total_removed,
            "total_objects_moved": total_moved
        }

METRICS = Metrics()