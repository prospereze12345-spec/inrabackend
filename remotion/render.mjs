

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

const COMPOSITION_ENTRY =
  path.join(
    __dirname,
    "PromoVideo.tsx"
  );

const PUBLIC_DIR =
  path.join(
    __dirname,
    "public"
  );

const DEFAULT_MEDIA_ORIGIN =
  "https://inrabackend-docker.onrender.com";


// ============================================================================
// LOGGING
// ============================================================================

function log(
  verbose,
  message
) {
  if (verbose) {
    console.log(
      `[render] ${message}`
    );
  }
}


function warn(message) {
  console.warn(
    `[render] WARNING: ${message}`
  );
}


// ============================================================================
// CLI
// ============================================================================

function parseArgs(argv) {
  const result = {
    verbose: false,
    configPath: null,
  };

  for (
    let i = 0;
    i < argv.length;
    i++
  ) {
    const argument =
      argv[i];

    switch (argument) {
      case "--config": {
        const value =
          argv[++i];

        if (!value) {
          throw new Error(
            "--config requires a file path."
          );
        }

        result.configPath =
          value;

        break;
      }

      case "--verbose":
        result.verbose = true;
        break;

      default:
        throw new Error(
          `Unknown argument: ${argument}`
        );
    }
  }

  if (!result.configPath) {
    throw new Error(
      "Missing required argument: --config <config.json>"
    );
  }

  return result;
}


// ============================================================================
// CONFIGURATION
// ============================================================================

function loadConfig(
  configPath
) {
  const absolutePath =
    path.resolve(
      configPath
    );

  if (
    !fs.existsSync(
      absolutePath
    )
  ) {
    throw new Error(
      `Config file not found: ${absolutePath}`
    );
  }

  let config;

  try {
    config =
      JSON.parse(
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
    typeof config !== "object"
  ) {
    throw new Error(
      "Render config must be a JSON object."
    );
  }

  const requiredFields = [
    "compositionId",
    "inputProps",
    "width",
    "height",
    "fps",
    "outputPath",
  ];

  const missingFields =
    requiredFields.filter(
      (field) =>
        config[field] === undefined ||
        config[field] === null
    );

  if (
    missingFields.length > 0
  ) {
    throw new Error(
      `Render config is missing required fields: ${missingFields.join(
        ", "
      )}`
    );
  }

  const isStill =
    config.stillFrame !==
    undefined;

  if (
    !isStill &&
    (
      config.durationInFrames ===
        undefined ||
      config.durationInFrames <= 0
    )
  ) {
    /*
     * We allow PromoVideo's
     * calculateMetadata() to determine
     * the actual dynamic duration.
     *
     * Therefore durationInFrames is
     * no longer mandatory for dynamic
     * PromoVideo renders.
     */
    if (
      config.compositionId !==
      "PromoVideo"
    ) {
      throw new Error(
        "Video render config requires a valid durationInFrames."
      );
    }
  }

  validateDimensions(
    config
  );

  validateInputProps(
    config
  );

  return config;
}


function validateDimensions(
  config
) {
  const numericFields = [
    "width",
    "height",
    "fps",
  ];

  for (
    const field of numericFields
  ) {
    const value =
      Number(
        config[field]
      );

    if (
      !Number.isFinite(
        value
      ) ||
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
      !Number.isFinite(
        duration
      ) ||
      duration <= 0
    ) {
      throw new Error(
        `Invalid durationInFrames: ${config.durationInFrames}`
      );
    }
  }
}


function validateInputProps(
  config
) {
  if (
    !config.inputProps ||
    typeof config.inputProps !==
      "object"
  ) {
    throw new Error(
      "inputProps must be a JSON object."
    );
  }
}


// ============================================================================
// NORMALIZATION
// ============================================================================

function text(
  value
) {
  return typeof value === "string"
    ? value.trim()
    : "";
}


function array(
  value
) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) =>
      String(item).trim()
    )
    .filter(Boolean);
}


function cleanProps(
  inputProps
) {
  const props = {
    ...(inputProps || {}),
  };

  return {
    ...props,

    headline:
      text(props.headline),

    subtext:
      text(props.subtext),

    ctaText:
      text(props.ctaText),

    price:
      text(props.price),

    brandName:
      text(props.brandName),

    website:
      text(props.website),

    productImage:
      text(props.productImage),

    phone:
      text(props.phone),

    email:
      text(props.email),

    logoImage:
      text(props.logoImage),

    features:
      array(
        props.features
      ).slice(0, 3),

    whyChooseUs:
      array(
        props.whyChooseUs
      ).slice(0, 3),

    voiceoverText:
      text(
        props.voiceoverText
      ),

    voiceoverVoice:
      text(
        props.voiceoverVoice
      ),

    musicUrl:
      text(props.musicUrl),
  };
}


