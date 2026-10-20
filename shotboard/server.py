"""Local-only API. All inference submissions and output retrieval use Comfy SDK."""
from contextlib import asynccontextmanager
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import queue
import threading
import time
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from comfy_sdk import Comfy
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
import httpx
from PIL import Image
from pydantic import BaseModel, Field

from .core import (ROOT, PRESETS, LENSES, ANGLES, MOVES, LIGHTS, LOOKS,
                   expand_shots, seed_for, workflow_for, export_board, sha256)

DATA = Path(os.environ.get("SHOTBOARD_DATA_DIR", ROOT / ".runtime/boards"))
MODEL_DIR = Path(os.environ.get("SHOTBOARD_MODEL_DIR", ROOT / ".runtime/models/checkpoints"))
SDK_URL = os.environ.get("COMFY_BASE_URL", "http://127.0.0.1:8189")
if urlparse(SDK_URL).hostname not in ("127.0.0.1", "localhost", "::1") or urlparse(SDK_URL).scheme != "http":
    raise RuntimeError("Shot Board only accepts a local HTTP Comfy proxy.")
os.environ["COMFY_BASE_URL"] = SDK_URL
os.environ.pop("COMFY_API_KEY", None)
for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(key, None)
os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
TERMINAL = {"succeeded", "failed", "cancelled", "canceled", "expired", "error"}


class Scene(BaseModel):
    scene: str = Field(min_length=3, max_length=600)
    character: str = Field(default="An adult traveler with short dark hair, mustard raincoat, brown satchel", min_length=3, max_length=400)
    setting: str = Field(default="A quiet glass greenhouse, ferns, rain on windows, wooden potting table", min_length=3, max_length=400)
    lens: Literal["24", "35", "50", "85"] = "35"
    angle: Literal["Eye level", "Low angle", "High angle"] = "Eye level"
    move: Literal["Static", "Push in", "Lateral drift"] = "Static"
    lighting: Literal["Window light", "Blue hour", "Hard rim", "Practical tungsten"] = "Window light"
    look: Literal["Muted film", "Warm grain", "Cool chrome", "Monochrome"] = "Muted film"
    count: int = Field(default=6, ge=6, le=9)
    seed: int = Field(default=20261020, ge=0, le=2**32-1)
    preset: Literal["sdxl-base"] = "sdxl-base"


class ShotEdit(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=3, max_length=4000)
    negative: str = Field(max_length=1000)


class Generate(BaseModel):
    takes: int = Field(default=2, ge=1, le=4)
    shot_id: str | None = None


class Pick(BaseModel):
    take_id: str


