
import React from "react";

import {
  registerRoot,
  Composition,
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Img,
  Audio,
  staticFile,
} from "remotion";

// ============================================================================
// TYPES
// ============================================================================

type PromoColors = {
  primary: string;
  secondary: string;
  accent: string;
};

type DiscountBadge = {
  visible: boolean;
  text: string;
  subText: string;
  textColor: string;
  bgColor: string;
  transform: {
    x: number;
    y: number;
    scale: number;
  };
};

export type PromoVideoProps = {
  headline: string;
  subtext: string;
  ctaText: string;
  price: string;

  brandName: string;
  website: string;

  productImage: string;

  colors: PromoColors;

  logoImage?: string | null;

  badge?: DiscountBadge | null;

  features?: string[];
  whyChooseUs?: string[];

  featuresVisible?: boolean;
  whyChooseUsVisible?: boolean;

  phone?: string;
  email?: string;

  phoneVisible?: boolean;
  emailVisible?: boolean;
  websiteVisible?: boolean;

  ctaVisible?: boolean;

  voiceoverUrl?: string;
  voiceoverText?: string;
  voiceoverVoice?: string;

  voicePreset?: string;

  musicUrl?: string;
  musicVolume?: number;
};

// ============================================================================
// DEFAULT PROPS
// ============================================================================

const DEFAULT_PROPS: PromoVideoProps = {
  headline: "Timeless Elegance Guaranteed",

  subtext:
    "Elevate your space with our Classic Analog Wall Clock.",

  ctaText: "DM to order now",

  price: "From ₦4,500",

  brandName: "Premium Brand",

  website: "your-store.com",

  productImage: "",

  colors: {
    primary: "#0a0a0a",
    secondary: "#ffffff",
    accent: "#c9a84c",
  },

  logoImage: null,

  badge: null,

  features: [
    "Premium quality",
    "Elegant modern design",
    "Built to last",
  ],

  whyChooseUs: [
    "Trusted quality",
    "Fast delivery",
    "Great customer service",
  ],

  featuresVisible: true,
  whyChooseUsVisible: true,

  phone: "",
  email: "",

  phoneVisible: true,
  emailVisible: true,
  websiteVisible: true,

  ctaVisible: true,

  voiceoverUrl: "",
  voiceoverText: "",
  voiceoverVoice: "en-US-AriaNeural",

  voicePreset: "female_us",

  musicUrl: "",
  musicVolume: 0.12,
};

// ============================================================================
// ASSET RESOLUTION
// ============================================================================

function resolveAsset(
  value: string | undefined | null,
  mediaOrigin: string
): string {
  if (!value) {
    return "";
  }

  const clean = String(value).trim();

  if (!clean) {
    return "";
  }

  // Absolute URLs and browser-generated assets
  if (
    clean.startsWith("http://") ||
    clean.startsWith("https://") ||
    clean.startsWith("data:") ||
    clean.startsWith("blob:")
  ) {
    return clean;
  }

  // Remotion public/static assets
  if (
    clean.startsWith("voiceovers/") ||
    clean.startsWith("/voiceovers/")
  ) {
    return staticFile(clean.replace(/^\/+/, ""));
  }

  if (
    clean.startsWith("music/") ||
    clean.startsWith("/music/")
  ) {
    return staticFile(clean.replace(/^\/+/, ""));
  }

  // Backend media
  if (clean.startsWith("/media/")) {
    return `${mediaOrigin}${clean}`;
  }

  if (clean.startsWith("media/")) {
    return `${mediaOrigin}/${clean}`;
  }

  return `${mediaOrigin}/media/${clean.replace(/^\/+/, "")}`;
}

// ============================================================================
// HELPERS
// ============================================================================

function safeArray(value?: string[]): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => String(item ?? "").trim())
    .filter(Boolean)
    .slice(0, 3);
}