// ============================================================================
// DYNAMIC VOICEOVER TEXT
// ============================================================================

/*
 * This is deliberately generated from the SAME props used by PromoVideo.
 *
 * Do NOT manually hard-code Features / Why Choose Us into narration.
 *
 * The final flyer state decides what gets spoken.
 */

function buildNarration(
  props
) {
  const parts = [];

  const brand =
    text(
      props.brandName
    );

  const headline =
    text(
      props.headline
    );

  const subtext =
    text(
      props.subtext
    );

  const price =
    text(
      props.price
    );

  const features =
    array(
      props.features
    ).slice(0, 3);

  const benefits =
    array(
      props.whyChooseUs
    ).slice(0, 3);

  const cta =
    text(
      props.ctaText
    );


  // --------------------------------------------------------------------------
  // BRAND
  // --------------------------------------------------------------------------

  if (brand) {
    parts.push(
      brand
    );
  }


  // --------------------------------------------------------------------------
  // HEADLINE
  // --------------------------------------------------------------------------

  if (headline) {
    parts.push(
      headline
    );
  }


  // --------------------------------------------------------------------------
  // SUBTEXT
  // --------------------------------------------------------------------------

  if (subtext) {
    parts.push(
      subtext
    );
  }


  // --------------------------------------------------------------------------
  // PRICE
  // --------------------------------------------------------------------------

  if (price) {
    parts.push(
      `Available at ${price}.`
    );
  }


  // --------------------------------------------------------------------------
  // FEATURES
  // --------------------------------------------------------------------------

  if (
    features.length > 0
  ) {
    parts.push(
      `Key features include ${features.join(
        ", "
      )}.`
    );
  }


  // --------------------------------------------------------------------------
  // WHY CHOOSE US
  // --------------------------------------------------------------------------

  if (
    benefits.length > 0
  ) {
    parts.push(
      `Why choose us? ${benefits.join(
        ". "
      )}.`
    );
  }


  // --------------------------------------------------------------------------
  // CTA
  // --------------------------------------------------------------------------

  if (cta) {
    parts.push(
      cta
    );
  }


  /*
   * Keep narration natural rather than
   * returning a giant block with labels.
   */
  return parts
    .join(". ")
    .replace(
      /\.{2,}/g,
      "."
    )
    .trim();
}


// ============================================================================
// FILESYSTEM
// ============================================================================

function ensureDir(
  filePath
) {
  const directory =
    path.dirname(
      path.resolve(
        filePath
      )
    );

  fs.mkdirSync(
    directory,
    {
      recursive: true,
    }
  );
}


function ensurePublicDir(
  relativePath
) {
  const safeRelative =
    relativePath.replace(
      /^\/+/,
      ""
    );

  const absolutePath =
    path.join(
      PUBLIC_DIR,
      safeRelative
    );

  fs.mkdirSync(
    path.dirname(
      absolutePath
    ),
    {
      recursive: true,
    }
  );

  return absolutePath;
}


// ============================================================================
// MEDIA ORIGIN
// ============================================================================

