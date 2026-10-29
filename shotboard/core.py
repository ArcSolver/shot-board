"""Deterministic coverage, model presets and reproducible export."""
from copy import deepcopy
import hashlib
import io
import json
import os
import re
from pathlib import Path
import zipfile

from .storyboard import storyboard_png, SIZES

ROOT = Path(__file__).resolve().parents[1]
LENSES = ["24", "35", "50", "85"]
ANGLES = ["Eye level", "Low angle", "High angle"]
MOVES = ["Static", "Push in", "Lateral drift"]
LIGHTS = ["Window light", "Blue hour", "Hard rim", "Practical tungsten"]
LOOKS = ["Muted film", "Warm grain", "Cool chrome", "Monochrome"]
LIGHT_PROMPTS = {
    "Window light": "soft directional window light, natural soft shadows",
    "Blue hour": "blue hour ambient light, cool shadows, soft warm highlights",
    "Hard rim": "hard rim light, deep shadows, dramatic contrast",
    "Practical tungsten": "warm practical tungsten lighting, pools of amber light",
}
LOOK_PROMPTS = {
    "Muted film": "muted cinematic colors, gentle contrast, subtle 35mm film grain",
    "Warm grain": "warm film colors, fine film grain, soft highlight rolloff",
    "Cool chrome": "cool cinematic color grade, silvery highlights, crisp detail",
    "Monochrome": "black and white film photograph, rich tonal range, fine grain",
}
# Shot framing takes precedence over camera chips that would contradict coverage.
# Dimensions are multiples of 64 for SDXL; Qwen edits reuse them.
COVERAGE = [
    ("Establishing", "extreme wide establishing shot, distant full-body {subject} tiny in frame, expansive environment", "close-up, portrait, cropped body", 1216, 704, 6.5),
    ("Medium", "medium waist-up shot, head and torso visible, {subject} examining {prop}", "extreme close-up, distant figure, full body", 1024, 768, 6.0),
    ("Close-up", "tight face close-up portrait, face fills almost the entire frame, eyes in sharp focus, cropped at chin and forehead", "wide shot, medium shot, waist, torso, full body, hands, object in foreground", 768, 1024, 7.0),
    ("Over shoulder", "over-the-shoulder POV, back of {subject}'s head and clothed shoulder clearly visible filling left third foreground, camera immediately behind the person looking past their shoulder toward {prop} on table, rear three-quarter view", "empty room, no person, unoccupied, front view, facing camera, portrait, eye contact, full body", 1152, 768, 7.0),
    ("Insert", "macro insert detail shot of {prop} held in fingers, object fills frame, only hands and object visible", "face, head, portrait, torso, full body, wide shot, medium shot", 1024, 1024, 6.5),
    ("Low angle", "dramatic worm's-eye view from floor level looking steeply upward at {subject}, towering figure, architecture overhead, strong foreshortening", "eye level, high angle, overhead view, flat perspective, looking down", 768, 1024, 7.5),
    ("Profile", "side profile medium shot of {subject}, face in profile", "front view, facing camera", 1024, 768, 6.5),
    ("High angle", "high-angle wide shot looking down on {subject} and environment from above", "low angle, eye level", 1216, 704, 6.5),
    ("Closing", "wide rear view of {subject} walking away into the scene", "front view, portrait", 1216, 704, 6.5),
]
# A scene without a person keeps six cuts but drops faces, hands and shoulders.
OBJECT_COVERAGE = {
    "Establishing": ("Establishing", "extreme wide establishing shot, {subject} small in frame, expansive environment", "close-up, cropped", 1216, 704, 6.5),
    "Medium": ("Medium", "medium shot, {subject} fully visible with its immediate surroundings", "extreme close-up, distant view", 1024, 768, 6.0),
    "Close-up": ("Detail", "tight detail close-up of {subject}, surface texture and fine detail fill the frame, sharp focus", "wide shot, medium shot, full view", 768, 1024, 7.0),
    "Over shoulder": ("Side angle", "side angle view of {subject} at eye level, the environment visible behind it", "front view, overhead view", 1152, 768, 7.0),
    "Insert": ("Insert", "macro insert detail shot of {prop}, object fills frame", "wide shot, medium shot", 1024, 1024, 6.5),
    "Low angle": ("Low angle", "dramatic worm's-eye view from floor level looking steeply upward at {subject}, architecture overhead, strong foreshortening", "eye level, high angle, overhead view, flat perspective, looking down", 768, 1024, 7.5),
    "Profile": ("Three-quarter", "three-quarter view medium shot of {subject}", "front view, rear view", 1024, 768, 6.5),
    "Closing": ("Closing", "wide final shot of {subject} in the quiet environment, slow pull back", "close-up, portrait", 1216, 704, 6.5),
}
NO_PERSON_NEGATIVE = "person, people, human figure, face, hands"
PERSON_WORDS = (
    "person", "people", "man", "men", "woman", "women", "boy", "girl", "child", "children", "kid", "baby",
    "he", "she", "him", "his", "her", "traveler", "traveller", "stranger", "friend", "couple", "crowd",
    "mother", "father", "detective", "soldier", "worker", "technician", "chef", "doctor", "nurse",
    "pilot", "driver", "dancer", "singer", "actor", "student", "teacher", "farmer", "officer", "guard",
)
PERSON_PATTERN = re.compile(r"\b(?:" + "|".join(PERSON_WORDS) + r")s?\b", re.IGNORECASE)


