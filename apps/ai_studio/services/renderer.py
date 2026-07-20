import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoFormat:
    """Configuration for a target social media video format."""
    width: int
    height: int
    fps: int
    duration: int  # in frames

    @property
    def frame_range(self) -> str:
        return f"0-{self.duration - 1}"


# Formats mirrored 1:1 from the frontend's SOCIAL_FORMATS (ids, ratios, durations).
# Keep the "id" values in sync with app/editor's SOCIAL_FORMATS array.
SOCIAL_FORMATS: Dict[str, VideoFormat] = {
    "ig":     VideoFormat(1080, 1350, 30, 360),  # 4:5   – 12s
    "square": VideoFormat(1080, 1080, 30, 360),  # 1:1   – 12s
    "story":  VideoFormat(1080, 1920, 30, 450),  # 9:16  – 15s
    "yt":     VideoFormat(1920, 1080, 30, 450),  # 16:9  – 15s
    "tiktok": VideoFormat(1080, 1920, 30, 360),  # 9:16  – 12s
    "banner": VideoFormat(1680,  720, 30, 300),  # 21:9  – 10s
}


class RemotionRenderer:
    """
    Renders the PromoVideo composition via a small Node.js render script
    (remotion/render.mjs) that calls @remotion/renderer's bundle() /
    selectComposition() / renderMedia() directly against the composition
    file.

    This replaces the old approach of shelling out to
    `npx remotion render <index.ts entry> PromoVideo ...`:

    - There is no separate Remotion "entry point" (index.ts / registerRoot)
      to discover on disk anymore. The Node script bundles straight from
      the composition file.
    - There are no Chrome/Puppeteer flags, executable paths, or --gl /
      --browser-timeout CLI args to manage. @remotion/renderer downloads
      and drives its own headless browser (chrome-headless-shell)
      internally on first use, with zero configuration from us.
    """

    DEFAULT_RENDER_TIMEOUT = 300  # seconds, total time allowed for the subprocess

    def __init__(
        self,
        project_root: Optional[Path] = None,
        node_path: Optional[Path] = None,
        render_timeout: int = DEFAULT_RENDER_TIMEOUT,
    ):
        self.project_root = project_root or self._find_project_root()
        self.node_path = node_path or self._find_node()
        self.render_script = self._find_render_script(self.project_root)
        self.render_timeout = render_timeout

    # ----------------------------------------------------------------------
    # Discovery methods
    # ----------------------------------------------------------------------

    @staticmethod
    def _find_node() -> Path:
        """Locate the node executable on PATH. Raises EnvironmentError if not found."""
        node_cmd = shutil.which("node")
        if node_cmd:
            return Path(node_cmd)

        raise EnvironmentError(
            "node not found. Install Node.js from https://nodejs.org, "
            "ensure it is on your PATH, and restart the worker."
        )

    @staticmethod
    def _find_project_root() -> Path:
        """
        Find the render project root by walking up until package.json is found.
        Can be overridden by the REMOTION_PROJECT_ROOT environment variable.
        """
        env_override = os.environ.get("REMOTION_PROJECT_ROOT")
        if env_override:
            p = Path(env_override)
            if p.is_dir():
                return p

        here = Path(__file__).resolve().parent
        for _ in range(6):
            if (here / "package.json").is_file():
                return here
            here = here.parent

        raise EnvironmentError(
            "Could not locate the render project root (no package.json found). "
            "Set REMOTION_PROJECT_ROOT environment variable."
        )

    @staticmethod
    def _find_render_script(project_root: Path) -> Path:
        """
        Locate the standalone render script, a thin wrapper around
        @remotion/renderer's programmatic bundle()/renderMedia() API.
        Overridable via REMOTION_RENDER_SCRIPT for non-standard layouts.
        """
        env_override = os.environ.get("REMOTION_RENDER_SCRIPT")
        if env_override:
            p = Path(env_override)
            if p.is_file():
                return p

        candidate = project_root / "remotion" / "render.mjs"
        if candidate.is_file():
            return candidate

        raise FileNotFoundError(
            f"Render script not found: {candidate}\n"
            "Expected remotion/render.mjs, or set REMOTION_RENDER_SCRIPT."
        )

    # ----------------------------------------------------------------------
    # Environment construction
    # ----------------------------------------------------------------------

    def _build_render_env(self) -> Dict[str, str]:
        """Build the environment dictionary for the subprocess (CI-friendly only)."""
        env = os.environ.copy()
        env.setdefault("CI", "1")
        return env

    # ----------------------------------------------------------------------
    # Core rendering method
    # ----------------------------------------------------------------------

    def render(
        self,
        props: Dict[str, Any],
        output_path: Path,
        format_name: str = "ig",
        verbose: bool = False,
        retries: int = 1,
    ) -> Path:
        """
        Render a Remotion video.

        Args:
            props: Dictionary of props passed to the composition.
            output_path: Where to save the rendered video.
            format_name: Key in SOCIAL_FORMATS (must match frontend format ids).
            verbose: Enable verbose logging from the render script.
            retries: Number of retry attempts on failure (0 for no retry).

        Returns:
            The output_path (validated).

        Raises:
            RuntimeError: If rendering fails permanently.
        """
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        format_config = SOCIAL_FORMATS.get(format_name)
        if not format_config:
            raise ValueError(f"Unknown format: {format_name}. Available: {list(SOCIAL_FORMATS.keys())}")

        render_env = self._build_render_env()
        last_exception = None

        # Props/config go in a temp JSON file rather than a CLI arg: avoids
        # OS argv-length limits and shell-escaping issues with long headlines
        # or base64 image data, and keeps the render script's CLI trivial.
        config_path = self._write_config_file(props, format_config, output_path)

        try:
            cmd = [str(self.node_path), str(self.render_script), "--config", str(config_path)]
            if verbose:
                cmd.append("--verbose")

            for attempt in range(retries + 1):
                try:
                    if attempt > 0:
                        logger.warning(
                            "Retry attempt %d of %d for render %s",
                            attempt,
                            retries,
                            output_path.name,
                        )

                    self._run_render_command(cmd, render_env)

                    if output_path.is_file():
                        return output_path
                    raise RuntimeError(f"Render completed but output file is missing: {output_path}")

                except subprocess.TimeoutExpired as e:
                    last_exception = e
                    logger.error("Render attempt %d timed out: %s", attempt, e)
                    if attempt >= retries:
                        raise RuntimeError(
                            f"Render timed out after {self.render_timeout}s and all retries exhausted."
                        ) from e
                    continue
                except (subprocess.CalledProcessError, RuntimeError) as e:
                    last_exception = e
                    logger.error("Render attempt %d failed: %s", attempt, e)
                    if attempt >= retries:
                        raise
                    continue

            raise RuntimeError(f"Render failed after {retries} retries.") from last_exception
        finally:
            config_path.unlink(missing_ok=True)

    def _write_config_file(
        self,
        props: Dict[str, Any],
        format_config: VideoFormat,
        output_path: Path,
    ) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(
                {
                    "compositionId": "PromoVideo",
                    "inputProps": props,
                    "width": format_config.width,
                    "height": format_config.height,
                    "fps": format_config.fps,
                    "durationInFrames": format_config.duration,
                    "outputPath": str(output_path),
                },
                tmp,
                ensure_ascii=False,
            )
            return Path(tmp.name)

    # ----------------------------------------------------------------------
    # Still-frame rendering (NEW — powers PNG/PDF flyer export)
    # ----------------------------------------------------------------------

    def render_still(
        self,
        props: Dict[str, Any],
        output_path: Path,
        width: int,
        height: int,
        frame: int,
        verbose: bool = False,
        retries: int = 1,
    ) -> Path:
        """
        Render a single still PNG frame of the PromoVideo composition.

        Reuses the exact same render.mjs entry point as render(), just with
        a "stillFrame" key in the config instead of "durationInFrames" +
        "fps". This tells render.mjs to call Remotion's renderStill()
        instead of renderMedia() — same bundling, same composition file,
        same headless browser, zero new infra.

        NOTE: render.mjs needs a small branch added to support this — see
        the "Node-side" note below this class. Nothing here touches the
        existing render()/generate_video() path.
        """
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        render_env = self._build_render_env()
        last_exception = None

        config_path = self._write_still_config_file(props, output_path, width, height, frame)

        try:
            cmd = [str(self.node_path), str(self.render_script), "--config", str(config_path)]
            if verbose:
                cmd.append("--verbose")

            for attempt in range(retries + 1):
                try:
                    if attempt > 0:
                        logger.warning(
                            "Retry attempt %d of %d for still render %s",
                            attempt,
                            retries,
                            output_path.name,
                        )

                    self._run_render_command(cmd, render_env)

                    if output_path.is_file():
                        return output_path
                    raise RuntimeError(f"Still render completed but output file is missing: {output_path}")

                except subprocess.TimeoutExpired as e:
                    last_exception = e
                    logger.error("Still render attempt %d timed out: %s", attempt, e)
                    if attempt >= retries:
                        raise RuntimeError(
                            f"Still render timed out after {self.render_timeout}s and all retries exhausted."
                        ) from e
                    continue
                except (subprocess.CalledProcessError, RuntimeError) as e:
                    last_exception = e
                    logger.error("Still render attempt %d failed: %s", attempt, e)
                    if attempt >= retries:
                        raise
                    continue

            raise RuntimeError(f"Still render failed after {retries} retries.") from last_exception
        finally:
            config_path.unlink(missing_ok=True)

    def _write_still_config_file(
        self,
        props: Dict[str, Any],
        output_path: Path,
        width: int,
        height: int,
        frame: int,
    ) -> Path:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            json.dump(
                {
                    "compositionId": "PromoVideo",
                    "inputProps": props,
                    "width": width,
                    "height": height,
                    "fps": 30,
                    "stillFrame": frame,   # ← presence of this key signals render.mjs to use renderStill()
                    "outputPath": str(output_path),
                },
                tmp,
                ensure_ascii=False,
            )
            return Path(tmp.name)

    def _run_render_command(self, cmd: list, env: dict) -> None:
        """Execute the render subprocess with capture and logging."""
        logger.debug("Running command: %s", " ".join(cmd))
        logger.debug("Working directory: %s", self.project_root)

        result = subprocess.run(
            cmd,
            cwd=str(self.project_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=self.render_timeout,
            check=False,  # return code handled manually below
        )

        self._log_subprocess_output(result)

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd,
                output=result.stdout,
                stderr=result.stderr,
            )

    @staticmethod
    def _log_subprocess_output(result: subprocess.CompletedProcess) -> None:
        """Log stdout/stderr with appropriate levels."""
        if result.stdout:
            stdout = result.stdout[:2000] + ("..." if len(result.stdout) > 2000 else "")
            logger.info("STDOUT:\n%s", stdout)
        if result.stderr:
            stderr = result.stderr[:2000] + ("..." if len(result.stderr) > 2000 else "")
            logger.warning("STDERR:\n%s", stderr)

        logger.info("Return code: %d", result.returncode)


