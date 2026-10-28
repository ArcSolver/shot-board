# Third-party notices

Shot Board source is MIT. Each dependency keeps its own license.

## Fonts

The app serves two fonts from `shotboard/static`, both under the SIL Open Font License 1.1:

- [Hanken Grotesk](https://github.com/marcologous/hanken-grotesk), copyright 2021 The Hanken Grotesk Project Authors. License: [OFL-hanken-grotesk.txt](shotboard/static/OFL-hanken-grotesk.txt).
- [Courier Prime](https://github.com/quoteunquoteapps/CourierPrime), copyright 2015 The Courier Prime Project Authors. License: [OFL-courier-prime.txt](shotboard/static/OFL-courier-prime.txt).

## Generation models

**SDXL Base 1.0**: Stability AI, [model card](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0), [CreativeML Open RAIL++-M license](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md).

## Generation engine

- [ComfyUI](https://github.com/Comfy-Org/ComfyUI/blob/master/LICENSE): GPL-3.0.
- [Comfy SDK](https://github.com/Comfy-Org/comfy-python-sdk): MIT.
- [comfy-api-proxy](https://github.com/Comfy-Org/comfy-api-proxy): MIT.

## App Python runtime

| Package | License | Upstream |
|---|---|---|
| FastAPI | MIT | [fastapi](https://github.com/fastapi/fastapi) |
| Starlette | BSD-3-Clause | [starlette](https://github.com/Kludex/starlette) |
| Uvicorn | BSD-3-Clause | [uvicorn](https://github.com/Kludex/uvicorn) |
| HTTPX, HTTPcore | BSD-3-Clause | [httpx](https://github.com/encode/httpx), [httpcore](https://github.com/encode/httpcore) |
| Pillow | MIT-CMU | [Pillow](https://github.com/python-pillow/Pillow) |
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

## Continuity preset

Qwen-Image-Edit-2511 Q8_0 and Q4_K_M GGUF (Unsloth conversion), Qwen2.5-VL-7B-Instruct Q8_0 and Q4_K_M GGUF and its F16 vision projector, and Qwen image VAE (Comfy-Org packaging) are Apache-2.0. Pinned in [qwen-model-lock.json](workflows/qwen-model-lock.json) and [qwen-model-lock-q4_k_m.json](workflows/qwen-model-lock-q4_k_m.json).

Upstream model cards: [Qwen edit](https://huggingface.co/Qwen/Qwen-Image-Edit-2511), [diffusion GGUF](https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF), [encoder GGUF](https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF), [Comfy-Org VAE](https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI).

[ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF): Apache-2.0.
