import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import {
  renderMedia,
  renderStill,
  selectComposition,
} from "@remotion/renderer";
import getPort from "get-port";

import { generateVoiceover } from "./tts.mjs";

// ============================================================================
// PATHS
// ============================================================================

const __dirname = path.dirname(
  fileURLToPath(import.meta.url)
);

const COMPOSITION_ENTRY = path.join(
  __dirname,
  "PromoVideo.tsx"
);

const PUBLIC_DIR = path.join(
  __dirname,
  "public"
);

// ============================================================================
// DEFAULTS
// ============================================================================

const DEFAULT_MEDIA_ORIGIN =
  "https://inrabackend-docker.onrender.com";

const DEFAULT_VOICE =
  "en-US-AriaNeural";

const DEFAULT_CONCURRENCY = 2;

const RENDER_TIMEOUT = 120_000;

// ============================================================================
// LOGGING
// ============================================================================

function log(verbose, message) {
  if (verbose) {
    console.log(`[render] ${message}`);
  }
}

function warn(message) {
  console.warn(`[render] WARNING: ${message}`);
}

// ============================================================================
// CLI
// ============================================================================

function parseArgs(argv) {
  const args = {
    verbose: false,
    configPath: null,
  };

  for (
    let i = 0;
    i < argv.length;
    i++
  ) {
    const argument = argv[i];

    if (argument === "--verbose") {
      args.verbose = true;
      continue;
    }

    if (argument === "--config") {
      const value = argv[++i];

      if (!value) {
        throw new Error(
          "--config requires a file path."
        );
      }

      args.configPath = value;
      continue;
    }

    throw new Error(
      `Unknown argument: ${argument}`
    );
  }

  if (!args.configPath) {
    throw new Error(
      "Missing required argument: --config <config.json>"
    );
  }

  return args;
}

// ============================================================================
// GENERIC HELPERS
// ============================================================================

function cleanText(value) {
  return typeof value === "string"
    ? value.trim()
    : "";
}

function cleanArray(value) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => String(item).trim())
    .filter(Boolean);
}

function ensureDirectory(filePath) {
  const directory =
    path.dirname(
      path.resolve(filePath)
    );

  fs.mkdirSync(directory, {
    recursive: true,
  });
}

function ensurePublicFile(relativePath) {
  const safePath = String(
    relativePath || ""
  ).replace(/^\/+/, "");

  const absolutePath = path.join(
    PUBLIC_DIR,
    safePath
  );

  fs.mkdirSync(
    path.dirname(absolutePath),
    {
      recursive: true,
    }
  );

  return absolutePath;
}

function removeFileIfExists(filePath) {
  try {
    if (fs.existsSync(filePath)) {
      fs.unlinkSync(filePath);
    }
  } catch (error) {
    warn(
      `Could not remove file ${filePath}: ${
        error?.message || error
      }`
    );
  }
}

// ============================================================================
// CONFIG
// ============================================================================

function loadConfig(configPath) {
  const absolutePath =
    path.resolve(configPath);

  if (!fs.existsSync(absolutePath)) {
    throw new Error(
      `Config file not found: ${absolutePath}`
    );
  }

  let config;

  try {
    config = JSON.parse(
      fs.readFileSync(
        absolutePath,
        "utf8"
      )
    );
  } catch (error) {
    throw new Error(
      `Could not parse config JSON: ${
        error?.message || error
      }`
    );
  }

  if (
    !config ||
    typeof config !== "object" ||
    Array.isArray(config)
  ) {
    throw new Error(
      "Render config must be a JSON object."
    );
  }

  const required = [
    "compositionId",
    "inputProps",
    "width",
    "height",
    "fps",
    "outputPath",
  ];

  const missing =
    required.filter(
      (field) =>
        config[field] === undefined ||
        config[field] === null
    );

  if (missing.length) {
    throw new Error(
      `Render config is missing required fields: ${missing.join(
        ", "
      )}`
    );
  }

  validateDimensions(config);
  validateInputProps(config);

  const isStill =
    config.stillFrame !== undefined;

  if (
    !isStill &&
    config.compositionId !== "PromoVideo" &&
    (!Number.isFinite(
      Number(config.durationInFrames)
    ) ||
      Number(config.durationInFrames) <= 0)
  ) {
    throw new Error(
      "Video render config requires a valid durationInFrames."
    );
  }

  return config;
}

