"""Local-only API. All inference submissions and output retrieval use Comfy SDK."""
from contextlib import asynccontextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
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

from .storyboard import storyboard_png
from .memory import MemoryGuard, MemorySafetyError

from .core import (ROOT, PRESETS, LENSES, ANGLES, MOVES, LIGHTS, LOOKS,
                   expand_shots, seed_for, workflow_for, settings_for, export_board, sha256)

DATA = Path(os.environ.get("SHOTBOARD_DATA_DIR", ROOT / ".runtime/boards"))
MODEL_DIR = Path(os.environ.get("SHOTBOARD_MODEL_DIR", ROOT / ".runtime/models/checkpoints"))
REFERENCE_MODEL_DIR = Path(os.environ.get("SHOTBOARD_REFERENCE_MODEL_DIR", ROOT.parent / "models"))
QWEN_MODEL_DIR = Path(os.environ.get("SHOTBOARD_QWEN_MODEL_DIR", ROOT / ".runtime/models/diffusion_models"))
# Optional private report copied over SSH after hashing the remote engine's files.
ENGINE_MANIFEST = os.environ.get("SHOTBOARD_ENGINE_MANIFEST")
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
    prop: str = Field(default="the scene's key object", min_length=3, max_length=160)
    lens: Literal["24", "35", "50", "85"] = "35"
    angle: Literal["Eye level", "Low angle", "High angle"] = "Eye level"
    move: Literal["Static", "Push in", "Lateral drift"] = "Static"
    lighting: Literal["Window light", "Blue hour", "Hard rim", "Practical tungsten"] = "Window light"
    look: Literal["Muted film", "Warm grain", "Cool chrome", "Monochrome"] = "Muted film"
    count: int = Field(default=6, ge=6, le=9)
    seed: int = Field(default=20261020, ge=0, le=2**32-1)
    preset: Literal["sdxl-base"] = "sdxl-base"


class RenderSettings(BaseModel):
    width: int = Field(ge=512, le=1536, multiple_of=64)
    height: int = Field(ge=512, le=1536, multiple_of=64)
    cfg: float = Field(ge=1, le=12)


class ShotEdit(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=3, max_length=4000)
    negative: str = Field(max_length=1000)
    render_settings: RenderSettings | None = None


class Generate(BaseModel):
    takes: int = Field(default=2, ge=1, le=4)
    shot_id: str | None = None
    preset: Literal["sdxl-base", "qwen-reference"] | None = None


