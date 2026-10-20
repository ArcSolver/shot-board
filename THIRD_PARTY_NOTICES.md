# Third-party notices

Shot Board source is MIT. Dependencies are installed separately from their upstream distributions and retain their respective copyright notices and license files. This repository does not vendor dependency code, ComfyUI source or model weights. Preserve upstream notices and satisfy each license if redistributing those components.

## Actual generation model

**SDXL Base 1.0** — Stability AI, [model card](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0), [CreativeML Open RAIL++-M license](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md). This is an open-weight model with use restrictions, not an MIT/Apache model. The checkpoint, including its embedded SDXL diffusion network, CLIP-L/OpenCLIP bigG encoders and VAE, is governed by the checkpoint distribution terms. The app requires compliance with those use restrictions. The checkpoint revision and SHA-256 are recorded in `workflows/model-lock.json` and each exported take.

CLIP and OpenCLIP implementations originate under MIT; that does not replace the SDXL checkpoint distribution terms. See the [SDXL model card](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) and [OpenCLIP](https://github.com/mlfoundations/open_clip/blob/main/LICENSE). The runtime implementations come from the separate ComfyUI installation. No refiner, custom LoRA or standalone encoder/VAE weight is used for A1.

## Separate generation engine

- [ComfyUI](https://github.com/Comfy-Org/ComfyUI/blob/master/LICENSE): GPL-3.0. Separate process, native `CheckpointLoaderSimple`, `CLIPTextEncode`, `EmptyLatentImage`, `KSampler`, `VAEDecode`, `SaveImage` nodes. No source is copied into Shot Board. ComfyUI and its installed Python/GPU dependencies retain their own distribution obligations.
- [Comfy SDK 0.5.0](https://github.com/Comfy-Org/comfy-python-sdk): MIT.
- [comfy-api-proxy 0.1.6](https://github.com/Comfy-Org/comfy-api-proxy): MIT, separate local HTTP proxy process. Its runtime dependencies include aiohttp (Apache-2.0), aiosignal (Apache-2.0), aiohappyeyeballs (PSF-2.0), attrs (MIT), frozenlist/multidict/yarl/propcache (Apache-2.0), blake3 (CC0-1.0 or Apache-2.0), and typing-extensions (PSF-2.0).
- [PyTorch](https://github.com/pytorch/pytorch/blob/main/LICENSE): BSD-3-Clause with bundled-component notices. Used by the user's separate ComfyUI installation. Other ComfyUI dependencies remain governed by its installation's notices; this app does not redistribute that environment.

An existing installation may load custom-node packages at startup. The supplied SDXL graph uses only the native nodes listed above and no Partner Nodes. A custom-node loader being installed does not mean its models participate in the graph.

## App Python runtime

| Package | License | Upstream |
|---|---|---|
| FastAPI 0.119.0 | MIT | [fastapi](https://github.com/fastapi/fastapi) |
| Starlette | BSD-3-Clause | [starlette](https://github.com/Kludex/starlette) |
| Uvicorn 0.37.0 | BSD-3-Clause | [uvicorn](https://github.com/Kludex/uvicorn) |
| HTTPX 0.28.1, HTTPcore | BSD-3-Clause | [httpx](https://github.com/encode/httpx), [httpcore](https://github.com/encode/httpcore) |
| Pillow 13.0.0 | MIT-CMU | [Pillow](https://github.com/python-pillow/Pillow) |
| Pydantic, pydantic-core | MIT | [pydantic](https://github.com/pydantic/pydantic), [pydantic-core](https://github.com/pydantic/pydantic-core) |
| AnyIO | MIT | [anyio](https://github.com/agronholm/anyio) |
| annotated-types | MIT | [annotated-types](https://github.com/annotated-types/annotated-types) |
| typing-inspection | MIT | [typing-inspection](https://github.com/pydantic/typing-inspection) |
| typing-extensions | PSF-2.0 | [typing_extensions](https://github.com/python/typing_extensions) |
| Click | BSD-3-Clause | [click](https://github.com/pallets/click) |
| h11 | MIT | [h11](https://github.com/python-hyper/h11) |
| idna | BSD-3-Clause | [idna](https://github.com/kjd/idna) |
| certifi | MPL-2.0 | [certifi](https://github.com/certifi/python-certifi) |
| PyYAML | MIT | [pyyaml](https://github.com/yaml/pyyaml) |
| blake3 | CC0-1.0 or Apache-2.0 | [blake3-py](https://github.com/oconnor663/blake3-py) |
| Python standard library | PSF-2.0 | [Python](https://www.python.org/doc/copyright/) |

Frontend: original HTML, CSS and JavaScript; system fonts, no downloaded fonts, icons, images or JavaScript libraries.

## Verification tools, not product dependencies

Playwright (Apache-2.0) and its browser distributions were used for local screenshots and interaction checks. They are not shipped with the app. Python unittest is part of Python. Downloading weights uses the Python standard library.

## Planned capabilities, not used models

Qwen-Image-Edit-2511 and FLUX.2 klein **4B** are disabled preset placeholders. No Qwen, FLUX, geometry, research-only depth weights or remote model service is used to generate this release's example. Future adapters must record the exact diffusion model, encoders, VAE, quantization and any LoRAs with their own licenses and hashes; the 4B license must not be generalized to other FLUX variants.