function clampText(
  value: string,
  maxLength: number
): string {
  const text = String(value || "").trim();

  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength - 1).trim()}…`;
}

function splitHeadline(
  text: string,
  maxWords = 12
): string[] {
  return String(text || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, maxWords);
}

function fadeUp(
  frame: number,
  start: number,
  duration = 18
) {
  const opacity = interpolate(
    frame,
    [start, start + duration],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  const y = interpolate(
    frame,
    [start, start + duration],
    [22, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  return {
    opacity,
    transform: `translateY(${y}px)`,
  };
}

function springIn(
  frame: number,
  start: number,
  fps: number
): number {
  return spring({
    frame: Math.max(0, frame - start),
    fps,
    config: {
      damping: 16,
      stiffness: 140,
      mass: 0.65,
    },
  });
}

function hexAlpha(hex: string, alphaHex: string) {
  return `${hex}${alphaHex}`;
}

// ============================================================================
// SCENE TIMING ENGINE
//
// A promo video should read like a sequence of cuts, not one static canvas
// with everything stacked on it. Every "beat" (brand intro, hero, features,
// benefits, closing) gets the whole frame to itself, and consecutive beats
// cross-fade/slide into one another over a short shared transition window.
// Beats with no content (no features, no benefits) are skipped and their
// time is folded back into the timeline automatically.
// ============================================================================

const TRANSITION = 14;

type SceneWindow = { start: number; end: number };

function clampFrames(
  value: number,
  min: number,
  max = Infinity
): number {
  return Math.max(min, Math.min(max, Math.round(value)));
}

function buildTimeline(
  total: number,
  hasFeatures: boolean,
  hasBenefits: boolean
) {
  const brandFrames = clampFrames(total * 0.09, 18, 45);
  const brand: SceneWindow = { start: 0, end: brandFrames };

  const heroFrames = clampFrames(total * 0.36, 70, total);
  const hero: SceneWindow = {
    start: brand.end - TRANSITION,
    end: brand.end - TRANSITION + heroFrames,
  };

  let cursor = hero.end;

  let features: SceneWindow | null = null;

  if (hasFeatures) {
    const featuresFrames = clampFrames(total * 0.17, 45, total);

    features = {
      start: cursor - TRANSITION,
      end: cursor - TRANSITION + featuresFrames,
    };

    cursor = features.end;
  }

  let benefits: SceneWindow | null = null;

  if (hasBenefits) {
    const benefitsFrames = clampFrames(total * 0.17, 45, total);

    benefits = {
      start: cursor - TRANSITION,
      end: cursor - TRANSITION + benefitsFrames,
    };

    cursor = benefits.end;
  }

  const closing: SceneWindow = {
    start: cursor - TRANSITION,
    end: Math.max(cursor - TRANSITION + 60, total),
  };

  return { brand, hero, features, benefits, closing };
}

function useSceneMotion(
  window: SceneWindow,
  transition = TRANSITION
) {
  const frame = useCurrentFrame();

  const midpoint = Math.max(
    window.start + transition,
    window.end - transition
  );

  const opacity = interpolate(
    frame,
    [window.start, window.start + transition, midpoint, window.end],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const enterY = interpolate(
    frame,
    [window.start, window.start + transition],
    [28, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const exitY = interpolate(
    frame,
    [midpoint, window.end],
    [0, -28],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const mounted = frame >= window.start - 1 && frame <= window.end + 1;

  return { opacity, y: enterY + exitY, mounted };
}

function Scene({
  window,
  zIndex = 5,
  children,
}: {
  window: SceneWindow;
  zIndex?: number;
  children: React.ReactNode;
}) {
  const { opacity, y, mounted } = useSceneMotion(window);

  if (!mounted) {
    return null;
  }

  return (
    <AbsoluteFill
      style={{
        opacity,
        transform: `translateY(${y}px)`,
        zIndex,
        pointerEvents: "none",
      }}
    >
      {children}
    </AbsoluteFill>
  );
}

// ============================================================================
// SEGMENTED PROGRESS BAR (story-style beat indicator)
// ============================================================================

function ProgressBar({
  segments,
  accent,
  secondary,
  side,
  top,
}: {
  segments: SceneWindow[];
  accent: string;
  secondary: string;
  side: number;
  top: number;
}) {
  const frame = useCurrentFrame();

  return (
    <div
      style={{
        position: "absolute",
        top: top * 0.5,
        left: side,
        right: side,
        display: "flex",
        gap: 5,
        zIndex: 95,
      }}
    >
      {segments.map((segment, index) => {
        const progress = interpolate(
          frame,
          [segment.start, Math.max(segment.start + 1, segment.end - TRANSITION)],
          [0, 100],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );

        return (
          <div
            key={index}
            style={{
              flex: 1,
              height: 2.5,
              borderRadius: 999,
              background: hexAlpha(secondary, "20"),
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${progress}%`,
                height: "100%",
                background: accent,
                borderRadius: 999,
              }}
            />
          </div>
        );
      })}
    </div>
  );
}

