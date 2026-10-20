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

**Reframe remains an experimental stub**, returns `enabled: false` and queues no generation. FLUX.2 klein 4B remains disabled.

## Run locally

Python 3.12, a separate working ComfyUI installation and a supported local GPU are required. This workspace's Mac has 64 GiB unified memory. Qwen uses about 30 GB of pinned weights, in addition to the 6.94 GB SDXL checkpoint and runtime memory. Keep all servers on loopback.

Install from this directory:

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt --require-hashes
```

In the existing parent workspace, the separate environment is `../local/shotboard-venv/bin/python`; substitute that for `.venv/bin/python` below. It leaves the engine's `../local/venv/` unchanged.

### SDXL setup

Read the [SDXL license](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md), including its use restrictions.

```sh
.venv/bin/python scripts/download_model.py
```

The pinned checkpoint is stored in ignored `.runtime/models/checkpoints/`. The app verifies its SHA-256 before accepting generation. `SHOTBOARD_MODEL_DIR` can point to another directory containing the exact file; ensure the engine loads that same file. The bundled launcher uses the runtime checkpoint directory.

### Optional continuity setup

The [reference lock](workflows/qwen-model-lock.json) pins every component under Apache-2.0:

- Qwen-Image-Edit-2511 **Q8_0 GGUF**, 21.76 GB.
- Qwen2.5-VL-7B-Instruct **Q6_K GGUF** text encoder and F16 vision projector, 7.61 GB together.
- Qwen image VAE, 0.25 GB.
- Already available 4-step Lightning V1.0 BF16 LoRA, 0.85 GB. No angle LoRA.

The existing workspace originally contained the diffusion Q6_K file, not Q8_0. Q8_0 is downloaded separately into this app's ignored runtime. The other four components are read from the existing parent `../models/` directory, which is never changed. ComfyUI must already have [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) installed; this app does not install or modify custom nodes.

```sh
.venv/bin/python scripts/setup_reference.py --download-q8
```

Without `--download-q8`, the script only verifies files. The script downloads only the pinned public Q8 file and never downloads or changes the other components. For another read-only component directory, set `SHOTBOARD_REFERENCE_MODEL_DIR` in both terminals or pass `--reference-model-dir` to setup and the stack launcher. Diffusion Q8 defaults to `.runtime/models/diffusion_models/`; the app supports `SHOTBOARD_QWEN_MODEL_DIR`, and a custom engine must expose the same pinned file.

### Engine and app

In terminal 1, from this directory:

```sh
export COMFYUI_DIR="../vendor/ComfyUI"
export COMFYUI_PYTHON="../local/venv/bin/python"
.venv/bin/python scripts/stack.py
```

The launcher starts separate, unmodified ComfyUI and SDK proxy processes, refuses occupied ports and stops only its children on Ctrl-C. It uses `--offline --disable-partner-nodes`, no previews and a loopback network sandbox on macOS. Logs and engine inputs / outputs stay in ignored `.runtime/`. Use `--log-dir` to keep logs elsewhere. Do not overlap this with another engine using those ports.

Terminal 2:

```sh
COMFY_BASE_URL=http://127.0.0.1:8189 .venv/bin/python -m uvicorn shotboard.server:app --host 127.0.0.1 --port 8790
```

Open **http://127.0.0.1:8790**. Build the shot list and click **Render board**. Use Compare & pick to select takes and optionally lock their seeds. For continuity, choose the hero and **Use selected as hero**, set takes per cut, then **Render reference edits**. Each cut references that same frozen hero directly; edits are not chained. The hero cut cannot be regenerated or have its pick replaced while this mode is on. Choose another picked hero with the same button, or turn the mode off first.

Qwen uses cut-specific sizes around 0.25 megapixels, four Lightning steps, CFG 1, Euler / simple, shift 3.1 and denoise 1. The negative branch is retained in the recipe but is not evaluated at CFG 1. Changing CFG for SDXL does not change Qwen. Reference input resizing preserves aspect ratio; portrait and wide outputs are shown without cropping in the UI.

The queue and comparison show real elapsed seconds, including reference upload, model loading, encoding, sampling and output download. A reference take exceeding 240 seconds is marked **slow on Mac / fast on NVIDIA target**. NVIDIA speed has not been measured here. Model download, queue wait, preflight hashing and human selection time are separate. See the [measured six-cut comparison](examples/greenhouse-a2/README.md).

Export activates after each cut has a pick. Existing take recipes survive later prompt/settings edits, hero changes and disabling continuity. The portable reference graph loads `references/<hash>.png`, included in the ZIP; upload it into the engine input tree to replay locally. The accompanying `*.submitted.api.json` records the original SDK `core/ASSET` binding, whose local asset ID belongs to that proxy, not another installation. Its archive file hash and the canonical submission fingerprint are recorded separately.

Stop the app and launcher with Ctrl-C. Do not use multiple workers or `--reload` during generation. After a forced restart, queued/running takes become interrupted; inspect the engine queue before retrying. Single-user local MVP: no authentication, remote hosting or automatic resume. Caps: four takes per request, sixteen per cut, thirty-minute engine timeout per take.

## Open examples without rendering

Stop the app before importing:

```sh
.venv/bin/python scripts/import_example.py
.venv/bin/python scripts/import_example.py --example greenhouse-a2
```

Restart and choose **Open a board**. The original greenhouse example preserves all twelve A1 images and recipes. The A2 example contains the final six SDXL images plus five reference edits and their hero. Browsing, picking and exporting work with the engine offline. The A2 sheets contain letterboxed original images, not retouched renders.

## Tests and structure

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests exercise template ordering and conflicting angles, dimensions / CFG, explicit subject and prop, seed families, Qwen graph and model lock, hero selection / freeze / tampering / queue rules, per-cut settings validation, export source and graph hashes, original API / persistence / same-origin protections and non-generating Reframe. Tests do not run diffusion; checked-in examples and screenshots record actual local runs.

`shotboard/core.py` owns templates, preset settings, graph construction and export. `shotboard/server.py` owns persistence, model verification, hero freezing and the single SDK worker. Every take snapshots its own settings, models, graph and reference. Public PNGs omit engine metadata. `workflows/` pins the model components. `scripts/stack.py` reuses the separate engine; it does not redistribute it.

The future Reframe route is `POST /api/boards/{board}/shots/{shot}/reframe`. A close-up / small-parallax implementation should record geometry models, camera transforms, masks and source provenance, then reuse the existing take queue and export contract. It must be evaluated separately from reference editing.

## Licenses

App source is [MIT](LICENSE). SDXL is CreativeML Open RAIL++-M, with use restrictions. Qwen diffusion, encoder, vision projector, VAE and Lightning are Apache-2.0. ComfyUI is GPL-3.0 and runs as a separate process. ComfyUI-GGUF is Apache-2.0. No weights or engine source are redistributed. See [third-party notices](THIRD_PARTY_NOTICES.md) and model locks for exact upstream references and revisions.
