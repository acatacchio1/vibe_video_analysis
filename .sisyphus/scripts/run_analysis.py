#!/usr/bin/env python3
import sys
import json
import eventlet
eventlet.monkey_patch()

import time
import requests
from socketio import Client

URL = "http://127.0.0.1:10000"
VIDEO_PATH = "YTDown.com_YouTube_Squirrel-dropkicks-groundhog_Media_B7zDTlQP1-o_002_720p.mp4"
MODEL = "qwen3-27b-q8"
PROVIDER_TYPE = "litellm"
FPM = 10

state = {
    "job_id": None,
    "job_created_received": False,
    "job_complete_received": False,
    "success": False,
    "frame_count": 0,
    "stage": "pending",
    "progress": 0,
    "errors": [],
    "start_time": None,
}

sio = Client()

def log(msg):
    print(msg, flush=True)

def is_my_job(data):
    jid = data.get("job_id")
    return state["job_id"] is None or jid == state["job_id"]

def on_job_created(data):
    jid = data.get("job_id")
    if jid:
        state["job_id"] = jid
        state["job_created_received"] = True
        log(f"\n{'='*60}")
        log(f"JOB CREATED: {jid}")
        log(f"{'='*60}")

def on_error(data):
    msg = data.get("message", "Unknown error")
    state["errors"].append(msg)
    log(f"ERROR: {msg}")

def on_job_status(data):
    if is_my_job(data):
        stage = data.get("stage", "?")
        progress = data.get("progress", 0)
        current = data.get("current_frame", 0)
        total = data.get("total_frames", 0)
        state["stage"] = stage
        state["progress"] = progress
        if total:
            log(f"[{stage}] {current}/{total} frames ({progress:.1f}%)")

def on_frame_analysis(data):
    if is_my_job(data):
        state["frame_count"] += 1
        fn = data.get("frame_number", "?")
        ts = data.get("timestamp", "?")
        analysis = data.get("analysis", "")
        preview = analysis[:80] if analysis else "(empty)"
        log(f"[FRAME {fn}] ts={ts}s: {preview}...")

def on_frame_synthesis(data):
    if is_my_job(data):
        fn = data.get("frame_number", "?")
        combined = data.get("combined_analysis", "")
        preview = combined[:80] if combined else "(empty)"
        log(f"[SYNTHESIS {fn}]: {preview}...")

def on_job_transcript(data):
    if is_my_job(data):
        transcript = data.get("transcript", "")
        preview = transcript[:200] if transcript else "(empty)"
        log(f"[TRANSCRIPT]: {preview}...")

def on_job_description(data):
    if is_my_job(data):
        desc = data.get("description", "")
        preview = desc[:200] if desc else "(empty)"
        log(f"[DESCRIPTION]: {preview}...")

def on_job_complete(data):
    if is_my_job(data):
        success = data.get("success", False)
        state["job_complete_received"] = True
        state["success"] = success
        elapsed = time.time() - state["start_time"] if state["start_time"] else 0
        log(f"\n{'='*60}")
        log(f"JOB COMPLETE: {data.get('job_id')}")
        log(f"Success: {success}")
        log(f"Frames analyzed: {state['frame_count']}")
        log(f"Elapsed: {elapsed:.1f}s ({elapsed/60:.1f}min)")
        log(f"{'='*60}")

log("Connecting to SocketIO...")
sio.on("connect", lambda: log("Connected!"))
sio.on("disconnect", lambda: log("Disconnected"))
sio.on("job_created", on_job_created)
sio.on("job_complete", on_job_complete)
sio.on("job_status", on_job_status)
sio.on("frame_analysis", on_frame_analysis)
sio.on("frame_synthesis", on_frame_synthesis)
sio.on("job_transcript", on_job_transcript)
sio.on("job_description", on_job_description)
sio.on("error", on_error)

sio.connect(URL, wait_timeout=15)
if not sio.connected:
    log("FATAL: Failed to connect to SocketIO")
    sys.exit(1)

params = {
    "fps": 30.0,
    "frames_per_minute": FPM,
    "similarity_threshold": 0.6,
    "temperature": 0.0,
    "prompt": "",
    "whisper_model": "large",
    "language": "en",
    "pipeline_type": "standard_two_step",
}
payload = {
    "video_path": VIDEO_PATH,
    "provider_type": PROVIDER_TYPE,
    "provider_name": PROVIDER_TYPE,
    "model": MODEL,
    "priority": 5,
    "provider_config": {},
    "params": params,
}

log(f"Starting analysis: {MODEL} on {VIDEO_PATH}")
log(f"Frames per minute: {FPM}")
state["start_time"] = time.time()

sio.emit("start_analysis", payload)

log("Waiting for job creation confirmation...")
wait_start = time.time()
while not state["job_created_received"]:
    eventlet.sleep(1)
    elapsed = time.time() - wait_start
    if elapsed >= 300:
        break
    if elapsed % 10 < 2:
        log(f"  Still waiting... ({int(elapsed)}s)")

if not state["job_created_received"]:
    log("FATAL: Timed out waiting for job creation")
    sio.disconnect()
    sys.exit(1)

log(f"Job {state['job_id']} submitted. Monitoring progress...")
sio.emit("subscribe_job", {"job_id": state["job_id"]})
eventlet.sleep(1)

monitor_start = time.time()
while not state["job_complete_received"]:
    eventlet.sleep(5)
    elapsed = time.time() - monitor_start
    if elapsed >= 18000:
        break
    if (elapsed // 150) > ((elapsed - 5) // 150):
        log(f"  Still running... ({int(elapsed)}s | {state['frame_count']} frames | stage: {state['stage']})")

if not state["job_complete_received"]:
    log("WARNING: Timed out before job completion. Job may still be running.")
    job_id = state["job_id"]
    for attempt in range(12):
        try:
            r = requests.get(f"{URL}/api/jobs/{job_id}")
            if r.status_code == 200:
                jdata = r.json()
                jstatus = jdata.get("status", "unknown")
                log(f"REST API status: {jstatus}")
                if jstatus in ("completed", "failed", "cancelled"):
                    state["job_complete_received"] = True
                    state["success"] = (jstatus == "completed")
                    break
            eventlet.sleep(5)
        except Exception:
            break

sio.disconnect()
eventlet.sleep(2)

log(f"\n--- FINAL SUMMARY ---")
log(f"Job ID     : {state['job_id']}")
log(f"Status     : {'COMPLETED' if state['success'] else 'FAILED/INCOMPLETE'}")
log(f"Frames     : {state['frame_count']}")
log(f"Stage      : {state['stage']}")
if state["errors"]:
    log(f"Errors     : {state['errors']}")
elapsed = time.time() - state["start_time"] if state["start_time"] else 0
log(f"Elapsed    : {elapsed:.1f}s ({elapsed/60:.1f}min)")

try:
    r = requests.get(f"{URL}/api/jobs/{state['job_id']}")
    if r.status_code == 200:
        jdata = r.json()
        log(f"REST status: {jdata.get('status')}")
        log(f"REST exit_code: {jdata.get('exit_code')}")
except Exception as e:
    log(f"REST poll failed: {e}")

with open("/home/anthony/video-analyzer-web/.sisyphus/evidence/task-11-state.json", "w") as f:
    json.dump(state, f, indent=2)

log(f"\nState saved to .sisyphus/evidence/task-11-state.json")
