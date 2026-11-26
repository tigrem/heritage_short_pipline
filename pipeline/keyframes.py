"""Generate and cache storyboard keyframes with Cloudflare Workers AI."""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import tempfile
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from dotenv import dotenv_values
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

from pipeline.cache import load_cached_output, save_cached_output
from pipeline.logger import log_cache_hit, log_call
from pipeline.retry import is_transient_error, retry
from pipeline.validate import ASSETS_REFS_DIR, STORYBOARD_PATH, validate_storyboard

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = _PROJECT_ROOT / "outputs" / "keyframes"
FAILURES_PATH = _PROJECT_ROOT / "FAILURES.md"
DEFAULT_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
DEFAULT_REFERENCE_MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct"
REFERENCE_PROMPT = (
    "Describe only the visible appearance, clothing, setting, lighting, and "
    "distinctive visual details in this attached reference image. Be concise; "
    "do not invent people or infer identity."
)
MAX_ATTEMPTS = 3
MAX_REFS = 3
MAX_REFERENCE_DESCRIPTION_CHARS = 140
MIN_IMAGE_DIMENSION = 512
MIN_PIXEL_VARIANCE = 25.0
VISUAL_PROMPT_GUARD = (
    "Strict framing and anatomy guard: match the described shot and references; "
    "every visible person has a complete, clearly visible head and face with "
    "natural headroom, complete natural anatomy, and no cropped heads, missing "
    "or blank faces, extra people, or malformed limbs. Include no instruments "
    "or props unless the shot explicitly requests them."
)
IDENTITY_LOCATION_GUARD = (
    "Canonical reference preservation: the attached Eden and Ato Girma images "
    "define their identities. Keep the same apparent age, skin tone, face shape, "
    "hair color, hairstyle and texture, body build, clothing silhouette, colors, "
    "and woven garment patterns. Change pose and facial expression only as "
    "required by this shot. Use the attached location image as the setting; "
    "preserve its room layout, windows, furniture, colors, and textiles. Make "
    "one continuous cinematic scene, not a collage, portrait panel, or card. "
    "Do not add people, wardrobe, props, or locations that are not requested."
)
REFERENCE_ANCHORS = {
    "eden.jpeg": (
        "Eden character anchor: young Ethiopian woman with medium-brown skin, "
        "long dark curly hair, and a teal dress; ignore the white studio backdrop."
    ),
    "girma.png": (
        "Ato Girma character anchor: elderly Ethiopian man with white curly hair "
        "and beard, wearing a white traditional garment with colorful green-red "
        "woven trim; ignore the white studio backdrop."
    ),
    "living_room.jpg": (
        "Living-room anchor: warm wood furnishings, beige sofa, colorful woven "
        "textiles, books, framed art, plants, and daylight."
    ),
    "story_telling_area.jpg": (
        "Storytelling-area anchor: traditional carved wooden chair, bright "
        "windows, patterned woven textiles, and warm domestic details."
    ),
}
CONDITIONING_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
LOCKED_COMPOSITION_MODEL = "pillow-reference-locked-composite"
LOCKED_COMPOSITION_VERSION = 2
PROMPT_CONTRACT_VERSION = 5
KEYFRAME_MODES = frozenset(("reference_locked", "reference_conditioned", "ai"))
ALLOWED_REFS = frozenset(
    ("eden.jpeg", "girma.png", "living_room.jpg", "story_telling_area.jpg")
)


