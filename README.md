# Shot Board

<img src="shotboard/static/logo.svg" width="388" height="64" alt="Shot Board — one scene, six shots">

**A storyboard app for film coverage: one scene, six shots.**

![Six-shot storyboard of a traveler finding a brass compass in a rainy greenhouse](examples/greenhouse-continuity/storyboard-landscape.png)

*A six-shot storyboard exported from Shot Board.*

Shot Board turns a scene into editable film coverage using open weights in ComfyUI.

## Try it without a GPU

Browse, review and export the three bundled examples without a GPU. You need Git and uv.

```sh
git clone [REPO_URL] shot-board
cd shot-board
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt --require-hashes
.venv/bin/python -m uvicorn shotboard.server:app --host 127.0.0.1 --port 8790
```

Open **http://127.0.0.1:8790** and choose **Explore the board** on an example. Rendering new takes requires a GPU worker; see [Run it locally](#run-it-locally).

## What it does

You write one scene. Shot Board turns it into a shot list and renders takes for each cut. You compare, review and pick, then export the picks as a storyboard plus a ZIP that records how each frame was made.

- **Coverage from one scene.** Plan six editable shots from one scene: establishing, medium, face close-up, over shoulder, insert and low angle. You can add up to three more. Add character, prop and setting details if needed.
- **Editable cuts.** Each cut's prompt and negative prompt can be edited. Size and CFG can be edited for SDXL takes only; Qwen edits keep their reference size and CFG 4.
- **Takes you can compare.** SDXL renders takes for each cut. Compare & pick shows every take of a cut side by side, with its render details one click away. Seeds can be locked and reused.
- **Hero reference.** Use an SDXL hero for Qwen reference edits. Every other cut is re-rendered with Qwen-Image-Edit-2511 from that same image.
- **Reviews.** Save your own reviews with each take: a pass, fail or pending verdict and a note.
- **Export.** Export landscape or portrait storyboards, plus stills, ComfyUI workflows and saved recipes.

| Home | Board | Compare & pick | Storyboard |
|---|---|---|---|
| ![Home](docs/screenshots/12-home.png) | ![Board](docs/screenshots/13-board.png) | ![Compare](docs/screenshots/14-compare.png) | ![Storyboard export](docs/screenshots/15-storyboard.png) |

## How it works

```text
Browser ──▶ Shot Board (FastAPI, CPU)
              │  Comfy SDK 0.5.0
              ▼
            comfy-api-proxy 0.1.6 (loopback)
              ▼
            ComfyUI --offline --disable-partner-nodes  (GPU worker)
              ├─ SDXL Base 1.0            → first takes and the hero
              └─ Qwen-Image-Edit-2511     → reference edits from the frozen hero
```

All inference requests and reference uploads go through the Comfy SDK and a loopback proxy to your own ComfyUI. The engine start command in SETUP.md runs ComfyUI with `--offline --disable-partner-nodes`, so no partner nodes, paid APIs or cloud credentials are involved. All weights are open and pinned by SHA-256.

- **SDXL Base 1.0** renders the first takes: 20 steps, Euler/normal, with framing-first weighted prompts, shot-specific negatives, aspect ratios and CFG. Pinned in [model-lock.json](workflows/model-lock.json); graph in [sdxl-base.api.json](workflows/sdxl-base.api.json).
- **Qwen-Image-Edit-2511** (Q8_0 GGUF) handles reference edits together with the Qwen2.5-VL-7B Q8_0 encoder, its F16 vision projector and the Qwen image VAE: 24 steps, CFG 4, Euler/simple, shift 3.1, about one megapixel per cut, no LoRA. Pinned in [qwen-model-lock.json](workflows/qwen-model-lock.json); graph in [qwen-reference.api.json](workflows/qwen-reference.api.json). The GGUF loaders come from ComfyUI-GGUF.
- The hero is hashed and frozen when you select it. The SDK uploads that same image for every edit, and each take snapshots its own settings, models, graph and reference.
- The setup scripts download each model file from a pinned revision and check its size and SHA-256 before moving it into place. Downloads never rewrite the lock files; changing a lock is a separate, explicit step.

## Run it locally

[docs/SETUP.md](docs/SETUP.md) has the full setup in order: the pinned ComfyUI and ComfyUI-GGUF checkouts, the five model files with their URLs, sizes and hashes, the model report, the SSH tunnel, and start and stop commands for every process. It also records the worker environment we used. The short version follows.