class SeedLock(BaseModel):
    seed: int | None = Field(default=None, ge=0, le=2**32-1)


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.boards = {}
        self.tasks = queue.Queue()
        self.stop = threading.Event()
        self.thread = None
        self.active_job = None

    def save(self, board):
        dest = DATA / board["id"] / "board.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.with_suffix(".tmp")
        temp.write_text(json.dumps(board, indent=2) + "\n")
        temp.replace(dest)

    def start(self):
        DATA.mkdir(parents=True, exist_ok=True)
        for path in DATA.glob("*/board.json"):
            board = json.loads(path.read_text())
            for shot in board["shots"]:
                for take in shot["takes"]:
                    if take["status"] in ("queued", "running"):
                        take.update(status="interrupted", error="Server restarted. Review before generating again.")
            self.boards[board["id"]] = board
            self.save(board)
        self.stop.clear()
        self.thread = threading.Thread(target=self.work, daemon=True)
        self.thread.start()

    def work(self):
        while not self.stop.is_set():
            try:
                bid, sid, tid = self.tasks.get(timeout=0.5)
            except queue.Empty:
                continue
            with self.lock:
                board = self.boards[bid]
                shot = next(s for s in board["shots"] if s["id"] == sid)
                take = next(t for t in shot["takes"] if t["id"] == tid)
                if take["status"] != "queued":
                    self.tasks.task_done()
                    continue
                take.update(status="running", phase="Submitting through Comfy SDK", started_at=time.time())
                self.save(board)
            start = time.monotonic()
            job = None
            try:
                with Comfy(timeout=30) as client:
                    job = client.submit(client.workflows.from_json(take["workflow"]))
                    with self.lock:
                        self.active_job = job
                        take.update(job_id=job.id, phase="Waiting for local engine", engine_status=job.status)
                        self.save(board)
                    deadline = time.monotonic() + 1800
                    while job.status not in TERMINAL:
                        if self.stop.wait(1) or take.get("cancel_requested"):
                            job.cancel()
                            raise RuntimeError("Generation cancelled")
                        if time.monotonic() > deadline:
                            job.cancel()
                            raise TimeoutError("Local generation exceeded 30 minutes")
                        job.refresh()
                        with self.lock:
                            take.update(engine_status=job.status, phase="Local engine · " + job.status,
                                        elapsed_seconds=round(time.monotonic()-start, 2))
                    if job.status != "succeeded":
                        raise RuntimeError("Local engine did not complete the take")
                    outputs = job.get_outputs("7")
                    if len(outputs) != 1:
                        raise RuntimeError("Expected exactly one still")
                    relative = f"{sid}-{tid}.png"
                    dest = DATA / bid / relative
                    raw = dest.with_suffix(".download")
                    outputs[0].to_file(raw)
                    # Keep pixels, strip embedded workflow/system metadata before public export.
                    with Image.open(raw) as image:
                        image.convert("RGB").save(dest, format="PNG")
                    raw.unlink()
                    with self.lock:
                        take.update(status="succeeded", phase="Complete", image=relative,
                                    image_sha256=sha256(dest), elapsed_seconds=round(time.monotonic()-start, 3))
            except Exception as exc:
                if job is not None:
                    try:
                        if job.status not in TERMINAL:
                            job.cancel()
                    except Exception:
                        pass
                with self.lock:
                    # Do not expose engine exception bodies, credentials, or filesystem paths.
                    take.update(status="cancelled" if take.get("cancel_requested") or self.stop.is_set() else "failed",
                                error=f"{type(exc).__name__}: local generation stopped. Check the local engine and retry.",
                                elapsed_seconds=round(time.monotonic()-start, 3))
            finally:
                with self.lock:
                    self.active_job = None
                    self.save(board)
                self.tasks.task_done()


store = Store()


@asynccontextmanager
async def lifespan(app):
    store.start()
    yield
    store.stop.set()
    with store.lock:
        for board in store.boards.values():
            for shot in board["shots"]:
                for take in shot["takes"]:
                    if take["status"] == "queued":
                        take["status"] = "interrupted"
            store.save(board)
    store.thread.join(timeout=35)


app = FastAPI(title="Shot Board", lifespan=lifespan)