# ----------------------------------------------------------------------
# Module-level convenience function (backwards compatible)
# ----------------------------------------------------------------------

def generate_video(
    props: dict,
    output_path: str,
    format_name: str = "ig",
    verbose: bool = False,
) -> str:
    """
    Legacy-compatible wrapper for RemotionRenderer.render().

    Signature is unchanged, so the stage_6 caller (`generate_video(props=...,
    output_path=..., format_name=..., verbose=...)`) keeps working as-is.
    """
    renderer = RemotionRenderer()
    rendered_path = renderer.render(
        props=props,
        output_path=Path(output_path),
        format_name=format_name,
        verbose=verbose,
        retries=1,
    )
    return str(rendered_path)


# ----------------------------------------------------------------------
# NEW — flyer still-image export (PNG / PDF), reusing the same renderer
# ----------------------------------------------------------------------

# Default canvas for the still flyer export — matches the editor's default
# portrait canvas ratio (4:5), independent of the video's SOCIAL_FORMATS
# since the flyer export isn't tied to a social-platform aspect ratio.
FLYER_STILL_WIDTH = 1080
FLYER_STILL_HEIGHT = 1350

# Frame index in the PromoVideo timeline where headline, price, subtext,
# and CTA are all fully faded in and settled (see PromoVideo's Sequence/
# interpolate offsets — CTA underline finishes animating at frame 195,
# well before the outro sequence begins). Picked comfortably after that
# so nothing is mid-animation in the captured still.
FLYER_STILL_FRAME = 200


