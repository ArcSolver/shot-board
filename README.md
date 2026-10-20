# Shot Board

**A Popcorn-style storyboard app on open weights: one scene, six shots.**

![Six-shot storyboard of a traveler finding a brass compass in a rainy greenhouse](examples/greenhouse-continuity/storyboard-landscape.png)

*The continuity example as the app exports it, a 1600 × 900 PNG. Every example output was rendered on an RTX 4090. Continuity across the six frames is partial, and the last frame is an SDXL fallback; see [Limitations](#limitations).*

Higgsfield Popcorn is Higgsfield's storyboard tool for visual consistency: you write a story, add reference images if you like, and it makes 4, 6 or 8 frames. Shot Board is a smaller, independent app built around the same idea and aimed at film coverage. It runs on open weights in ComfyUI. Higgsfield did not make it, and it does not match that tool's features.

## Try it without a GPU

The three bundled examples open in the CPU app with no engine running. You can browse, pick, review and export them; the footer shows the engine as offline. You need Git and uv.

```sh
git clone [REPO_URL] shot-board
cd shot-board
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt --require-hashes
.venv/bin/python -m uvicorn shotboard.server:app --host 127.0.0.1 --port 8790
```

Open **http://127.0.0.1:8790** and choose **Explore the board** on an example. Rendering new takes needs a GPU worker; see [Run it locally](#run-it-locally).

## What it does

You write one scene. Shot Board turns it into a shot list and renders takes for each cut. You compare, review and pick, then export the picks as a storyboard plus a ZIP that records how each frame was made.

- **Coverage from one scene.** A scene becomes six cuts: establishing, medium, face close-up, over shoulder, insert and low angle. You can add up to three more. Fixed framing templates do the expansion. No prompt service rewrites your sentence, so the scene text carries the content. Under **Fine-tune the scene**, the Character, Key prop and Set fields are optional and start empty; empty fields add nothing to the prompts. **Use example** fills the scene and those fields from the bundled greenhouse example. Line breaks and extra spaces in the scene are cleaned up first.
- **Editable cuts.** Each cut's prompt and negative prompt can be edited. Size and CFG can be edited for SDXL takes only; Qwen edits keep their reference size and CFG 4.
- **Takes you can compare.** SDXL renders takes for each cut. Compare & pick shows every take of a cut side by side with its seed, time and settings. Seeds can be locked and reused.
- **Keep continuity.** Pick an SDXL take and mark it as the hero. Only an SDXL original can be the hero: the app refuses a Qwen take and says why. Every other cut is then re-rendered with Qwen-Image-Edit-2511, and each edit uses the same frozen hero as its reference. Edits are never chained, so a mistake in one edit does not carry into the next.
- **A review on every take.** Each take has a verdict (pass, fail or pending) and a note of up to 400 characters, editable on the card and in Compare & pick. Reviews are saved with the board and survive a restart. When you change a pick, the card shows the review saved for that take, or pending if it has none. You write the verdicts; the app does not judge images. The bundled examples ship with our own verdicts filled in.
- **Storyboard export.** One click gives a 1600 × 900 landscape or 1080 × 1350 portrait PNG with shot numbers, shot names, lens labels, the scene text and a "Made with open weights in ComfyUI" credit. The PNG holds pictures and labels only; the recipe is in the ZIP.
- **A recipe for every frame.** The ZIP holds both storyboards, the selected stills, a portable ComfyUI API graph for each cut, and a manifest with model hashes, revisions, licenses, seeds, prompts, settings, elapsed times, file hashes and reviews: every saved review on the board, plus the review of each picked take. Qwen edits also get the exact graph the SDK submitted. When the picks include Qwen edits, the frozen hero PNG comes along. The continuity example's ZIP has six portable graphs, four submitted graphs and one hero PNG. An SDXL-only export has no submitted graphs and no hero PNG. If a storyboard PNG fails to render, you still get the stills and recipes, and the manifest lists the failed layout under `storyboard_errors`.
- **Opens without a GPU.** The home gallery and the bundled examples load in the CPU app with no engine running. Browsing, picking, reviewing and exporting all work offline.

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

All inference requests and reference uploads go through the Comfy SDK and a loopback proxy to your own ComfyUI. The engine start command in SETUP.md runs ComfyUI with `--offline --disable-partner-nodes`, so no partner nodes, paid APIs or cloud credentials are involved. The app does not inspect how the engine was started, so keep those flags if you change the command. All weights are open and pinned by SHA-256.

- **SDXL Base 1.0** renders the first takes: 20 steps, Euler/normal, with framing-first weighted prompts, shot-specific negatives, aspect ratios and CFG. Pinned in [model-lock.json](workflows/model-lock.json); graph in [sdxl-base.api.json](workflows/sdxl-base.api.json).
- **Qwen-Image-Edit-2511** (Q8_0 GGUF) handles reference edits together with the Qwen2.5-VL-7B Q8_0 encoder, its F16 vision projector and the Qwen image VAE: 24 steps, CFG 4, Euler/simple, shift 3.1, about one megapixel per cut, no LoRA. Pinned in [qwen-model-lock.json](workflows/qwen-model-lock.json); graph in [qwen-reference.api.json](workflows/qwen-reference.api.json). The GGUF loaders come from ComfyUI-GGUF.
- The hero is hashed and frozen when you select it. The SDK uploads that same image for every edit, and each take snapshots its own settings, models, graph and reference.
- One serial SDK worker runs jobs, so the queue shows real elapsed seconds and never a made-up progress percentage.
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

The same start command works with no worker connected. The gallery, the examples, reviews and export all run; the footer shows the engine as offline, and rendering waits for a worker.

`ENGINE_MODE` tells the app where the models run, `local` or `remote`. If you leave it unset, engine port 8188 counts as local and any other loopback port counts as a remote tunnel, so the block above runs as remote. Set it yourself for a tunnel on 8188 or for a local engine on another port. SETUP.md shows the remote command and a local GPU command, each with `ENGINE_MODE` set. In both modes the engine and proxy URLs must stay loopback HTTP. The app's memory pressure and swap check runs only for a local engine on macOS, during Qwen edits; in remote mode, and on other systems, it does not run.

On the worker, run ComfyUI with `--offline --disable-partner-nodes` and the separate `comfy-api-proxy` on loopback, and install ComfyUI-GGUF. Download public weights only, hash them on the worker, and copy the report back over SSH. `SHOTBOARD_ENGINE_MANIFEST` accepts schema version 1 with `verified: true` and a `models` array that lists `filename`, actual `sha256`, `bytes` and `verified: true` for each component. The app checks every component, SDXL included, against its pinned locks and rejects anything missing, unverified, or with the wrong hash or size. The report is a file you supply, and the app trusts it as written, so regenerate it whenever the worker's model files change. The app server never downloads weights or starts a worker. Without a report, it checks local model files at the paths set by the model-directory environment variables.

Open **http://127.0.0.1:8790** and choose **+ New scene**. Type a scene, or press **Use example** to load the greenhouse scene with its Character, Key prop and Set filled in. Build the shot list and render SDXL takes. Pick an SDXL medium take with a visible face, choose **Use selected as hero**, then **Render reference edits**. The hero cut stays selected and the other cuts get new reference takes. Compare the takes, save a verdict on each, and pick. To pick another take on the hero's own cut, turn continuity off first; marking an SDXL pick on another cut as the new hero works directly. Export unlocks when every cut has a pick.

Stop the app with Ctrl-C. Do not run multiple workers or `--reload` during generation; queued or running takes are marked interrupted after a restart. This is a single-user loopback app. One render request queues up to four takes per cut, so a six-cut board can queue up to 24 takes at once. A cut holds at most sixteen takes. The app stops waiting for a take thirty minutes after the SDK submits it; reference upload before that and image download after it are not counted in those thirty minutes.

### Open the examples without rendering

The home gallery shows the three bundled examples with only the CPU app running. **Explore the board** copies an example into your workspace and keeps your picks and reviews on later visits. To import from the command line instead, stop the app first:

```sh
.venv/bin/python scripts/import_example.py
.venv/bin/python scripts/import_example.py --example greenhouse-continuity
```

The first line imports the early greenhouse study; use `--example hangar` for the hangar board. Command-line imports bring the example reviews along, the same as **Explore the board**. Restart and choose **My boards**.

### Reuse a recipe outside the app

Each `workflows/sNN.api.json` in an export ZIP is a ComfyUI API-format graph with the cut's prompt, seed and settings filled in. SDXL graphs load `sd_xl_base_1.0.safetensors`. Qwen graphs load the hero from `references/<sha256>.png`, the same path the ZIP uses, so copy the ZIP's `references` folder into ComfyUI's input directory before you queue one. You need the same pinned model files and ComfyUI-GGUF. We have not checked whether a rerun reproduces the same pixels.

### Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check shotboard/static/app.js
```

The tests cover templates, dimensions and CFG, seed families, prompts with empty Character, Key prop and Set fields, the Qwen graph and model locks, pinned and atomic model downloads, hero freezing and the SDXL-only hero rule, scene text cleanup, saving reviews across restarts and pick changes and exporting them, matching example imports from the command line and from the gallery, storyboard export and its failure path, `ENGINE_MODE` memory checks, model report sizes and API protections. They do not run diffusion. The checked-in examples and screenshots record real GPU runs.

## Example outputs

All three examples were rendered in one session on the same NVIDIA RTX 4090, 42 source images in total. Timings are SDK seconds per take: upload, model load and unload, encoding, sampling, polling and download. They exclude setup, queue wait, model hashing and visual review. Each table records a single run.

### The continuity example

[This example](examples/greenhouse-continuity/README.md) is one scene rendered both ways: "A traveler discovers a small brass compass in a rain-soaked greenhouse."

- **SDXL first.** Thirteen SDXL attempts: one take for each cut plus seven more medium candidates, all from the 20261020 seed family. In some of the first four candidates SDXL drew a photo camera, because the framing prompt mentioned a camera; we removed that wording and put the compass first for the next four. Of the eight candidates, S02/T05 (seed 20679936) passes our medium-framing check: the whole head, torso, waist and the hands holding an open brass compass are in frame. It became the frozen hero.
- **Qwen edits.** Ten Qwen attempt slots, the cap we set for this run. Seven ran on the engine, five images came back, and four of those were selected. Three slots never reached the engine because the connection to the remote worker failed, and two finished on the engine but their images never reached the app. The retries used seeds 20261021 and 20261022.
- **Final picks.** Four Qwen edits, the SDXL hero, and an SDXL take for S06, whose two Qwen attempts both failed to deliver an image.

That makes 23 attempts and 18 published images: 13 SDXL and 5 Qwen.

| | Seconds |
|---|---:|
| SDXL, one attempt (13 attempts) | 2.638–3.777 |
| SDXL, six picks of the SDXL-only board, total | 22.114 |
| SDXL, all 13 attempts | 44.001 |
| Qwen reference edit, five returned images | 80.000–100.425 |
| Qwen, mean of those five | 90.153 |
| Qwen, four selected edits, total | 350.341 |
| Qwen, all ten slots including failures | 581.205 |
| All 23 attempts | 625.206 |

The first SDXL cut used a model that was already loaded. Failed slots stopped early, so their seconds are not edit times.

- [storyboard-landscape.png](examples/greenhouse-continuity/storyboard-landscape.png) and [storyboard-portrait.png](examples/greenhouse-continuity/storyboard-portrait.png): the app's own storyboard exports.
- [continuity-vs-sdxl.png](examples/greenhouse-continuity/continuity-vs-sdxl.png): SDXL picks next to the final picks, cut by cut.
- [hero-contact-sheet.png](examples/greenhouse-continuity/hero-contact-sheet.png) and [hero-review.json](examples/greenhouse-continuity/hero-review.json): all eight hero candidates and their framing verdicts.
- [all-qwen-runs.png](examples/greenhouse-continuity/all-qwen-runs.png): all ten Qwen slots, failed ones included. [qwen-attempts.png](examples/greenhouse-continuity/qwen-attempts.png): first slot versus final pick for each cut.
- [selects.zip](examples/greenhouse-continuity/selects.zip) and [export/manifest.json](examples/greenhouse-continuity/export/manifest.json): the full export with graphs, hero and hashes. [sdxl-selects.zip](examples/greenhouse-continuity/sdxl-selects.zip) holds the SDXL-only picks.
- [timing.csv](examples/greenhouse-continuity/timing.csv) and the review JSON files: per-attempt seconds and separate face, outfit, prop, set and framing verdicts, failures included.
- [before-after-sheet.png](examples/greenhouse-continuity/before-after-sheet.png): the early recipe next to the coverage recipe. Both were rendered on the same RTX 4090 with different settings.

### The early study

[This example](examples/greenhouse/README.md) keeps the first SDXL-only recipe for the same scene: six cuts with two takes each, 1024 × 576, 20 steps, CFG 6. All twelve takes were rendered again from the stored graphs, prompts, seeds and sampler settings on the same RTX 4090, and all twelve recipes match the originals. Nothing from earlier hardware remains. Takes ran 2.488–8.185 seconds each, 35.888 seconds for all twelve. Its export holds six stills, six graphs, two storyboards and the manifest.

### The hangar example: what happens without continuity

[This example](examples/hangar/README.md) uses a different scene: "A gray utility robot with a square metal head, a single blue optical sensor and mechanical gripper arms repairs a small spaceship engine on a workbench in a quiet hangar at night." Character, Key prop and Set were left empty, and no cut prompt was edited. None of the positive prompts mention a traveler, greenhouse, compass or raincoat. The run shows that a scene with empty extra fields works end to end. It does not show good results.

Each hangar cut was generated independently from text, with no frozen hero and no Qwen continuity edit. The robot drifts from cut to cut, and the base model sometimes adds human faces or workers. In the picks, the close-up shows a humanoid cyborg face instead of the square metal head, the over-shoulder cut adds human workers and misses the left-shoulder framing, the medium loses the single-sensor design, and the insert and low angle leave out the repair. We treat this drift as a limit of the base model when cuts are generated on their own. The continuity example above works differently: a frozen SDXL hero plus Qwen edits keeps the look closer. We did not run the continuity step on the hangar, so we cannot say how much it would fix there.

This is the second hangar attempt. A shorter scene sentence came first; the published board uses a more explicit description of the robot. The first twelve takes are kept with the run records, outside this example. The published twelve took 2.606–22.981 seconds each, 62.295 seconds in total. The review notes on each pick record these failures.

### Screenshots

All captures come from the current CPU app in headless Chromium, showing outputs from the RTX 4090 session above. The full list is in [docs/screenshots](docs/screenshots/README.md).

| Capture | State |
|---|---|
| [Home](docs/screenshots/12-home.png) | Featured continuity board and the three examples, desktop |
| [New scene](docs/screenshots/21-new-scene.png) | Empty scene input with shot pictograms |
| [Scene settings](docs/screenshots/01-scene.png) | The greenhouse scene with Character, Key prop and Set filled in, plus camera and atmosphere chips |
| [Hangar queue](docs/screenshots/03-rendering.png) | The live SDXL queue while the hangar board rendered |
| [Qwen queue](docs/screenshots/08-continuity-rendering.png) | The live Qwen queue, before its connection failures |
| [Continuity board](docs/screenshots/13-board.png) | Six picks with hero badge, verdicts and notes |
| [Compare & pick](docs/screenshots/14-compare.png) | Over-shoulder cut: SDXL take, failed slot and selected Qwen edit, each with its review |
| [Storyboard](docs/screenshots/15-storyboard.png) | Storyboard export, landscape |
| [Portrait storyboard](docs/screenshots/16-storyboard-portrait.png) | Storyboard export, portrait |
| [Mobile compare](docs/screenshots/19-mobile-compare.png) | Compare at 390 px |

## Limitations

Continuity improved in the greenhouse example, but only partly. Read the verdicts in [the continuity example](examples/greenhouse-continuity/README.md) before you reuse the method.

- **The first Qwen board was mostly lost.** Only one of its five edits came back. It missed the requested framing, so counting the hero, 1 of 6 cuts matched its shot type. The other four failed on the connection to the remote worker and were never judged.
- **The final 5 of 6 is not an automatic success rate.** It counts the reused SDXL hero and the SDXL fallback for S06. The Qwen cuts used prompts we had edited by hand in the cut editor, and S01 was edited again for its retry.
- **The hero prompts were hand-edited too.** All eight medium hero candidates, the chosen hero S02/T05 included, used prompts we had edited by hand.
- **The wide shot is still too close.** The figure fills about a quarter of the image height where an extreme wide was asked for.
- **Props and sets drift.** The over-shoulder cut gets the left shoulder right, but the compass dial moves onto the hinged lid. The insert's needle layout cannot be checked against the small compass in the hero. The SDXL low angle invents a domed stairwell.
- **What holds.** The face close-up looks compatible with the hero. In the over-shoulder cut, SDXL alone drew a different person in a tan jacket; the reference edit keeps the yellow coat, the teal scarf and the left shoulder. The Qwen low angle never came back, so we cannot say whether it would have kept the person.
- **Other scenes drift more without continuity.** In the hangar example, cuts made from text alone turn the robot into a human face or add workers. See [above](#the-hangar-example-what-happens-without-continuity).
- **Some things cannot be checked from a still.** Hidden faces, hidden props and parts of the set never shown cannot be verified, and the review files mark them as unverified. Verdicts are our own visual judgments, entered through the review controls; no biometric check was run.
- **Lens and movement chips are text.** They steer the prompt and do not model calibrated cameras or motion. The app outputs stills.
- **Minimum hardware is unknown.** The examples ran on one RTX 4090 with 24 GB, which peaked at 22,330 MiB of VRAM. Minimum VRAM, RAM and disk were never measured.
- Storyboard text uses Pillow's embedded default font, which covers a limited range of non-Latin characters.
- FLUX.2 klein 4B is a disabled placeholder.

## License and third-party notices

Shot Board source is [MIT](LICENSE).

SDXL Base 1.0 is licensed under CreativeML Open RAIL++-M, which carries use restrictions. The Qwen diffusion model, encoder, vision projector and VAE are Apache-2.0. ComfyUI is GPL-3.0 and runs as a separate process. ComfyUI-GGUF is Apache-2.0. Comfy SDK and comfy-api-proxy are MIT. This repository does not include model weights or engine source. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the model locks in [workflows/](workflows/) for exact upstream revisions and hashes.