def has_person(config):
    """A filled Character field or a person named in the scene keeps the face and shoulder cuts."""
    return bool(config.get("character", "").strip()) or bool(PERSON_PATTERN.search(config.get("scene", "")))


def coverage_for(config):
    person = has_person(config)
    return [entry if person else OBJECT_COVERAGE.get(entry[0], entry) for entry in COVERAGE[:config["count"]]]


# Q8_0 is the measured default. Q4_K_M brings the four Qwen files from about 31 GB to about 20 GB.
QWEN_LOCKS = {"Q8_0": "qwen-model-lock.json", "Q4_K_M": "qwen-model-lock-q4_k_m.json"}
QWEN_QUANT = os.environ.get("SHOTBOARD_QWEN_QUANT", "Q8_0")
if QWEN_QUANT not in QWEN_LOCKS:
    raise RuntimeError("SHOTBOARD_QWEN_QUANT must be one of: " + ", ".join(QWEN_LOCKS))
QWEN_LOCK = ROOT / "workflows" / QWEN_LOCKS[QWEN_QUANT]
_QWEN_FILES = {m["component"]: m["filename"] for m in json.loads(QWEN_LOCK.read_text())}
PRESETS = {
    "sdxl-base": {
        "label": "SDXL Base 1.0", "enabled": True,
        "checkpoint": "sd_xl_base_1.0.safetensors",
        "license": "CreativeML Open RAIL++-M",
        "repository": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0",
        "width": 1024, "height": 576, "steps": 20, "cfg": 6.0,
        "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
    },
    "qwen-reference": {
        "label": "Qwen continuity · reference edit", "enabled": True,
        "license": "Apache-2.0", "capability": "reference-edit",
        "unet": _QWEN_FILES["diffusion"],
        "encoder": _QWEN_FILES["text encoder"], "vae": _QWEN_FILES["VAE"],
        "width": 512, "height": 512, "steps": 24, "cfg": 4.0,
        "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
        "shift": 3.1, "reference_megapixels": 1.0,
    },
}
NEGATIVE = "anime, cartoon, illustration, drawing, painting, 3d render, text, watermark, logo, celebrity, nudity, gore, duplicate subject, extra limbs, deformed hands, low quality, blurry"


