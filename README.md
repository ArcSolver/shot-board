# Shot Board

**A Popcorn-style storyboard app on open weights: one scene, six shots.**

![Six-shot storyboard of a traveler finding a brass compass in a rainy greenhouse](examples/greenhouse-a2/storyboard-landscape.png)

*The greenhouse example as the app exports it, a 1600 × 900 PNG. Every frame was rendered on one RTX 4090. Continuity across the six frames is partial; see [Limitations](#limitations).*

Higgsfield Popcorn is Higgsfield's storyboard tool for visual consistency: you write a story, add reference images if you like, and it makes 4, 6 or 8 frames. Shot Board is a smaller, independent app built around the same idea and aimed at film coverage. It runs on open weights in ComfyUI. Higgsfield did not make it, and it does not match that tool's features.

## What it does

You write one scene. Shot Board turns it into a shot list and renders takes for each cut. You compare and pick, then export the picks as a storyboard plus a ZIP that records how each frame was made.

- **Coverage from one scene.** A scene becomes six cuts: establishing, medium, face close-up, over shoulder, insert and low angle. You can add up to three more. Fixed templates do the expansion, so no prompt service is involved. Line breaks and extra spaces in the scene are cleaned up first. Each cut's prompt, negative prompt, size and CFG stay editable.
- **Takes you can compare.** SDXL renders takes for each cut. Compare & pick shows two takes side by side with seed, time and settings. Seeds can be locked and reused.
- **Keep continuity.** Pick an SDXL take and mark it as the hero. Only an SDXL original can be the hero: the app refuses a Qwen take and shows why. Every other cut is then re-rendered with Qwen-Image-Edit-2511, and each edit uses the same frozen hero as its reference. Edits are never chained, so a mistake in one edit does not carry into the next.
- **Review stays on the board.** Each card carries a one-line visual verdict, such as "Framing: failed" or "Prop: unverified". The compare view shows the full observation. Change a pick and its verdict goes back to review pending.
- **Storyboard export.** One click gives a 1600 × 900 landscape or 1080 × 1350 portrait PNG with shot numbers, shot names, lens labels, the scene text and a "Made with open weights in ComfyUI" credit.
- **A recipe for every frame.** The ZIP holds both storyboards, the selected stills, portable ComfyUI API graphs, the exact graphs the SDK submitted, the frozen hero PNG, and a manifest with model hashes, revisions, licenses, seeds, prompts, settings, elapsed times and file hashes. If a storyboard PNG fails to render, you still get the stills and recipes, and the manifest lists the failed layout under `storyboard_errors`.
- **Opens without a GPU.** The home gallery and the bundled examples load in the CPU app with no engine running. Browsing, picking and exporting all work offline.

| Home | Board | Compare & pick | Storyboard |
|---|---|---|---|
| ![Home](docs/screenshots/12-a3-home.png) | ![Board](docs/screenshots/13-a3-board.png) | ![Compare](docs/screenshots/14-a3-compare.png) | ![Storyboard export](docs/screenshots/15-a3-storyboard.png) |

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

All inference requests and reference uploads go through the Comfy SDK and a loopback proxy to your own ComfyUI. ComfyUI runs with `--offline --disable-partner-nodes`, so no partner nodes, paid APIs or cloud credentials are involved. All weights are open and pinned by SHA-256.

- **SDXL Base 1.0** renders the first takes: 20 steps, Euler/normal, with framing-first weighted prompts, shot-specific negatives, aspect ratios and CFG. Pinned in [model-lock.json](workflows/model-lock.json); graph in [sdxl-base.api.json](workflows/sdxl-base.api.json).
- **Qwen-Image-Edit-2511** (Q8_0 GGUF) handles reference edits together with the Qwen2.5-VL-7B Q8_0 encoder, its F16 vision projector and the Qwen image VAE: 24 steps, CFG 4, Euler/simple, shift 3.1, about one megapixel per cut, no LoRA. Pinned in [qwen-model-lock.json](workflows/qwen-model-lock.json); graph in [qwen-reference.api.json](workflows/qwen-reference.api.json). The GGUF loaders come from ComfyUI-GGUF.
- The hero is hashed and frozen when you select it. The SDK uploads that same image for every edit, and each take snapshots its own settings, models, graph and reference.
- One serial SDK worker runs jobs, so the queue shows real elapsed seconds and never a made-up progress percentage.
- The setup scripts download each model file from a pinned revision and check its size and SHA-256 before moving it into place. Downloads never rewrite the lock files; changing a lock is a separate, explicit step.

## Run it locally

[docs/SETUP.md](docs/SETUP.md) has the full setup in order: the pinned ComfyUI and ComfyUI-GGUF checkouts, the five model files with their URLs, sizes and hashes, the model report, the SSH tunnel, and start and stop commands for every process. It also records the one worker we used. The short version follows.

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

`ENGINE_MODE` tells the app where the models run, `local` or `remote`. In remote mode the app skips its own memory pressure and swap checks, since the models load on the worker. If you leave it unset, engine port 8188 counts as local and any other loopback port counts as a remote tunnel, so the block above runs as remote. Set it yourself for a tunnel on 8188 or for a local engine on another port. SETUP.md shows the remote command and a local GPU command, each with `ENGINE_MODE` set. In both modes the engine and proxy URLs must stay loopback HTTP.

On the worker, run ComfyUI with `--offline --disable-partner-nodes` and the separate `comfy-api-proxy` on loopback, and install ComfyUI-GGUF. Download public weights only, hash them on the worker, and copy the report back over SSH. `SHOTBOARD_ENGINE_MANIFEST` accepts schema version 1 with `verified: true` and a `models` array that lists `filename`, actual `sha256`, `bytes` and `verified: true` for each component. The app checks every component, SDXL included, against its pinned locks and rejects anything missing, unverified, or with the wrong hash or size. The report is a file you supply, so regenerate it whenever the worker's model files change. The app server never downloads weights or starts a worker. Without a report, it checks local model files at the paths set by the model-directory environment variables.

Open **http://127.0.0.1:8790**, choose **New scene**, build the shot list and render SDXL takes. Pick an SDXL medium take with a visible face, choose **Use selected as hero**, then **Render reference edits**. The hero cut stays selected and the other cuts get new reference takes. Compare both takes before you pick. To change the hero, turn continuity off first. Export unlocks when every cut has a pick.

Stop the app with Ctrl-C. Do not run multiple workers or `--reload` during generation; queued or running takes are marked interrupted after a restart. This is a single-user loopback app, capped at four takes per request, sixteen per cut and thirty minutes per take.

### Open the examples without rendering

The home gallery shows the bundled examples with only the CPU app running. **Explore the board** copies an example into your workspace and keeps your picks on later visits. To import from the command line instead, stop the app first:

```sh
.venv/bin/python scripts/import_example.py
.venv/bin/python scripts/import_example.py --example greenhouse-a2
```

Restart and choose **My boards**.

### Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check shotboard/static/app.js
```

The tests cover templates, dimensions and CFG, seed families, the Qwen graph and model locks, pinned and atomic model downloads, hero freezing and the SDXL-only hero rule, scene text cleanup, storyboard export and its failure path, `ENGINE_MODE` memory checks, model report sizes and API protections. They do not run diffusion. The checked-in examples and screenshots record real GPU runs.

## Example outputs

[examples/greenhouse-a2](examples/greenhouse-a2/README.md) is one scene rendered both ways: "A traveler discovers a small brass compass in a rain-soaked greenhouse", seed 20261020, on one NVIDIA RTX 4090.

- [storyboard-landscape.png](examples/greenhouse-a2/storyboard-landscape.png) and [storyboard-portrait.png](examples/greenhouse-a2/storyboard-portrait.png): the app's own storyboard exports.
- [continuity-vs-sdxl.png](examples/greenhouse-a2/continuity-vs-sdxl.png): SDXL alone next to hero continuity, cut by cut.
- [all-qwen-runs.png](examples/greenhouse-a2/all-qwen-runs.png) and [qwen-attempts.png](examples/greenhouse-a2/qwen-attempts.png): all nine Qwen attempts, including the four discarded ones.
- [selects.zip](examples/greenhouse-a2/selects.zip) and [export/manifest.json](examples/greenhouse-a2/export/manifest.json): the full export with graphs, hero and hashes. [sdxl-selects.zip](examples/greenhouse-a2/sdxl-selects.zip) holds the SDXL-only picks.
- [timing.csv](examples/greenhouse-a2/timing.csv) and the review JSON files: per-take seconds and per-cut visual verdicts, failures included.

The example has 15 takes: six SDXL takes and nine Qwen attempts. S02/T01 is the SDXL hero, reused without another render. Measured on that run:

| | Seconds |
|---|---:|
| SDXL, six cuts total (first cut includes model load) | 39.015 |
| One Qwen reference edit (range over nine attempts) | 85.862–106.775 |
| Qwen, mean per attempt | 96.021 |
| Qwen, five selected edits total | 457.920 |

These times include SDK upload, model load and unload, encoding, sampling, polling and download. They exclude queue wait and setup. They come from a single run, so treat them as one observation.

The original [greenhouse](examples/greenhouse/) example keeps an earlier SDXL-only board with twelve takes.

### Screenshots

| Capture | State |
|---|---|
| [12-a3-home.png](docs/screenshots/12-a3-home.png) | Home: featured board and example gallery, desktop |
| [13-a3-board.png](docs/screenshots/13-a3-board.png) | Board with six picks, verdict lines and the hero badge |
| [14-a3-compare.png](docs/screenshots/14-a3-compare.png) | Compare & pick: SDXL and Qwen takes of the over-shoulder cut |
| [15-a3-storyboard.png](docs/screenshots/15-a3-storyboard.png) | Storyboard export, landscape |
| [16-a3-storyboard-portrait.png](docs/screenshots/16-a3-storyboard-portrait.png) | Storyboard export, portrait |
| [17-a3-mobile-home.png](docs/screenshots/17-a3-mobile-home.png) | Home at 390 px |
| [18-a3-mobile-board.png](docs/screenshots/18-a3-mobile-board.png) | Board at 390 px |
| [19-a3-mobile-compare.png](docs/screenshots/19-a3-mobile-compare.png) | Compare at 390 px |
| [20-a3-mobile-storyboard.png](docs/screenshots/20-a3-mobile-storyboard.png) | Storyboard export at 390 px |
| [21-a3-new-scene.png](docs/screenshots/21-a3-new-scene.png) | New scene: one input with shot pictograms |

Captures 01–11 in [docs/screenshots](docs/screenshots/README.md) record the earlier interface and the live 4090 continuity run.

## Limitations

Continuity improved in the greenhouse example, but only partly. Read the verdicts in [the example README](examples/greenhouse-a2/README.md) before you reuse the method.

- **Shot types needed hand edits.** The first Qwen board hit the requested shot type on 2 of 6 cuts, counting the reused hero. Long scene prompts overrode framing. After four prompt retries on three cuts in the app's cut editor, with the same seed and hero, it reached 5 of 6. That score reflects manual editing.
- **The medium hero is too tight.** It came out as a face-and-hands crop where a waist-up medium was asked for, and it still counts as a framing failure.
- **Sets and props drift.** The establishing shot invents a much larger arched greenhouse. The over-shoulder compass turns into a hinged-lid object, and the insert swaps the dial for green arrow needles. The over-shoulder figure also lands in the right foreground instead of the requested left.
- **What holds.** The face close-up and the low angle look compatible with the hero. In the over-shoulder cut, SDXL alone drew a different person in a different coat; the reference edit keeps the dark bob and the yellow hood.
- **Some things cannot be checked from a still.** Hidden faces, hidden props and parts of the set never shown cannot be verified. Face judgments come from human visual review; no biometric check was run.
- **Lens and movement chips are text.** They steer the prompt and do not model calibrated cameras or motion. The app outputs stills.
- **Minimum hardware is unknown.** SETUP.md records the one worker we used, an RTX 4090 with 24 GB that peaked at 22,426 MiB. Minimum VRAM, RAM and disk were never measured.
- Storyboard text uses Pillow's embedded default font, which covers a limited range of non-Latin characters.
- FLUX.2 klein 4B is a disabled placeholder.

## License and third-party notices

Shot Board source is [MIT](LICENSE).

SDXL Base 1.0 is licensed under CreativeML Open RAIL++-M, which carries use restrictions. The Qwen diffusion model, encoder, vision projector and VAE are Apache-2.0. ComfyUI is GPL-3.0 and runs as a separate process. ComfyUI-GGUF is Apache-2.0. Comfy SDK and comfy-api-proxy are MIT. This repository does not include model weights or engine source. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the model locks in [workflows/](workflows/) for exact upstream revisions and hashes.