function resolveMediaOrigin(
  config
) {
  const candidates = [
    config.mediaOrigin,

    process.env
      .DJANGO_MEDIA_ORIGIN,

    process.env
      .REMOTION_MEDIA_ORIGIN,

    process.env
      .NEXT_PUBLIC_REMOTION_MEDIA_ORIGIN,

    DEFAULT_MEDIA_ORIGIN,
  ];

  for (
    const candidate of candidates
  ) {
    if (
      typeof candidate ===
        "string" &&
      candidate.trim()
    ) {
      return candidate
        .trim()
        .replace(
          /\/+$/,
          ""
        );
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
  const props =
    cleanProps(
      config.inputProps
    );


  // --------------------------------------------------------------------------
  // CUSTOM / PRE-GENERATED VOICEOVER
  // --------------------------------------------------------------------------

  /*
   * If voiceoverText exists, it means the narration belongs
   * to the current flyer state.
   *
   * Therefore we regenerate it rather than blindly reusing
   * an old MP3.
   */

  const explicitNarration =
    text(
      props.voiceoverText
    );


  /*
   * If there is no narration text but a voiceover URL exists,
   * preserve it. This supports externally supplied/custom audio.
   */

  if (
    !explicitNarration &&
    text(props.voiceoverUrl)
  ) {
    log(
      verbose,
      `Using externally supplied voiceover: ${props.voiceoverUrl}`
    );

    return props;
  }


  // --------------------------------------------------------------------------
  // AUTO-GENERATE NARRATION
  // --------------------------------------------------------------------------

  const narration =
    buildNarration(
      props
    );


  if (!narration) {
    log(
      verbose,
      "Voiceover disabled: final flyer contains no narratable text."
    );

    return {
      ...props,
      voiceoverUrl: "",
    };
  }


  // --------------------------------------------------------------------------
  // VOICE
  // --------------------------------------------------------------------------

  const voice =
    text(
      props.voiceoverVoice
    ) ||
    "en-US-AriaNeural";


  // --------------------------------------------------------------------------
  // JOB ID
  // --------------------------------------------------------------------------

  const rawJobId =
    config.jobId ||
    props.jobId ||
    `voice-${Date.now()}`;


  const jobId =
    String(
      rawJobId
    ).replace(
      /[^a-zA-Z0-9_-]/g,
      "-"
    );


  // --------------------------------------------------------------------------
  // OUTPUT
  // --------------------------------------------------------------------------

  const relativeVoicePath =
    `voiceovers/${jobId}.mp3`;


  const absoluteVoicePath =
    ensurePublicDir(
      relativeVoicePath
    );


  // --------------------------------------------------------------------------
  // REMOVE OLD FILE
  // --------------------------------------------------------------------------

  /*
   * Prevent stale audio from surviving
   * a failed/changed generation.
   */

  if (
    fs.existsSync(
      absoluteVoicePath
    )
  ) {
    fs.unlinkSync(
      absoluteVoicePath
    );
  }


  // --------------------------------------------------------------------------
  // GENERATE
  // --------------------------------------------------------------------------

  log(
    verbose,
    `Generating narration from FINAL flyer state...`
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

    outputPath:
      absoluteVoicePath,
  });


  // --------------------------------------------------------------------------
  // VALIDATE
  // --------------------------------------------------------------------------

  if (
    !fs.existsSync(
      absoluteVoicePath
    )
  ) {
    throw new Error(
      `Voiceover generation completed but no file was created: ${absoluteVoicePath}`
    );
  }


  const stats =
    fs.statSync(
      absoluteVoicePath
    );


  if (
    stats.size < 1_000
  ) {
    throw new Error(
      `Generated voiceover appears invalid. File size: ${stats.size} bytes`
    );
  }


  log(
    verbose,
    `Voiceover generated: ${relativeVoicePath}`
  );


  // --------------------------------------------------------------------------
  // RETURN
  // --------------------------------------------------------------------------

  return {
    ...props,

    /*
     * PromoVideo recognizes voiceovers/
     * as a Remotion public asset.
     */
    voiceoverUrl:
      relativeVoicePath,

    /*
     * Store the exact narration used.
     * This makes debugging much easier.
     */
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

    disableWebSecurity:
      false,
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

      onProgress:
        verbose
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
    process.stdout.write(
      "\n"
    );
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
// SELECT COMPOSITION
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
        120_000,

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
  /*
   * IMPORTANT:
   *
   * For PromoVideo, Remotion's
   * calculateMetadata() determines
   * the dynamic duration.
   *
   * Therefore we do NOT blindly
   * overwrite it with an old fixed
   * duration.
   */

  const isDynamicPromo =
    config.compositionId ===
    "PromoVideo";


  return {
    ...composition,

    width:
      Number(
        config.width
      ),

    height:
      Number(
        config.height
      ),

    fps:
      Number(
        config.fps
      ),

    durationInFrames:
      isStill
        ? (
            composition.durationInFrames ??
            Number(
              config.stillFrame
            ) + 1
          )

        : isDynamicPromo
          ? composition.durationInFrames

          : Number(
              config.durationInFrames
            ),
  };
}


// ============================================================================
// STILL RENDER
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

    frame:
      Number(
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
      120_000,

    chromiumOptions,
  });
}


