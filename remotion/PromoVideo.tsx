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

  subtext: "Elevate your space with our Classic Analog Wall Clock.",

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

  features: ["Premium quality", "Elegant modern design", "Built to last"],

  whyChooseUs: ["Trusted quality", "Fast delivery", "Great customer service"],

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

function resolveAsset(value: string | undefined | null, mediaOrigin: string): string {
  if (!value) return "";

  const clean = String(value).trim();
  if (!clean) return "";

  if (
    clean.startsWith("http://") ||
    clean.startsWith("https://") ||
    clean.startsWith("data:") ||
    clean.startsWith("blob:")
  ) {
    return clean;
  }

  if (clean.startsWith("voiceovers/") || clean.startsWith("/voiceovers/")) {
    return staticFile(clean.replace(/^\/+/, ""));
  }

  if (clean.startsWith("music/") || clean.startsWith("/music/")) {
    return staticFile(clean.replace(/^\/+/, ""));
  }

  if (clean.startsWith("/media/")) {
    return `${mediaOrigin}${clean}`;
  }

  if (clean.startsWith("media/")) {
    return `${mediaOrigin}/${clean}`;
  }

  return `${mediaOrigin}/media/${clean.replace(/^\/+/, "")}`;
}

// ============================================================================
// GENERIC HELPERS
// ============================================================================

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function safeArray(value: string[] | undefined, limit = 4): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item ?? "").trim())
    .filter(Boolean)
    .slice(0, limit);
}

