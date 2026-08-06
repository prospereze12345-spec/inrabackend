
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

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMPOSITION_ENTRY = path.join(__dirname, "PromoVideo.tsx");

const CHROMIUM_OPTIONS = {
  gl: "swiftshader",
};

function parseArgs(argv) {
  const out = {
    verbose: false,
  };

  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case "--config":
        out.configPath = argv[++i];
        break;

      case "--verbose":
        out.verbose = true;
        break;
    }
  }

  if (!out.configPath) {
    throw new Error(
      "Missing required argument: --config <config.json>"
    );
  }

  return out;
}

function loadConfig(configPath) {
  if (!fs.existsSync(configPath)) {
    throw new Error(`Config file not found: ${configPath}`);
  }

  const config = JSON.parse(
    fs.readFileSync(configPath, "utf8")
  );

  const commonFields = [
    "compositionId",
    "inputProps",
    "width",
    "height",
    "fps",
    "outputPath",
  ];

  const missing = commonFields.filter(
    (field) => config[field] === undefined
  );

  if (missing.length) {
    throw new Error(
      `Config file ${configPath} is missing required fields: ${missing.join(
        ", "
      )}`
    );
  }

  const isStill = config.stillFrame !== undefined;

  if (!isStill && config.durationInFrames === undefined) {
    throw new Error(
      `Config file ${configPath} is missing required field: durationInFrames`
    );
  }

  return config;
}

async function main() {
  const { configPath, verbose } = parseArgs(
    process.argv.slice(2)
  );

  const config = loadConfig(configPath);

  const {
    compositionId,
    inputProps,
    width,
    height,
    fps,
    durationInFrames,
    stillFrame,
    outputPath,
  } = config;

  const isStill = stillFrame !== undefined;

  if (!fs.existsSync(COMPOSITION_ENTRY)) {
    throw new Error(
      `Composition entry not found: ${COMPOSITION_ENTRY}`
    );
  }
if (verbose) {
    console.log("[render] Bundling composition...");
  }

  // Django serves /media/... on its own origin (e.g. http://127.0.0.1:8000),
  // which is NOT the same as the Remotion render server's port. Relative
  // product image paths (e.g. "nobg/xxx.png") need this baked into the
  // bundle at build time so PromoVideo.tsx can resolve them to a fetchable
  // absolute URL inside headless Chromium. Uses the same env var name
  // (NEXT_PUBLIC_REMOTION_MEDIA_ORIGIN) that page.tsx relies on in the
  // browser, so both the final server-side render and the in-browser
  // Player/renderMediaOnWeb preview stay consistent.
  const mediaOrigin =
    process.env.DJANGO_MEDIA_ORIGIN || "http://127.0.0.1:8000";

  if (verbose) {
    console.log(`[render] Using media origin ${mediaOrigin}`);
  }

  const serveUrl = await bundle({
    entryPoint: COMPOSITION_ENTRY,
    onProgress: verbose
      ? (p) => process.stdout.write(`\r[bundle] ${p}%`)
      : undefined,
    envVariables: {
      NEXT_PUBLIC_REMOTION_MEDIA_ORIGIN: mediaOrigin,
    },
  });

  if (verbose) {
    console.log("\n[render] Bundle complete");
  }

  const port = await getPort({
    port: [8123, 8124, 8125, 8126],
  });

  if (verbose) {
    console.log(`[render] Using port ${port}`);
  }

  const composition = await selectComposition({
    serveUrl,
    id: compositionId,
    inputProps,
    port,
    timeoutInMilliseconds: 60000,
    chromiumOptions: CHROMIUM_OPTIONS,
  });

  fs.mkdirSync(path.dirname(outputPath), {
    recursive: true,
  });

  if (verbose) {
    console.log(
      `[render] ${isStill ? "Rendering still" : "Rendering video"}`
    );
  }

  if (isStill) {
    await renderStill({
      serveUrl,
      port,
      composition: {
        ...composition,
        width,
        height,
        fps,
        durationInFrames:
          composition.durationInFrames ??
          stillFrame + 1,
      },
      frame: stillFrame,
      output: outputPath,
      imageFormat: "png",
      inputProps,
      timeoutInMilliseconds: 60000,
      chromiumOptions: CHROMIUM_OPTIONS,
    });
  } else {
    await renderMedia({
      serveUrl,
      port,
      composition: {
        ...composition,
        width,
        height,
        fps,
        durationInFrames,
      },
      codec: "h264",
      outputLocation: outputPath,
      inputProps,
      timeoutInMilliseconds: 60000,
      chromiumOptions: CHROMIUM_OPTIONS,
      onProgress: verbose
        ? ({ progress }) =>
            process.stdout.write(
              `\r[render] ${Math.round(progress * 100)}%`
            )
        : undefined,
    });
  }

  if (!fs.existsSync(outputPath)) {
    throw new Error(
      `Render completed but output file was not created:\n${outputPath}`
    );
  }

  if (verbose) {
    console.log(`\n[render] Done -> ${outputPath}`);
  }
}

main().catch((err) => {
  console.error("\n==============================");
  console.error("REMOTION RENDER FAILED");
  console.error("==============================");

  console.error(err);

  if (err.stack) {
    console.error(err.stack);
  }

  process.exit(1);
});