class CloudflareAPIError(RuntimeError):
    """Workers AI returned an unsuccessful HTTP response."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        super().__init__(f"Cloudflare Workers AI HTTP {status_code}: {detail}")


class KeyframeQualityError(ValueError):
    """A generated image failed basic integrity or framing-quality checks."""

    transient = True


def _setting(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value.strip()
    value = dotenv_values(_PROJECT_ROOT / ".env").get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _keyframe_mode() -> str:
    mode = (_setting("KEYFRAME_MODE", "reference_conditioned") or "").casefold()
    if mode not in KEYFRAME_MODES:
        raise ValueError(
            "KEYFRAME_MODE must be 'reference_conditioned', "
            "'reference_locked', or 'ai'."
        )
    return mode


def _credentials() -> tuple[str, str]:
    account_id = _setting("CLOUDFLARE_ACCOUNT_ID")
    api_token = _setting("CLOUDFLARE_API_TOKEN")
    if not account_id or not api_token:
        raise RuntimeError(
            "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be configured "
            "in the environment or project .env."
        )
    return account_id, api_token


def _safe_error(error: Exception, token: str) -> str:
    return f"{type(error).__name__}: {str(error).replace(token, '[REDACTED]')}"[:1500]


def _request_model(
    model: str,
    payload: dict[str, Any],
    account_id: str,
    api_token: str,
) -> Any:
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    if model == CONDITIONING_MODEL:
        body, content_type = _multipart_form_data(payload)
    else:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        content_type = "application/json"
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": content_type,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        try:
            decoded = json.loads(detail)
            errors = decoded.get("errors", [])
            detail = "; ".join(
                str(item.get("message", item)) for item in errors
            ) or str(decoded.get("result", decoded))
        except json.JSONDecodeError:
            pass
        raise CloudflareAPIError(error.code, detail[:1000]) from error

    if "application/json" not in content_type:
        return {"image_bytes": data}
    result = json.loads(data.decode("utf-8"))
    if result.get("success") is False:
        errors = result.get("errors", [])
        detail = "; ".join(str(item.get("message", item)) for item in errors)
        raise RuntimeError(f"Cloudflare Workers AI request failed: {detail or result}")
    return result.get("result", result)


def _logged_request(
    *,
    stage: str,
    shot_id: str,
    model: str,
    seed: int | None,
    payload: dict[str, Any],
    account_id: str,
    api_token: str,
) -> Any:
    attempt_number = 0

    def request_and_log() -> dict[str, Any]:
        nonlocal attempt_number
        attempt_number += 1
        started = time.perf_counter()
        try:
            result = _request_model(model, payload, account_id, api_token)
        except Exception as error:
            log_call(
                stage,
                shot_id,
                model,
                seed,
                time.perf_counter() - started,
                "retrying"
                if attempt_number < MAX_ATTEMPTS and is_transient_error(error)
                else "failure",
                error=_safe_error(error, api_token),
            )
            raise
        log_call(
            stage,
            shot_id,
            model,
            seed,
            time.perf_counter() - started,
            "success",
        )
        return result

    return retry(
        request_and_log,
        attempts=MAX_ATTEMPTS,
        base_delay=1.0,
        max_delay=12.0,
        jitter=0.25,
    )


def _reference_path(filename: str) -> Path:
    if filename not in ALLOWED_REFS or Path(filename).name != filename:
        raise ValueError(f"Unsupported reference image: {filename!r}")
    path = ASSETS_REFS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Storyboard reference image does not exist: {path}")
    return path


def _reference_description(
    path: Path,
    shot_id: str,
    account_id: str,
    api_token: str,
) -> str:
    model = _setting("CF_REFERENCE_MODEL", DEFAULT_REFERENCE_MODEL)
    if model is None:
        raise RuntimeError("CF_REFERENCE_MODEL cannot be empty.")
    inputs = {
        "image": path,
        "prompt": REFERENCE_PROMPT,
        "model": model,
    }
    cached, output = load_cached_output("keyframe_reference", path.name, inputs)
    if cached:
        log_cache_hit("keyframe_reference", shot_id)
        return str(output["description"])[:MAX_REFERENCE_DESCRIPTION_CHARS]

    image = base64.b64encode(path.read_bytes()).decode("ascii")
    suffix = path.suffix.casefold()
    mime_type = "image/png" if suffix == ".png" else "image/jpeg"
    result = _logged_request(
        stage="keyframe_reference",
        shot_id=shot_id,
        model=model,
        seed=None,
        payload={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": REFERENCE_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image}"
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 160,
            "temperature": 0.0,
        },
        account_id=account_id,
        api_token=api_token,
    )
    if isinstance(result, str):
        description = result
    elif isinstance(result, dict):
        description = (
            result.get("description")
            or result.get("response")
            or result.get("text")
            or result.get("caption")
        )
    else:
        description = None
    if not isinstance(description, str) or not description.strip():
        raise ValueError(
            f"Reference model {model} returned no description for {path.name}."
        )
    description = " ".join(description.split())[:MAX_REFERENCE_DESCRIPTION_CHARS]
    save_cached_output(
        "keyframe_reference",
        path.name,
        inputs,
        {"description": description},
    )
    return description


def _multipart_form_data(payload: dict[str, Any]) -> tuple[bytes, str]:
    boundary = f"----heritage-short-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in payload.items():
        if isinstance(value, bytes):
            disposition = (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{name}.png"\r\n'
            )
            parts.extend(
                (
                    f"--{boundary}\r\n{disposition}"
                    "Content-Type: image/png\r\n\r\n".encode("ascii"),
                    value,
                    b"\r\n",
                )
            )
        else:
            parts.extend(
                (
                    f'--{boundary}\r\nContent-Disposition: form-data; '
                    f'name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"),
                )
            )
    parts.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _image_bytes(result: Any) -> bytes:
    if not isinstance(result, dict):
        raise ValueError("Cloudflare image response was not a JSON object.")
    direct_bytes = result.get("image_bytes")
    if isinstance(direct_bytes, bytes):
        return direct_bytes
    encoded = result.get("image")
    if isinstance(encoded, dict):
        encoded = encoded.get("data") or encoded.get("image")
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("Cloudflare image response did not contain an image.")
    return base64.b64decode(encoded, validate=True)


def _validate_generated_image(image_data: bytes, shot_id: str) -> None:
    try:
        with Image.open(io.BytesIO(image_data)) as image:
            image.load()
            width, height = image.size
            if width < MIN_IMAGE_DIMENSION or height < MIN_IMAGE_DIMENSION:
                raise KeyframeQualityError(
                    f"{shot_id} image is too small: {width}x{height}."
                )
            aspect_ratio = width / height
            if not 0.5 <= aspect_ratio <= 2.0:
                raise KeyframeQualityError(
                    f"{shot_id} image has unsupported aspect ratio {aspect_ratio:.2f}."
                )
            sample = image.convert("L").resize((64, 64))
            variance = ImageStat.Stat(sample).var[0]
            if variance < MIN_PIXEL_VARIANCE:
                raise KeyframeQualityError(
                    f"{shot_id} image is nearly blank (pixel variance {variance:.1f})."
                )
    except KeyframeQualityError:
        raise
    except (OSError, ValueError) as error:
        raise KeyframeQualityError(
            f"{shot_id} image could not be decoded: {error}"
        ) from error


def _reference_contact_sheet(
    ref_paths: list[Path],
    shot: dict[str, Any] | None = None,
) -> bytes:
    if not ref_paths:
        raise ValueError("Image-conditioned generation requires at least one ref.")
    if shot is not None:
        return _make_reference_locked_composite(shot, ref_paths)
    canvas = Image.new("RGB", (1024, 1024), (32, 32, 32))
    columns = 2 if len(ref_paths) > 1 else 1
    rows = (len(ref_paths) + columns - 1) // columns
    cell_width = 1024 // columns
    cell_height = 1024 // rows
    for index, path in enumerate(ref_paths):
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((cell_width - 24, cell_height - 24), Image.Resampling.LANCZOS)
            x = (index % columns) * cell_width + (cell_width - image.width) // 2
            y = (index // columns) * cell_height + (cell_height - image.height) // 2
            canvas.paste(image, (x, y))
    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def _reference_image_bytes(path: Path) -> bytes:
    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((511, 511), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="PNG")
    return output.getvalue()


def _build_prompt(
    shot: dict[str, Any],
    ref_paths: list[Path],
    descriptions: dict[str, str],
) -> str:
    for description_limit in (MAX_REFERENCE_DESCRIPTION_CHARS, 120, 100, 80, 60, 40, 20, 0):
        visual_anchors = "\n".join(
            f"Reference image {index} is {path.name}. "
            f"Visual anchor: {REFERENCE_ANCHORS[path.name]} "
            f"Observed reference details: "
            f"{descriptions.get(path.name, '')[:description_limit]}"
            for index, path in enumerate(ref_paths)
        )
        prompt_parts = [
            shot["keyframe_prompt"],
            f"Visual variation seed: {shot['seed']}.",
            "Use the supplied reference images as the only source for each character "
            "and the room. Keep their identity, apparent age, skin tone, facial "
            "features, hair, body build, clothing, and the room unchanged. Vary only "
            "the shot-specific posture, gesture, position, and expression.",
            IDENTITY_LOCATION_GUARD,
            visual_anchors,
            VISUAL_PROMPT_GUARD,
        ]
        prompt = "\n".join(part for part in prompt_parts if part)
        if len(prompt) <= 2048:
            return prompt
    compact_static = "\n".join(
        part
        for part in (
            f"Visual variation seed: {shot['seed']}.",
            "Change only posture, gesture, position in the room, and facial expression.",
            IDENTITY_LOCATION_GUARD,
            visual_anchors,
            VISUAL_PROMPT_GUARD,
        )
        if part
    )
    shot_prompt_budget = max(0, 2048 - len(compact_static) - 1)
    compact_prompt = f"{shot['keyframe_prompt'][:shot_prompt_budget]}\n{compact_static}"
    return compact_prompt[:2048]


def _append_quality_failure(shot_id: str, message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    escaped = message.replace("|", "\\|").replace("\n", " ")
    with FAILURES_PATH.open("a", encoding="utf-8", newline="\n") as report:
        report.write(
            f"\n## Keyframe quality failure — {timestamp}\n\n"
            "| Shot | Error |\n| --- | --- |\n"
            f"| `{shot_id}` | {escaped} |\n"
        )


def _write_image(path: Path, image_data: bytes) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: str | None = None
    try:
        with Image.open(io.BytesIO(image_data)) as image:
            converted = image.convert("RGB")
            normalized = io.BytesIO()
            converted.save(normalized, format="PNG")
            png_data = normalized.getvalue()
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as output:
                temp_path = output.name
                output.write(png_data)
        os.replace(temp_path, path)
        return png_data
    except Exception:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows = Path(os.environ.get("WINDIR", "C:\\Windows"))
    for candidate in (windows / "Fonts" / "arial.ttf", windows / "Fonts" / "segoeui.ttf"):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _make_disclosure_card(title: str) -> bytes:
    image = Image.new("RGB", (1920, 1080), (24, 23, 26))
    draw = ImageDraw.Draw(image)
    gold = (229, 198, 129)
    ivory = (245, 244, 239)
    title_font = _font(54)
    disclosure_font = _font(43)
    detail_font = _font(24)
    draw.line((660, 360, 1260, 360), fill=(112, 91, 56), width=3)
    for text, font, fill, y in (
        (title, title_font, gold, 420),
        ("AI-assisted film", disclosure_font, ivory, 530),
        ("Created with the assistance of artificial intelligence", detail_font, (185, 181, 171), 620),
    ):
        bounds = draw.textbbox((0, 0), text, font=font)
        draw.text(((1920 - (bounds[2] - bounds[0])) // 2, y), text, font=font, fill=fill)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _make_reference_locked_composite(
    shot: dict[str, Any],
    ref_paths: list[Path],
) -> bytes:
    """Compose the complete supplied character photos over the exact room photo."""
    location_name = shot.get("location_anchor")
    if location_name is None:
        location_name = next(
            (
                path.name
                for path in ref_paths
                if path.name in ("living_room.jpg", "story_telling_area.jpg")
            ),
            None,
        )
    if location_name is None:
        raise ValueError(f"{shot['shot_id']} has no approved location reference.")
    location_path = _reference_path(location_name)
    character_paths = [
        path for path in ref_paths if path.name in ("eden.jpeg", "girma.png")
    ]
    if not character_paths:
        raise ValueError(f"{shot['shot_id']} has no approved character reference.")

    canvas_size = (1024, 1024)
    with Image.open(location_path) as source:
        canvas = ImageOps.fit(
            source.convert("RGB"),
            canvas_size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )

    def cut_out_background(path: Path) -> tuple[Image.Image, Image.Image]:
        with Image.open(path) as source:
            rgb = source.convert("RGB")
        width, height = rgb.size
        pixels = rgb.load()
        background = pixels[0, 0]
        visited = bytearray(width * height)
        alpha = Image.new("L", (width, height), 255)
        alpha_pixels = alpha.load()

        from collections import deque

        queue: deque[tuple[int, int]] = deque()
        for x in range(width):
            queue.append((x, 0))
            queue.append((x, height - 1))
        for y in range(height):
            queue.append((0, y))
            queue.append((width - 1, y))

        while queue:
            x, y = queue.popleft()
            index = y * width + x
            if visited[index]:
                continue
            visited[index] = 1
            red, green, blue = pixels[x, y]
            if (
                abs(red - background[0]) > 34
                or abs(green - background[1]) > 34
                or abs(blue - background[2]) > 34
            ):
                continue
            alpha_pixels[x, y] = 0
            if x > 0:
                queue.append((x - 1, y))
            if x + 1 < width:
                queue.append((x + 1, y))
            if y > 0:
                queue.append((x, y - 1))
            if y + 1 < height:
                queue.append((x, y + 1))

        alpha = alpha.filter(ImageFilter.GaussianBlur(1.2))
        bbox = alpha.getbbox()
        if bbox is None:
            raise ValueError(f"Reference has no visible subject: {path.name}")
        rgb = rgb.crop(bbox)
        alpha = alpha.crop(bbox)
        return rgb, alpha

    characters: dict[str, tuple[Image.Image, Image.Image]] = {}
    for path in character_paths:
        characters[path.name] = cut_out_background(path)

    shot_id = shot["shot_id"]
    eden = characters.get("eden.jpeg")
    girma = characters.get("girma.png")

    close_shots = {"shot_03", "shot_04", "shot_05", "shot_06"}
    if shot_id in close_shots:
        selected = eden if eden is not None and shot_id == "shot_03" else girma
        if selected is not None:
            character, alpha = selected
            character.thumbnail((650, 920), Image.Resampling.LANCZOS)
            alpha = alpha.resize(character.size, Image.Resampling.LANCZOS)
            x = (canvas_size[0] - character.width) // 2
            y = canvas_size[1] - character.height - 12
            canvas.paste(character, (x, y), alpha)
    elif eden is not None and girma is not None:
        eden_image, eden_alpha = eden
        girma_image, girma_alpha = girma
        eden_image = eden_image.copy()
        girma_image = girma_image.copy()

        eden_height = 700 if shot_id in {"shot_07", "shot_08", "shot_09"} else 760
        girma_height = eden_height
        eden_image.thumbnail((520, eden_height), Image.Resampling.LANCZOS)
        girma_image.thumbnail((520, girma_height), Image.Resampling.LANCZOS)
        eden_alpha = eden_alpha.resize(eden_image.size, Image.Resampling.LANCZOS)
        girma_alpha = girma_alpha.resize(girma_image.size, Image.Resampling.LANCZOS)

        if shot_id in {"shot_08", "shot_09"}:
            eden_x = 170
            girma_x = 562
        else:
            eden_x = 100
            girma_x = 570
        eden_y = canvas_size[1] - eden_image.height - 12
        girma_y = canvas_size[1] - girma_image.height - 12
        canvas.paste(eden_image, (eden_x, eden_y), eden_alpha)
        canvas.paste(girma_image, (girma_x, girma_y), girma_alpha)
    elif eden is not None:
        character, alpha = eden
        character.thumbnail((650, 920), Image.Resampling.LANCZOS)
        alpha = alpha.resize(character.size, Image.Resampling.LANCZOS)
        x = (canvas_size[0] - character.width) // 2
        y = canvas_size[1] - character.height - 12
        canvas.paste(character, (x, y), alpha)
    elif girma is not None:
        character, alpha = girma
        character.thumbnail((650, 920), Image.Resampling.LANCZOS)
        alpha = alpha.resize(character.size, Image.Resampling.LANCZOS)
        x = (canvas_size[0] - character.width) // 2
        y = canvas_size[1] - character.height - 12
        canvas.paste(character, (x, y), alpha)

    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def _cache_inputs(
    shot: dict[str, Any],
    refs: list[Path],
    model: str,
    reference_model: str,
    descriptions: dict[str, str],
    title: str | None,
) -> dict[str, Any]:
    is_locked_composition = model == LOCKED_COMPOSITION_MODEL
    is_conditioned_model = model == CONDITIONING_MODEL
    return {
        "keyframe_prompt": None if is_locked_composition else shot["keyframe_prompt"],
        "prompt_guard": None if is_locked_composition else VISUAL_PROMPT_GUARD,
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        "locked_composition_version": (
            LOCKED_COMPOSITION_VERSION
            if is_locked_composition
            else None
        ),
        "seed": None if is_locked_composition else shot["seed"],
        "refs": refs,
        "location_anchor": (
            _reference_path(shot["location_anchor"])
            if shot.get("location_anchor") is not None
            else None
        ),
        "reference_anchors": {
            path.name: REFERENCE_ANCHORS[path.name] for path in refs
        },
        "reference_descriptions": descriptions,
        "model": model,
        "conditioning_mode": (
            "reference_locked_composite"
            if is_locked_composition
            else (
                "image_conditioned"
                if is_conditioned_model
                else "text_and_reference_anchors"
            )
        ),
        "reference_model": reference_model,
        "display_title": title,
        "guidance": 4.0 if is_conditioned_model else None,
        "strength": None,
        "steps": 4 if is_conditioned_model else (0 if is_locked_composition else 4),
        "reference_image_mode": (
            "individual_originals_under_512px"
            if is_conditioned_model
            else None
        ),
        "output_format": "png",
    }


def generate_keyframe(
    shot: dict[str, Any],
    title: str,
    output_dir: str | Path = OUTPUT_DIR,
) -> Path:
    """Generate one PNG keyframe and reuse it while all its inputs are unchanged."""
    shot_id = shot["shot_id"]
    output_path = Path(output_dir) / f"{shot_id}.png"
    mode = _keyframe_mode()
    if mode == "reference_locked":
        image_model = LOCKED_COMPOSITION_MODEL
    elif mode == "reference_conditioned":
        image_model = CONDITIONING_MODEL
    else:
        image_model = _setting("CF_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)
    reference_model = (
        _setting("CF_REFERENCE_MODEL", DEFAULT_REFERENCE_MODEL)
        if mode == "ai"
        else "not-used"
    )
    if not image_model or not reference_model:
        raise RuntimeError("CF_IMAGE_MODEL and CF_REFERENCE_MODEL must not be empty.")
    refs = shot["refs"]
    if len(refs) > MAX_REFS:
        raise ValueError(f"{shot_id} has more than {MAX_REFS} reference images.")
    ref_paths = [_reference_path(filename) for filename in refs]

    if shot["shot_type"] == "ai_disclosure_end_card":
        inputs = _cache_inputs(
            shot,
            ref_paths,
            "programmatic-disclosure-card",
            "not-used",
            {},
            title,
        )
        cached, saved = load_cached_output("keyframes", shot_id, inputs)
        if cached and output_path.is_file():
            try:
                cached_data = base64.b64decode(saved["image_base64"], validate=True)
                _validate_generated_image(cached_data, shot_id)
                if output_path.read_bytes() == cached_data:
                    log_cache_hit("keyframes", shot_id, shot.get("seed"))
                    return output_path
            except (KeyError, ValueError) as error:
                log_call(
                    "keyframes_quality",
                    shot_id,
                    "Pillow disclosure card",
                    shot["seed"],
                    0.0,
                    "failure",
                    error=f"Invalid cached disclosure image: {error}"[:1500],
                )
        started = time.perf_counter()
        try:
            image_data = _make_disclosure_card(title)
            _validate_generated_image(image_data, shot_id)
            image_data = _write_image(output_path, image_data)
            save_cached_output(
                "keyframes",
                shot_id,
                inputs,
                {"image_base64": base64.b64encode(image_data).decode("ascii")},
            )
        except Exception as error:
            log_call(
                "keyframes",
                shot_id,
                "Pillow disclosure card",
                shot["seed"],
                time.perf_counter() - started,
                "failure",
                error=f"{type(error).__name__}: {error}"[:1500],
            )
            raise
        log_call(
            "keyframes",
            shot_id,
            "Pillow disclosure card",
            shot["seed"],
            time.perf_counter() - started,
            "success",
        )
        return output_path

    if mode == "reference_locked":
        inputs = _cache_inputs(
            shot,
            ref_paths,
            LOCKED_COMPOSITION_MODEL,
            reference_model,
            {},
            None,
        )
        cached, saved = load_cached_output("keyframes", shot_id, inputs)
        if cached and output_path.is_file():
            try:
                cached_data = base64.b64decode(saved["image_base64"], validate=True)
                _validate_generated_image(cached_data, shot_id)
                if output_path.read_bytes() == cached_data:
                    log_cache_hit("keyframes", shot_id, shot.get("seed"))
                    return output_path
            except (KeyError, ValueError) as error:
                log_call(
                    "keyframes_quality",
                    shot_id,
                    LOCKED_COMPOSITION_MODEL,
                    shot.get("seed"),
                    0.0,
                    "failure",
                    error=f"Invalid cached reference composition: {error}"[:1500],
                )

        started = time.perf_counter()
        try:
            image_data = _make_reference_locked_composite(shot, ref_paths)
            _validate_generated_image(image_data, shot_id)
            image_data = _write_image(output_path, image_data)
            save_cached_output(
                "keyframes",
                shot_id,
                inputs,
                {"image_base64": base64.b64encode(image_data).decode("ascii")},
            )
        except Exception as error:
            log_call(
                "keyframes",
                shot_id,
                LOCKED_COMPOSITION_MODEL,
                shot.get("seed"),
                time.perf_counter() - started,
                "failure",
                error=f"{type(error).__name__}: {error}"[:1500],
            )
            raise
        log_call(
            "keyframes",
            shot_id,
            LOCKED_COMPOSITION_MODEL,
            shot.get("seed"),
            time.perf_counter() - started,
            "success",
        )
        return output_path

    account_id, api_token = _credentials()
    descriptions = {
        path.name: _reference_description(path, shot_id, account_id, api_token)
        for path in ref_paths
    } if mode == "ai" else {}
    inputs = _cache_inputs(
        shot, ref_paths, image_model, reference_model, descriptions, None
    )
    cached, saved = load_cached_output("keyframes", shot_id, inputs)
    if cached:
        try:
            image_data = base64.b64decode(saved["image_base64"], validate=True)
            _validate_generated_image(image_data, shot_id)
            if not output_path.is_file() or output_path.read_bytes() != image_data:
                image_data = _write_image(output_path, image_data)
                save_cached_output(
                    "keyframes",
                    shot_id,
                    inputs,
                    {"image_base64": base64.b64encode(image_data).decode("ascii")},
                )
            log_cache_hit("keyframes", shot_id, shot.get("seed"))
            return output_path
        except (KeyError, ValueError) as error:
            log_call(
                "keyframes_quality",
                shot_id,
                image_model,
                shot["seed"],
                0.0,
                "failure",
                error=f"Invalid cached keyframe: {error}"[:1500],
            )

    prompt = _build_prompt(shot, ref_paths, descriptions)
    payload: dict[str, Any] = {"prompt": prompt, "steps": 4}
    if image_model == CONDITIONING_MODEL:
        payload = {
            "prompt": prompt,
            **{
                f"input_image_{index}": _reference_image_bytes(path)
                for index, path in enumerate(ref_paths)
            },
            "width": 1024,
            "height": 1024,
            "seed": int(shot["seed"]),
            "guidance": 4.0,
        }

    quality_attempt = 0

    def request_valid_image() -> bytes:
        nonlocal quality_attempt
        try:
            result = _logged_request(
                stage="keyframes",
                shot_id=shot_id,
                model=image_model,
                seed=shot["seed"],
                payload=payload,
                account_id=account_id,
                api_token=api_token,
            )
            generated = _image_bytes(result)
            _validate_generated_image(generated, shot_id)
            return generated
        except (OSError, ValueError) as error:
            quality_attempt += 1
            quality_error = (
                error
                if isinstance(error, KeyframeQualityError)
                else KeyframeQualityError(f"{shot_id} returned invalid image data: {error}")
            )
            log_call(
                "keyframes_quality",
                shot_id,
                image_model,
                shot["seed"],
                0.0,
                "retrying" if quality_attempt < MAX_ATTEMPTS else "failure",
                error=str(quality_error)[:1500],
            )
            raise quality_error from error

    try:
        image_data = retry(
            request_valid_image,
            attempts=MAX_ATTEMPTS,
            base_delay=1.0,
            max_delay=12.0,
            jitter=0.25,
            retry_if=lambda error: isinstance(error, KeyframeQualityError),
        )
    except KeyframeQualityError as error:
        _append_quality_failure(shot_id, str(error))
        raise
    image_data = _write_image(output_path, image_data)
    _validate_generated_image(image_data, shot_id)
    save_cached_output(
        "keyframes",
        shot_id,
        inputs,
        {"image_base64": base64.b64encode(image_data).decode("ascii")},
    )
    return output_path


def generate_keyframes(
    shots: list[dict[str, Any]],
    title: str,
    output_dir: str | Path = OUTPUT_DIR,
) -> dict[str, Path]:
    return {
        shot["shot_id"]: generate_keyframe(shot, title, output_dir)
        for shot in shots
    }


def _validated_file(path: Path, shot_id: str) -> bool:
    try:
        _validate_generated_image(path.read_bytes(), shot_id)
        return True
    except (OSError, ValueError):
        return False


def has_current_keyframe(shot: dict[str, Any], title: str | None = None) -> bool:
    """Check that the current keyframe cache matches the shot and its reference files."""
    try:
        mode = _keyframe_mode()
    except ValueError:
        return False
    image_model = "programmatic-disclosure-card"
    reference_model = "not-used"
    if shot["shot_type"] != "ai_disclosure_end_card":
        if mode == "reference_locked":
            image_model = LOCKED_COMPOSITION_MODEL
        elif mode == "reference_conditioned":
            image_model = CONDITIONING_MODEL
        else:
            image_model = _setting("CF_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)
            reference_model = _setting("CF_REFERENCE_MODEL", DEFAULT_REFERENCE_MODEL)
    if not image_model or not reference_model:
        return False
    try:
        paths = [_reference_path(filename) for filename in shot["refs"]]
        descriptions = (
            {}
            if (
                shot["shot_type"] == "ai_disclosure_end_card"
                or image_model == LOCKED_COMPOSITION_MODEL
                or image_model == CONDITIONING_MODEL
            )
            else {
                path.name: str(
                    load_cached_output(
                        "keyframe_reference",
                        path.name,
                        {
                            "image": path,
                            "prompt": REFERENCE_PROMPT,
                            "model": reference_model,
                        },
                    )[1]["description"]
                )[:MAX_REFERENCE_DESCRIPTION_CHARS]
                for path in paths
            }
        )
        inputs = _cache_inputs(
            shot,
            paths,
            image_model,
            reference_model,
            descriptions,
            title if shot["shot_type"] == "ai_disclosure_end_card" else None,
        )
        cached, saved = load_cached_output("keyframes", shot["shot_id"], inputs)
        output_path = OUTPUT_DIR / f"{shot['shot_id']}.png"
        return (
            cached
            and output_path.is_file()
            and output_path.read_bytes()
            == base64.b64decode(saved["image_base64"], validate=True)
            and _validated_file(output_path, shot["shot_id"])
        )
    except (OSError, KeyError, TypeError, ValueError):
        return False


def _read_storyboard() -> dict[str, Any]:
    errors = validate_storyboard()
    if errors:
        raise ValueError("Storyboard is invalid:\n- " + "\n- ".join(errors))
    return json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shot")
    args = parser.parse_args(argv)
    try:
        storyboard = _read_storyboard()
        shots = storyboard["shots"]
        if args.shot:
            shots = [shot for shot in shots if shot["shot_id"] == args.shot]
            if not shots:
                raise ValueError(f"Shot {args.shot} is not present in the storyboard.")
        generated = generate_keyframes(shots, storyboard["title"])
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Keyframe generation failed: {error}", file=sys.stderr)
        return 1
    print(f"Keyframes ready for {len(generated)} shot(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