function validateDimensions(config) {
  for (const field of [
    "width",
    "height",
    "fps",
  ]) {
    const value =
      Number(config[field]);

    if (
      !Number.isFinite(value) ||
      value <= 0
    ) {
      throw new Error(
        `Invalid ${field}: ${config[field]}`
      );
    }
  }

  if (
    config.durationInFrames !==
    undefined
  ) {
    const duration =
      Number(
        config.durationInFrames
      );

    if (
      !Number.isFinite(duration) ||
      duration <= 0
    ) {
      throw new Error(
        `Invalid durationInFrames: ${config.durationInFrames}`
      );
    }
  }
}

function validateInputProps(config) {
  if (
    !config.inputProps ||
    typeof config.inputProps !==
      "object" ||
    Array.isArray(config.inputProps)
  ) {
    throw new Error(
      "inputProps must be a JSON object."
    );
  }
}

// ============================================================================
// PROPS
// ============================================================================

function cleanProps(inputProps) {
  const props = {
    ...(inputProps || {}),
  };

  return {
    ...props,

    headline: cleanText(
      props.headline
    ),

    subtext: cleanText(
      props.subtext
    ),

    ctaText: cleanText(
      props.ctaText
    ),

    price: cleanText(
      props.price
    ),

    brandName: cleanText(
      props.brandName
    ),

    website: cleanText(
      props.website
    ),

    productImage: cleanText(
      props.productImage
    ),

    logoImage: cleanText(
      props.logoImage
    ),

    phone: cleanText(
      props.phone
    ),

    email: cleanText(
      props.email
    ),

    voiceoverText: cleanText(
      props.voiceoverText
    ),

    voiceoverVoice: cleanText(
      props.voiceoverVoice
    ),

    voiceoverUrl: cleanText(
      props.voiceoverUrl
    ),

    musicUrl: cleanText(
      props.musicUrl
    ),

    features: cleanArray(
      props.features
    ).slice(0, 3),

    whyChooseUs: cleanArray(
      props.whyChooseUs
    ).slice(0, 3),
  };
}

// ============================================================================
// NARRATION
// ============================================================================

function buildNarration(props) {
  const parts = [];

  const brand = cleanText(
    props.brandName
  );

  const headline = cleanText(
    props.headline
  );

  const subtext = cleanText(
    props.subtext
  );

  const price = cleanText(
    props.price
  );

  const features = cleanArray(
    props.features
  ).slice(0, 3);

  const benefits = cleanArray(
    props.whyChooseUs
  ).slice(0, 3);

  const cta = cleanText(
    props.ctaText
  );

  if (brand) {
    parts.push(brand);
  }

  if (headline) {
    parts.push(headline);
  }

  if (subtext) {
    parts.push(subtext);
  }

  if (price) {
    parts.push(
      `Available at ${price}.`
    );
  }

  if (features.length) {
    parts.push(
      `Key features include ${features.join(
        ", "
      )}.`
    );
  }

  if (benefits.length) {
    parts.push(
      `Why choose us? ${benefits.join(
        ". "
      )}.`
    );
  }

  if (cta) {
    parts.push(cta);
  }

  return parts
    .join(". ")
    .replace(/\.{2,}/g, ".")
    .trim();
}

// ============================================================================
// MEDIA ORIGIN
// ============================================================================

