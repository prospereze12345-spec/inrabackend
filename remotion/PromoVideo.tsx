import React from "react";

import {
  registerRoot,
  Composition,
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Sequence,
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
// DEFAULTS
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

  features: [],
  whyChooseUs: [],

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
// TIMING
// ============================================================================

const TIMING = {
  brandIntro: 24,

  productEntrance: 18,

  headline: 52,

  price: 96,

  subtext: 116,

  featureItemGap: 16,

  whyChooseItemGap: 16,

  ctaGap: 22,

  footerGap: 18,

  outroLead: 30,
};

// ============================================================================
// ASSET RESOLUTION
// ============================================================================

function resolveAsset(
  value: string | undefined | null,
  mediaOrigin: string,
  options?: {
    staticSubdir?: string;
  }
) {
  if (!value) {
    return "";
  }

  const clean = value.trim();

  if (!clean) {
    return "";
  }

  // Absolute remote URL
  if (
    clean.startsWith("http://") ||
    clean.startsWith("https://")
  ) {
    return clean;
  }

  // Local Remotion-generated voiceover
  if (
    clean.startsWith("voiceovers/") ||
    clean.startsWith("/voiceovers/")
  ) {
    return staticFile(
      clean.replace(/^\/+/, "")
    );
  }

  // Local Remotion music
  if (
    clean.startsWith("music/") ||
    clean.startsWith("/music/")
  ) {
    return staticFile(
      clean.replace(/^\/+/, "")
    );
  }

  // Django media
  if (clean.startsWith("/media/")) {
    return `${mediaOrigin}${clean}`;
  }

  if (clean.startsWith("media/")) {
    return `${mediaOrigin}/${clean}`;
  }

  // Explicit static directory
  if (options?.staticSubdir) {
    return staticFile(
      `${options.staticSubdir}/${clean.replace(/^\/+/, "")}`
    );
  }

  // Treat unknown relative assets as Django media.
  return `${mediaOrigin}/media/${clean.replace(/^\/+/, "")}`;
}

// ============================================================================
// SAFE ARRAY
// ============================================================================

function safeArray(value?: string[]) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => String(item).trim())
    .filter(Boolean);
}

// ============================================================================
// BULLET ROW
// ============================================================================

function BulletRow({
  text,
  index,
  startFrame,
  gap,
  accent,
  textColor,
  fontSize = 15,
}: {
  text: string;
  index: number;
  startFrame: number;
  gap: number;
  accent: string;
  textColor: string;
  fontSize?: number;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const delay = startFrame + index * gap;

  const progress = spring({
    frame: frame - delay,
    fps,

    config: {
      damping: 20,
      stiffness: 140,
    },
  });

  const opacity = interpolate(
    frame,
    [delay, delay + 14],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  const x = interpolate(
    progress,
    [0, 1],
    [-18, 0]
  );

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        opacity,
        transform: `translateX(${x}px)`,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: accent,
          flexShrink: 0,
        }}
      />

      <span
        style={{
          fontSize,
          color: textColor,
          opacity: 0.88,
          fontWeight: 600,
          lineHeight: 1.25,
        }}
      >
        {text}
      </span>
    </div>
  );
}

// ============================================================================
// SECTION LABEL
// ============================================================================

function SectionLabel({
  children,
  textColor,
}: {
  children: React.ReactNode;
  textColor: string;
}) {
  return (
    <div
      style={{
        fontSize: 9,
        fontWeight: 800,
        letterSpacing: "0.18em",
        textTransform: "uppercase",
        color: textColor,
        opacity: 0.38,
        marginBottom: 7,
      }}
    >
      {children}
    </div>
  );
}