def expand_shots(config):
    """Same bible and chips always produce the same editable six to nine cuts.

    The six-cut template is fixed except for one branch: without a person, the
    face close-up and over-shoulder become a detail close-up and a side angle.
    """
    bible_parts = [config['scene'].strip().rstrip('.,; ')]
    for key, label in (("character", "Character"), ("setting", "Set"), ("prop", "Key prop")):
        if config.get(key, '').strip():
            bible_parts.append(f"{label}: {config[key].strip().rstrip('.,; ')}")
    bible = ". ".join(bible_parts)
    atmosphere = ", ".join([LIGHT_PROMPTS[config['lighting']], LOOK_PROMPTS[config['look']],
                            "cinematic still photograph"])
    motion = {"Static": "locked camera composition", "Push in": "visual intent of a slow push in",
              "Lateral drift": "visual intent of a lateral camera drift"}[config["move"]]
    person = has_person(config)
    shots = []
    for i, (title, direction, avoid, width, height, cfg) in enumerate(coverage_for(config)):
        # Only compatible cuts inherit angle; a low-angle chip must not undo OTS.
        angle = config["angle"].lower() if title in ("Medium", "Profile", "Three-quarter") else ""
        direction = direction.format(subject=config.get('character', '').split(',')[0].strip().rstrip('.; ') or "the main subject",
                                     prop=config.get('prop', '').strip().rstrip('.,; ') or "the focal detail")
        prompt = ", ".join(part for part in (
            f"({direction}:1.45)", "live-action RAW photograph", bible,
            f"{config['lens']}mm lens", angle, atmosphere, motion) if part)
        shots.append(dict(id=f"s{i+1:02}", title=title, direction=direction,
                          template_version=4, shot_type=title,
                          render_settings=dict(width=width, height=height, cfg=cfg),
                          reference_size=dict(width=width, height=height),
                          prompt=prompt, negative=f"{avoid}, {NEGATIVE}" if person else f"{avoid}, {NO_PERSON_NEGATIVE}, {NEGATIVE}",
                          locked_seed=None, picked=None, takes=[]))
    return shots


def settings_for(shot, preset_id):
    preset = deepcopy(PRESETS[preset_id])
    preset["preset_id"] = preset_id
    preset.update(shot.get("reference_size" if preset_id == "qwen-reference" else "render_settings", {}))
    return preset


def reference_prompt(shot):
    # Qwen follows natural edit instructions; SDXL attention syntax is not portable.
    framing = re.sub(r"\(([^()]+):[0-9.]+\)", r"\1", shot["prompt"])
    return ("Requested framing: " + shot.get("shot_type", shot["title"]) + ". "
            "Edit the reference photograph into a new camera shot of the SAME scene. "
            "Preserve the exact same person and facial identity, hair, outfit, bag, object design, "
            "materials, lighting and set architecture from the reference. "
            "Change camera position and framing as requested; do not simply repeat the reference composition. "
            + framing + ". Keep only elements visible in this framing; do not force a face into a detail or rear view.")


def seed_for(base, take_index, locked=None):
    # A take column shares a seed family across every cut. Framing comes from text.
    return locked if locked is not None else (base + take_index * 104729) % (2**32)


