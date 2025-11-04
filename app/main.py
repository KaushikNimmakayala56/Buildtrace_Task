import os, json, uuid, traceback
from typing import Dict, Any, List
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import storage, pubsub_v1
from google.api_core.exceptions import NotFound
from app.diff import diff
from app.metrics import METRICS

PROJECT_ID = os.environ.get("PROJECT_ID")
TOPIC_ID   = os.environ.get("TOPIC_ID", "bt-jobs")
DLQ_TOPIC  = f"{TOPIC_ID}-dlq"
BUCKET     = os.environ.get("BUCKET")  # gs://<bucket>
SERVICE_URL= os.environ.get("SERVICE_URL")  # https://<run>/worker (for docs)

# Anomaly detection thresholds (configurable)
FAILURE_RATE_THRESHOLD = float(os.environ.get("FAILURE_RATE_THRESHOLD", "0.1"))  # 10%
STALLED_JOBS_THRESHOLD = float(os.environ.get("STALLED_JOBS_THRESHOLD", "0.2"))  # 20%
SPIKE_MULTIPLIER = float(os.environ.get("SPIKE_MULTIPLIER", "10.0"))  # 10x

if not PROJECT_ID or not BUCKET:
    raise RuntimeError("Set env: PROJECT_ID, BUCKET (and optionally TOPIC_ID, SERVICE_URL)")

app = FastAPI(title="BuildTrace Challenge")

# Mount static files for dashboard
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

gcs = storage.Client()
pub = pubsub_v1.PublisherClient()
topic_path = pub.topic_path(PROJECT_ID, TOPIC_ID)

def parse_gs_uri(uri: str):
    assert uri.startswith("gs://")
    _, rest = uri.split("://", 1)
    bucket, *path = rest.split("/", 1)
    return bucket, (path[0] if path else "")

def read_json_gcs(gs_uri: str) -> Any:
    bkt, path = parse_gs_uri(gs_uri)
    blob = gcs.bucket(bkt).blob(path)
    data = blob.download_as_text()
    return json.loads(data)

def write_json_gcs(gs_uri: str, payload: Any):
    bkt, path = parse_gs_uri(gs_uri)
    blob = gcs.bucket(bkt).blob(path)
    blob.upload_from_string(json.dumps(payload, ensure_ascii=False), content_type="application/json")

@app.get("/dashboard")
def dashboard():
    """Redirect to dashboard HTML page."""
    return RedirectResponse(url="/static/dashboard.html")

@app.get("/metrics")
def metrics():
    return METRICS.snapshot()

@app.get("/changes")
def get_changes(drawing_id: str = Query(..., description="Drawing ID to retrieve changes for")):
    """Retrieve detected changes for a specific drawing."""
    try:
        out_uri = f"{BUCKET.rstrip('/')}/results/{drawing_id}.json" if BUCKET.startswith("gs://") else f"gs://{BUCKET}/results/{drawing_id}.json"
        result = read_json_gcs(out_uri)
        return result
    except NotFound:
        raise HTTPException(404, f"Results not found for drawing_id={drawing_id}")
    except Exception as e:
        raise HTTPException(500, f"Error reading results: {str(e)}")