function clampText(value: string, maxLength: number): string {
  const text = String(value || "").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trim()}…`;
}

function splitHeadline(text: string, maxWords = 12): string[] {
  return String(text || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, maxWords);
}

function fadeUp(frame: number, start: number, duration = 18) {
  const opacity = interpolate(frame, [start, start + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const y = interpolate(frame, [start, start + duration], [22, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return { opacity, transform: `translateY(${y}px)` };
}

function springIn(frame: number, start: number, fps: number): number {
  return spring({
    frame: Math.max(0, frame - start),
    fps,
    config: { damping: 16, stiffness: 140, mass: 0.65 },
  });
}

// ============================================================================
// FILM GRAIN OVERLAY — cheap, subtle, adds a "shot on camera" premium feel
// ============================================================================

function FilmGrain() {
  return (
    <svg
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        opacity: 0.05,
        mixBlendMode: "overlay",
        pointerEvents: "none",
      }}
    >
      <filter id="grain">
        <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch" />
        <feColorMatrix type="saturate" values="0" />
      </filter>
      <rect width="100%" height="100%" filter="url(#grain)" />
    </svg>
  );
}

// ============================================================================
// FLOATING PARTICLES — soft ambient depth, drifts slowly the whole video
// ============================================================================

function FloatingParticles({
  accent,
  width,
  height,
}: {
  accent: string;
  width: number;
  height: number;
}) {
  const frame = useCurrentFrame();

  const particles = React.useMemo(
    () =>
      Array.from({ length: 9 }).map((_, i) => ({
        x: (i * 137.5) % width,
        baseY: (i * 271) % height,
        size: 2 + ((i * 5) % 4),
        speed: 0.12 + (i % 4) * 0.045,
        phase: i * 33,
      })),
    [width, height]
  );

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {particles.map((p, i) => {
        const y = ((p.baseY - frame * p.speed) % (height + 60) + height + 60) % (height + 60) - 30;
        const twinkle = 0.25 + 0.35 * Math.abs(Math.sin((frame + p.phase) / 40));

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: p.x,
              top: y,
              width: p.size,
              height: p.size,
              borderRadius: "50%",
              background: accent,
              opacity: twinkle,
              filter: "blur(0.4px)",
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
}

// ============================================================================
// SECTION TITLE
// ============================================================================

function SectionTitle({
  children,
  accent,
  color,
}: {
  children: React.ReactNode;
  accent: string;
  color: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 8 }}>
      <div
        style={{
          width: 16,
          height: 2,
          borderRadius: 999,
          background: accent,
          flexShrink: 0,
        }}
      />
      <div
        style={{
          fontSize: 10,
          fontWeight: 800,
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color,
          opacity: 0.55,
        }}
      >
        {children}
      </div>
    </div>
  );
}

// ============================================================================
// CHECK ICON — used for feature bullets instead of a plain dot
// ============================================================================

function CheckIcon({ accent, size = 16 }: { accent: string; size?: number }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: `${accent}22`,
        border: `1px solid ${accent}55`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      <svg width={size * 0.55} height={size * 0.55} viewBox="0 0 24 24" fill="none">
        <path
          d="M20 6L9 17l-5-5"
          stroke={accent}
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

// ============================================================================
// FEATURE ROW
// ============================================================================

function FeatureRow({
  text,
  index,
  start,
  accent,
  textColor,
  width,
  fps,
}: {
  text: string;
  index: number;
  start: number;
  accent: string;
  textColor: string;
  width: number;
  fps: number;
}) {
  const frame = useCurrentFrame();
  const delay = start + index * 5;
  const progress = springIn(frame, delay, fps);

  const opacity = interpolate(frame, [delay, delay + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const x = interpolate(progress, [0, 1], [-18, 0]);

  const blur = interpolate(frame, [delay, delay + 12], [4, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        marginBottom: 7,
        opacity,
        filter: `blur(${blur}px)`,
        transform: `translateX(${x}px)`,
      }}
    >
      <CheckIcon accent={accent} size={Math.max(14, Math.round(width * 0.015))} />
      <div
        style={{
          fontSize: Math.max(13, Math.round(width * 0.014)),
          color: textColor,
          fontWeight: 650,
          lineHeight: 1.25,
          paddingTop: 1,
        }}
      >
        {clampText(text, 85)}
      </div>
    </div>
  );
}

// ============================================================================
// BENEFIT CARD
// ============================================================================

function BenefitCard({
  text,
  index,
  start,
  accent,
  textColor,
  primary,
  width,
  fps,
}: {
  text: string;
  index: number;
  start: number;
  accent: string;
  textColor: string;
  primary: string;
  width: number;
  fps: number;
}) {
  const frame = useCurrentFrame();
  const delay = start + index * 5;
  const progress = springIn(frame, delay, fps);

  const opacity = interpolate(frame, [delay, delay + 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const y = interpolate(progress, [0, 1], [12, 0]);
  const scaleIn = interpolate(progress, [0, 1], [0.92, 1]);

  // gentle continuous float after settling, keeps cards feeling "alive"
  const floatOffset = Math.sin((frame - delay) / 55 + index) * 2;

  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        padding: "9px 10px",
        borderRadius: 9,
        border: `1px solid ${textColor}14`,
        background: `${textColor}07`,
        boxShadow: `0 7px 20px ${primary}40`,
        opacity,
        transform: `translateY(${y + floatOffset}px) scale(${scaleIn})`,
      }}
    >
      <div
        style={{
          width: 5,
          height: 5,
          borderRadius: "50%",
          background: accent,
          marginBottom: 6,
          boxShadow: `0 0 8px ${accent}`,
        }}
      />
      <div
        style={{
          fontSize: Math.max(10, Math.round(width * 0.0105)),
          lineHeight: 1.25,
          fontWeight: 650,
          color: textColor,
          opacity: 0.82,
        }}
      >
        {clampText(text, 52)}
      </div>
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
  // CONTENT
  // ==========================================================================

  // NOTE: caps raised from 3 -> 4 for features so real content isn't silently
  // dropped when the editor / backend legitimately supplies 4 items. Benefit
  // cards stay at 3 since they render side-by-side (4 would overcrowd).
  const safeFeatures = safeArray(features, 4);
  const safeBenefits = safeArray(whyChooseUs, 3);

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
  const side = Math.round(width * 0.065);
  const top = Math.round(height * 0.035);
  const bottom = Math.round(height * 0.035);

  // ==========================================================================
  // CONTENT ZONES
  // ==========================================================================

  const headerHeight = Math.round(height * 0.065);
  const productHeight = Math.round(height * 0.2);
  const headlineHeight = Math.round(height * 0.105);
  const descriptionHeight = Math.round(height * 0.075);
  const featuresHeight = hasFeatures ? Math.round(height * 0.13) : 0;
  const benefitsHeight = hasBenefits ? Math.round(height * 0.115) : 0;
  const ctaHeight = hasCTA ? Math.round(height * 0.065) : 0;
  const footerHeight = hasFooter ? Math.round(height * 0.055) : 0;

  // ==========================================================================
  // VERTICAL LAYOUT
  // ==========================================================================

  let currentY = top;
  const headerY = currentY;
  currentY += headerHeight;

  const productSectionY = currentY;
  currentY += productHeight;

  const headlineY = currentY;
  currentY += headlineHeight;

  const descriptionY = currentY;
  currentY += descriptionHeight;

  const featuresY = currentY;
  currentY += featuresHeight;

  const benefitsY = currentY;
  currentY += benefitsHeight;

  const ctaY = currentY;
  const footerY = height - footerHeight - bottom;

  // ==========================================================================
  // TIMELINE
  // ==========================================================================

  const brandStart = 0;
  const productStart = 12;
  const headlineStart = 36;
  const priceStart = 48;
  const subtextStart = 62;
  const featuresStart = 82;

  const benefitsStart = featuresStart + Math.max(16, safeFeatures.length * 5);
  const ctaStart = benefitsStart + Math.max(18, safeBenefits.length * 5);
  const footerStart = ctaStart + 12;

  // near-end cinematic flash, purely a polish beat before the video loops/ends
  const flashStart = Math.max(footerStart + 30, durationInFrames - 26);

  // ==========================================================================
  // BACKGROUND ANIMATION
  // ==========================================================================

  const glowProgress = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const glowScale = interpolate(glowProgress, [0, 1], [1, 1.08]);
  const glowDrift = Math.sin(frame / 130) * 18;
  const glowRotate = interpolate(frame, [0, durationInFrames], [0, 8], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ==========================================================================
  // BRAND INTRO
  // ==========================================================================

  const brandOpacity = interpolate(frame, [0, 7, 20], [0, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const brandScale = interpolate(frame, [0, 18], [0.8, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ==========================================================================
  // PRODUCT ANIMATION — entrance spring + continuous Ken Burns drift
  // ==========================================================================

  const productProgress = spring({
    frame: Math.max(0, frame - productStart),
    fps,
    config: { damping: 17, stiffness: 100, mass: 0.8 },
  });

  const productOpacity = interpolate(frame, [productStart, productStart + 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const productOffsetY = interpolate(productProgress, [0, 1], [55, 0]);
  const productScale = interpolate(productProgress, [0, 1], [0.78, 1]);

  const productElapsed = Math.max(0, frame - productStart);
  const productBob = Math.sin(productElapsed / 20) * 2;
  const productRotate = Math.sin(productElapsed / 45) * 0.35;

  // Ken Burns: slow continuous zoom + diagonal pan across the FULL runtime,
  // layered on top of the entrance spring so the hero shot never sits still.
  const kenBurnsScale = interpolate(frame, [productStart + 24, durationInFrames], [1, 1.11], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const kenBurnsX = interpolate(frame, [productStart + 24, durationInFrames], [-6, 14], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const kenBurnsY = interpolate(frame, [productStart + 24, durationInFrames], [4, -10], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ==========================================================================
  // HEADLINE
  // ==========================================================================

  const headlineWords = splitHeadline(headline);

  // ==========================================================================
  // PRICE
  // ==========================================================================

  const priceProgress = spring({
    frame: Math.max(0, frame - priceStart),
    fps,
    config: { damping: 12, stiffness: 190, mass: 0.5 },
  });

  const priceOpacity = interpolate(frame, [priceStart, priceStart + 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const priceScale = interpolate(priceProgress, [0, 1], [0.8, 1]);

  // ==========================================================================
  // DESCRIPTION
  // ==========================================================================

  const subtextStyle = fadeUp(frame, subtextStart, 16);

  // ==========================================================================
  // CTA — entrance + a looping "shine sweep" like a premium ad lower-third
  // ==========================================================================

  const ctaProgress = hasCTA
    ? spring({ frame: Math.max(0, frame - ctaStart), fps, config: { damping: 12, stiffness: 180, mass: 0.5 } })
    : 0;

  const ctaOpacity = hasCTA
    ? interpolate(frame, [ctaStart, ctaStart + 14], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;

  const ctaScale = hasCTA ? interpolate(ctaProgress, [0, 1], [0.92, 1]) : 1;

  const ctaLine = hasCTA
    ? interpolate(frame, [ctaStart + 5, ctaStart + 22], [0, 100], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;

  const ctaShineCycle = 90;
  const ctaShinePos = hasCTA ? ((frame - ctaStart) % ctaShineCycle) / ctaShineCycle : 0;
  const ctaArrowPulse = 1 + 0.12 * Math.abs(Math.sin(frame / 18));

  // ==========================================================================
  // FOOTER
  // ==========================================================================

  const footerStyle = fadeUp(frame, footerStart, 16);

  // ==========================================================================
  // BADGE — clamped so it can never render off-canvas
  // ==========================================================================

  const badgeProgress = spring({
    frame: Math.max(0, frame - (productStart + 18)),
    fps,
    config: { damping: 10, stiffness: 210, mass: 0.5 },
  });

  const badgeSize = 94 * scale;
  const badgeRightInset = side * 0.1;
  const maxBadgeTranslateX = Math.max(0, badgeRightInset - 6);
  const maxBadgeTranslateY = Math.max(0, productHeight * 0.1 - 6);

  const clampedBadgeX = badge ? clamp(badge.transform.x, -maxBadgeTranslateX, maxBadgeTranslateX) : 0;
  const clampedBadgeY = badge ? clamp(badge.transform.y, -maxBadgeTranslateY, maxBadgeTranslateY) : 0;

  const badgeScale = badge
    ? badge.transform.scale * interpolate(badgeProgress, [0, 1], [0.5, 1])
    : 1;

  const badgePulse = 1 + 0.03 * Math.sin(frame / 14);

  // ==========================================================================
  // FINAL FLASH — a soft cinematic light pass near the end
  // ==========================================================================

  const flashOpacity = interpolate(
    frame,
    [flashStart, flashStart + 8, flashStart + 20],
    [0, 0.16, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // ==========================================================================
  // AUDIO
  // ==========================================================================

  const musicBaseVolume = clamp(Number(musicVolume ?? 0.12), 0, 1);
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
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif",
        overflow: "hidden",
      }}
    >
      {resolvedVoiceover ? <Audio src={resolvedVoiceover} volume={1} /> : null}
      {resolvedMusic ? <Audio src={resolvedMusic} volume={musicVolumeAtFrame} /> : null}

      {/* ================================================================== */}
      {/* BACKGROUND */}
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
            background: `radial-gradient(circle, ${accent}22 0%, ${accent}08 32%, transparent 72%)`,
            transform: `scale(${glowScale}) translate(${glowDrift}px, ${-glowDrift}px) rotate(${glowRotate}deg)`,
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
            background: `radial-gradient(circle, ${accent}14 0%, transparent 72%)`,
            transform: `translate(${-glowDrift * 0.6}px, ${glowDrift * 0.6}px)`,
          }}
        />

        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: "50%",
            width: 1,
            background: `linear-gradient(to bottom, transparent, ${accent}12, transparent)`,
          }}
        />

        <FloatingParticles accent={accent} width={width} height={height} />
        <FilmGrain />
      </AbsoluteFill>

      {/* ================================================================== */}
      {/* BRAND INTRO */}
      {/* ================================================================== */}

      {brandName ? (
        <AbsoluteFill
          style={{
            alignItems: "center",
            justifyContent: "center",
            opacity: brandOpacity,
            pointerEvents: "none",
            zIndex: 90,
          }}
        >
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 9,
              transform: `scale(${brandScale})`,
            }}
          >
            <div
              style={{
                fontSize: 14 * scale,
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
      ) : null}

      {/* ================================================================== */}
      {/* MAIN CONTENT */}
      {/* ================================================================== */}

      <AbsoluteFill style={{ zIndex: 5 }}>
        {/* HEADER */}
        <div
          style={{
            position: "absolute",
            top: headerY,
            left: side,
            right: side,
            height: headerHeight,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            zIndex: 20,
          }}
        >
          {brandName ? (
            <div
              style={{
                fontSize: 10 * scale,
                fontWeight: 800,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                color: secondary,
                opacity: 0.5,
              }}
            >
              {brandName}
            </div>
          ) : (
            <div />
          )}

          {hasLogo ? (
            <Img
              src={resolvedLogo}
              style={{ width: 46 * scale, height: 46 * scale, objectFit: "contain" }}
            />
          ) : null}
        </div>

        {/* PRODUCT — with continuous Ken Burns drift */}
        <div
          style={{
            position: "absolute",
            top: productSectionY,
            left: side,
            right: side,
            height: productHeight,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            opacity: productOpacity,
            transform: `translate(${kenBurnsX}px, ${productOffsetY + productBob + kenBurnsY}px) scale(${
              productScale * kenBurnsScale
            }) rotate(${productRotate}deg)`,
            zIndex: 4,
          }}
        >
          <div
            style={{
              position: "absolute",
              width: "68%",
              height: "90%",
              borderRadius: "50%",
              background: `radial-gradient(circle, ${accent}18 0%, transparent 68%)`,
              filter: "blur(18px)",
            }}
          />

          {resolvedProductImage ? (
            <Img
              src={resolvedProductImage}
              style={{
                maxWidth: "60%",
                maxHeight: "92%",
                objectFit: "contain",
                filter: "drop-shadow(0 22px 40px rgba(0,0,0,0.65))",
              }}
            />
          ) : (
            <div
              style={{
                width: 150 * scale,
                height: 150 * scale,
                borderRadius: 26,
                border: `1px solid ${accent}44`,
                background: `${accent}12`,
              }}
            />
          )}
        </div>

        {/* BADGE — clamped inside canvas bounds */}
        {hasBadge && badge ? (
          <div
            style={{
              position: "absolute",
              right: badgeRightInset,
              top: productSectionY + productHeight * 0.1,
              width: badgeSize,
              height: badgeSize,
              transform: `translate(${clampedBadgeX}px, ${clampedBadgeY}px) scale(${
                badgeScale * badgePulse
              }) rotate(-8deg)`,
              zIndex: 25,
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
                border: `1px dashed ${badge.textColor}80`,
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

        {/* HEADLINE — with a subtle focus-pull blur-in */}
        <div
          style={{
            position: "absolute",
            top: headlineY,
            left: side,
            right: side,
            height: headlineHeight,
            zIndex: 10,
            overflow: "hidden",
          }}
        >
          <div style={{ maxWidth: "96%", lineHeight: 0.98 }}>
            {headlineWords.map((word, index) => {
              const delay = headlineStart + index * 3;
              const progress = springIn(frame, delay, fps);

              const opacity = interpolate(frame, [delay, delay + 9], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });

              const y = interpolate(progress, [0, 1], [18, 0]);

              const blur = interpolate(frame, [delay, delay + 9], [8, 0], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });

              return (
                <span
                  key={`${word}-${index}`}
                  style={{
                    display: "inline-block",
                    marginRight: 6 * scale,
                    marginBottom: 2,
                    fontSize: Math.max(26, Math.round(width * 0.03)),
                    fontWeight: 950,
                    letterSpacing: "-0.045em",
                    color: index === 0 ? accent : secondary,
                    opacity,
                    filter: `blur(${blur}px)`,
                    transform: `translateY(${y}px)`,
                  }}
                >
                  {word}
                </span>
              );
            })}
          </div>
        </div>

        {/* PRICE */}
        {price ? (
          <div
            style={{
              position: "absolute",
              top: headlineY + headlineHeight - Math.round(height * 0.012),
              left: side,
              opacity: priceOpacity,
              transform: `scale(${priceScale})`,
              transformOrigin: "left center",
              zIndex: 11,
            }}
          >
            <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 18, height: 2, background: accent }} />
              <span
                style={{
                  fontSize: Math.max(21, Math.round(width * 0.025)),
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

        {/* DESCRIPTION */}
        {subtext ? (
          <div
            style={{
              position: "absolute",
              top: descriptionY,
              left: side,
              right: side,
              height: descriptionHeight,
              maxWidth: "90%",
              fontSize: Math.max(12, Math.round(width * 0.012)),
              lineHeight: 1.35,
              color: secondary,
              opacity: Number(subtextStyle.opacity) * 0.75,
              transform: subtextStyle.transform,
              zIndex: 10,
              overflow: "hidden",
            }}
          >
            {clampText(subtext, 180)}
          </div>
        ) : null}

        {/* FEATURES */}
        {hasFeatures ? (
          <div
            style={{
              position: "absolute",
              top: featuresY,
              left: side,
              right: side,
              height: featuresHeight,
              zIndex: 10,
              overflow: "hidden",
            }}
          >
            <SectionTitle accent={accent} color={secondary}>
              Features
            </SectionTitle>
            {safeFeatures.map((feature, index) => (
              <FeatureRow
                key={`feature-${index}`}
                text={feature}
                index={index}
                start={featuresStart}
                accent={accent}
                textColor={secondary}
                width={width}
                fps={fps}
              />
            ))}
          </div>
        ) : null}

        {/* WHY CHOOSE US */}
        {hasBenefits ? (
          <div
            style={{
              position: "absolute",
              top: benefitsY,
              left: side,
              right: side,
              height: benefitsHeight,
              zIndex: 10,
              overflow: "hidden",
            }}
          >
            <SectionTitle accent={accent} color={secondary}>
              Why Choose Us
            </SectionTitle>
            <div style={{ display: "flex", gap: 8, width: "100%" }}>
              {safeBenefits.map((benefit, index) => (
                <BenefitCard
                  key={`benefit-${index}`}
                  text={benefit}
                  index={index}
                  start={benefitsStart}
                  accent={accent}
                  textColor={secondary}
                  primary={primary}
                  width={width}
                  fps={fps}
                />
              ))}
            </div>
          </div>
        ) : null}

        {/* CTA — with looping shine sweep across the text */}
        {hasCTA ? (
          <div
            style={{
              position: "absolute",
              left: side,
              right: side,
              top: ctaY,
              height: ctaHeight,
              opacity: ctaOpacity,
              transform: `scale(${ctaScale})`,
              transformOrigin: "left center",
              zIndex: 15,
            }}
          >
            <div style={{ display: "inline-flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{
                    fontSize: 14 * scale,
                    fontWeight: 900,
                    letterSpacing: "0.07em",
                    textTransform: "uppercase",
                    backgroundImage: `linear-gradient(100deg, ${secondary} 40%, ${accent} 50%, ${secondary} 60%)`,
                    backgroundSize: "250% 100%",
                    backgroundPosition: `${ctaShinePos * 100}% 0`,
                    WebkitBackgroundClip: "text",
                    backgroundClip: "text",
                    color: "transparent",
                  }}
                >
                  {clampText(ctaText, 60)}
                </span>
                <span
                  style={{
                    fontSize: 16 * scale,
                    color: accent,
                    display: "inline-block",
                    transform: `scale(${ctaArrowPulse})`,
                  }}
                >
                  →
                </span>
              </div>
              <div
                style={{
                  height: 2,
                  width: `${ctaLine}%`,
                  background: accent,
                  borderRadius: 3,
                }}
              />
            </div>
          </div>
        ) : null}

        {/* FOOTER */}
        {hasFooter ? (
          <div
            style={{
              position: "absolute",
              left: side,
              right: side,
              top: footerY,
              height: footerHeight,
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "7px 10px",
              borderRadius: 9,
              border: `1px solid ${secondary}16`,
              background: `${secondary}05`,
              opacity: footerStyle.opacity,
              transform: footerStyle.transform,
              zIndex: 20,
              overflow: "hidden",
              boxSizing: "border-box",
            }}
          >
            {hasWebsite ? (
              <span
                style={{
                  fontSize: 9 * scale,
                  color: secondary,
                  opacity: 0.65,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {website}
              </span>
            ) : null}

            {hasPhone ? (
              <>
                <span
                  style={{ width: 3, height: 3, borderRadius: "50%", background: accent, flexShrink: 0 }}
                />
                <span
                  style={{
                    fontSize: 9 * scale,
                    color: secondary,
                    opacity: 0.55,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {phone}
                </span>
              </>
            ) : null}

            {hasEmail ? (
              <>
                <span
                  style={{ width: 3, height: 3, borderRadius: "50%", background: accent, flexShrink: 0 }}
                />
                <span
                  style={{
                    fontSize: 9 * scale,
                    color: secondary,
                    opacity: 0.55,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {email}
                </span>
              </>
            ) : null}
          </div>
        ) : null}
      </AbsoluteFill>

      {/* FINAL CINEMATIC FLASH */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at 50% 40%, ${secondary}, transparent 70%)`,
          opacity: flashOpacity,
          pointerEvents: "none",
          zIndex: 95,
        }}
      />
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