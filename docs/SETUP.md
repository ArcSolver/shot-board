# Technical setup

A2r worker — recorded environment (not minimum requirements)

```sh
# Container: runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404
# OS: Ubuntu 24.04 image; kernel and NVIDIA driver version: unknown
# Python: 3.12.3; PyTorch: 2.8.0+cu128; torchvision: 0.23.0+cu128
# GPU: one NVIDIA GeForce RTX 4090, 24 GB; observed peak: 22,426 MiB
# Engine-reported RAM: 89,645 MB; provisioned container disk: 100 GB
# Minimum VRAM/RAM/disk and other GPU/OS compatibility: unknown
# SDK: 0.5.0; proxy: 0.1.6; no Lightning or angle LoRA
# Sources: A2r saved engine log, pip freeze, GPU samples and container record
```

CPU client — verified A4 tests

```sh
# Debian GNU/Linux 13; CPython 3.12.15; Node v24.21.0
# No PyTorch or GPU required for gallery, export or tests
# Prerequisites: Git, uv, Node; SSH/SCP for a remote worker
cd /path/to/shot-board
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt --require-hashes
.venv/bin/python -m unittest discover -s tests -v
node --check shotboard/static/app.js
```

CPU client — copy committed app source to an existing GPU worker

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
# GPU worker only; never the source/file-store machine
cd /opt/shot-board
mkdir -p .runtime
export COMFY_DIR="$PWD/.runtime/ComfyUI"
git clone https://github.com/Comfy-Org/ComfyUI.git "$COMFY_DIR"
git -C "$COMFY_DIR" checkout --detach e3bee7ffcb7d6547ed0bcd15221792f3b8646b17
git clone https://github.com/city96/ComfyUI-GGUF.git "$COMFY_DIR/custom_nodes/ComfyUI-GGUF"
git -C "$COMFY_DIR/custom_nodes/ComfyUI-GGUF" checkout --detach 6ea2651e7df66d7585f6ffee804b20e92fb38b8a
python3.12 -m venv --system-site-packages .runtime/engine-venv
# A2r image already provides torch; explicit versions for a fresh Python environment
.runtime/engine-venv/bin/python -m pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
.runtime/engine-venv/bin/python -m pip install -r "$COMFY_DIR/requirements.txt" -r "$COMFY_DIR/custom_nodes/ComfyUI-GGUF/requirements.txt" comfy-sdk==0.5.0 comfy-api-proxy==0.1.6
# Remaining engine dependency versions are not locked here
.runtime/engine-venv/bin/python --version
.runtime/engine-venv/bin/python -c 'import torch; print(torch.__version__, torch.cuda.get_device_name(0))'
```

GPU worker — five public model files, pinned downloads and verification

```sh
cd /opt/shot-board
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN COMFY_API_KEY
.runtime/engine-venv/bin/python scripts/download_model.py --model-dir .runtime/ComfyUI/models/checkpoints
.runtime/engine-venv/bin/python scripts/setup_reference.py --download --reference-model-dir .runtime/ComfyUI/models --qwen-model-dir .runtime/ComfyUI/models/diffusion_models
# Verify-only retry: omit --download; all four components are checked
.runtime/engine-venv/bin/python scripts/setup_reference.py --reference-model-dir .runtime/ComfyUI/models --qwen-model-dir .runtime/ComfyUI/models/diffusion_models
```

SDXL checkpoint

```sh
# Repository: stabilityai/stable-diffusion-xl-base-1.0
# Revision: 462165984030d82259a11f4367a4eed129e94a7b
# In-repository path: sd_xl_base_1.0.safetensors
# URL: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/462165984030d82259a11f4367a4eed129e94a7b/sd_xl_base_1.0.safetensors
# Placement: .runtime/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors
# Size (bytes): 6938078334
# SHA-256: 31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b
```

diffusion

```sh
# Repository: unsloth/Qwen-Image-Edit-2511-GGUF
# Revision: 0d33d9692b4b26212297240d87b0d4719aa4fd06
# In-repository path: qwen-image-edit-2511-Q8_0.gguf
# URL: https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF/resolve/0d33d9692b4b26212297240d87b0d4719aa4fd06/qwen-image-edit-2511-Q8_0.gguf
# Placement: .runtime/ComfyUI/models/diffusion_models/qwen-image-edit-2511-Q8_0.gguf
# Size (bytes): 21761817184
# SHA-256: ab4f0622fb002fccaaa679a2ecce6fd1b3190d8ea28a5b7b2b17b8669bc24afa
```

text encoder

```sh
# Repository: unsloth/Qwen2.5-VL-7B-Instruct-GGUF
# Revision: 68bb8bc4b7df5289c143aaec0ab477a7d4051aab
# In-repository path: Qwen2.5-VL-7B-Instruct-Q8_0.gguf
# URL: https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/resolve/68bb8bc4b7df5289c143aaec0ab477a7d4051aab/Qwen2.5-VL-7B-Instruct-Q8_0.gguf
# Placement: .runtime/ComfyUI/models/text_encoders/Qwen2.5-VL-7B-Instruct-Q8_0.gguf
# Size (bytes): 8098524032
# SHA-256: ee770c700d7429cc6f0c74d6c7ab3c063bf521312fc36e80776d1d79bc9fa4ad
```

vision projector

```sh
# Repository: unsloth/Qwen2.5-VL-7B-Instruct-GGUF
# Revision: 68bb8bc4b7df5289c143aaec0ab477a7d4051aab
# In-repository path: mmproj-F16.gguf
# URL: https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/resolve/68bb8bc4b7df5289c143aaec0ab477a7d4051aab/mmproj-F16.gguf
# Placement: .runtime/ComfyUI/models/text_encoders/Qwen2.5-VL-7B-Instruct-mmproj-F16.gguf
# Size (bytes): 1354163040
# SHA-256: 987dd0733033fb5dd9b124d1ca926ae865572e432384eee7618b2eec3e735e17
```

VAE

```sh
# Repository: Comfy-Org/Qwen-Image_ComfyUI
# Revision: 1f12b17be14c89b026c51a91d67c32f84bb047bc
# In-repository path: split_files/vae/qwen_image_vae.safetensors
# URL: https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/1f12b17be14c89b026c51a91d67c32f84bb047bc/split_files/vae/qwen_image_vae.safetensors
# Placement: .runtime/ComfyUI/models/vae/qwen_image_vae.safetensors
# Size (bytes): 253806246
# SHA-256: a70580f0213e67967ee9c95f05bb400e8fb08307e017a924bf3441223e023d1f
```

GPU worker — private model report (repeat after any model file change)

```sh
cd /opt/shot-board
.runtime/engine-venv/bin/python scripts/model_report.py --models-dir .runtime/ComfyUI/models > .runtime/engine-models.json.tmp && mv .runtime/engine-models.json.tmp .runtime/engine-models.json
```

GPU worker — terminal 1, engine; Ctrl-C to stop

```sh
cd /opt/shot-board
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN COMFY_API_KEY
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NO_PROXY=127.0.0.1,localhost
mkdir -p .runtime/input .runtime/output .runtime/user
.runtime/engine-venv/bin/python .runtime/ComfyUI/main.py --listen 127.0.0.1 --port 8188 --input-directory "$PWD/.runtime/input" --output-directory "$PWD/.runtime/output" --user-directory "$PWD/.runtime/user" --offline --disable-partner-nodes --disable-auto-launch --preview-method none --cache-lru 8 --reserve-vram 1 --disable-dynamic-vram --disable-fast-disk
```

GPU worker — terminal 2, SDK proxy; Ctrl-C to stop

```sh
cd /opt/shot-board
.runtime/engine-venv/bin/comfy-api-proxy run --host 127.0.0.1 --port 8189 --comfyui http://127.0.0.1:8188 --state-dir "$PWD/.runtime/proxy"
```

CPU client — optional remote worker report copy and SSH tunnel; Ctrl-C to stop

```sh
cd /path/to/shot-board
mkdir -p .runtime
# Configure an SSH alias with the worker address, port and key
export GPU_SSH=gpu-worker
scp "$GPU_SSH:/opt/shot-board/.runtime/engine-models.json" .runtime/engine-models.json
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18188:127.0.0.1:8188 -L 127.0.0.1:18189:127.0.0.1:8189 "$GPU_SSH"
```

CPU client — another terminal, app for the remote worker; Ctrl-C to stop

```sh
cd /path/to/shot-board
ENGINE_MODE=remote COMFY_BASE_URL=http://127.0.0.1:18189 COMFY_ENGINE_URL=http://127.0.0.1:18188 SHOTBOARD_ENGINE_MANIFEST="$PWD/.runtime/engine-models.json" .venv/bin/python -m uvicorn shotboard.server:app --host 127.0.0.1 --port 8790
# Open http://127.0.0.1:8790
# Hero: a picked SDXL original only; Qwen edits cannot be heroes
```

Local GPU alternative — app on the GPU worker, no tunnel

```sh
cd /opt/shot-board
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.lock.txt --require-hashes
ENGINE_MODE=local COMFY_BASE_URL=http://127.0.0.1:8189 COMFY_ENGINE_URL=http://127.0.0.1:8188 SHOTBOARD_ENGINE_MANIFEST="$PWD/.runtime/engine-models.json" .venv/bin/python -m uvicorn shotboard.server:app --host 127.0.0.1 --port 8790
# ENGINE_MODE: local or remote; remote skips client memory_pressure/swap checks
# Default inference: loopback port 8188 => local; other loopback ports => remote tunnel
# Set ENGINE_MODE explicitly for a tunnel on 8188 or a local engine on another port
# Engine and proxy control URLs must remain loopback HTTP in both modes
```

SDXL lock maintenance — explicit operator action, separate from setup

```sh
# Replace the revision below with a reviewed full 40-character commit
.venv/bin/python scripts/update_model_lock.py --update-lock --revision 462165984030d82259a11f4367a4eed129e94a7b
# Review and commit workflows/model-lock.json separately; downloads never rewrite it
```
