# Technical setup

Requires an NVIDIA GPU with 24 GB VRAM.

CPU client — tests

```sh
# Prerequisites: Git, uv, Node; SSH/SCP for a remote worker
cd /path/to/shot-board
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt --require-hashes
.venv/bin/python -m unittest discover -s tests -v
node --check shotboard/static/app.js
```

CPU client — copy the app to the GPU worker

```sh
cd /path/to/shot-board
export GPU_SSH=gpu-worker
mkdir -p .runtime
git archive --format=tar.gz --output=.runtime/source.tar.gz HEAD
scp .runtime/source.tar.gz "$GPU_SSH:/tmp/shot-board-source.tar.gz"
ssh "$GPU_SSH" 'mkdir -p /opt/shot-board && tar -xzf /tmp/shot-board-source.tar.gz -C /opt/shot-board'
```

GPU worker — pinned engine installation

```sh
cd /opt/shot-board
mkdir -p .runtime
export COMFY_DIR="$PWD/.runtime/ComfyUI"
git clone https://github.com/Comfy-Org/ComfyUI.git "$COMFY_DIR"
git -C "$COMFY_DIR" checkout --detach e3bee7ffcb7d6547ed0bcd15221792f3b8646b17
git clone https://github.com/city96/ComfyUI-GGUF.git "$COMFY_DIR/custom_nodes/ComfyUI-GGUF"
git -C "$COMFY_DIR/custom_nodes/ComfyUI-GGUF" checkout --detach 6ea2651e7df66d7585f6ffee804b20e92fb38b8a
python3.12 -m venv --system-site-packages .runtime/engine-venv
# skip if torch is already installed
.runtime/engine-venv/bin/python -m pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
.runtime/engine-venv/bin/python -m pip install -r "$COMFY_DIR/requirements.txt" -r "$COMFY_DIR/custom_nodes/ComfyUI-GGUF/requirements.txt" comfy-sdk==0.5.0 comfy-api-proxy==0.1.6
```

GPU worker — model downloads

```sh
cd /opt/shot-board
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN COMFY_API_KEY
.runtime/engine-venv/bin/python scripts/download_model.py --model-dir .runtime/ComfyUI/models/checkpoints
.runtime/engine-venv/bin/python scripts/setup_reference.py --download --reference-model-dir .runtime/ComfyUI/models --qwen-model-dir .runtime/ComfyUI/models/diffusion_models
```

SDXL checkpoint

```sh
# URL: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/462165984030d82259a11f4367a4eed129e94a7b/sd_xl_base_1.0.safetensors
# Placement: .runtime/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors
```

diffusion

```sh
# URL: https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/resolve/0d33d9692b4b26212297240d87b0d4719aa4fd06/qwen-image-edit-2511-Q8_0.gguf
# Placement: .runtime/ComfyUI/models/diffusion_models/qwen-image-edit-2511-Q8_0.gguf
```

text encoder

```sh
# URL: https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/resolve/68bb8bc4b7df5289c143aaec0ab477a7d4051aab/Qwen2.5-VL-7B-Instruct-Q8_0.gguf
# Placement: .runtime/ComfyUI/models/text_encoders/Qwen2.5-VL-7B-Instruct-Q8_0.gguf
```

vision projector

```sh
# URL: https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/resolve/68bb8bc4b7df5289c143aaec0ab477a7d4051aab/mmproj-F16.gguf
# Placement: .runtime/ComfyUI/models/text_encoders/Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf
```

VAE

```sh
# URL: https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/1f12b17be14c89b026c51a91d67c32f84bb047bc/split_files/vae/qwen_image_vae.safetensors
# Placement: .runtime/ComfyUI/models/vae/qwen_image_vae.safetensors
```

GPU worker — model report

```sh
cd /opt/shot-board
.runtime/engine-venv/bin/python scripts/model_report.py --models-dir .runtime/ComfyUI/models > .runtime/engine-models.json.tmp && mv .runtime/engine-models.json.tmp .runtime/engine-models.json
```

GPU worker — terminal 1, engine

```sh
cd /opt/shot-board
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN COMFY_API_KEY
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NO_PROXY=127.0.0.1,localhost
mkdir -p .runtime/input .runtime/output .runtime/user
.runtime/engine-venv/bin/python .runtime/ComfyUI/main.py --listen 127.0.0.1 --port 8188 --input-directory "$PWD/.runtime/input" --output-directory "$PWD/.runtime/output" --user-directory "$PWD/.runtime/user" --offline --disable-partner-nodes --disable-auto-launch --preview-method none --cache-lru 8 --reserve-vram 1 --disable-dynamic-vram --disable-fast-disk
```

GPU worker — terminal 2, SDK proxy

```sh
cd /opt/shot-board
.runtime/engine-venv/bin/comfy-api-proxy run --host 127.0.0.1 --port 8189 --comfyui http://127.0.0.1:8188 --state-dir "$PWD/.runtime/proxy"
```

CPU client — SSH tunnel to the GPU worker

```sh
cd /path/to/shot-board
mkdir -p .runtime
# Configure an SSH alias with the worker address, port and key
export GPU_SSH=gpu-worker
scp "$GPU_SSH:/opt/shot-board/.runtime/engine-models.json" .runtime/engine-models.json
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18188:127.0.0.1:8188 -L 127.0.0.1:18189:127.0.0.1:8189 "$GPU_SSH"
```

CPU client — another terminal, app for the remote worker

```sh
cd /path/to/shot-board
ENGINE_MODE=remote COMFY_BASE_URL=http://127.0.0.1:18189 COMFY_ENGINE_URL=http://127.0.0.1:18188 SHOTBOARD_ENGINE_MANIFEST="$PWD/.runtime/engine-models.json" .venv/bin/python -m uvicorn shotboard.server:app --host 127.0.0.1 --port 8790
# Open http://127.0.0.1:8790
```

Local GPU alternative — app on the GPU worker

```sh
cd /opt/shot-board
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt --require-hashes
ENGINE_MODE=local COMFY_BASE_URL=http://127.0.0.1:8189 COMFY_ENGINE_URL=http://127.0.0.1:8188 SHOTBOARD_ENGINE_MANIFEST="$PWD/.runtime/engine-models.json" .venv/bin/python -m uvicorn shotboard.server:app --host 127.0.0.1 --port 8790
```
