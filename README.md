# Shot Board

**A scene, seen six ways.** A local workspace for planning cinematic stills with open weights and ComfyUI.

Write a scene and character / prop / set bible, build six to nine editable cuts, render takes, compare and pick, then export your stills with their original generation recipes.

![Shot Board](docs/screenshots/01-scene.png)

## What works

- Establishing, medium, face close-up, over shoulder, insert and low-angle coverage; three optional cuts. Deterministic expansion, no prompt service.
- Framing-first weighted SDXL prompts, shot-specific negatives, aspect ratios and CFG. Explicit coverage overrides conflicting angle chips. Edit prompts, negatives, SDXL width / height / CFG per cut.
- **Keep continuity:** pick a completed take in Compare & pick, then **Use selected as hero**. Other cuts use Qwen reference editing; the hero cut stays selected. Turn the checkbox off to return to SDXL. A reference edit is a new take, so compare it against the original before selecting it.
- Real serial queue, engine status, elapsed seconds, stop / retry, persistent boards and immutable take snapshots. No invented sampling percentage.
- Shared seed families, seed zero, seed lock / reuse. Matching seeds guide variation; they do not lock identity.
- ZIP export: selected PNGs, portable API graphs and a manifest with models / hashes / revisions / licenses, seed, prompt, settings, dimensions, elapsed time and file hashes. Reference edits also include the frozen hero PNG and source recipe, plus the exact SDK-submitted graph and its SHA-256.
- Every inference and reference upload uses **Comfy SDK 0.5.0 → local comfy-api-proxy 0.1.6 → ComfyUI**. No partner nodes, paid APIs or cloud credentials.

Reference editing can still change faces, clothing, props and geometry or miss a requested angle. Hidden features cannot be verified from a still. Review each cut. Lens chips are text conditioning, and movement chips describe a still's composition, not calibrated cameras or video.

FLUX.2 klein 4B remains disabled.

## Run with a remote GPU