// ============================================================================
// MAIN
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

  const {
    fps,
    durationInFrames,
    width,
    height,
  } = useVideoConfig();

  // ==========================================================================
  // MEDIA
  // ==========================================================================

  const MEDIA_ORIGIN = (
    process.env.REMOTION_MEDIA_ORIGIN ||
    "https://inrabackend-docker.onrender.com"
  ).replace(/\/+$/, "");

  const resolvedProductImage = resolveAsset(
    productImage,
    MEDIA_ORIGIN
  );

  const resolvedVoiceover = resolveAsset(
    voiceoverUrl,
    MEDIA_ORIGIN
  );

  const resolvedMusic = resolveAsset(
    musicUrl,
    MEDIA_ORIGIN
  );

  // ==========================================================================
  // NORMALIZE CONTENT
  // ==========================================================================

  const safeFeatures = safeArray(features).slice(0, 3);
  const safeBenefits = safeArray(whyChooseUs).slice(0, 3);

  const hasFeatures =
    featuresVisible &&
    safeFeatures.length > 0;

  const hasBenefits =
    whyChooseUsVisible &&
    safeBenefits.length > 0;

  const hasWebsite =
    websiteVisible &&
    Boolean(website?.trim());

  const hasPhone =
    phoneVisible &&
    Boolean(phone?.trim());

  const hasEmail =
    emailVisible &&
    Boolean(email?.trim());

  const hasFooter =
    hasWebsite ||
    hasPhone ||
    hasEmail;

  const hasCTA =
    ctaVisible &&
    Boolean(ctaText?.trim());

  const hasLogo =
    Boolean(logoImage?.trim());

  const hasBadge =
    Boolean(
      badge &&
      badge.visible
    );

  // ==========================================================================
  // RESPONSIVE SCALE
  // ==========================================================================

  const scale = width / 1080;

  const horizontalPadding =
    Math.round(width * 0.085);

  const topPadding =
    Math.round(height * 0.045);

  const productHeight =
    height >= 1700
      ? "32%"
      : height <= 1100
        ? "30%"
        : "32%";

  // ==========================================================================
  // DYNAMIC TIMELINE
  // ==========================================================================

  let cursor = TIMING.subtext + 28;

  const featuresStart = hasFeatures
    ? cursor
    : -1;

  if (hasFeatures) {
    cursor +=
      safeFeatures.length *
        TIMING.featureItemGap +
      30;
  }

  const whyChooseStart = hasBenefits
    ? cursor
    : -1;

  if (hasBenefits) {
    cursor +=
      safeBenefits.length *
        TIMING.whyChooseItemGap +
      30;
  }

  const ctaStart = hasCTA
    ? cursor
    : -1;

  if (hasCTA) {
    cursor +=
      TIMING.ctaGap + 25;
  }

  const footerStart = hasFooter
    ? cursor
    : -1;

  if (hasFooter) {
    cursor +=
      TIMING.footerGap + 32;
  }

  // Keep outro safely toward the end.
  const outroFrom = Math.min(
    durationInFrames - 1,
    Math.max(
      durationInFrames - TIMING.outroLead,
      cursor
    )
  );

  // ==========================================================================
  // SPRING
  // ==========================================================================

  const sp = (
    frameValue: number,
    delay = 0,
    mass = 1
  ) =>
    spring({
      frame: frameValue - delay,
      fps,

      config: {
        damping: 18,
        stiffness: 80,
        mass,
      },
    });

  // ==========================================================================
  // BRAND INTRO
  // ==========================================================================

  const brandProgress = interpolate(
    frame,
    [0, 20],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  const brandOpacity = interpolate(
    frame,
    [0, 16, TIMING.brandIntro],
    [0, 1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  // ==========================================================================
  // PRODUCT
  // ==========================================================================

  const productProgress = sp(
    frame,
    TIMING.productEntrance
  );

  const productY = interpolate(
    productProgress,
    [0, 1],
    [60, 0]
  );

  const productScale = interpolate(
    productProgress,
    [0, 1],
    [0.84, 1]
  );

  const productOpacity = interpolate(
    frame,
    [
      TIMING.productEntrance,
      TIMING.productEntrance + 24,
    ],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  const productElapsed = Math.max(
    0,
    frame - TIMING.productEntrance
  );

  const bobY =
    productElapsed > 0
      ? Math.sin(productElapsed / 18) * 5
      : 0;

  const wobbleDeg =
    productElapsed > 0
      ? Math.sin(productElapsed / 42) * 1.4
      : 0;

  // ==========================================================================
  // KEN BURNS
  // ==========================================================================

  const kbProgress = interpolate(
    frame,
    [
      TIMING.productEntrance,
      durationInFrames,
    ],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  const kbScale = interpolate(
    kbProgress,
    [0, 1],
    [1, 1.08]
  );

  const kbX = interpolate(
    kbProgress,
    [0, 1],
    [0, -8]
  );

  const kbY = interpolate(
    kbProgress,
    [0, 1],
    [0, 5]
  );

  // ==========================================================================
  // HEADLINE
  // ==========================================================================

  const headlineWords = String(
    headline || ""
  )
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 7);

  // ==========================================================================
  // PRICE
  // ==========================================================================

  const priceProgress = spring({
    frame: frame - TIMING.price,
    fps,

    config: {
      damping: 12,
      stiffness: 200,
      mass: 0.5,
    },
  });

  const priceOpacity = interpolate(
    frame,
    [
      TIMING.price,
      TIMING.price + 15,
    ],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  // ==========================================================================
  // SUBTEXT
  // ==========================================================================

  const subOpacity = interpolate(
    frame,
    [
      TIMING.subtext,
      TIMING.subtext + 20,
    ],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  const subY = interpolate(
    sp(frame, TIMING.subtext),
    [0, 1],
    [18, 0]
  );

  // ==========================================================================
  // CTA
  // ==========================================================================

  const ctaProgress = hasCTA
    ? spring({
        frame: frame - ctaStart,
        fps,

        config: {
          damping: 10,
          stiffness: 180,
          mass: 0.4,
        },
      })
    : 0;

  const ctaOpacity = hasCTA
    ? interpolate(
        frame,
        [
          ctaStart,
          ctaStart + 18,
        ],
        [0, 1],
        {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }
      )
    : 0;

  const ctaScale = interpolate(
    ctaProgress,
    [0, 1],
    [0.9, 1]
  );

  const ctaLine = hasCTA
    ? interpolate(
        frame,
        [
          ctaStart + 12,
          ctaStart + 38,
        ],
        [0, 100],
        {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }
      )
    : 0;

  // ==========================================================================
  // FOOTER
  // ==========================================================================

  const footerOpacity = hasFooter
    ? interpolate(
        frame,
        [
          footerStart,
          footerStart + 18,
        ],
        [0, 1],
        {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }
      )
    : 0;

  const footerY = hasFooter
    ? interpolate(
        sp(frame, footerStart),
        [0, 1],
        [14, 0]
      )
    : 0;

  // ==========================================================================
  // BADGE
  // ==========================================================================

  const badgeProgress = spring({
    frame:
      frame -
      (TIMING.productEntrance + 18),

    fps,

    config: {
      damping: 9,
      stiffness: 220,
      mass: 0.5,
    },
  });

  // ==========================================================================
  // OUTRO
  // ==========================================================================

  const outroOpacity = interpolate(
    frame,
    [
      outroFrom,
      Math.min(
        durationInFrames,
        outroFrom + 15
      ),
    ],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  // ==========================================================================
  // COLORS
  // ==========================================================================

  const accent =
    colors?.accent || "#c9a84c";

  const primary =
    colors?.primary || "#0a0a0a";

  const textColor =
    colors?.secondary || "#ffffff";

  // ==========================================================================
  // RENDER
  // ==========================================================================

  return (
    <AbsoluteFill
      style={{
        background: primary,

        fontFamily:
          "-apple-system, BlinkMacSystemFont, " +
          "'Helvetica Neue', Arial, sans-serif",

        overflow: "hidden",
      }}
    >
      {/* ================================================================== */}
      {/* AUDIO */}
      {/* ================================================================== */}

      {resolvedMusic && (
        <Audio
          src={resolvedMusic}
          volume={(audioFrame) =>
            interpolate(
              audioFrame,
              [
                0,
                30,
                Math.max(
                  30,
                  outroFrom - 15
                ),
                outroFrom + 10,
              ],
              [
                0,
                musicVolume,
                musicVolume,
                0,
              ],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }
            )
          }
        />
      )}

      {resolvedVoiceover && (
        <Audio
          src={resolvedVoiceover}
          volume={1}
        />
      )}

      {/* ================================================================== */}
      {/* BACKGROUND */}
      {/* ================================================================== */}

      <AbsoluteFill
        style={{
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            position: "absolute",

            width: 620 * scale,
            height: 620 * scale,

            borderRadius: "50%",

            background:
              `radial-gradient(circle, ${accent}18 0%, transparent 70%)`,

            top: -220 * scale,
            right: -160 * scale,

            transform:
              `scale(${interpolate(
                frame,
                [0, durationInFrames],
                [1, 1.12]
              )})`,
          }}
        />

        <div
          style={{
            position: "absolute",

            width: 420 * scale,
            height: 420 * scale,

            borderRadius: "50%",

            background:
              `radial-gradient(circle, ${accent}0d 0%, transparent 70%)`,

            bottom: -120 * scale,
            left: -120 * scale,
          }}
        />
      </AbsoluteFill>

      {/* ================================================================== */}
      {/* BRAND INTRO */}
      {/* ================================================================== */}

      <Sequence
        from={0}
        durationInFrames={TIMING.brandIntro}
      >
        <AbsoluteFill
          style={{
            alignItems: "center",
            justifyContent: "center",
            flexDirection: "column",
            gap: 9,
            opacity: brandOpacity,
          }}
        >
          <div
            style={{
              fontSize: 13 * scale,
              fontWeight: 800,
              letterSpacing: "0.3em",
              textTransform: "uppercase",
              color: textColor,

              transform:
                `scale(${interpolate(
                  brandProgress,
                  [0, 1],
                  [0.65, 1]
                )})`,
            }}
          >
            {brandName}
          </div>

          <div
            style={{
              width: interpolate(
                brandProgress,
                [0, 1],
                [0, 44]
              ),

              height: 1,
              background: accent,
            }}
          />
        </AbsoluteFill>
      </Sequence>

      {/* ================================================================== */}
      {/* MAIN */}
      {/* ================================================================== */}

      <Sequence
        from={TIMING.productEntrance}
        durationInFrames={Math.max(
          1,
          outroFrom - TIMING.productEntrance
        )}
      >
        <AbsoluteFill
          style={{
            paddingTop: topPadding,
            paddingLeft: horizontalPadding,
            paddingRight: horizontalPadding,

            paddingBottom:
              Math.round(height * 0.035),

            flexDirection: "column",
          }}
        >
          {/* BRAND */}

          {brandName && (
            <div
              style={{
                fontSize: 9 * scale,
                fontWeight: 700,
                letterSpacing: "0.2em",
                textTransform: "uppercase",
                color: textColor,
                opacity: 0.42,
                marginBottom: 7,
              }}
            >
              {brandName}
            </div>
          )}

          {/* PRODUCT */}

          <div
            style={{
              height: productHeight,

              display: "flex",
              alignItems: "center",
              justifyContent: "center",

              opacity: productOpacity,

              overflow: "visible",

              transform:
                `translateY(${productY + bobY}px) ` +
                `scale(${productScale}) ` +
                `rotate(${wobbleDeg}deg)`,
            }}
          >
            {resolvedProductImage ? (
              <Img
                src={resolvedProductImage}
                style={{
                  maxWidth: "70%",
                  maxHeight: "100%",
                  objectFit: "contain",

                  filter:
                    "drop-shadow(0 24px 40px rgba(0,0,0,0.6))",

                  transform:
                    `scale(${kbScale}) ` +
                    `translate(${kbX}px, ${kbY}px)`,
                }}
              />
            ) : (
              <div
                style={{
                  width: 120 * scale,
                  height: 120 * scale,

                  borderRadius: 18,

                  background: `${accent}22`,

                  border:
                    `1px solid ${accent}44`,
                }}
              />
            )}
          </div>

          {/* HEADLINE */}

          <div
            style={{
              marginTop: 12,
              marginBottom: 7,
              maxWidth: "92%",
            }}
          >
            {headlineWords.map(
              (word, index) => {
                const delay =
                  TIMING.headline +
                  index * 6;

                const opacity =
                  interpolate(
                    frame,
                    [
                      delay,
                      delay + 14,
                    ],
                    [0, 1],
                    {
                      extrapolateLeft: "clamp",
                      extrapolateRight: "clamp",
                    }
                  );

                const y =
                  interpolate(
                    spring({
                      frame:
                        frame - delay,

                      fps,

                      config: {
                        damping: 20,
                        stiffness: 120,
                      },
                    }),
                    [0, 1],
                    [20, 0]
                  );

                return (
                  <span
                    key={`${word}-${index}`}
                    style={{
                      display: "inline-block",

                      marginRight: 7,
                      marginBottom: 2,

                      fontSize:
                        Math.max(
                          24,
                          Math.round(
                            width * 0.026
                          )
                        ),

                      fontWeight: 850,
                      lineHeight: 1.05,

                      letterSpacing:
                        "-0.035em",

                      color:
                        index === 0
                          ? accent
                          : textColor,

                      opacity,

                      transform:
                        `translateY(${y}px)`,
                    }}
                  >
                    {word}
                  </span>
                );
              }
            )}
          </div>

          {/* PRICE */}

          {price && (
            <div
              style={{
                opacity: priceOpacity,

                transform:
                  `scale(${interpolate(
                    priceProgress,
                    [0, 1],
                    [0.6, 1]
                  )})`,

                transformOrigin:
                  "left center",

                marginBottom: 7,
              }}
            >
              <span
                style={{
                  fontSize:
                    Math.max(
                      27,
                      Math.round(
                        width * 0.030
                      )
                    ),

                  fontWeight: 900,

                  letterSpacing:
                    "-0.045em",

                  color: accent,
                }}
              >
                {price}
              </span>
            </div>
          )}

          {/* SUBTEXT */}

          {subtext && (
            <div
              style={{
                fontSize:
                  Math.max(
                    11,
                    Math.round(
                      width * 0.011
                    )
                  ),

                lineHeight: 1.45,

                color: textColor,

                opacity:
                  subOpacity * 0.72,

                transform:
                  `translateY(${subY}px)`,

                maxWidth: "88%",

                marginBottom: 12,
              }}
            >
              {subtext}
            </div>
          )}

          {/* FEATURES */}

          {hasFeatures && (
            <div
              style={{
                marginBottom: 11,
              }}
            >
              <SectionLabel
                textColor={textColor}
              >
                Features
              </SectionLabel>

              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 5,
                }}
              >
                {safeFeatures.map(
                  (feature, index) => (
                    <BulletRow
                      key={`feature-${index}`}
                      text={feature}
                      index={index}
                      startFrame={
                        featuresStart
                      }
                      gap={
                        TIMING.featureItemGap
                      }
                      accent={accent}
                      textColor={
                        textColor
                      }
                      fontSize={Math.max(
                        12,
                        Math.round(
                          width * 0.014
                        )
                      )}
                    />
                  )
                )}
              </div>
            </div>
          )}

          {/* WHY CHOOSE US */}

          {hasBenefits && (
            <div
              style={{
                marginBottom: 10,
              }}
            >
              <SectionLabel
                textColor={textColor}
              >
                Why Choose Us
              </SectionLabel>

              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 5,
                }}
              >
                {safeBenefits.map(
                  (benefit, index) => (
                    <BulletRow
                      key={`benefit-${index}`}
                      text={benefit}
                      index={index}
                      startFrame={
                        whyChooseStart
                      }
                      gap={
                        TIMING.whyChooseItemGap
                      }
                      accent={accent}
                      textColor={
                        textColor
                      }
                      fontSize={Math.max(
                        12,
                        Math.round(
                          width * 0.014
                        )
                      )}
                    />
                  )
                )}
              </div>
            </div>
          )}

          {/* FLEX SPACE */}

          <div
            style={{
              flex: 1,
            }}
          />

          {/* CTA */}

          {hasCTA && (
            <div
              style={{
                opacity: ctaOpacity,

                transform:
                  `scale(${ctaScale})`,

                transformOrigin:
                  "left center",
              }}
            >
              <div
                style={{
                  display: "inline-flex",

                  flexDirection: "column",

                  gap: 5,
                }}
              >
                <span
                  style={{
                    fontSize: 14 * scale,

                    fontWeight: 800,

                    letterSpacing:
                      "0.045em",

                    color: textColor,

                    textTransform:
                      "uppercase",
                  }}
                >
                  {ctaText}
                </span>

                <div
                  style={{
                    height: 2,

                    width:
                      `${ctaLine}%`,

                    background: accent,

                    borderRadius: 2,
                  }}
                />
              </div>
            </div>
          )}

          {/* FOOTER */}

          {hasFooter && (
            <div
              style={{
                marginTop: 11,

                opacity: footerOpacity,

                transform:
                  `translateY(${footerY}px)`,

                display: "flex",

                alignItems: "center",

                gap: 13,

                flexWrap: "wrap",

                padding: "9px 13px",

                borderRadius: 12,

                border:
                  `1px solid ${textColor}18`,
              }}
            >
              {hasWebsite && (
                <span
                  style={{
                    fontSize: 9 * scale,
                    letterSpacing: "0.07em",
                    color: textColor,
                    opacity: 0.56,
                  }}
                >
                  {website}
                </span>
              )}

              {hasPhone && (
                <span
                  style={{
                    fontSize: 9 * scale,
                    letterSpacing: "0.07em",
                    color: textColor,
                    opacity: 0.56,
                  }}
                >
                  {phone}
                </span>
              )}

              {hasEmail && (
                <span
                  style={{
                    fontSize: 9 * scale,
                    letterSpacing: "0.07em",
                    color: textColor,
                    opacity: 0.56,
                  }}
                >
                  {email}
                </span>
              )}
            </div>
          )}

          {/* LOGO + BADGE */}

          <div
            style={{
              position: "absolute",
              inset: 0,
              pointerEvents: "none",
            }}
          >
            {hasLogo && (
              <Img
                src={resolveAsset(
                  logoImage,
                  MEDIA_ORIGIN
                )}
                style={{
                  position: "absolute",

                  left: "13%",
                  top: "12%",

                  transform:
                    "translate(-50%, -50%)",

                  width: 72 * scale,
                  height: 72 * scale,

                  objectFit: "contain",

                  opacity: 0.96,
                }}
              />
            )}

            {hasBadge && badge && (
              <div
                style={{
                  position: "absolute",

                  left:
                    `${badge.transform.x}%`,

                  top:
                    `${badge.transform.y}%`,

                  transform:
                    `translate(-50%, -50%) ` +
                    `scale(${
                      badge.transform.scale *
                      interpolate(
                        badgeProgress,
                        [0, 1],
                        [0.4, 1]
                      )
                    })`,

                  width: 112 * scale,
                  height: 112 * scale,
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    inset: 0,

                    background:
                      badge.bgColor,

                    clipPath:
                      "polygon(50% 0%, 61% 12%, 75% 2%, 80% 18%, 95% 15%, 92% 32%, 100% 42%, 88% 50%, 100% 58%, 92% 68%, 95% 85%, 80% 82%, 75% 98%, 61% 88%, 50% 100%, 39% 88%, 25% 98%, 20% 82%, 5% 85%, 8% 68%, 0% 58%, 12% 50%, 0% 42%, 8% 32%, 5% 15%, 20% 18%, 25% 2%, 39% 12%)",

                    transform:
                      "rotate(-10deg)",

                    boxShadow:
                      "0 12px 26px rgba(0,0,0,0.35)",
                  }}
                />

                <div
                  style={{
                    position: "absolute",
                    inset: 7,

                    border:
                      `2px dashed ${badge.textColor}50`,

                    clipPath:
                      "polygon(50% 0%, 61% 12%, 75% 2%, 80% 18%, 95% 15%, 92% 32%, 100% 42%, 88% 50%, 100% 58%, 92% 68%, 95% 85%, 80% 82%, 75% 98%, 61% 88%, 50% 100%, 39% 88%, 25% 98%, 20% 82%, 5% 85%, 8% 68%, 0% 58%, 12% 50%, 0% 42%, 8% 32%, 5% 15%, 20% 18%, 25% 2%, 39% 12%)",

                    transform:
                      "rotate(-10deg)",
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

                    gap: 1,

                    padding: "0 8px",
                  }}
                >
                  <div
                    style={{
                      fontWeight: 900,

                      fontSize:
                        22 * scale,

                      lineHeight: 1,

                      letterSpacing:
                        "-0.03em",

                      color:
                        badge.textColor,

                      textAlign: "center",
                    }}
                  >
                    {badge.text}
                  </div>

                  <div
                    style={{
                      fontWeight: 800,

                      fontSize:
                        10 * scale,

                      letterSpacing:
                        "0.11em",

                      color:
                        badge.textColor,

                      opacity: 0.85,

                      textAlign: "center",
                    }}
                  >
                    {badge.subText}
                  </div>
                </div>
              </div>
            )}
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* ================================================================== */}
      {/* OUTRO */}
      {/* ================================================================== */}

      <Sequence from={outroFrom}>
        <AbsoluteFill
          style={{
            background: primary,

            opacity: outroOpacity,

            alignItems: "center",
            justifyContent: "center",

            flexDirection: "column",

            gap: 8,
          }}
        >
          <div
            style={{
              fontSize: 18 * scale,

              fontWeight: 900,

              letterSpacing: "0.2em",

              textTransform: "uppercase",

              color: accent,

              textAlign: "center",
            }}
          >
            {brandName}
          </div>

          {hasWebsite && (
            <div
              style={{
                fontSize: 9 * scale,

                letterSpacing: "0.16em",

                color: textColor,

                opacity: 0.45,

                textAlign: "center",
              }}
            >
              {website}
            </div>
          )}
        </AbsoluteFill>
      </Sequence>
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