@app.middleware("http")
async def local_guard(request: Request, call_next):
    if request.url.hostname not in ("localhost", "127.0.0.1", "::1", "testserver"):
        return Response("Local access only", status_code=403)
    origin = request.headers.get("origin")
    if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
        return Response("Same-origin access only", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    return response


def board_for(bid):
    if bid not in store.boards:
        raise HTTPException(404, "Board not found")
    return store.boards[bid]


def shot_for(board, sid):
    shot = next((s for s in board["shots"] if s["id"] == sid), None)
    if shot is None:
        raise HTTPException(404, "Shot not found")
    return shot


@app.get("/api/config")
def config():
    return dict(lens=LENSES, angle=ANGLES, move=MOVES, lighting=LIGHTS, look=LOOKS, presets=PRESETS,
                reframe=dict(enabled=False, experimental=True))


@app.get("/api/health")
def health():
    try:
        with httpx.Client(trust_env=False, timeout=2) as client:
            # Connectivity only; generation never uses a direct ComfyUI API.
            response = client.get(SDK_URL + "/api/v2/jobs", params={"limit": 1})
        ready = response.status_code == 200
    except httpx.HTTPError:
        ready = False
    return dict(proxy_ready=ready, checkpoint_present=(MODEL_DIR / PRESETS["sdxl-base"]["checkpoint"]).is_file())


@app.get("/api/boards")
def list_boards():
    with store.lock:
        return [dict(id=b["id"], title=b["title"]) for b in reversed(list(store.boards.values()))]


@app.post("/api/boards", status_code=201)
def create_board(scene: Scene):
    with store.lock:
        config = scene.model_dump()
        board = dict(id=uuid4().hex, title=scene.scene[:80], config=config, shots=expand_shots(config), created_at=time.time())
        store.boards[board["id"]] = board
        store.save(board)
        return deepcopy(board)


@app.get("/api/boards/{bid}")
def get_board(bid: str):
    with store.lock:
        return deepcopy(board_for(bid))


@app.patch("/api/boards/{bid}/shots/{sid}")
def edit_shot(bid: str, sid: str, edit: ShotEdit):
    with store.lock:
        board = board_for(bid)
        shot_for(board, sid).update(edit.model_dump())
        store.save(board)
    return dict(ok=True)


@app.post("/api/boards/{bid}/generate", status_code=202)
def generate(bid: str, request: Generate):
    with store.lock:
        board = board_for(bid)
        shots = [shot_for(board, request.shot_id)] if request.shot_id else board["shots"]
        if any(t["status"] in ("queued", "running") for s in board["shots"] for t in s["takes"]):
            raise HTTPException(409, "This board already has work in the queue.")
        if any(len(s["takes"])+request.takes > 16 for s in shots):
            raise HTTPException(409, "Maximum 16 takes per shot. Create a new board for more coverage.")
        preset = deepcopy(PRESETS[board["config"]["preset"]])
        model = MODEL_DIR / preset["checkpoint"]
        if not model.is_file():
            raise HTTPException(409, "SDXL checkpoint missing. Follow the model setup in README.")
        digest = sha256(model)
        lock_path = ROOT / "workflows/model-lock.json"
        lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
        if lock.get("sha256") and digest != lock["sha256"]:
            raise HTTPException(409, "Model hash differs from the pinned checkpoint.")
        models = [dict(filename=preset["checkpoint"], sha256=digest, license=preset["license"],
                       repository=preset["repository"], revision=lock.get("revision"),
                       components=["SDXL UNet", "CLIP-L", "OpenCLIP bigG", "VAE (checkpoint embedded)"])]
        tasks = []
        for shot in shots:
            offset = len(shot["takes"])
            for i in range(request.takes):
                tid = f"t{offset+i+1:02}"
                seed = seed_for(board["config"]["seed"], offset+i, shot["locked_seed"])
                take = dict(id=tid, seed=seed, status="queued", phase="Queued locally", settings=preset,
                            models=models, workflow=workflow_for(shot, seed, preset), elapsed_seconds=0)
                shot["takes"].append(take)
                tasks.append((bid, shot["id"], tid))
        store.save(board)
        for task in tasks:
            store.tasks.put(task)
        return dict(queued=len(tasks))


@app.post("/api/boards/{bid}/cancel")
def cancel(bid: str):
    with store.lock:
        board = board_for(bid)
        for shot in board["shots"]:
            for take in shot["takes"]:
                if take["status"] == "queued":
                    take["status"] = "cancelled"
                elif take["status"] == "running":
                    take["cancel_requested"] = True
        store.save(board)
    return dict(ok=True)


@app.post("/api/boards/{bid}/shots/{sid}/pick")
def pick(bid: str, sid: str, request: Pick):
    with store.lock:
        board = board_for(bid)
        shot = shot_for(board, sid)
        if not any(t["id"] == request.take_id and t["status"] == "succeeded" for t in shot["takes"]):
            raise HTTPException(409, "Pick a completed take")
        shot["picked"] = request.take_id
        store.save(board)
    return dict(ok=True)


@app.post("/api/boards/{bid}/shots/{sid}/seed")
def lock_seed(bid: str, sid: str, request: SeedLock):
    with store.lock:
        board = board_for(bid)
        shot_for(board, sid)["locked_seed"] = request.seed
        store.save(board)
    return dict(ok=True)


@app.post("/api/boards/{bid}/shots/{sid}/reframe")
def reframe(bid: str, sid: str):
    with store.lock:
        shot = shot_for(board_for(bid), sid)
        if not shot["picked"]:
            raise HTTPException(409, "Pick a still before reframing")
    return dict(enabled=False, experimental=True, status="coming_soon",
                message="Reframe is coming soon: close-up and small parallax experiments.")


@app.get("/api/boards/{bid}/export")
def export(bid: str):
    with store.lock:
        try:
            data = export_board(board_for(bid), DATA)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    return Response(data, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="shot-board.zip"'})


@app.get("/api/boards/{bid}/images/{filename}")
def image(bid: str, filename: str):
    with store.lock:
        board = board_for(bid)
        if not any(t.get("image") == filename for s in board["shots"] for t in s["takes"]):
            raise HTTPException(404, "Image not found")
    return FileResponse(DATA / bid / filename)


@app.get("/")
def index():
    return FileResponse(ROOT / "shotboard/static/index.html")


app.mount("/static", StaticFiles(directory=ROOT / "shotboard/static"), name="static")