The app is a CPU client. Run ComfyUI on a separate GPU worker and expose its engine and SDK proxy through SSH loopback tunnels. Keep one serial GPU job active. The source/file-store machine must never run ComfyUI or load models.

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt --require-hashes
# Forward local 18188 -> worker 8188 and local 18189 -> worker 8189 over SSH.
COMFY_BASE_URL=http://127.0.0.1:18189 \
COMFY_ENGINE_URL=http://127.0.0.1:18188 \
SHOTBOARD_ENGINE_MANIFEST=/path/to/private/engine-models.json \
.venv/bin/python -m uvicorn shotboard.server:app --host 127.0.0.1 --port 8790
```

On the worker, run ComfyUI with `--offline --disable-partner-nodes` and the separate `comfy-api-proxy` on loopback. Install ComfyUI-GGUF. Download public weights only, then hash the files on that worker. Copy the resulting private report back over SSH. `SHOTBOARD_ENGINE_MANIFEST` accepts schema version 1 with `verified: true` and a `models` array containing `filename`, actual `sha256`, `bytes`, and `verified: true` per component. The app rejects missing, unverified or mismatched components against its pinned locks. This is an operator-supplied file report, not a live attestation protocol: regenerate it whenever worker model files change. The app never downloads weights or starts a worker. Without a report, it verifies local model files as specified by the model-directory environment variables.

[SDXL Base](workflows/model-lock.json) includes its VAE and encoders and uses CreativeML Open RAIL++-M. [Qwen components](workflows/qwen-model-lock.json) are Apache-2.0: Edit-2511 Q8_0 diffusion, Qwen2.5-VL-7B Q8_0 encoder, F16 vision projector and Qwen image VAE. No Lightning or angle LoRA is used. Reference edits run 24 steps, CFG 4, Euler/simple, shift 3.1 and cut-specific dimensions around one megapixel. The same frozen hero is uploaded through the SDK for every edit. Edits are never chained.

Open **http://127.0.0.1:8790**, build a list, and render SDXL takes. Pick a face-visible medium take, choose **Use selected as hero**, and click **Render reference edits**. The hero cut stays selected; the other cuts receive new reference takes. Compare both takes before picking. To change the hero pick, disable continuity first. The UI shows real elapsed seconds including upload, model loading, encoding, sampling and output download. Queue wait, setup and model verification are separate. Speed and visual quality are measurements, not guarantees; see the [six-cut comparison](examples/greenhouse-a2/README.md).

Export activates when every cut has a pick. Existing take recipes survive edits and mode changes. Reference exports include `references/<hash>.png`, its source recipe, portable graphs, exact SDK-submitted graphs and hashes. SDK asset IDs belong to the original proxy. For portable replay, upload the included hero under the reference path in the graph.

Stop the app with Ctrl-C. Do not use multiple workers or `--reload` during generation. Queued/running takes become interrupted after a restart. Single-user loopback MVP; caps are four takes per request, sixteen per cut and a thirty-minute per-take timeout. The included local stack launcher is optional for other GPU machines; never run it on the source/file-store machine.

## Open examples without rendering

Stop the app before importing:

```sh
.venv/bin/python scripts/import_example.py
.venv/bin/python scripts/import_example.py --example greenhouse-a2
```

Restart and choose **Open a board**. The original greenhouse example preserves all twelve A1 images and recipes. The A2 example contains the six SDXL images plus five reference edits and their shared SDXL hero. Browsing, picking and exporting work with the engine offline. The A2 sheets contain letterboxed original images, not retouched renders.

## Tests and structure

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests exercise template ordering and conflicting angles, dimensions / CFG, explicit subject and prop, seed families, Qwen graph and model lock, hero selection / freeze / tampering / queue rules, per-cut settings validation, export source and graph hashes, original API / persistence / same-origin protections and removal of the retired route. Tests do not run diffusion; checked-in examples and screenshots record actual GPU runs.

`shotboard/core.py` owns templates, preset settings, graph construction and export. `shotboard/server.py` owns persistence, model verification, hero freezing and the single SDK worker. Every take snapshots its own settings, models, graph and reference. Public PNGs omit engine metadata. `workflows/` pins the model components. `scripts/stack.py` reuses the separate engine; it does not redistribute it.


## Licenses

App source is [MIT](LICENSE). SDXL is CreativeML Open RAIL++-M, with use restrictions. Qwen diffusion, encoder, vision projector and VAE are Apache-2.0. ComfyUI is GPL-3.0 and runs as a separate process. ComfyUI-GGUF is Apache-2.0. No weights or engine source are redistributed. See [third-party notices](THIRD_PARTY_NOTICES.md) and model locks for exact upstream references and revisions.

## Example and storyboard endpoints

The home gallery is available with the CPU app alone; no engine or import command is required. **Explore the board** copies a bundled example into private workspace state on first open. Later opens preserve edits and picks. The CLI import commands above remain optional; imported boards appear under **My boards**.

| Endpoint | Result |
|---|---|
| `GET /api/examples` | Bundled examples with board snapshots and available visual reviews |
| `GET /api/examples/{slug}/images/{filename}` | A bundled take, restricted to the example's recorded images |
| `POST /api/examples/{slug}/open` | Open or copy an example into workspace state without generation |
| `GET /api/boards/{id}/storyboard?layout=landscape` | Selected cuts as a 1600 × 900 PNG |
| `GET /api/boards/{id}/storyboard?layout=portrait` | Selected cuts as a 1080 × 1350 PNG |
| `GET /api/boards/{id}/storyboard?layout=landscape&download=true` | The same PNG with an attachment filename |
| `GET /api/boards/{id}/export` | ZIP with both storyboards, selected stills, graphs, references and manifest |

Storyboards require a completed pick for every cut and verify each source image hash. Pillow 13.0.0 renders them on CPU with its embedded default font; no OS font lookup, model load or inference is needed. Identical board data and image bytes produce identical PNG bytes under the locked runtime. Images are fitted without cropping. The manifest lists dimensions, SHA-256, layout version, credit and the picked take IDs for both PNGs; available visual reviews and the frozen hero recipe are retained. Unicode coverage follows Pillow's embedded font. Keyboard controls: left/right to move between cuts, Enter/Space to compare, Escape to close dialogs. Motion respects the system's reduced-motion preference.
