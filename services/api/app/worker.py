"""Durable DB outbox worker for deterministic rendering only.

No paid AI submit is implemented: an unknown provider request cannot be retried.
"""
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from .config import settings
from .db import transaction
from .domain import settle
from .storage import local_path,upload

logging.basicConfig(level=logging.INFO)
log=logging.getLogger("studio.worker")
ROOT=Path(__file__).resolve().parents[3]

def claim():
    with transaction() as cur:
        # Expired render leases are never silently released or redispatched.
        cur.execute("UPDATE app_runs SET state='needs_reconciliation',error_code='WORKER_LEASE_EXPIRED' WHERE state='rendering' AND lease_until<now()")
        cur.execute("SELECT r.* FROM app_runs r JOIN app_outbox o ON o.run_id=r.id WHERE r.state='queued' ORDER BY r.created_at FOR UPDATE OF r SKIP LOCKED LIMIT 1")
        run=cur.fetchone()
        if not run:return None
        cur.execute("SELECT account_id FROM app_run_accounts WHERE run_id=%s AND account_id LIKE 'workspace:%%'",(run["id"],))
        period=cur.fetchone()
        if period and period["account_id"]!=f"workspace:{time.strftime('%Y-%m',time.gmtime())}":
            cur.execute("UPDATE app_runs SET cancel_requested=true,error_code='BUDGET_PERIOD_CHANGED' WHERE id=%s",(run["id"],))
            run["cancel_requested"]=True
        cur.execute("UPDATE app_runs SET state='rendering',lease_until=now()+interval '5 minutes' WHERE id=%s",(run["id"],))
        cur.execute("UPDATE app_outbox SET delivered_at=now() WHERE run_id=%s",(run["id"],))
        return run

def cancelled(run_id):
    with transaction() as cur:
        cur.execute("UPDATE app_runs SET lease_until=now()+interval '5 minutes' WHERE id=%s AND state='rendering' RETURNING cancel_requested",(run_id,))
        row=cur.fetchone()
        return not row or row["cancel_requested"]

class RenderCancelled(Exception):pass

def command(args,run_id,cwd=None):
    # Arguments are a list, never shell interpolation. Output written to scratch.
    with tempfile.TemporaryFile() as errors:
        proc=subprocess.Popen(args,cwd=cwd,stdout=subprocess.DEVNULL,stderr=errors)
        started=time.monotonic()
        try:
            while proc.poll() is None:
                if time.monotonic()-started>600:raise TimeoutError("Render timed out")
                if cancelled(run_id):raise RenderCancelled()
                time.sleep(.5)
            if proc.returncode:
                errors.seek(0)
                raise RuntimeError(errors.read(3000).decode(errors='replace'))
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()

def render(run):
    run_id=run["id"]
    if run["cancel_requested"]:raise RenderCancelled()
    doc=run["snapshot"]["document"]
    dims={"16:9":(1280,720),"9:16":(720,1280),"1:1":(1080,1080)}
    w,h=dims[doc["ratio"]]
    key=f"exports/{run_id}.mp4"
    target=local_path(key);target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="frame-") as temp:
        scratch=Path(temp)
        for i,scene in enumerate(doc["scenes"]):
            if cancelled(run_id):raise RenderCancelled()
            image=ROOT/"apps"/"web"/"public"/"art"/f"{scene['art']}.png"
            shutil.copyfile(image,scratch/f"{i}.png")
            # libass subtitles are loaded from a file and special chars are escaped.
            text=scene["script"].replace("\\","\\\\").replace("{","\\{").replace("}","\\}").replace("\n","\\N")
            duration=scene["duration"]
            ass=f"[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,DejaVu Sans,{max(22,w//40)},&H00FFFFFF,&H00FFFFFF,&H00223226,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,60,60,70,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:{duration:02d}.00,Default,,0,0,0,,{text}\n"
            (scratch/f"{i}.ass").write_text(ass,encoding="utf-8")
            filt=f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,crop={w*2}:{h*2},zoompan=z='min(zoom+0.00025,1.04)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={duration*24}:s={w}x{h}:fps=24,subtitles={i}.ass"
            command(["ffmpeg","-y","-i",f"{i}.png","-vf",filt,"-t",str(duration),"-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p",f"{i}.mp4"],run_id,scratch)
        (scratch/"files.txt").write_text("".join(f"file '{i}.mp4'\n" for i in range(len(doc["scenes"]))),encoding="utf-8")
        command(["ffmpeg","-y","-f","concat","-safe","0","-i","files.txt","-c","copy","-movflags","+faststart",str(target)],run_id,scratch)
        check=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","json",str(target)],capture_output=True,text=True,check=True,timeout=30)
        actual=float(json.loads(check.stdout)["format"]["duration"])
        expected=sum(s["duration"] for s in doc["scenes"])
        if abs(actual-expected)>1:raise RuntimeError("Output duration did not pass QC")
        if cancelled(run_id):raise RenderCancelled()
        upload(target,key)
    return key

def work_once():
    run=claim()
    if not run:return False
    try:
        key=render(run)
        tariff=sum(l["base_micro_usd"] for l in run["snapshot"]["lines"])
        settle(run["id"],tariff,"completed",key)
    except RenderCancelled:
        settle(run["id"],0,"cancelled",error_code="CANCELLED")
    except Exception:
        log.exception("Deterministic render failed for run %s",run["id"])
        # Render jobs bill the internal tariff only on success. No external AI was submitted.
        # If settlement fails too, hold remains until explicit reconciliation.
        settle(run["id"],0,"failed",error_code="RENDER_FAILED")
    return True

def main():
    while True:
        try:
            if not work_once():time.sleep(2)
        except Exception:
            log.exception("Worker iteration failed; hold preserved")
            time.sleep(5)

if __name__=="__main__":main()
