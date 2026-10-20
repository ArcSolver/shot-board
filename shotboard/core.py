"""Deterministic coverage, model presets and reproducible export."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import zipfile

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
COVERAGE = [
    ("Establishing", "wide establishing shot, subject small in the frame, show the environment"),
    ("Medium", "medium shot, subject and immediate surroundings, balanced composition"),
    ("Close-up", "close-up portrait of the subject, shallow depth of field, intimate framing"),
    ("Over shoulder", "over-the-shoulder view from behind the subject, looking into the set"),
    ("Insert", "extreme close-up detail of the subject's hands and the object in the scene"),
    ("Low angle", "low-angle medium shot of the subject, camera below eye level"),
    ("Profile", "side profile medium shot of the subject"),
    ("High angle", "high-angle wide shot looking down on the subject and set"),
    ("Closing", "wide rear view of the subject, quiet closing composition"),
]
PRESETS = {
    "sdxl-base": {
        "label": "SDXL Base 1.0", "enabled": True,
        "checkpoint": "sd_xl_base_1.0.safetensors",
        "license": "CreativeML Open RAIL++-M",
        "repository": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0",
        "width": 1024, "height": 576, "steps": 20, "cfg": 6.0,
        "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
    },
    "qwen-reference": {"label": "Qwen reference edit · planned", "enabled": False,
                       "license": "Apache-2.0", "capability": "reference-edit"},
    "flux-klein-4b": {"label": "FLUX.2 klein 4B · planned", "enabled": False,
                      "license": "Apache-2.0", "capability": "text-and-reference"},
}
NEGATIVE = "text, watermark, logo, celebrity, nudity, gore, duplicate subject, extra limbs, deformed hands, low quality, blurry"


def expand_shots(config):
    """Same bible and chips always produce the same editable six to nine cuts."""
    bible = f"{config['scene']}. Character: {config['character']}. Set: {config['setting']}."
    shared = ", ".join([bible, f"{config['lens']}mm lens", config['angle'].lower(),
                        LIGHT_PROMPTS[config['lighting']], LOOK_PROMPTS[config['look']],
                        "cinematic still photograph, one continuous scene"])
    motion = {"Static": "locked camera composition", "Push in": "forward-facing composition, visual intent of a slow push in",
              "Lateral drift": "layered foreground and background, visual intent of a lateral camera drift"}[config["move"]]
    return [dict(id=f"s{i+1:02}", title=title, direction=direction,
                 prompt=f"{shared}, {direction}, {motion}", negative=NEGATIVE,
                 locked_seed=None, picked=None, takes=[])
            for i, (title, direction) in enumerate(COVERAGE[:config["count"]])]


def seed_for(base, take_index, locked=None):
    # A take column shares a seed family across every cut. Framing comes from text.
    return locked if locked is not None else (base + take_index * 104729) % (2**32)


def workflow_for(shot, seed, preset):
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
    manifest = dict(schema_version=1, app="Shot Board", board_id=board["id"],
                    title=board["title"], scene=deepcopy(board["config"]),
                    consistency="Shared character/set bible and seed families; identity is not guaranteed.",
                    generation_path="Comfy SDK → local API proxy → ComfyUI", shots=[])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for shot in board["shots"]:
            take = next((t for t in shot["takes"] if t["id"] == shot["picked"] and t["status"] == "succeeded"), None)
            if take is None:
                raise ValueError("Pick one completed take for every shot before exporting.")
            image = Path(data_root) / board["id"] / take["image"]
            if sha256(image) != take["image_sha256"]:
                raise ValueError("A picked image changed on disk; export stopped.")
            image_name = f"stills/{shot['id']}.png"
            workflow_name = f"workflows/{shot['id']}.api.json"
            archive.write(image, image_name)
            graph = json.dumps(take["workflow"], indent=2) + "\n"
            archive.writestr(workflow_name, graph)
            manifest["shots"].append(dict(id=shot["id"], title=shot["title"], take_id=take["id"],
                seed=take["seed"], seed_locked=shot["locked_seed"] is not None,
                settings=deepcopy(take["settings"]), models=deepcopy(take["models"]),
                prompt=take["workflow"]["2"]["inputs"]["text"],
                negative=take["workflow"]["3"]["inputs"]["text"],
                image=image_name, image_sha256=take["image_sha256"], workflow=workflow_name,
                workflow_sha256=hashlib.sha256(graph.encode()).hexdigest(),
                elapsed_seconds=take["elapsed_seconds"]))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
    return buffer.getvalue()