def generate_flyer_image(
    props: dict,
    output_path: str,
    format: str = "png",
    width: int = FLYER_STILL_WIDTH,
    height: int = FLYER_STILL_HEIGHT,
    frame: int = FLYER_STILL_FRAME,
    verbose: bool = False,
) -> str:
    """
    Render a still flyer image from the same PromoVideo composition used
    for video export, capturing one fully-settled frame instead of the
    full animated timeline.

    format="png" -> writes the PNG straight from Remotion's renderStill().
    format="pdf" -> renders the PNG first, then wraps it losslessly into a
                    single-page PDF via Pillow (no separate PDF rendering
                    pipeline needed).

    This keeps the flyer image and the flyer video perfectly in sync: both
    come from the exact same composition and the exact same live editor
    props, just video captures every frame and this captures one.
    """
    output_path = Path(output_path)
    renderer = RemotionRenderer()

    if format == "png":
        rendered_path = renderer.render_still(
            props=props,
            output_path=output_path,
            width=width,
            height=height,
            frame=frame,
            verbose=verbose,
            retries=1,
        )
        return str(rendered_path)

    if format == "pdf":
        # Render the PNG to a temp file first, then convert.
        with tempfile.TemporaryDirectory() as tmp_dir:
            png_path = Path(tmp_dir) / "flyer_still.png"
            renderer.render_still(
                props=props,
                output_path=png_path,
                width=width,
                height=height,
                frame=frame,
                verbose=verbose,
                retries=1,
            )

            try:
                from PIL import Image
            except ImportError as exc:
                raise RuntimeError(
                    "Pillow is required for PDF export (pip install Pillow)."
                ) from exc

            image = Image.open(png_path).convert("RGB")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(output_path, "PDF", resolution=150.0)

        return str(output_path)

    raise ValueError(f"Unknown flyer export format: {format}. Available: ['png', 'pdf']")