// ============================================================================
// VIDEO RENDER
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
   * Conservative default for CI.
   *
   * Two concurrent frames is generally
   * much safer than aggressively using
   * every available CPU.
   */
  const concurrency =
    Math.max(
      1,
      Number(
        config.concurrency ??
          2
      )
    );


  const x264Preset =
    config.x264Preset ||
    "fast";


  log(
    verbose,
    `Rendering ${composition.width}x${composition.height} @ ${composition.fps}fps...`
  );


  log(
    verbose,
    `Duration: ${composition.durationInFrames} frames`
  );


  log(
    verbose,
    `Approx duration: ${(
      composition.durationInFrames /
      composition.fps
    ).toFixed(2)} seconds`
  );


  log(
    verbose,
    `Concurrency: ${concurrency}`
  );


  log(
    verbose,
    "Codec: h264"
  );


  log(
    verbose,
    `x264 preset: ${x264Preset}`
  );


  await renderMedia({
    serveUrl,

    port,

    composition,

    codec:
      "h264",

    outputLocation:
      config.outputPath,

    inputProps,

    timeoutInMilliseconds:
      120_000,

    chromiumOptions,

    concurrency,

    x264Preset,

    onProgress:
      verbose
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
    process.stdout.write(
      "\n"
    );
  }
}


// ============================================================================
// OUTPUT VALIDATION
// ============================================================================

function validateOutput(
  outputPath
) {
  const absoluteOutput =
    path.resolve(
      outputPath
    );


  if (
    !fs.existsSync(
      absoluteOutput
    )
  ) {
    throw new Error(
      `Render completed but output file was not created:\n${absoluteOutput}`
    );
  }


  const stats =
    fs.statSync(
      absoluteOutput
    );


  if (
    stats.size < 10_000
  ) {
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


  log(
    verbose,
    `Config: ${path.resolve(
      configPath
    )}`
  );


  // --------------------------------------------------------------------------
  // LOAD CONFIG
  // --------------------------------------------------------------------------

  const config =
    loadConfig(
      configPath
    );


  // --------------------------------------------------------------------------
  // MEDIA ORIGIN
  // --------------------------------------------------------------------------

  const mediaOrigin =
    resolveMediaOrigin(
      config
    );


  log(
    verbose,
    `Media origin: ${mediaOrigin}`
  );


  // --------------------------------------------------------------------------
  // FINAL PROPS
  // --------------------------------------------------------------------------

  const inputProps =
    await prepareVoiceover(
      config,
      verbose
    );


  // --------------------------------------------------------------------------
  // FINAL CONTENT LOG
  // --------------------------------------------------------------------------

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
    }`);


  log(
    verbose,
    `Voiceover: ${
      inputProps.voiceoverUrl
        ? inputProps.voiceoverUrl
        : "disabled"
    }`
  );


  log(
    verbose,
    `Music: ${
      inputProps.musicUrl
        ? inputProps.musicUrl
        : "disabled"
    }`
  );


  // --------------------------------------------------------------------------
  // OUTPUT DIRECTORY
  // --------------------------------------------------------------------------

  ensureDir(
    config.outputPath
  );


  // --------------------------------------------------------------------------
  // CHROMIUM
  // --------------------------------------------------------------------------

  const chromiumOptions =
    getChromiumOptions();


  // --------------------------------------------------------------------------
  // BUNDLE
  // --------------------------------------------------------------------------

  const serveUrl =
    await createBundle(
      mediaOrigin,
      verbose
    );


  // --------------------------------------------------------------------------
  // PORT
  // --------------------------------------------------------------------------

  const port =
    await getRenderPort(
      verbose
    );


  // --------------------------------------------------------------------------
  // SELECT
  // --------------------------------------------------------------------------

  const composition =
    await selectRenderComposition({
      serveUrl,

      port,

      config,

      inputProps,

      chromiumOptions,

      verbose,
    });


  // --------------------------------------------------------------------------
  // STILL / VIDEO
  // --------------------------------------------------------------------------

  const isStill =
    config.stillFrame !==
    undefined;


  const finalComposition =
    buildComposition({
      composition,

      config,

      isStill,
    });


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


  // --------------------------------------------------------------------------
  // VALIDATE
  // --------------------------------------------------------------------------

  const stats =
    validateOutput(
      config.outputPath
    );


  // --------------------------------------------------------------------------
  // COMPLETE
  // --------------------------------------------------------------------------

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