def workflow_for(shot, seed, preset, reference=None):
    if preset.get("capability") == "reference-edit":
        if not reference:
            raise ValueError("Pick a hero still before reference editing.")
        graph = json.loads((ROOT / "workflows/qwen-reference.api.json").read_text())
        graph["1"]["inputs"]["image"] = reference["image"]
        graph["2"]["inputs"]["prompt"] = reference_prompt(shot)
        graph["3"]["inputs"]["prompt"] = shot["negative"]
        graph["4"]["inputs"].update(width=preset["width"], height=preset["height"])
        graph["5"]["inputs"].update(seed=seed, **{k: preset[k] for k in
            ("steps", "cfg", "sampler_name", "scheduler", "denoise")})
        graph["8"]["inputs"]["unet_name"] = preset["unet"]
        graph["9"]["inputs"]["clip_name"] = preset["encoder"]
        graph["10"]["inputs"]["vae_name"] = preset["vae"]
        graph["12"]["inputs"]["shift"] = preset["shift"]
        graph["14"]["inputs"]["megapixels"] = preset["reference_megapixels"]
        return graph
    graph = json.loads((ROOT / "workflows/sdxl-base.api.json").read_text())
    graph["1"]["inputs"]["ckpt_name"] = preset["checkpoint"]
    graph["2"]["inputs"]["text"] = shot["prompt"]
    graph["3"]["inputs"]["text"] = shot["negative"]
    graph["4"]["inputs"].update(width=preset["width"], height=preset["height"])
    graph["5"]["inputs"].update(seed=seed, **{k: preset[k] for k in
        ("steps", "cfg", "sampler_name", "scheduler", "denoise")})
    return graph


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def export_board(board, data_root):
    """Export immutable take snapshots, never the later-edited shot settings."""
    manifest = dict(schema_version=2, app="Shot Board", board_id=board["id"],
                    title=board["title"], scene=deepcopy(board["config"]),
                    generation_path="Comfy SDK → local API proxy → ComfyUI",
                    review=deepcopy(board.get("review", [])), hero=deepcopy(board.get("continuity", {}).get("hero")),
                    storyboards=[], storyboard_errors=[], shots=[])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        exported_references = set()
        for shot in board["shots"]:
            take = next((t for t in shot["takes"] if t["id"] == shot["picked"] and t["status"] == "succeeded"), None)
            if take is None:
                raise ValueError("Pick one completed take for every cut before exporting.")
            image = Path(data_root) / board["id"] / take["image"]
            if sha256(image) != take["image_sha256"]:
                raise ValueError("A picked image changed on disk; export stopped.")
            image_name = f"stills/{shot['id']}.png"
            imported = take.get('source', {}).get('type') == 'imported'
            workflow_name = None if imported else f"workflows/{shot['id']}.api.json"
            archive.write(image, image_name)
            reference = deepcopy(take.get("reference"))
            if reference:
                source = Path(data_root) / board["id"] / reference["image"]
                if sha256(source) != reference["image_sha256"]:
                    raise ValueError("The hero reference changed on disk; export stopped.")
                if reference["image"] not in exported_references:
                    archive.write(source, reference["image"])
                    exported_references.add(reference["image"])
            graph = json.dumps(take["workflow"], indent=2) + "\n"
            if workflow_name:
                archive.writestr(workflow_name, graph)
            submitted_name = None
            submitted_hash = None
            if take.get("submitted_workflow"):
                submitted_name = f"workflows/{shot['id']}.submitted.api.json"
                submitted_graph = json.dumps(take["submitted_workflow"], indent=2) + "\n"
                archive.writestr(submitted_name, submitted_graph)
                submitted_hash = hashlib.sha256(submitted_graph.encode()).hexdigest()
            manifest["shots"].append(dict(id=shot["id"], title=shot["title"], take_id=take["id"],
                review=deepcopy(next((r for r in board.get("review", [])
                                     if r["shot"] == shot["id"] and r["take"] == take["id"]),
                                    dict(shot=shot["id"], take=take["id"], verdict="pending", note=""))),
                seed=take["seed"], seed_locked=shot["locked_seed"] is not None,
                settings=deepcopy(take["settings"]), models=deepcopy(take["models"]),
                prompt=None if imported else take["workflow"]["2"]["inputs"].get("text", take["workflow"]["2"]["inputs"].get("prompt")),
                negative=None if imported else take["workflow"]["3"]["inputs"].get("text", take["workflow"]["3"]["inputs"].get("prompt")),
                source=deepcopy(take.get('source')),
                reference=reference,
                submitted_workflow=submitted_name,
                submitted_workflow_sha256=submitted_hash,
                submission_fingerprint_sha256=take.get("submission_fingerprint_sha256"),
                image=image_name, image_sha256=take["image_sha256"], workflow=workflow_name,
                workflow_sha256=hashlib.sha256(graph.encode()).hexdigest() if workflow_name else None,
                elapsed_seconds=take["elapsed_seconds"]))
        for layout, size in SIZES.items():
            try:
                png = storyboard_png(board, data_root, layout)
            except Exception as exc:
                # Picks, hashes and recipes are already validated above. A CPU
                # preview failure must not prevent their independent export.
                # Do not copy exception messages containing private paths.
                manifest['storyboard_errors'].append(dict(layout=layout, error=type(exc).__name__,
                    message='Storyboard rendering failed; selected stills and recipes are included.'))
                continue
            name = f"storyboard-{layout}.png"
            archive.writestr(name, png)
            manifest["storyboards"].append(dict(file=name, width=size[0], height=size[1],
                sha256=hashlib.sha256(png).hexdigest(),
                layout_version=1, fit="contain", selections=[dict(shot_id=s["id"], take_id=s["picked"]) for s in board["shots"]]))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
    return buffer.getvalue()