The app is a CPU client. ComfyUI runs on a separate GPU worker, and the app reaches the engine and the SDK proxy through SSH loopback tunnels. Keep one serial GPU job active.

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt --require-hashes
# Forward local 18188 -> worker 8188 and local 18189 -> worker 8189 over SSH.
COMFY_BASE_URL=http://127.0.0.1:18189 \
COMFY_ENGINE_URL=http://127.0.0.1:18188 \
SHOTBOARD_ENGINE_MANIFEST=/path/to/private/engine-models.json \
.venv/bin/python -m uvicorn shotboard.server:app --host 127.0.0.1 --port 8790
```

The same start command works with no worker connected. The gallery, the examples, reviews and export all run; the footer reads "SDXL setup needed", or "Continuity setup needed" on the continuity board, and rendering waits for a worker.

On the worker, run ComfyUI with `--offline --disable-partner-nodes` and the separate `comfy-api-proxy` on loopback, and install ComfyUI-GGUF. See [SETUP.md](docs/SETUP.md) for engine configuration and runtime limits.

Open **http://127.0.0.1:8790** and choose **+ New scene**. Type a scene, or press **Use example** to load the greenhouse scene with its Character, Key prop and Set filled in. Build the shot list and render SDXL takes. Pick an SDXL medium take with a visible face, choose **Use selected as hero**, then **Render reference edits**. The hero cut stays selected and the other cuts get new reference takes. Compare the takes, save a verdict on each, and pick. To pick another take on the hero's own cut, turn off **Use hero reference** first; marking an SDXL pick on another cut as the new hero works directly. Export unlocks when every cut has a pick.

Stop the app with Ctrl-C.

### Open the examples without rendering

The home gallery shows the three bundled examples with only the CPU app running. **Explore the board** copies an example into your workspace and keeps your picks and reviews on later visits. To import from the command line instead, stop the app first:

```sh
.venv/bin/python scripts/import_example.py
.venv/bin/python scripts/import_example.py --example greenhouse-continuity
```

The first line imports the early greenhouse study; use `--example hangar` for the hangar board. Command-line imports bring the example reviews along, the same as **Explore the board**. Restart and choose **My boards**.

### Reuse a recipe outside the app

Each `workflows/sNN.api.json` in an export ZIP is a ComfyUI API-format graph with the cut's prompt, seed and settings filled in. SDXL graphs load `sd_xl_base_1.0.safetensors`. Qwen graphs load the hero from `references/<sha256>.png`, the same path the ZIP uses, so copy the ZIP's `references` folder into ComfyUI's input directory before you queue one. You need the same pinned model files and ComfyUI-GGUF.

### Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check shotboard/static/app.js
```

The tests cover templates, dimensions and CFG, seed families, prompts with empty Character, Key prop and Set fields, the Qwen graph and model locks, pinned and atomic model downloads, hero freezing and the SDXL-only hero rule, scene text cleanup, saving reviews across restarts and pick changes and exporting them, matching example imports from the command line and from the gallery, storyboard export and its failure path, `ENGINE_MODE` memory checks, model report sizes and API protections. They do not run diffusion.

## Example outputs

Explore the greenhouse and hangar boards, with saved takes, reviews and recipes.

- [Greenhouse continuity](examples/greenhouse-continuity/README.md): "A traveler discovers a small brass compass in a rain-soaked greenhouse." An SDXL hero with Qwen reference edits, both storyboards, the export ZIP and the review files.
- [Greenhouse study](examples/greenhouse/README.md): the same scene with the first SDXL-only recipe.
- [Hangar](examples/hangar/README.md): "A gray utility robot with a square metal head, a single blue optical sensor and mechanical gripper arms repairs a small spaceship engine on a workbench in a quiet hangar at night." SDXL only, each cut made from text.

### Screenshots

The full list is in [docs/screenshots](docs/screenshots/README.md).

| Capture | State |
|---|---|
| [Home](docs/screenshots/12-home.png) | Featured continuity board and the three examples, desktop |
| [New scene](docs/screenshots/21-new-scene.png) | Empty scene input with shot pictograms |
| [Scene settings](docs/screenshots/01-scene.png) | The greenhouse scene with Character, Key prop and Set filled in, plus camera and atmosphere chips |
| [Hangar board](docs/screenshots/03-rendering.png) | The finished hangar board: six cuts, two takes each, all six picked and reviewed |
| [Qwen board](docs/screenshots/08-continuity-rendering.png) | The finished greenhouse continuity board with the render panel open, all six cuts picked |
| [Continuity board](docs/screenshots/13-board.png) | Six picks with hero badge, verdicts and notes |
| [Compare & pick](docs/screenshots/14-compare.png) | Over-shoulder cut: SDXL take, failed slot and selected Qwen edit, each with its review |
| [Storyboard](docs/screenshots/15-storyboard.png) | Storyboard export, landscape |
| [Portrait storyboard](docs/screenshots/16-storyboard-portrait.png) | Storyboard export, portrait |
| [Mobile compare](docs/screenshots/19-mobile-compare.png) | Compare at 390 px |

## Notes

- Camera controls guide still-image prompts.
- Tested on an RTX 4090 with 24 GB VRAM.
- Storyboard text uses Pillow's embedded default font, which covers a limited range of non-Latin characters.

## License and third-party notices

Shot Board source is [MIT](LICENSE).

SDXL Base 1.0 is licensed under CreativeML Open RAIL++-M, which carries use restrictions. The Qwen diffusion model, encoder, vision projector and VAE are Apache-2.0. ComfyUI is GPL-3.0 and runs as a separate process. ComfyUI-GGUF is Apache-2.0. Comfy SDK and comfy-api-proxy are MIT. This repository does not include model weights or engine source. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the model locks in [workflows/](workflows/) for exact upstream revisions and hashes.