class Continuity(BaseModel):
    enabled: bool
    shot_id: str | None = None
    take_id: str | None = None


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
        self.memory_guard = MemoryGuard()

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
                self.memory_guard.prepare(take["settings"]["preset_id"])
                with Comfy(timeout=30) as client:
                    workflow = client.workflows.from_json(deepcopy(take["workflow"]))
                    if take.get("reference"):
                        source = DATA / bid / take["reference"]["image"]
                        if sha256(source) != take["reference"]["image_sha256"]:
                            raise ValueError("Hero reference changed")
                        asset = client.assets.from_file(source)
                        # Record the exact SDK materialized input without replacing the portable graph.
                        binding = asset.as_reference()
                        workflow.set_input("1", "image", binding)
                        take["reference"]["sdk_asset"] = binding
                        take["submitted_workflow"] = deepcopy(workflow.json)
                        take["submission_fingerprint_sha256"] = hashlib.sha256(
                            json.dumps(workflow.json, sort_keys=True).encode()).hexdigest()
                    job = client.submit(workflow)
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
                        self.memory_guard.check_running()
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
                    if isinstance(exc, MemorySafetyError):
                        for pending_board in self.boards.values():
                            for pending_shot in pending_board["shots"]:
                                for pending in pending_shot["takes"]:
                                    if pending["status"] == "queued":
                                        pending.update(status="cancelled", error=str(exc))
                            self.save(pending_board)
                    take.update(status="cancelled" if take.get("cancel_requested") or self.stop.is_set() else "failed",
                                error=str(exc) if isinstance(exc, MemorySafetyError) else f"{type(exc).__name__}: local generation stopped. Check the local engine and retry.",
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
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
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
    return dict(lens=LENSES, angle=ANGLES, move=MOVES, lighting=LIGHTS, look=LOOKS, presets=PRESETS)


@app.get("/api/health")
def health():
    try:
        with httpx.Client(trust_env=False, timeout=2) as client:
            # Connectivity only; generation never uses a direct ComfyUI API.
            response = client.get(SDK_URL + "/api/v2/jobs", params={"limit": 1})
        ready = response.status_code == 200
    except httpx.HTTPError:
        ready = False
    reference_components_present = all(
        ((QWEN_MODEL_DIR / m["filename"]) if m["component"] == "diffusion" else
         (REFERENCE_MODEL_DIR / m["folder"] / m["filename"])).is_file()
        for m in json.loads((ROOT / "workflows/qwen-model-lock.json").read_text()))
    checkpoint_present = (MODEL_DIR / PRESETS["sdxl-base"]["checkpoint"]).is_file()
    if ENGINE_MANIFEST:
        def available(preset):
            try:
                verify_models(preset)
                return True
            except ValueError:
                return False
        checkpoint_present = available("sdxl-base")
        reference_components_present = available("qwen-reference")
    return dict(proxy_ready=ready, reference_components_present=reference_components_present, checkpoint_present=checkpoint_present)


EXAMPLES = {"greenhouse-a2": "The greenhouse / continuity", "greenhouse": "The greenhouse / early study"}


def example_board(slug):
    if slug not in EXAMPLES:
        raise HTTPException(404, "Example not found")
    folder = ROOT / "examples" / slug
    board = json.loads((folder / "board.json").read_text())
    review = folder / "continuity-review.json"
    board["review"] = json.loads(review.read_text()) if review.exists() else []
    return board


@app.get("/api/examples")
def examples():
    return [dict(slug=slug, label=label, board=example_board(slug)) for slug, label in EXAMPLES.items()]


@app.get("/api/examples/{slug}/images/{filename}")
def example_image(slug: str, filename: str):
    board = example_board(slug)
    if not any(t.get("image") == filename for s in board["shots"] for t in s["takes"]):
        raise HTTPException(404, "Image not found")
    return FileResponse(ROOT / "examples" / slug / "takes" / filename)


@app.post("/api/examples/{slug}/open")
def open_example(slug: str):
    source = example_board(slug)
    with store.lock:
        # Reopening preserves user picks and edits in the private workspace.
        if source["id"] not in store.boards:
            destination = DATA / source["id"]
            destination.mkdir(parents=True, exist_ok=True)
            for shot in source["shots"]:
                for take in shot["takes"]:
                    shutil.copyfile(ROOT / "examples" / slug / "takes" / take["image"], destination / take["image"])
            refs = ROOT / "examples" / slug / "references"
            if refs.is_dir():
                shutil.copytree(refs, destination / "references", dirs_exist_ok=True)
            store.boards[source["id"]] = source
            store.save(source)
        else:
            store.boards[source["id"]].setdefault("review", source["review"])
        return dict(id=source["id"])


@app.get("/api/boards")
def list_boards():
    with store.lock:
        return [dict(id=b["id"], title=b["title"]) for b in reversed(list(store.boards.values()))]


@app.post("/api/boards", status_code=201)
def create_board(scene: Scene):
    with store.lock:
        config = scene.model_dump()
        board = dict(id=uuid4().hex, title=scene.scene[:80], config=config, shots=expand_shots(config),
                     continuity=dict(enabled=False, hero=None), created_at=time.time())
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
        shot_for(board, sid).update(edit.model_dump(exclude_none=True))
        store.save(board)
    return dict(ok=True)


@app.post("/api/boards/{bid}/generate", status_code=202)
def generate(bid: str, request: Generate):
    with store.lock:
        board = board_for(bid)
        continuity = board.get("continuity", {})
        preset_id = request.preset or ("qwen-reference" if continuity.get("enabled") else "sdxl-base")
        reference = None
        if preset_id == "qwen-reference":
            if not continuity.get("enabled") or not continuity.get("hero"):
                raise HTTPException(409, "Pick a hero and enable Keep continuity first.")
            reference = deepcopy(continuity["hero"])
            if sha256(DATA / bid / reference["image"]) != reference["image_sha256"]:
                raise HTTPException(409, "Hero reference changed on disk.")
        shots = [shot_for(board, request.shot_id)] if request.shot_id else board["shots"]
        if reference:
            if request.shot_id == reference["shot_id"]:
                raise HTTPException(409, "The hero cut stays selected. Choose another cut for a reference edit.")
            shots = [s for s in shots if s["id"] != reference["shot_id"]]
        if any(t["status"] in ("queued", "running") for s in board["shots"] for t in s["takes"]):
            raise HTTPException(409, "This board already has work in the queue.")
        if any(len(s["takes"])+request.takes > 16 for s in shots):
            raise HTTPException(409, "Maximum 16 takes per shot. Create a new board for more coverage.")
        try:
            models = verify_models(preset_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        tasks = []
        for shot in shots:
            preset = settings_for(shot, preset_id)
            offset = max((int(t["id"][1:]) for t in shot["takes"]), default=0)
            for i in range(request.takes):
                tid = f"t{offset+i+1:02}"
                seed = seed_for(board["config"]["seed"], offset+i, shot["locked_seed"])
                take = dict(id=tid, seed=seed, status="queued", phase="Queued locally", settings=preset,
                            models=deepcopy(models), workflow=workflow_for(shot, seed, preset, reference),
                            reference=deepcopy(reference), elapsed_seconds=0)
                shot["takes"].append(take)
                tasks.append((bid, shot["id"], tid))
        store.save(board)
        for task in tasks:
            store.tasks.put(task)
        return dict(queued=len(tasks))


def verify_models(preset_id):
    """Every external component is pinned, including GGUF's implicit vision projector."""
    if preset_id == "sdxl-base":
        lock = json.loads((ROOT / "workflows/model-lock.json").read_text())
        requirements = [dict(filename=lock["filename"], sha256=lock["sha256"],
                             license=lock["license"], repository=lock["repository"], revision=lock["revision"],
                             components=["SDXL UNet", "CLIP-L", "OpenCLIP bigG", "VAE (checkpoint embedded)"])]
    else:
        requirements = json.loads((ROOT / "workflows/qwen-model-lock.json").read_text())
    if ENGINE_MANIFEST:
        try:
            report = json.loads(Path(ENGINE_MANIFEST).read_text())
            if report.get("schema_version") != 1 or report.get("verified") is not True:
                raise ValueError("Unverified engine model report")
            for model in requirements:
                component = next((m for m in report["models"] if m["filename"] == model["filename"]), None)
                if not component or component.get("sha256") != model["sha256"] or component.get("verified") is not True:
                    raise ValueError("Engine model report differs from pinned component")
                if "bytes" in model and component.get("bytes") != model["bytes"]:
                    raise ValueError("Engine model size differs from pinned component")
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Engine model report unavailable or invalid") from exc
        return requirements
    for model in requirements:
        if preset_id == "sdxl-base":
            path = MODEL_DIR / model["filename"]
        elif model["component"] == "diffusion":
            path = QWEN_MODEL_DIR / model["filename"]
        else:
            path = REFERENCE_MODEL_DIR / model["folder"] / model["filename"]
        if not path.is_file():
            raise ValueError("Model component missing: " + model["filename"] + ". Follow README setup.")
        if sha256(path) != model["sha256"]:
            raise ValueError("Model hash differs from the pinned component: " + model["filename"])
    return requirements


@app.post("/api/boards/{bid}/continuity")
def set_continuity(bid: str, request: Continuity):
    with store.lock:
        board = board_for(bid)
        if any(t["status"] in ("queued", "running") for s in board["shots"] for t in s["takes"]):
            raise HTTPException(409, "Wait for the current queue before changing the hero.")
        if not request.enabled:
            board.setdefault("continuity", {})["enabled"] = False
        else:
            if not request.shot_id or not request.take_id:
                raise HTTPException(409, "Choose a picked hero take.")
            shot = shot_for(board, request.shot_id)
            take = next((t for t in shot["takes"] if t["id"] == request.take_id and t["status"] == "succeeded"), None)
            if not take or shot["picked"] != request.take_id:
                raise HTTPException(409, "Pick the hero take before enabling continuity.")
            source = DATA / bid / take["image"]
            if sha256(source) != take["image_sha256"]:
                raise HTTPException(409, "The picked hero changed on disk.")
            relative = "references/" + take["image_sha256"] + ".png"
            dest = DATA / bid / relative
            dest.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, dest)
            hero = dict(shot_id=shot["id"], take_id=take["id"], image=relative,
                        image_sha256=take["image_sha256"], seed=take["seed"],
                        settings=deepcopy(take["settings"]), models=deepcopy(take["models"]),
                        workflow=deepcopy(take["workflow"]))
            board["continuity"] = dict(enabled=True, hero=hero)
        store.save(board)
    return deepcopy(board["continuity"])


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
        continuity = board.get("continuity", {})
        hero = continuity.get("hero") or {}
        if continuity.get("enabled") and hero.get("shot_id") == sid and hero.get("take_id") != request.take_id:
            raise HTTPException(409, "Turn off Keep continuity before changing the hero pick.")
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


@app.get("/api/boards/{bid}/storyboard")
def storyboard(bid: str, layout: Literal["landscape", "portrait"] = "landscape", download: bool = False):
    with store.lock:
        try:
            png = storyboard_png(board_for(bid), DATA, layout)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    headers = {"Content-Disposition": f'attachment; filename="storyboard-{layout}.png"'} if download else {}
    return Response(png, media_type="image/png", headers=headers)


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