function resolveMediaOrigin(config) {
  const candidates = [
    config.mediaOrigin,

    process.env.DJANGO_MEDIA_ORIGIN,

    process.env.REMOTION_MEDIA_ORIGIN,

    process.env
      .NEXT_PUBLIC_REMOTION_MEDIA_ORIGIN,

    DEFAULT_MEDIA_ORIGIN,
  ];

  for (const candidate of candidates) {
    if (
      typeof candidate === "string" &&
      candidate.trim()
    ) {
      return candidate
        .trim()
        .replace(/\/+$/, "");
    }
  }

  return DEFAULT_MEDIA_ORIGIN;
}

// ============================================================================
// VOICEOVER
// ============================================================================

async function prepareVoiceover(
  config,
  verbose
) {
  const props = cleanProps(
    config.inputProps
  );

  /*
   * If the caller explicitly provides an
   * external voiceover URL and no narration
   * should be generated, preserve it.
   */
  if (
    !props.voiceoverText &&
    props.voiceoverUrl
  ) {
    log(
      verbose,
      `Using external voiceover: ${props.voiceoverUrl}`
    );

    return props;
  }

  const narration =
    buildNarration(props);

  if (!narration) {
    log(
      verbose,
      "Voiceover disabled: no narratable content."
    );

    return {
      ...props,
      voiceoverUrl: "",
      voiceoverText: "",
    };
  }

  const voice =
    props.voiceoverVoice ||
    DEFAULT_VOICE;

  const rawJobId =
    config.jobId ||
    props.jobId ||
    `voice-${Date.now()}`;

  const jobId = String(
    rawJobId
  ).replace(
    /[^a-zA-Z0-9_-]/g,
    "-"
  );

  const relativePath =
    `voiceovers/${jobId}.mp3`;

  const absolutePath =
    ensurePublicFile(
      relativePath
    );

  // Never leave stale audio.
  removeFileIfExists(
    absolutePath
  );

  log(
    verbose,
    "Generating voiceover..."
  );

  log(
    verbose,
    `Voice: ${voice}`
  );

  log(
    verbose,
    `Narration: "${narration}"`
  );

  await generateVoiceover({
    text: narration,
    voice,
    outputPath: absolutePath,
  });

  if (!fs.existsSync(absolutePath)) {
    throw new Error(
      `Voiceover generation completed but no file was created: ${absolutePath}`
    );
  }

  const stats =
    fs.statSync(
      absolutePath
    );

  if (stats.size < 1000) {
    throw new Error(
      `Generated voiceover appears invalid. File size: ${stats.size} bytes`
    );
  }

  log(
    verbose,
    `Voiceover created: ${(
      stats.size / 1024
    ).toFixed(1)} KB`
  );

  /*
   * IMPORTANT:
   *
   * This is deliberately a Remotion public
   * path, NOT a Django /media path.
   *
   * PromoVideo.tsx detects voiceovers/*
   * and resolves it through staticFile().
   */
  return {
    ...props,

    voiceoverUrl:
      relativePath,

    voiceoverText:
      narration,
  };
}

// ============================================================================
// CHROMIUM
// ============================================================================

function getChromiumOptions() {
  return {
    gl: "swiftshader",

    disableWebSecurity: false,

    // Better reliability on GitHub runners.
    args: [
      "--disable-gpu",
      "--disable-dev-shm-usage",
      "--no-sandbox",
      "--disable-setuid-sandbox",
    ],
  };
}

// ============================================================================
// BUNDLE
// ============================================================================

async function createBundle(
  mediaOrigin,
  verbose
) {
  if (
    !fs.existsSync(
      COMPOSITION_ENTRY
    )
  ) {
    throw new Error(
      `Composition entry not found: ${COMPOSITION_ENTRY}`
    );
  }

  log(
    verbose,
    "Bundling PromoVideo..."
  );

  const serveUrl =
    await bundle({
      entryPoint:
        COMPOSITION_ENTRY,

      envVariables: {
        NEXT_PUBLIC_REMOTION_MEDIA_ORIGIN:
          mediaOrigin,

        REMOTION_MEDIA_ORIGIN:
          mediaOrigin,
      },

      onProgress: verbose
        ? (progress) => {
            process.stdout.write(
              `\r[bundle] ${Math.round(
                progress
              )}%`
            );
          }
        : undefined,
    });

  if (verbose) {
    process.stdout.write("\n");
  }

  log(
    verbose,
    "Bundle complete."
  );

  return serveUrl;
}