// ============================================================================
// PERSISTENT BRAND MARK (small watermark that bridges hero -> closing)
// ============================================================================

function BrandCorner({
  from,
  to,
  brandName,
  logo,
  secondary,
  scale,
  side,
  top,
}: {
  from: number;
  to: number;
  brandName: string;
  logo: string;
  secondary: string;
  scale: number;
  side: number;
  top: number;
}) {
  const frame = useCurrentFrame();

  const opacity = interpolate(
    frame,
    [from, from + TRANSITION, to - TRANSITION, to],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  if (frame < from - 1 || frame > to + 1 || !brandName) {
    return null;
  }

  return (
    <div
      style={{
        position: "absolute",
        top: top * 0.8,
        left: side,
        display: "flex",
        alignItems: "center",
        gap: 8 * scale,
        opacity,
        zIndex: 85,
      }}
    >
      {logo ? (
        <Img
          src={logo}
          style={{
            width: 24 * scale,
            height: 24 * scale,
            objectFit: "contain",
          }}
        />
      ) : null}

      <span
        style={{
          fontSize: 10 * scale,
          fontWeight: 800,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: secondary,
          opacity: 0.55,
        }}
      >
        {brandName}
      </span>
    </div>
  );
}

// ============================================================================
// SECTION TITLE
// ============================================================================

function SectionTitle({
  children,
  accent,
  color,
  scale,
}: {
  children: React.ReactNode;
  accent: string;
  color: string;
  scale: number;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 9 * scale,
        marginBottom: 22 * scale,
      }}
    >
      <div
        style={{
          width: 26 * scale,
          height: 2.5,
          borderRadius: 999,
          background: accent,
          flexShrink: 0,
        }}
      />

      <div
        style={{
          fontSize: 15 * scale,
          fontWeight: 850,
          letterSpacing: "0.22em",
          textTransform: "uppercase",
          color,
          opacity: 0.6,
        }}
      >
        {children}
      </div>
    </div>
  );
}

// ============================================================================
// FEATURE ROW (full-screen beat, so it gets real breathing room)
// ============================================================================

function FeatureRow({
  text,
  index,
  start,
  accent,
  textColor,
  scale,
  fps,
}: {
  text: string;
  index: number;
  start: number;
  accent: string;
  textColor: string;
  scale: number;
  fps: number;
}) {
  const frame = useCurrentFrame();

  const delay = start + index * 7;

  const progress = springIn(frame, delay, fps);

  const opacity = interpolate(
    frame,
    [delay, delay + 14],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const x = interpolate(progress, [0, 1], [-26, 0]);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 14 * scale,
        marginBottom: 22 * scale,
        opacity,
        transform: `translateX(${x}px)`,
      }}
    >
      <div
        style={{
          width: 10 * scale,
          height: 10 * scale,
          marginTop: 8 * scale,
          borderRadius: "50%",
          background: accent,
          flexShrink: 0,
        }}
      />

      <div
        style={{
          fontSize: 30 * scale,
          color: textColor,
          fontWeight: 700,
          lineHeight: 1.22,
          letterSpacing: "-0.01em",
        }}
      >
        {clampText(text, 60)}
      </div>
    </div>
  );
}

// ============================================================================
// BENEFIT ROW (stacked, full width — easier to read in portrait than
// squeezing three cards side by side)
// ============================================================================

function BenefitRow({
  text,
  index,
  start,
  accent,
  textColor,
  primary,
  scale,
  fps,
}: {
  text: string;
  index: number;
  start: number;
  accent: string;
  textColor: string;
  primary: string;
  scale: number;
  fps: number;
}) {
  const frame = useCurrentFrame();

  const delay = start + index * 7;

  const progress = springIn(frame, delay, fps);

  const opacity = interpolate(
    frame,
    [delay, delay + 16],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const y = interpolate(progress, [0, 1], [18, 0]);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16 * scale,
        padding: `${16 * scale}px ${18 * scale}px`,
        borderRadius: 14 * scale,
        border: `1px solid ${hexAlpha(textColor, "1a")}`,
        background: hexAlpha(textColor, "08"),
        boxShadow: `0 ${10 * scale}px ${26 * scale}px ${hexAlpha(primary, "40")}`,
        opacity,
        transform: `translateY(${y}px)`,
        marginBottom: 16 * scale,
      }}
    >
      <div
        style={{
          width: 34 * scale,
          height: 34 * scale,
          borderRadius: "50%",
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: hexAlpha(accent, "22"),
          color: accent,
          fontWeight: 900,
          fontSize: 15 * scale,
        }}
      >
        {String(index + 1).padStart(2, "0")}
      </div>

      <div
        style={{
          fontSize: 21 * scale,
          lineHeight: 1.3,
          fontWeight: 650,
          color: textColor,
          opacity: 0.9,
        }}
      >
        {clampText(text, 68)}
      </div>
    </div>
  );
}

