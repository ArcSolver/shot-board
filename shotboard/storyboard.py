"""CPU-only, deterministic social storyboards from verified selected stills."""
import hashlib
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SIZES = {"landscape": (1600, 900), "portrait": (1080, 1350)}


def selected_takes(board, data_root):
    selected = []
    for shot in board["shots"]:
        take = next((t for t in shot["takes"] if t["id"] == shot["picked"] and t["status"] == "succeeded"), None)
        if take is None:
            raise ValueError("Pick one completed take for every shot before exporting.")
        path = Path(data_root) / board["id"] / take["image"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != take["image_sha256"]:
            raise ValueError("A picked image changed on disk; export stopped.")
        selected.append((shot, take, path))
    return selected


def wrap(draw, text, font, width):
    lines, line = [], ""
    for char in text:
        if char == "\n" or draw.textlength(line + char, font=font) > width:
            lines.append(line)
            line = "" if char == "\n" else char
        else:
            line += char
    return lines + [line]


def storyboard_png(board, data_root, layout="landscape"):
    if layout not in SIZES:
        raise ValueError("Choose landscape or portrait.")
    selected = selected_takes(board, data_root)
    width, height = SIZES[layout]
    canvas = Image.new("RGB", (width, height), "#131314")
    draw = ImageDraw.Draw(canvas)
    font = lambda size: ImageFont.load_default(size=size)
    margin, gap = (42, 20) if layout == "landscape" else (34, 18)
    draw.text((margin, 26), "SHOT BOARD", font=font(21), fill="#0a84ff")
    scene = ' '.join(board["config"]["scene"].split())
    # Bound the header so all 6–9 cuts retain image space, including old boards
    # saved before input normalization. All valid 600-character scenes fit.
    scene_font = font(24)
    scene_lines = wrap(draw, scene, scene_font, width-2*margin)
    while len(scene_lines) * (scene_font.size + 6) > 180 and scene_font.size > 6:
        scene_font = font(scene_font.size - 1)
        scene_lines = wrap(draw, scene, scene_font, width-2*margin)
    y = 65
    for line in scene_lines:
        draw.text((margin, y), line, font=scene_font, fill="#f1f1f4")
        y += scene_font.size + 6
    top, bottom = y+20, height-63
    cols = 3 if layout == "landscape" else 2
    rows = (len(selected)+cols-1)//cols
    cell_w = (width-2*margin-gap*(cols-1))//cols
    cell_h = (bottom-top-gap*(rows-1))//rows
    if cell_h < 70:
        raise ValueError("Scene line is too long for this storyboard layout. Shorten the scene before exporting.")
    for i, (shot, take, path) in enumerate(selected):
        x, y = margin+(i % cols)*(cell_w+gap), top+(i//cols)*(cell_h+gap)
        draw.rectangle((x,y,x+cell_w,y+cell_h), fill="#1f2021")
        image_h = cell_h-43
        with Image.open(path) as original:
            image = original.convert("RGB")
            image.thumbnail((cell_w, image_h), Image.Resampling.LANCZOS)
            canvas.paste(image, (x+(cell_w-image.width)//2, y+(image_h-image.height)//2))
        label = f"{i+1:02}  {shot['title']}"
        label_font = font(16)
        lines = wrap(draw, label, label_font, cell_w-90)
        while len(lines) > 2 and label_font.size > 6:
            label_font = font(label_font.size-1)
            lines = wrap(draw, label, label_font, cell_w-90)
        for line_index, line in enumerate(lines):
            draw.text((x+12,y+image_h+5+line_index*18), line, font=label_font, fill="#f1f1f4")
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", compress_level=9)
    return buffer.getvalue()