// ============================================================================
// PORT
// ============================================================================

async function getRenderPort(
  verbose
) {
  const port =
    await getPort({
      port: [
        8123,
        8124,
        8125,
        8126,
        8127,
        8128,
      ],
    });

  log(
    verbose,
    `Using Remotion port ${port}.`
  );

  return port;
}

// ============================================================================
// COMPOSITION
// ============================================================================

async function selectRenderComposition({
  serveUrl,
  port,
  config,
  inputProps,
  chromiumOptions,
  verbose,
}) {
  log(
    verbose,
    `Selecting composition "${config.compositionId}"...`
  );

  const composition =
    await selectComposition({
      serveUrl,

      id:
        config.compositionId,

      inputProps,

      port,

      timeoutInMilliseconds:
        RENDER_TIMEOUT,

      chromiumOptions,
    });

  if (!composition) {
    throw new Error(
      `Could not select composition: ${config.compositionId}`
    );
  }

  return composition;
}

// ============================================================================
// COMPOSITION OVERRIDES
// ============================================================================

function buildComposition({
  composition,
  config,
  isStill,
}) {
  const isPromo =
    config.compositionId ===
    "PromoVideo";

  const durationInFrames =
    isStill
      ? (
          composition.durationInFrames ??
          Number(config.stillFrame) + 1
        )
      : isPromo
        ? composition.durationInFrames
        : Number(
            config.durationInFrames
          );

  return {
    ...composition,

    width: Number(
      config.width
    ),

    height: Number(
      config.height
    ),

    fps: Number(
      config.fps
    ),

    durationInFrames,
  };
}

// ============================================================================
// STILL
// ============================================================================

async function renderStillFrame({
  serveUrl,
  port,
  composition,
  config,
  inputProps,
  chromiumOptions,
  verbose,
}) {
  log(
    verbose,
    `Rendering still frame ${config.stillFrame}...`
  );

  await renderStill({
    serveUrl,

    port,

    composition,

    frame: Number(
      config.stillFrame
    ),

    output:
      config.outputPath,

    imageFormat:
      config.imageFormat ||
      "png",

    jpegQuality:
      config.jpegQuality ??
      undefined,

    inputProps,

    timeoutInMilliseconds:
      RENDER_TIMEOUT,

    chromiumOptions,
  });
}

// ============================================================================
// VIDEO
// ============================================================================

async function renderVideo({
  serveUrl,
  port,
  composition,
  config,
  inputProps,
  chromiumOptions,
  verbose,
}) {
  /*
   * GitHub Actions has enough CPU/memory,
   * but keeping concurrency configurable
   * avoids accidental memory explosions.
   */
  const concurrency =
    Math.max(
      1,
      Math.min(
        3,
        Number(
          config.concurrency ??
            DEFAULT_CONCURRENCY
        )
      )
    );

  const x264Preset =
    config.x264Preset ||
    "fast";

  const durationSeconds =
    composition.durationInFrames /
    composition.fps;

  log(
    verbose,
    `Rendering ${composition.width}x${composition.height} @ ${composition.fps}fps`
  );

  log(
    verbose,
    `Duration: ${composition.durationInFrames} frames (${durationSeconds.toFixed(
      2
    )}s)`
  );

  log(
    verbose,
    `Concurrency: ${concurrency}`
  );

  log(
    verbose,
    `x264 preset: ${x264Preset}`
  );

  await renderMedia({
    serveUrl,

    port,

    composition,

    codec: "h264",

    outputLocation:
      config.outputPath,

    inputProps,

    timeoutInMilliseconds:
      RENDER_TIMEOUT,

    chromiumOptions,

    concurrency,

    x264Preset,

    onProgress: verbose
      ? ({ progress }) => {
          process.stdout.write(
            `\r[render] ${Math.round(
              progress * 100
            )}%`
          );
        }
      : undefined,
  });

  if (verbose) {
    process.stdout.write("\n");
  }
}