@app.get("/dlq")
def view_dlq():
    """Check dead-letter queue status."""
    try:
        dlq_path = pub.topic_path(PROJECT_ID, DLQ_TOPIC)
        pub.get_topic(request={"topic": dlq_path})
        return {
            "dlq_topic": DLQ_TOPIC,
            "status": "configured",
            "note": "Use gcloud to view messages: gcloud pubsub subscriptions pull dlq-sub --topic bt-jobs-dlq"
        }
    except NotFound:
        return JSONResponse({"status": "not_configured", "dlq_topic": DLQ_TOPIC}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/health")
def health():
    """Health check with anomaly detection."""
    snapshot = METRICS.snapshot()
    alerts = []
    
    jobs_total = snapshot.get("jobs_total", 0)
    jobs_failed = snapshot.get("jobs_failed", 0)
    jobs_running = snapshot.get("jobs_running", 0)
    jobs_success = snapshot.get("jobs_success", 0)
    
    if jobs_total > 0:
        failure_rate = jobs_failed / jobs_total
        if failure_rate > FAILURE_RATE_THRESHOLD:
            alerts.append(f"High failure rate: {failure_rate*100:.1f}%")
        
        running_rate = jobs_running / jobs_total
        if running_rate > STALLED_JOBS_THRESHOLD:
            alerts.append(f"High stalled jobs: {running_rate*100:.1f}%")
    
    if jobs_success > 0:
        total_added = snapshot.get("total_objects_added", 0)
        avg_added = total_added / jobs_success
        
        jobs = METRICS.jobs
        completed_jobs = [j for j in jobs.values() if j.get("status") == "success" and "end_time" in j]
        if completed_jobs:
            most_recent = max(completed_jobs, key=lambda j: j.get("end_time", ""))
            last_added = most_recent.get("added_count", 0)
            
            if avg_added > 0 and last_added > SPIKE_MULTIPLIER * avg_added:
                alerts.append(f"Spike detected: last job has {last_added} additions vs {avg_added:.1f} average")
    
    success_rate = (jobs_success / jobs_total * 100) if jobs_total > 0 else 0.0
    
    return {
        "status": "healthy" if not alerts else "degraded",
        "alerts": alerts,
        "metrics_summary": {
            "total_jobs": jobs_total,
            "success_rate": f"{success_rate:.1f}%",
            "p99_latency_ms": round(snapshot.get("p99", 0) * 1000, 2)
        }
    }

@app.post("/process")
async def process(manifest: Dict[str, Any]):
    """
    manifest: { "pairs": [ {"id":"HPI-L3-0001", "a":"gs://bucket/inputs/HPI-L3-0001_A.json", "b":"gs://bucket/inputs/HPI-L3-0001_B.json"}, ... ] }
    """
    pairs: List[Dict[str, str]] = manifest.get("pairs", [])
    if not pairs:
        raise HTTPException(400, "No pairs provided")
    published = 0
    for p in pairs:
        job_id = p.get("id") or str(uuid.uuid4())
        data = json.dumps({"job_id": job_id, "a": p["a"], "b": p["b"]}).encode("utf-8")
        pub.publish(topic_path, data)
        published += 1
        METRICS.mark_start(job_id)
    return {"enqueued": published, "topic": TOPIC_ID, "push_subscription_url": SERVICE_URL or "set SERVICE_URL for docs"}

@app.post("/worker")  # Pub/Sub push endpoint
async def worker(request: Request):
    try:
        envelope = await request.json()
        msg_data = envelope["message"]["data"]
        payload = json.loads(bytes.fromhex("") if False else __import__("base64").b64decode(msg_data).decode("utf-8"))
        job_id, a_uri, b_uri = payload["job_id"], payload["a"], payload["b"]
        a = read_json_gcs(a_uri)
        b = read_json_gcs(b_uri)
        result = diff(a, b) 
        out_uri = f"{BUCKET.rstrip('/')}/results/{job_id}.json" if BUCKET.startswith("gs://") else f"gs://{BUCKET}/results/{job_id}.json"
        write_json_gcs(out_uri, result)
        METRICS.mark_end(job_id, ok=True, result=result)
        return JSONResponse({"status": "ok", "job_id": job_id})
    except Exception as e:
        # Best-effort: mark failure for last job in envelope (if any)
        try:
            payload = json.loads(__import__("base64").b64decode((await request.json())["message"]["data"]).decode("utf-8"))
            METRICS.mark_end(payload.get("job_id","unknown"), ok=False)
        except Exception:
            pass
        print("Worker error:", e, traceback.format_exc(), flush=True)
        # Return 500 to trigger retry, then dead-letter queue after max attempts
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)
