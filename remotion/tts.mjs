
import fs from "node:fs";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

// ============================================================================
// DEFAULT VOICE
// ============================================================================

export const DEFAULT_VOICE = "en-US-AriaNeural";

// ============================================================================
// HELPERS
// ============================================================================

function cleanString(value) {
  if (value === undefined || value === null) {
    return "";
  }

  return String(value).trim();
}

function ensureOutputDirectory(outputPath) {
  const directory = path.dirname(path.resolve(outputPath));

  fs.mkdirSync(directory, {
    recursive: true,
  });
}

// ============================================================================
// PYTHON COMMAND
// ============================================================================

function getPythonCommand() {
  /*
   * GitHub Ubuntu normally provides `python3`.
   * Windows local development normally provides `python`.
   */

  return process.platform === "win32"
    ? "python"
    : "python3";
}

// ============================================================================
// GENERATE VOICEOVER
// ============================================================================

export async function generateVoiceover({
  text,
  voice = DEFAULT_VOICE,
  outputPath,
}) {
  const narration = cleanString(text);
  const resolvedVoice =
    cleanString(voice) || DEFAULT_VOICE;

  const resolvedOutputPath =
    path.resolve(outputPath);

  if (!narration) {
    throw new Error(
      "Cannot generate voiceover: narration text is empty."
    );
  }

  if (!outputPath) {
    throw new Error(
      "Cannot generate voiceover: outputPath is missing."
    );
  }

  ensureOutputDirectory(resolvedOutputPath);

  console.log(
    `[tts] Generating voiceover with ${resolvedVoice}...`
  );

  console.log(
    `[tts] Output: ${resolvedOutputPath}`
  );

  const python = getPythonCommand();

  /*
   * edge-tts is installed in the GitHub Actions environment.
   *
   * Using:
   *
   *   python -m edge_tts
   *
   * is more reliable than relying on an npm executable.
   */

  try {
    await execFileAsync(
      python,
      [
        "-m",
        "edge_tts",
        "--voice",
        resolvedVoice,
        "--text",
        narration,
        "--write-media",
        resolvedOutputPath,
      ],
      {
        windowsHide: true,
        maxBuffer: 10 * 1024 * 1024,
      }
    );
  } catch (error) {
    const stdout = error?.stdout || "";
    const stderr = error?.stderr || "";

    throw new Error(
      [
        "Edge TTS generation failed.",
        `Python command: ${python}`,
        stdout
          ? `stdout: ${stdout}`
          : "",
        stderr
          ? `stderr: ${stderr}`
          : "",
        error?.message
          ? `error: ${error.message}`
          : "",
      ]
        .filter(Boolean)
        .join("\n")
    );
  }

  // ========================================================================
  // VALIDATE OUTPUT
  // ========================================================================

  if (!fs.existsSync(resolvedOutputPath)) {
    throw new Error(
      `Edge TTS completed but no audio file was created: ${resolvedOutputPath}`
    );
  }

  const stats = fs.statSync(resolvedOutputPath);

  if (stats.size < 1_000) {
    throw new Error(
      `Generated voiceover appears invalid. File size: ${stats.size} bytes`
    );
  }

  console.log(
    `[tts] Voiceover generated successfully (${stats.size} bytes).`
  );

  return resolvedOutputPath;
}