// ============================================================================
// CTA PILL — mirrors the flyer's SmartCTA (icon knockout + accent pill)
// ============================================================================

function CtaPill({
  text,
  primary,
  accent,
  scale,
}: {
  text: string;
  primary: string;
  accent: string;
  scale: number;
}) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 12 * scale,
        padding: `${12 * scale}px ${22 * scale}px ${12 * scale}px ${10 * scale}px`,
        borderRadius: 999,
        background: accent,
        color: primary,
        boxShadow: `0 ${12 * scale}px ${30 * scale}px ${hexAlpha(accent, "40")}`,
      }}
    >
      <span
        style={{
          width: 34 * scale,
          height: 34 * scale,
          borderRadius: "50%",
          background: primary,
          color: accent,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 16 * scale,
          flexShrink: 0,
        }}
      >
        →
      </span>

      <span
        style={{
          fontSize: 18 * scale,
          fontWeight: 900,
          letterSpacing: "0.05em",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        }}
      >
        {clampText(text, 40)}
      </span>
    </div>
  );
}

// ============================================================================
// PROMO VIDEO
// ============================================================================

export function PromoVideo({
  headline,
  subtext,
  ctaText,
  price,

  brandName,
  website,

  productImage,

  colors,

  logoImage,
  badge,

  features = [],
  whyChooseUs = [],

  featuresVisible = true,
  whyChooseUsVisible = true,

  phone,
  email,

  phoneVisible = true,
  emailVisible = true,
  websiteVisible = true,

  ctaVisible = true,

  voiceoverUrl,

  musicUrl,
  musicVolume = 0.12,
}: PromoVideoProps) {
  const frame = useCurrentFrame();

  const { fps, durationInFrames, width, height } = useVideoConfig();

  // ==========================================================================
  // MEDIA ORIGIN
  // ==========================================================================

  const MEDIA_ORIGIN = (
    process.env.REMOTION_MEDIA_ORIGIN ||
    process.env.NEXT_PUBLIC_REMOTION_MEDIA_ORIGIN ||
    "https://inrabackend-docker.onrender.com"
  ).replace(/\/+$/, "");

  const resolvedProductImage = resolveAsset(productImage, MEDIA_ORIGIN);
  const resolvedLogo = resolveAsset(logoImage, MEDIA_ORIGIN);
  const resolvedVoiceover = resolveAsset(voiceoverUrl, MEDIA_ORIGIN);
  const resolvedMusic = resolveAsset(musicUrl, MEDIA_ORIGIN);

  // ==========================================================================
  // CONTENT FLAGS
  // ==========================================================================

  const safeFeatures = safeArray(features);
  const safeBenefits = safeArray(whyChooseUs);

  const hasFeatures = featuresVisible && safeFeatures.length > 0;
  const hasBenefits = whyChooseUsVisible && safeBenefits.length > 0;
  const hasCTA = ctaVisible && Boolean(ctaText?.trim());
  const hasWebsite = websiteVisible && Boolean(website?.trim());
  const hasPhone = phoneVisible && Boolean(phone?.trim());
  const hasEmail = emailVisible && Boolean(email?.trim());
  const hasFooter = hasWebsite || hasPhone || hasEmail;
  const hasLogo = Boolean(resolvedLogo);
  const hasBadge = Boolean(badge?.visible && badge.text?.trim());

  // ==========================================================================
  // COLORS
  // ==========================================================================

  const primary = colors?.primary || "#0a0a0a";
  const secondary = colors?.secondary || "#ffffff";
  const accent = colors?.accent || "#c9a84c";

  // ==========================================================================
  // CANVAS
  // ==========================================================================

  const scale = width / 1080;
  const side = Math.round(width * 0.08);
  const top = Math.round(height * 0.05);
  const bottom = Math.round(height * 0.05);

  // ==========================================================================
  // SCENE TIMELINE
  // ==========================================================================

  const timeline = React.useMemo(
    () => buildTimeline(durationInFrames, hasFeatures, hasBenefits),
    [durationInFrames, hasFeatures, hasBenefits]
  );

  const progressSegments: SceneWindow[] = [
    timeline.brand,
    timeline.hero,
    ...(timeline.features ? [timeline.features] : []),
    ...(timeline.benefits ? [timeline.benefits] : []),
    timeline.closing,
  ];

  // ==========================================================================
  // BACKGROUND AMBIENCE (persists across every scene)
  // ==========================================================================

  const glowProgress = interpolate(
    frame,
    [0, durationInFrames],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const glowScale = interpolate(glowProgress, [0, 1], [1, 1.08]);

  // ==========================================================================
  // BRAND INTRO (scene 1)
  // ==========================================================================

  const brandLocalFrame = frame - timeline.brand.start;

  const brandIntroScale = interpolate(
    brandLocalFrame,
    [0, 18],
    [0.8, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // ==========================================================================
  // HERO (scene 2) — product
  // ==========================================================================

  const productLocalStart = timeline.hero.start + 4;

  const productProgress = spring({
    frame: Math.max(0, frame - productLocalStart),
    fps,
    config: { damping: 17, stiffness: 100, mass: 0.8 },
  });

  const productOpacity = interpolate(
    frame,
    [productLocalStart, productLocalStart + 18],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const productOffsetY = interpolate(productProgress, [0, 1], [45, 0]);
  const productScale = interpolate(productProgress, [0, 1], [0.8, 1]);

  const productElapsed = Math.max(0, frame - productLocalStart);
  const productBob = Math.sin(productElapsed / 20) * 2;
  const productRotate = Math.sin(productElapsed / 45) * 0.35;

  const cameraProgress = interpolate(
    frame,
    [timeline.hero.start, timeline.hero.end],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const cameraScale = interpolate(cameraProgress, [0, 1], [1, 1.035]);

  // ==========================================================================
  // HERO — headline / price / subtext
  // ==========================================================================

  const headlineWords = splitHeadline(headline);
  const headlineLocalStart = timeline.hero.start + 16;
  const priceLocalStart = timeline.hero.start + 30;
  const subtextLocalStart = timeline.hero.start + 40;

  const priceProgress = spring({
    frame: Math.max(0, frame - priceLocalStart),
    fps,
    config: { damping: 12, stiffness: 190, mass: 0.5 },
  });

  const priceOpacity = interpolate(
    frame,
    [priceLocalStart, priceLocalStart + 14],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const priceScale = interpolate(priceProgress, [0, 1], [0.8, 1]);

  const subtextStyle = fadeUp(frame, subtextLocalStart, 16);

  // ==========================================================================
  // HERO — badge
  // ==========================================================================

  const badgeLocalStart = timeline.hero.start + 22;

  const badgeProgress = spring({
    frame: Math.max(0, frame - badgeLocalStart),
    fps,
    config: { damping: 10, stiffness: 210, mass: 0.5 },
  });

  const badgeScale = badge
    ? badge.transform.scale * interpolate(badgeProgress, [0, 1], [0.5, 1])
    : 1;

  // ==========================================================================
  // FEATURES (scene 3)
  // ==========================================================================

  const featuresLocalStart = (timeline.features?.start ?? 0) + 18;

  // ==========================================================================
  // BENEFITS (scene 4)
  // ==========================================================================

  const benefitsLocalStart = (timeline.benefits?.start ?? 0) + 18;

  // ==========================================================================
  // CLOSING (scene 5) — CTA / footer
  // ==========================================================================

  const ctaLocalStart = timeline.closing.start + 12;
  const footerLocalStart = timeline.closing.start + 26;

  const ctaProgress = spring({
    frame: Math.max(0, frame - ctaLocalStart),
    fps,
    config: { damping: 12, stiffness: 180, mass: 0.5 },
  });

  const ctaOpacity = interpolate(
    frame,
    [ctaLocalStart, ctaLocalStart + 14],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const ctaScale = interpolate(ctaProgress, [0, 1], [0.9, 1]);

  const footerStyle = fadeUp(frame, footerLocalStart, 16);

  const closingPriceStyle = fadeUp(frame, timeline.closing.start + 4, 14);

  // ==========================================================================
  // AUDIO
  // ==========================================================================

  const musicBaseVolume = Math.max(0, Math.min(1, Number(musicVolume ?? 0.12)));
  const musicFadeStart = Math.max(0, durationInFrames - 30);

  const musicVolumeAtFrame = (audioFrame: number) => {
    const fade = interpolate(
      audioFrame,
      [0, 15, musicFadeStart, durationInFrames],
      [0, musicBaseVolume, musicBaseVolume, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );

    return Math.min(musicBaseVolume, fade);
  };

  // ==========================================================================
  // RENDER
  // ==========================================================================

  return (
    <AbsoluteFill
      style={{
        background: primary,
        color: secondary,
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif",
        overflow: "hidden",
      }}
    >
      {/* ================================================================== */}
      {/* AUDIO */}
      {/* ================================================================== */}

      {resolvedVoiceover ? <Audio src={resolvedVoiceover} volume={1} /> : null}

      {resolvedMusic ? (
        <Audio src={resolvedMusic} volume={musicVolumeAtFrame} />
      ) : null}

      {/* ================================================================== */}
      {/* AMBIENT BACKGROUND (persists across the whole ad) */}
      {/* ================================================================== */}

      <AbsoluteFill style={{ pointerEvents: "none" }}>
        <div
          style={{
            position: "absolute",
            width: 700 * scale,
            height: 700 * scale,
            right: -280 * scale,
            top: -260 * scale,
            borderRadius: "50%",
            background: `radial-gradient(circle, ${hexAlpha(accent, "22")} 0%, ${hexAlpha(
              accent,
              "08"
            )} 32%, transparent 72%)`,
            transform: `scale(${glowScale})`,
          }}
        />

        <div
          style={{
            position: "absolute",
            width: 550 * scale,
            height: 550 * scale,
            left: -260 * scale,
            bottom: -250 * scale,
            borderRadius: "50%",
            background: `radial-gradient(circle, ${hexAlpha(accent, "14")} 0%, transparent 72%)`,
          }}
        />

        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: "50%",
            width: 1,
            background: `linear-gradient(to bottom, transparent, ${hexAlpha(
              accent,
              "12"
            )}, transparent)`,
          }}
        />
      </AbsoluteFill>

      {/* ================================================================== */}
      {/* BEAT PROGRESS + PERSISTENT BRAND MARK */}
      {/* ================================================================== */}

      <ProgressBar
        segments={progressSegments}
        accent={accent}
        secondary={secondary}
        side={side}
        top={top}
      />

      <BrandCorner
        from={timeline.hero.start}
        to={timeline.closing.start}
        brandName={brandName}
        logo={resolvedLogo}
        secondary={secondary}
        scale={scale}
        side={side}
        top={top}
      />

      {/* ================================================================== */}
      {/* SCENE 1 — BRAND INTRO */}
      {/* ================================================================== */}

      <Scene window={timeline.brand} zIndex={90}>
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 9,
              transform: `scale(${brandIntroScale})`,
            }}
          >
            <div
              style={{
                fontSize: 15 * scale,
                fontWeight: 850,
                letterSpacing: "0.30em",
                textTransform: "uppercase",
                color: secondary,
              }}
            >
              {brandName}
            </div>

            <div style={{ width: 55 * scale, height: 2, background: accent }} />
          </div>
        </AbsoluteFill>
      </Scene>

      {/* ================================================================== */}
      {/* SCENE 2 — HERO (product / headline / price / subtext) */}
      {/* ================================================================== */}

      <Scene window={timeline.hero} zIndex={10}>
        <AbsoluteFill
          style={{
            paddingLeft: side,
            paddingRight: side,
            paddingTop: top * 1.8,
            paddingBottom: bottom,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {/* Product */}

          <div
            style={{
              position: "relative",
              flex: "1 1 auto",
              minHeight: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: productOpacity,
              transform: `translateY(${productOffsetY + productBob}px) scale(${productScale}) rotate(${productRotate}deg)`,
            }}
          >
            <div
              style={{
                position: "absolute",
                width: "72%",
                height: "88%",
                borderRadius: "50%",
                background: `radial-gradient(circle, ${hexAlpha(accent, "18")} 0%, transparent 68%)`,
                filter: "blur(18px)",
              }}
            />

            {resolvedProductImage ? (
              <Img
                src={resolvedProductImage}
                style={{
                  maxWidth: "70%",
                  maxHeight: "94%",
                  objectFit: "contain",
                  transform: `scale(${cameraScale})`,
                  filter: "drop-shadow(0 22px 40px rgba(0,0,0,0.65))",
                }}
              />
            ) : (
              <div
                style={{
                  width: 170 * scale,
                  height: 170 * scale,
                  borderRadius: 28,
                  border: `1px solid ${hexAlpha(accent, "44")}`,
                  background: hexAlpha(accent, "12"),
                }}
              />
            )}

            {hasBadge && badge ? (
              <div
                style={{
                  position: "absolute",
                  right: "4%",
                  top: "6%",
                  width: 100 * scale,
                  height: 100 * scale,
                  transform: `translate(${badge.transform.x}px, ${badge.transform.y}px) scale(${badgeScale}) rotate(-8deg)`,
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    borderRadius: "50%",
                    background: badge.bgColor,
                    boxShadow: "0 15px 35px rgba(0,0,0,0.4)",
                  }}
                />

                <div
                  style={{
                    position: "absolute",
                    inset: 7,
                    border: `1px dashed ${hexAlpha(badge.textColor, "80")}`,
                    borderRadius: "50%",
                  }}
                />

                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: 10,
                    boxSizing: "border-box",
                  }}
                >
                  <div
                    style={{
                      fontSize: 20 * scale,
                      fontWeight: 950,
                      color: badge.textColor,
                      lineHeight: 1,
                      textAlign: "center",
                    }}
                  >
                    {clampText(badge.text, 18)}
                  </div>

                  {badge.subText ? (
                    <div
                      style={{
                        marginTop: 4,
                        fontSize: 8 * scale,
                        fontWeight: 800,
                        letterSpacing: "0.08em",
                        color: badge.textColor,
                        opacity: 0.85,
                        textAlign: "center",
                      }}
                    >
                      {clampText(badge.subText, 25)}
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>

          {/* Headline */}

          <div style={{ flex: "0 0 auto", overflow: "hidden" }}>
            <div style={{ maxWidth: "96%", lineHeight: 0.98 }}>
              {headlineWords.map((word, index) => {
                const delay = headlineLocalStart + index * 3;

                const progress = springIn(frame, delay, fps);

                const opacity = interpolate(
                  frame,
                  [delay, delay + 9],
                  [0, 1],
                  { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
                );

                const y = interpolate(progress, [0, 1], [18, 0]);

                return (
                  <span
                    key={`${word}-${index}`}
                    style={{
                      display: "inline-block",
                      marginRight: 8 * scale,
                      marginBottom: 2,
                      fontSize: Math.max(30, Math.round(width * 0.036)),
                      fontWeight: 950,
                      letterSpacing: "-0.045em",
                      color: index === 0 ? accent : secondary,
                      opacity,
                      transform: `translateY(${y}px)`,
                    }}
                  >
                    {word}
                  </span>
                );
              })}
            </div>
          </div>

          {/* Price */}

          {price ? (
            <div
              style={{
                flex: "0 0 auto",
                marginTop: 10 * scale,
                opacity: priceOpacity,
                transform: `scale(${priceScale})`,
                transformOrigin: "left center",
              }}
            >
              <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                <div style={{ width: 18, height: 2, background: accent }} />

                <span
                  style={{
                    fontSize: Math.max(22, Math.round(width * 0.028)),
                    fontWeight: 950,
                    letterSpacing: "-0.04em",
                    color: accent,
                  }}
                >
                  {clampText(price, 35)}
                </span>
              </div>
            </div>
          ) : null}

          {/* Subtext */}

          {subtext ? (
            <div
              style={{
                flex: "0 0 auto",
                marginTop: 10 * scale,
                maxWidth: "90%",
                fontSize: Math.max(14, Math.round(width * 0.015)),
                lineHeight: 1.4,
                color: secondary,
                opacity: Number(subtextStyle.opacity) * 0.75,
                transform: subtextStyle.transform,
              }}
            >
              {clampText(subtext, 160)}
            </div>
          ) : null}
        </AbsoluteFill>
      </Scene>

      {/* ================================================================== */}
      {/* SCENE 3 — FEATURES */}
      {/* ================================================================== */}

      {timeline.features ? (
        <Scene window={timeline.features} zIndex={10}>
          <AbsoluteFill
            style={{
              paddingLeft: side,
              paddingRight: side,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
            }}
          >
            <SectionTitle accent={accent} color={secondary} scale={scale}>
              Features
            </SectionTitle>

            {safeFeatures.map((feature, index) => (
              <FeatureRow
                key={`feature-${index}`}
                text={feature}
                index={index}
                start={featuresLocalStart}
                accent={accent}
                textColor={secondary}
                scale={scale}
                fps={fps}
              />
            ))}
          </AbsoluteFill>
        </Scene>
      ) : null}

      {/* ================================================================== */}
      {/* SCENE 4 — WHY CHOOSE US */}
      {/* ================================================================== */}

      {timeline.benefits ? (
        <Scene window={timeline.benefits} zIndex={10}>
          <AbsoluteFill
            style={{
              paddingLeft: side,
              paddingRight: side,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
            }}
          >
            <SectionTitle accent={accent} color={secondary} scale={scale}>
              Why Choose Us
            </SectionTitle>

            {safeBenefits.map((benefit, index) => (
              <BenefitRow
                key={`benefit-${index}`}
                text={benefit}
                index={index}
                start={benefitsLocalStart}
                accent={accent}
                textColor={secondary}
                primary={primary}
                scale={scale}
                fps={fps}
              />
            ))}
          </AbsoluteFill>
        </Scene>
      ) : null}

      {/* ================================================================== */}
      {/* SCENE 5 — CLOSING (CTA + contact) */}
      {/* ================================================================== */}

      <Scene window={timeline.closing} zIndex={15}>
        <AbsoluteFill
          style={{
            paddingLeft: side,
            paddingRight: side,
            paddingBottom: bottom,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: 22 * scale,
          }}
        >
          {price ? (
            <div
              style={{
                opacity: closingPriceStyle.opacity,
                transform: closingPriceStyle.transform,
              }}
            >
              <div
                style={{
                  fontSize: Math.max(30, Math.round(width * 0.045)),
                  fontWeight: 950,
                  letterSpacing: "-0.04em",
                  color: accent,
                }}
              >
                {clampText(price, 35)}
              </div>
            </div>
          ) : null}

          {hasCTA ? (
            <div
              style={{
                opacity: ctaOpacity,
                transform: `scale(${ctaScale})`,
                transformOrigin: "left center",
              }}
            >
              <CtaPill text={ctaText} primary={primary} accent={accent} scale={scale} />
            </div>
          ) : null}

          {hasFooter ? (
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 12 * scale,
                padding: `${10 * scale}px ${14 * scale}px`,
                borderRadius: 12 * scale,
                border: `1px solid ${hexAlpha(secondary, "16")}`,
                background: hexAlpha(secondary, "05"),
                opacity: footerStyle.opacity,
                transform: footerStyle.transform,
                width: "fit-content",
                maxWidth: "100%",
                boxSizing: "border-box",
              }}
            >
              {hasWebsite ? (
                <span style={{ fontSize: 13 * scale, color: secondary, opacity: 0.7 }}>
                  {website}
                </span>
              ) : null}

              {hasPhone ? (
                <>
                  <span
                    style={{
                      width: 4,
                      height: 4,
                      borderRadius: "50%",
                      background: accent,
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ fontSize: 13 * scale, color: secondary, opacity: 0.6 }}>
                    {phone}
                  </span>
                </>
              ) : null}

              {hasEmail ? (
                <>
                  <span
                    style={{
                      width: 4,
                      height: 4,
                      borderRadius: "50%",
                      background: accent,
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ fontSize: 13 * scale, color: secondary, opacity: 0.6 }}>
                    {email}
                  </span>
                </>
              ) : null}
            </div>
          ) : null}
        </AbsoluteFill>
      </Scene>
    </AbsoluteFill>
  );
}

// ============================================================================
// REMOTION ROOT
// ============================================================================

function RemotionRoot() {
  return (
    <Composition
      id="PromoVideo"
      component={PromoVideo}
      durationInFrames={450}
      fps={30}
      width={1080}
      height={1350}
      defaultProps={DEFAULT_PROPS}
    />
  );
}

registerRoot(RemotionRoot);