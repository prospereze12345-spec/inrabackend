
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

  // Absolute URL
  if (
    clean.startsWith("http://") ||
    clean.startsWith("https://")
  ) {
    return clean;
  }

  // Remotion generated voice
  if (
    clean.startsWith("voiceovers/") ||
    clean.startsWith("/voiceovers/")
  ) {
    return staticFile(clean.replace(/^\/+/, ""));
  }

  // Remotion music
  if (
    clean.startsWith("music/") ||
    clean.startsWith("/music/")
  ) {
    return staticFile(clean.replace(/^\/+/, ""));
  }

  // Django media
  if (clean.startsWith("/media/")) {
    return `${mediaOrigin}${clean}`;
  }

  if (clean.startsWith("media/")) {
    return `${mediaOrigin}/${clean}`;
  }

  // Unknown relative asset.
  return `${mediaOrigin}/media/${clean.replace(/^\/+/, "")}`;
}

// ============================================================================
// SAFE ARRAY
// ============================================================================

function safeArray(value?: string[]): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => String(item).trim())
    .filter(Boolean)
    .slice(0, 3);
}

// ============================================================================
// ANIMATION HELPERS
// ============================================================================

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
    [28, 0],
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

function scaleIn(
  frame: number,
  start: number
) {
  const progress = spring({
    frame: frame - start,
    fps: 30,
    config: {
      damping: 14,
      stiffness: 150,
      mass: 0.6,
    },
  });

  return {
    opacity: interpolate(
      progress,
      [0, 1],
      [0, 1]
    ),

    transform: `scale(${interpolate(
      progress,
      [0, 1],
      [0.82, 1]
    )})`,
  };
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
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginBottom: 10,
      }}
    >
      <div
        style={{
          width: 18,
          height: 2,
          background: accent,
          borderRadius: 2,
        }}
      />

      <div
        style={{
          fontSize: 10,
          fontWeight: 800,
          letterSpacing: "0.18em",
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
// FEATURE ROW
// ============================================================================

function FeatureRow({
  text,
  index,
  start,
  accent,
  textColor,
  width,
}: {
  text: string;
  index: number;
  start: number;
  accent: string;
  textColor: string;
  width: number;
}) {
  const frame = useCurrentFrame();

  const delay = start + index * 7;

  const progress = spring({
    frame: frame - delay,
    fps: 30,
    config: {
      damping: 18,
      stiffness: 150,
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
    [-30, 0]
  );

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 9,
        opacity,
        transform: `translateX(${x}px)`,
        marginBottom: 6,
      }}
    >
      <div
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: accent,
          boxShadow: `0 0 12px ${accent}66`,
          flexShrink: 0,
        }}
      />

      <div
        style={{
          fontSize: Math.max(
            13,
            Math.round(width * 0.014)
          ),
          color: textColor,
          fontWeight: 650,
          lineHeight: 1.25,
        }}
      >
        {text}
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
}: {
  text: string;
  index: number;
  start: number;
  accent: string;
  textColor: string;
  primary: string;
  width: number;
}) {
  const frame = useCurrentFrame();

  const delay = start + index * 7;

  const progress = spring({
    frame: frame - delay,
    fps: 30,
    config: {
      damping: 16,
      stiffness: 130,
    },
  });

  const opacity = interpolate(
    frame,
    [delay, delay + 15],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  const y = interpolate(
    progress,
    [0, 1],
    [18, 0]
  );

  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        padding: "9px 10px",
        borderRadius: 10,
        border: `1px solid ${textColor}14`,
        background: `${textColor}07`,
        opacity,
        transform: `translateY(${y}px)`,
        boxShadow: `0 10px 30px ${primary}55`,
      }}
    >
      <div
        style={{
          width: 5,
          height: 5,
          borderRadius: "50%",
          background: accent,
          marginBottom: 6,
        }}
      />

      <div
        style={{
          fontSize: Math.max(
            10,
            Math.round(width * 0.011)
          ),
          lineHeight: 1.25,
          color: textColor,
          opacity: 0.82,
          fontWeight: 650,
        }}
      >
        {text}
      </div>
    </div>
  );
}