// ============================================================================
// OUTPUT
// ============================================================================

function validateOutput(
  outputPath
) {
  const absolutePath =
    path.resolve(outputPath);

  if (
    !fs.existsSync(
      absolutePath
    )
  ) {
    throw new Error(
      `Render completed but output file was not created:\n${absolutePath}`
    );
  }

  const stats =
    fs.statSync(
      absolutePath
    );

  if (stats.size < 10_000) {
    throw new Error(
      `Render output appears invalid. File size: ${stats.size} bytes`
    );
  }

  return stats;
}

// ============================================================================
// MAIN
// ============================================================================

async function main() {
  const {
    configPath,
    verbose,
  } = parseArgs(
    process.argv.slice(2)
  );

  log(
    verbose,
    "Starting INRASTUDIO Remotion renderer..."
  );

  const config =
    loadConfig(
      configPath
    );

  const mediaOrigin =
    resolveMediaOrigin(
      config
    );

  log(
    verbose,
    `Media origin: ${mediaOrigin}`
  );

  const inputProps =
    await prepareVoiceover(
      config,
      verbose
    );

  log(
    verbose,
    `Features: ${
      inputProps.features?.length ||
      0
    }`
  );

  log(
    verbose,
    `Why Choose Us: ${
      inputProps.whyChooseUs?.length ||
      0
    }`
  );

  log(
    verbose,
    `Voiceover: ${
      inputProps.voiceoverUrl ||
      "disabled"
    }`
  );

  log(
    verbose,
    `Music: ${
      inputProps.musicUrl ||
      "disabled"
    }`
  );

  ensureDirectory(
    config.outputPath
  );

  const chromiumOptions =
    getChromiumOptions();

  const serveUrl =
    await createBundle(
      mediaOrigin,
      verbose
    );

  const port =
    await getRenderPort(
      verbose
    );

  const composition =
    await selectRenderComposition({
      serveUrl,

      port,

      config,

      inputProps,

      chromiumOptions,

      verbose,
    });

  const isStill =
    config.stillFrame !==
    undefined;

  const finalComposition =
    buildComposition({
      composition,

      config,

      isStill,
    });

  if (
    !finalComposition
      .durationInFrames ||
    finalComposition
      .durationInFrames <= 0
  ) {
    throw new Error(
      "Remotion returned an invalid composition duration."
    );
  }

  if (isStill) {
    await renderStillFrame({
      serveUrl,

      port,

      composition:
        finalComposition,

      config,

      inputProps,

      chromiumOptions,

      verbose,
    });
  } else {
    await renderVideo({
      serveUrl,

      port,

      composition:
        finalComposition,

      config,

      inputProps,

      chromiumOptions,

      verbose,
    });
  }

  const stats =
    validateOutput(
      config.outputPath
    );

  log(
    verbose,
    `Output size: ${(
      stats.size /
      1024 /
      1024
    ).toFixed(2)} MB`
  );

  console.log(
    `\n[render] SUCCESS → ${config.outputPath}`
  );
}

// ============================================================================
// ERROR HANDLER
// ============================================================================

main().catch(
  (error) => {
    console.error(
      "\n========================================"
    );

    console.error(
      "INRASTUDIO REMOTION RENDER FAILED"
    );

    console.error(
      "========================================"
    );

    console.error(
      error?.message ||
        error
    );

    if (error?.stack) {
      console.error(
        "\nStack trace:"
      );

      console.error(
        error.stack
      );
    }

    process.exit(1);
  }
);