// ============================================================================
// MAIN PROMO VIDEO
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

  const resolvedProductImage =
    resolveAsset(
      productImage,
      MEDIA_ORIGIN
    );

  const resolvedVoiceover =
    resolveAsset(
      voiceoverUrl,
      MEDIA_ORIGIN
    );

  const resolvedMusic =
    resolveAsset(
      musicUrl,
      MEDIA_ORIGIN
    );

  // ==========================================================================
  // CONTENT
  // ==========================================================================

  const safeFeatures =
    safeArray(features);

  const safeBenefits =
    safeArray(whyChooseUs);

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
  // COLORS
  // ==========================================================================

  const primary =
    colors?.primary || "#0a0a0a";

  const secondary =
    colors?.secondary || "#ffffff";

  const accent =
    colors?.accent || "#c9a84c";

  // ==========================================================================
  // SCALE
  // ==========================================================================

  const scale = width / 1080;

  const side = Math.round(
    width * 0.075
  );

  // ==========================================================================
  // TIMELINE
  // ==========================================================================

  /*
   * The composition intentionally reveals content progressively.
   *
   * 0 - 24       Brand reveal
   * 18 - 100     Product entrance
   * 75 - 150     Headline
   * 125          Price
   * 145          Description
   * 190          Features
   * 260          Benefits
   * 335          CTA
   * 370          Footer
   * 405          Outro
   */

  const brandStart = 0;
  const productStart = 18;
  const headlineStart = 72;
  const priceStart = 124;
  const subtextStart = 146;
  const featuresStart = 194;
  const benefitsStart = 258;
  const ctaStart = 326;
  const footerStart = 366;
  const outroStart = Math.max(
    410,
    durationInFrames - 42
  );

  // ==========================================================================
  // BACKGROUND ANIMATION
  // ==========================================================================

  const glowProgress = interpolate(
    frame,
    [0, durationInFrames],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  const glowScale = interpolate(
    glowProgress,
    [0, 1],
    [1, 1.15]
  );

  // ==========================================================================
  // BRAND INTRO
  // ==========================================================================

  const brandOpacity = interpolate(
    frame,
    [
      brandStart,
      brandStart + 8,
      22,
    ],
    [0, 1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  const brandScale = interpolate(
    frame,
    [0, 18],
    [0.75, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  // ==========================================================================
  // PRODUCT
  // ==========================================================================

  const productProgress = spring({
    frame: frame - productStart,
    fps,
    config: {
      damping: 17,
      stiffness: 100,
      mass: 0.8,
    },
  });

  const productOpacity = interpolate(
    frame,
    [
      productStart,
      productStart + 18,
    ],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  const productY = interpolate(
    productProgress,
    [0, 1],
    [90, 0]
  );

  const productScale = interpolate(
    productProgress,
    [0, 1],
    [0.72, 1]
  );

  const productElapsed =
    Math.max(
      0,
      frame - productStart
    );

  const productBob =
    Math.sin(
      productElapsed / 17
    ) * 3;

  const productRotate =
    Math.sin(
      productElapsed / 40
    ) * 0.7;

  // Slow premium camera movement
  const cameraProgress =
    interpolate(
      frame,
      [
        productStart,
        durationInFrames,
      ],
      [0, 1],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }
    );

  const cameraScale =
    interpolate(
      cameraProgress,
      [0, 1],
      [1, 1.075]
    );

  // ==========================================================================
  // HEADLINE
  // ==========================================================================

  const headlineWords =
    String(headline || "")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 8);

  // ==========================================================================
  // PRICE
  // ==========================================================================

  const priceProgress =
    spring({
      frame: frame - priceStart,
      fps,
      config: {
        damping: 12,
        stiffness: 190,
        mass: 0.5,
      },
    });

  const priceOpacity =
    interpolate(
      frame,
      [
        priceStart,
        priceStart + 15,
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

  const subtextStyle =
    fadeUp(
      frame,
      subtextStart,
      18
    );

  // ==========================================================================
  // CTA
  // ==========================================================================

  const ctaProgress = hasCTA
    ? spring({
        frame: frame - ctaStart,
        fps,
        config: {
          damping: 12,
          stiffness: 180,
          mass: 0.5,
        },
      })
    : 0;

  const ctaOpacity = hasCTA
    ? interpolate(
        frame,
        [
          ctaStart,
          ctaStart + 15,
        ],
        [0, 1],
        {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        }
      )
    : 0;

  const ctaScale = hasCTA
    ? interpolate(
        ctaProgress,
        [0, 1],
        [0.85, 1]
      )
    : 1;

  const ctaLine =
    hasCTA
      ? interpolate(
          frame,
          [
            ctaStart + 8,
            ctaStart + 28,
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

  const footerStyle =
    fadeUp(
      frame,
      footerStart,
      18
    );

  // ==========================================================================
  // BADGE
  // ==========================================================================

  const badgeProgress =
    spring({
      frame:
        frame -
        (productStart + 22),
      fps,
      config: {
        damping: 10,
        stiffness: 210,
        mass: 0.5,
      },
    });

  const badgeScale =
    badge
      ? badge.transform.scale *
        interpolate(
          badgeProgress,
          [0, 1],
          [0.5, 1]
        )
      : 1;

  // ==========================================================================
  // OUTRO
  // ==========================================================================

  const outroOpacity =
    interpolate(
      frame,
      [
        outroStart,
        outroStart + 15,
      ],
      [0, 1],
      {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }
    );

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

      {resolvedVoiceover && (
        <Audio
          src={resolvedVoiceover}
          volume={1}
        />
      )}

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
                  outroStart - 15
                ),
                outroStart + 10,
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

      {/* ================================================================== */}
      {/* CINEMATIC BACKGROUND */}
      {/* ================================================================== */}

      <AbsoluteFill
        style={{
          pointerEvents: "none",
        }}
      >
        {/* Top-right glow */}
        <div
          style={{
            position: "absolute",
            width: 700 * scale,
            height: 700 * scale,
            borderRadius: "50%",
            right: -280 * scale,
            top: -260 * scale,
            background:
              `radial-gradient(circle, ${accent}22 0%, ${accent}08 32%, transparent 72%)`,
            transform:
              `scale(${glowScale})`,
          }}
        />

        {/* Bottom-left glow */}
        <div
          style={{
            position: "absolute",
            width: 550 * scale,
            height: 550 * scale,
            borderRadius: "50%",
            left: -260 * scale,
            bottom: -250 * scale,
            background:
              `radial-gradient(circle, ${accent}14 0%, transparent 72%)`,
          }}
        />

        {/* Cinematic vertical light */}
        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: "50%",
            width: 1,
            background:
              `linear-gradient(to bottom, transparent, ${accent}12, transparent)`,
            opacity: 0.8,
          }}
        />
      </AbsoluteFill>

      {/* ================================================================== */}
      {/* BRAND INTRO */}
      {/* ================================================================== */}

      <AbsoluteFill
        style={{
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
          opacity: brandOpacity,
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 10,
            transform:
              `scale(${brandScale})`,
          }}
        >
          <div
            style={{
              fontSize: 14 * scale,
              fontWeight: 850,
              letterSpacing: "0.32em",
              textTransform: "uppercase",
              color: secondary,
            }}
          >
            {brandName}
          </div>

          <div
            style={{
              width: 55 * scale,
              height: 2,
              background: accent,
              boxShadow:
                `0 0 18px ${accent}77`,
            }}
          />
        </div>
      </AbsoluteFill>

      {/* ================================================================== */}
      {/* MAIN CONTENT */}
      {/* ================================================================== */}

      <AbsoluteFill
        style={{
          padding:
            `${Math.round(height * 0.045)}px ${side}px ${Math.round(
              height * 0.035
            )}px`,
        }}
      >
        {/* ================================================================= */}
        {/* TOP BRAND */}
        {/* ================================================================= */}

        <div
          style={{
            position: "absolute",
            top: Math.round(height * 0.045),
            left: side,
            right: side,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            zIndex: 10,
          }}
        >
          {brandName && (
            <div
              style={{
                fontSize: 10 * scale,
                fontWeight: 800,
                letterSpacing: "0.2em",
                textTransform: "uppercase",
                color: secondary,
                opacity: 0.5,
              }}
            >
              {brandName}
            </div>
          )}

          {hasLogo && (
            <Img
              src={resolveAsset(
                logoImage,
                MEDIA_ORIGIN
              )}
              style={{
                width: 54 * scale,
                height: 54 * scale,
                objectFit: "contain",
                opacity: 0.95,
              }}
            />
          )}
        </div>

        {/* ================================================================= */}
        {/* PRODUCT ZONE */}
        {/* ================================================================= */}

        <div
          style={{
            position: "absolute",
            top: Math.round(height * 0.095),
            left: side,
            right: side,
            height: Math.round(height * 0.32),

            display: "flex",
            alignItems: "center",
            justifyContent: "center",

            opacity: productOpacity,

            transform:
              `translateY(${productY + productBob}px) scale(${productScale}) rotate(${productRotate}deg)`,

            zIndex: 2,
          }}
        >
          {/* Product spotlight */}
          <div
            style={{
              position: "absolute",
              width: "70%",
              height: "85%",
              borderRadius: "50%",
              background:
                `radial-gradient(circle, ${accent}18 0%, transparent 68%)`,
              filter: "blur(18px)",
            }}
          />

          {resolvedProductImage ? (
            <Img
              src={resolvedProductImage}
              style={{
                maxWidth: "72%",
                maxHeight: "100%",
                objectFit: "contain",

                transform:
                  `scale(${cameraScale})`,

                filter:
                  "drop-shadow(0 28px 45px rgba(0,0,0,0.65))",
              }}
            />
          ) : (
            <div
              style={{
                width: 180 * scale,
                height: 180 * scale,
                borderRadius: 30,
                border:
                  `1px solid ${accent}44`,
                background:
                  `${accent}12`,
              }}
            />
          )}
        </div>

        {/* ================================================================= */}
        {/* BADGE */}
        {/* ================================================================= */}

        {hasBadge && badge && (
          <div
            style={{
              position: "absolute",

              right: side * 0.15,
              top: Math.round(height * 0.18),

              width: 105 * scale,
              height: 105 * scale,

              transform:
                `scale(${badgeScale}) rotate(-8deg)`,

              zIndex: 20,
            }}
          >
            <div
              style={{
                position: "absolute",
                inset: 0,
                borderRadius: "50%",
                background: badge.bgColor,
                boxShadow:
                  "0 15px 35px rgba(0,0,0,0.4)",
              }}
            />

            <div
              style={{
                position: "absolute",
                inset: 7,
                border:
                  `1px dashed ${badge.textColor}80`,
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
              }}
            >
              <div
                style={{
                  fontSize: 23 * scale,
                  fontWeight: 950,
                  color: badge.textColor,
                  lineHeight: 1,
                }}
              >
                {badge.text}
              </div>

              <div
                style={{
                  marginTop: 4,
                  fontSize: 9 * scale,
                  fontWeight: 800,
                  letterSpacing: "0.12em",
                  color: badge.textColor,
                  opacity: 0.85,
                }}
              >
                {badge.subText}
              </div>
            </div>
          </div>
        )}

        {/* ================================================================= */}
        {/* HEADLINE ZONE */}
        {/* ================================================================= */}

        <div
          style={{
            position: "absolute",

            top: Math.round(height * 0.405),

            left: side,
            right: side,

            zIndex: 5,
          }}
        >
          <div
            style={{
              maxWidth: "94%",
              lineHeight: 1,
            }}
          >
            {headlineWords.map(
              (word, index) => {
                const delay =
                  headlineStart +
                  index * 5;

                const progress =
                  spring({
                    frame:
                      frame - delay,
                    fps,
                    config: {
                      damping: 20,
                      stiffness: 135,
                    },
                  });

                const opacity =
                  interpolate(
                    frame,
                    [
                      delay,
                      delay + 12,
                    ],
                    [0, 1],
                    {
                      extrapolateLeft:
                        "clamp",
                      extrapolateRight:
                        "clamp",
                    }
                  );

                const y =
                  interpolate(
                    progress,
                    [0, 1],
                    [30, 0]
                  );

                return (
                  <span
                    key={`${word}-${index}`}
                    style={{
                      display:
                        "inline-block",

                      marginRight: 8,
                      marginBottom: 4,

                      fontSize:
                        Math.max(
                          28,
                          Math.round(
                            width * 0.031
                          )
                        ),

                      fontWeight: 950,

                      letterSpacing:
                        "-0.045em",

                      color:
                        index === 0
                          ? accent
                          : secondary,

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
        </div>

        {/* ================================================================= */}
        {/* PRICE */}
        {/* ================================================================= */}

        {price && (
          <div
            style={{
              position: "absolute",

              top: Math.round(height * 0.505),

              left: side,

              opacity: priceOpacity,

              transform:
                `scale(${interpolate(
                  priceProgress,
                  [0, 1],
                  [0.7, 1]
                )})`,

              transformOrigin:
                "left center",

              zIndex: 5,
            }}
          >
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div
                style={{
                  width: 22,
                  height: 2,
                  background: accent,
                }}
              />

              <span
                style={{
                  fontSize:
                    Math.max(
                      24,
                      Math.round(
                        width * 0.028
                      )
                    ),

                  fontWeight: 950,

                  letterSpacing:
                    "-0.04em",

                  color: accent,
                }}
              >
                {price}
              </span>
            </div>
          </div>
        )}

        {/* ================================================================= */}
        {/* SUBTEXT */}
        {/* ================================================================= */}

        {subtext && (
          <div
            style={{
              position: "absolute",

              top: Math.round(height * 0.555),

              left: side,
              right: side,

              maxWidth: "82%",

              fontSize:
                Math.max(
                  12,
                  Math.round(
                    width * 0.012
                  )
                ),

              lineHeight: 1.45,

              color: secondary,

              opacity:
                (subtextStyle.opacity || 0) *
                0.75,

              transform:
                subtextStyle.transform,

              zIndex: 5,
            }}
          >
            {subtext}
          </div>
        )}

        {/* ================================================================= */}
        {/* FEATURES */}
        {/* ================================================================= */}

        {hasFeatures && (
          <div
            style={{
              position: "absolute",

              top: Math.round(height * 0.635),

              left: side,
              right: side,

              zIndex: 5,
            }}
          >
            <SectionTitle
              accent={accent}
              color={secondary}
            >
              Features
            </SectionTitle>

            <div>
              {safeFeatures.map(
                (feature, index) => (
                  <FeatureRow
                    key={`feature-${index}`}
                    text={feature}
                    index={index}
                    start={featuresStart}
                    accent={accent}
                    textColor={secondary}
                    width={width}
                  />
                )
              )}
            </div>
          </div>
        )}

        {/* ================================================================= */}
        {/* WHY CHOOSE US */}
        {/* ================================================================= */}

        {hasBenefits && (
          <div
            style={{
              position: "absolute",

              top: Math.round(height * 0.735),

              left: side,
              right: side,

              zIndex: 5,
            }}
          >
            <SectionTitle
              accent={accent}
              color={secondary}
            >
              Why Choose Us
            </SectionTitle>

            <div
              style={{
                display: "flex",
                gap: 8,
              }}
            >
              {safeBenefits.map(
                (benefit, index) => (
                  <BenefitCard
                    key={`benefit-${index}`}
                    text={benefit}
                    index={index}
                    start={benefitsStart}
                    accent={accent}
                    textColor={secondary}
                    primary={primary}
                    width={width}
                  />
                )
              )}
            </div>
          </div>
        )}

        {/* ================================================================= */}
        {/* CTA */}
        {/* ================================================================= */}

        {hasCTA && (
          <div
            style={{
              position: "absolute",

              left: side,
              right: side,

              top: Math.round(height * 0.835),

              opacity: ctaOpacity,

              transform:
                `scale(${ctaScale})`,

              transformOrigin:
                "left center",

              zIndex: 8,
            }}
          >
            <div
              style={{
                display: "inline-flex",
                flexDirection: "column",
                gap: 7,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 9,
                }}
              >
                <span
                  style={{
                    fontSize:
                      14 * scale,

                    fontWeight: 900,

                    letterSpacing:
                      "0.08em",

                    textTransform:
                      "uppercase",

                    color: secondary,
                  }}
                >
                  {ctaText}
                </span>

                <span
                  style={{
                    fontSize: 16 * scale,
                    color: accent,
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
                  boxShadow:
                    `0 0 14px ${accent}66`,
                }}
              />
            </div>
          </div>
        )}

        {/* ================================================================= */}
        {/* FOOTER */}
        {/* ================================================================= */}

        {hasFooter && (
          <div
            style={{
              position: "absolute",

              left: side,
              right: side,

              bottom: Math.round(
                height * 0.035
              ),

              display: "flex",
              alignItems: "center",

              gap: 14,

              padding:
                "9px 12px",

              borderRadius: 10,

              border:
                `1px solid ${secondary}16`,

              background:
                `${secondary}05`,

              opacity:
                footerStyle.opacity,

              transform:
                footerStyle.transform,

              zIndex: 8,
            }}
          >
            {hasWebsite && (
              <span
                style={{
                  fontSize: 9 * scale,
                  color: secondary,
                  opacity: 0.6,
                  letterSpacing:
                    "0.05em",
                  whiteSpace:
                    "nowrap",
                }}
              >
                {website}
              </span>
            )}

            {hasPhone && (
              <>
                <span
                  style={{
                    width: 3,
                    height: 3,
                    borderRadius: "50%",
                    background: accent,
                  }}
                />

                <span
                  style={{
                    fontSize: 9 * scale,
                    color: secondary,
                    opacity: 0.55,
                    whiteSpace:
                      "nowrap",
                  }}
                >
                  {phone}
                </span>
              </>
            )}

            {hasEmail && (
              <>
                <span
                  style={{
                    width: 3,
                    height: 3,
                    borderRadius: "50%",
                    background: accent,
                  }}
                />

                <span
                  style={{
                    fontSize: 9 * scale,
                    color: secondary,
                    opacity: 0.55,
                    whiteSpace:
                      "nowrap",
                  }}
                >
                  {email}
                </span>
              </>
            )}
          </div>
        )}
      </AbsoluteFill>

      {/* ================================================================== */}
      {/* OUTRO */}
      {/* ================================================================== */}

      <AbsoluteFill
        style={{
          background: primary,
          opacity: outroOpacity,
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
          zIndex: 100,
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div
            style={{
              width: 45,
              height: 2,
              background: accent,
              marginBottom: 4,
            }}
          />

          <div
            style={{
              fontSize: 20 * scale,
              fontWeight: 950,
              letterSpacing: "0.18em",
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
                color: secondary,
                opacity: 0.5,
                textAlign: "center",
              }}
            >
              {website}
            </div>
          )}
        </div>
      </AbsoluteFill>
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
