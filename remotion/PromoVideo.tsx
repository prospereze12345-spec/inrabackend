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
} from "remotion";

type PromoColors = {
  primary: string;
  secondary: string;
  accent: string;
};

// ─── Extended props to include logo and badge overlays ───────────────────
type DiscountBadge = {
  visible: boolean;
  text: string;
  subText: string;
  textColor: string;
  bgColor: string;
  transform: { x: number; y: number; scale: number };
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
  // New optional overlay props
  logoImage?: string | null;
  badge?: DiscountBadge | null;
};

const DEFAULT_PROPS: PromoVideoProps = {
  headline: "Timeless Elegance Guaranteed",
  subtext: "Elevate your space with our Classic Analog Wall Clock.",
  ctaText: "DM to order now",
  price: "From ₦4,500",
  brandName: "Premium Brand",
  website: "your-store.com",
  productImage: "",
  colors: { primary: "#0a0a0a", secondary: "#ffffff", accent: "#c9a84c" },
  logoImage: null,
  badge: null,
};

// ──────────────────────────────────────────────────────────────────────────
// Composition — same as before, plus logo & badge overlays
// ──────────────────────────────────────────────────────────────────────────

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
}: PromoVideoProps) {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Resolve product image URL (unchanged)
  const MEDIA_ORIGIN =
    process.env.REMOTION_MEDIA_ORIGIN || "http://127.0.0.1:8000";
  const resolvedProductImage = (() => {
    if (!productImage) return "";
    if (
      productImage.startsWith("http://") ||
      productImage.startsWith("https://")
    ) {
      return productImage;
    }
    if (productImage.startsWith("/media/")) {
      return `${MEDIA_ORIGIN}${productImage}`;
    }
    return `${MEDIA_ORIGIN}/media/${productImage.replace(/^\/+/, "")}`;
  })();

  // ─── Animation helpers ────────────────────────────────────────────────
  const sp = (f: number, delay = 0, mass = 1) =>
    spring({
      frame: f - delay,
      fps,
      config: { damping: 18, stiffness: 80, mass },
    });

  // Brand intro
  const brandScale = interpolate(frame, [0, 20], [0.6, 1], {
    extrapolateRight: "clamp",
  });
  const brandOpacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Product entrance
  const productY = interpolate(sp(frame, 15), [0, 1], [60, 0]);
  const productS = interpolate(sp(frame, 15), [0, 1], [0.85, 1]);
  const productO = interpolate(frame, [15, 45], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Ken Burns
  const kbScale = interpolate(
    frame,
    [15, durationInFrames],
    [1, 1.15],
    { extrapolateRight: "clamp" }
  );
  const kbX = interpolate(frame, [15, durationInFrames], [0, -14], {
    extrapolateRight: "clamp",
  });
  const kbY = interpolate(frame, [15, durationInFrames], [0, 8], {
    extrapolateRight: "clamp",
  });

  // Headline word‑by‑word
  const words = (headline || "").split(" ").filter(Boolean).slice(0, 6);

  // Price badge pop
  const priceS = spring({
    frame: frame - 90,
    fps,
    config: { damping: 12, stiffness: 200, mass: 0.5 },
  });
  const priceO = interpolate(frame, [90, 105], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Subtext slide
  const subO = interpolate(frame, [110, 130], [0, 1], {
    extrapolateRight: "clamp",
  });
  const subY = interpolate(sp(frame, 110), [0, 1], [20, 0]);

  // CTA reveal
  const ctaO = interpolate(frame, [145, 165], [0, 1], {
    extrapolateRight: "clamp",
  });
  const ctaW = interpolate(frame, [165, 195], [0, 100], {
    extrapolateRight: "clamp",
  });

  // Outro fade
  const outroO = interpolate(
    frame,
    [durationInFrames - 20, durationInFrames - 5],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const accent = colors?.accent || "#c9a84c";
  const primary = colors?.primary || "#0a0a0a";
  const textCol = colors?.secondary || "#ffffff";

  // ─── Overlay animations ──────────────────────────────────────────────
  // Logo and badge fade in after the brand intro, stay visible until outro
  const overlayOpacity = interpolate(
    frame,
    [20, 40, durationInFrames - 20, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // ─── Render ──────────────────────────────────────────────────────────
  return (
    <AbsoluteFill
      style={{
        background: primary,
        fontFamily: "-apple-system,'Helvetica Neue',sans-serif",
        overflow: "hidden",
      }}
    >
      {/* Ambient background circles (unchanged) */}
      <AbsoluteFill style={{ pointerEvents: "none" }}>
        <div
          style={{
            position: "absolute",
            width: 600,
            height: 600,
            borderRadius: "50%",
            background: `radial-gradient(circle, ${accent}18 0%, transparent 70%)`,
            top: -200,
            right: -150,
            transform: `scale(${interpolate(frame, [0, durationInFrames], [1, 1.15])})`,
          }}
        />
        <div
          style={{
            position: "absolute",
            width: 400,
            height: 400,
            borderRadius: "50%",
            background: `radial-gradient(circle, ${accent}0d 0%, transparent 70%)`,
            bottom: -100,
            left: -100,
          }}
        />
      </AbsoluteFill>

      {/* Brand intro (frames 0-25) */}
      <Sequence from={0} durationInFrames={25}>
        <AbsoluteFill
          style={{
            alignItems: "center",
            justifyContent: "center",
            flexDirection: "column",
            gap: 8,
            opacity: frame > 18 ? interpolate(frame, [18, 25], [1, 0]) : 1,
          }}
        >
          <div
            style={{
              fontSize: 13,
              fontWeight: 800,
              letterSpacing: "0.3em",
              textTransform: "uppercase",
              color: textCol,
              opacity: brandOpacity,
              transform: `scale(${brandScale})`,
            }}
          >
            {brandName}
          </div>
          <div
            style={{
              width: interpolate(frame, [0, 20], [0, 40]),
              height: 1,
              background: accent,
            }}
          />
        </AbsoluteFill>
      </Sequence>

      {/* Main content (frames 15 → end) */}
      <Sequence from={15} durationInFrames={Math.max(durationInFrames - 35, 1)}>
        <AbsoluteFill style={{ flexDirection: "column", padding: "8% 9%" }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: textCol,
              opacity: 0.4,
              marginBottom: 16,
            }}
          >
            {brandName}
          </div>

          {/* Product image (unchanged) */}
          <div
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: productO,
              overflow: "hidden",
              transform: `translateY(${productY}px) scale(${productS})`,
            }}
          >
            {productImage ? (
              <img
                src={resolvedProductImage}
                alt="Product"
                crossOrigin="anonymous"
                onError={(e) => {
                  console.error("Failed to load image:", resolvedProductImage);
                  console.error(e);
                }}
                style={{
                  maxWidth: "70%",
                  maxHeight: "55%",
                  objectFit: "contain",
                  filter: "drop-shadow(0 24px 40px rgba(0,0,0,0.6))",
                  transform: `scale(${kbScale}) translate(${kbX}px, ${kbY}px)`,
                }}
              />
            ) : (
              <div
                style={{
                  width: 120,
                  height: 120,
                  borderRadius: 16,
                  background: `${accent}22`,
                  border: `1px solid ${accent}44`,
                  transform: `scale(${kbScale})`,
                }}
              />
            )}
          </div>

          {/* Headline, price, subtext, CTA (unchanged) */}
          <div style={{ marginTop: 16, marginBottom: 10 }}>
            {words.map((word, i) => {
              const delay = 40 + i * 7;
              const wO = interpolate(frame, [delay, delay + 15], [0, 1], {
                extrapolateRight: "clamp",
              });
              const wY = interpolate(
                spring({
                  frame: frame - delay,
                  fps,
                  config: { damping: 20, stiffness: 120 },
                }),
                [0, 1],
                [20, 0]
              );
              return (
                <span
                  key={i}
                  style={{
                    display: "inline-block",
                    marginRight: 8,
                    fontSize: 28,
                    fontWeight: 800,
                    letterSpacing: "-0.02em",
                    color: i === 0 ? accent : textCol,
                    opacity: wO,
                    transform: `translateY(${wY}px)`,
                  }}
                >
                  {word}
                </span>
              );
            })}
          </div>

          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              opacity: priceO,
              transform: `scale(${interpolate(priceS, [0, 1], [0.6, 1])})`,
              transformOrigin: "left center",
              marginBottom: 10,
            }}
          >
            <span
              style={{
                fontSize: 36,
                fontWeight: 900,
                letterSpacing: "-0.04em",
                color: accent,
              }}
            >
              {price}
            </span>
          </div>

          <div
            style={{
              fontSize: 12,
              lineHeight: 1.55,
              color: textCol,
              opacity: subO * 0.6,
              transform: `translateY(${subY}px)`,
              maxWidth: "80%",
              marginBottom: 20,
            }}
          >
            {subtext}
          </div>

          <div style={{ opacity: ctaO }}>
            <div style={{ display: "inline-flex", flexDirection: "column", gap: 4 }}>
              <span
                style={{
                  fontSize: 14,
                  fontWeight: 700,
                  letterSpacing: "0.04em",
                  color: textCol,
                  textTransform: "uppercase",
                }}
              >
                {ctaText}
              </span>
              <div
                style={{
                  height: 2,
                  background: accent,
                  width: `${ctaW}%`,
                  borderRadius: 1,
                }}
              />
            </div>
          </div>

          <div
            style={{
              fontSize: 9,
              letterSpacing: "0.14em",
              color: textCol,
              opacity: ctaO * 0.3,
              marginTop: 6,
              textTransform: "lowercase",
            }}
          >
            {website}
          </div>

          {/* ─── OVERLAYS: Logo & Badge ──────────────────────────────────── */}
          {/* They are positioned on top of the content, using the same
              percentage-based x,y and scale from the editor. The opacity
              fades in/out with the rest of the composition. */}
          <div style={{ opacity: overlayOpacity }}>
            {/* Logo */}
            {logoImage && (
              <Img
                src={logoImage}
                style={{
                  position: "absolute",
                  left: `${15}%`, // Default position (can be overridden by props)
                  top: `${15}%`,
                  transform: "translate(-50%, -50%) scale(1)",
                  width: 80,
                  height: 80,
                  objectFit: "contain",
                  // In a full implementation, you would read the transform
                  // from the logoOverlay prop. For now, we use static values.
                  // To make it dynamic, pass the transform via props.
                }}
              />
            )}

            {/* Discount Badge */}
            {badge && badge.visible && (
              <div
                style={{
                  position: "absolute",
                  left: `${badge.transform.x}%`,
                  top: `${badge.transform.y}%`,
                  transform: `translate(-50%, -50%) scale(${badge.transform.scale})`,
                  width: 116,
                  height: 116,
                }}
              >
                {/* Sunburst background */}
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    background: badge.bgColor,
                    clipPath:
                      "polygon(50% 0%, 61% 12%, 75% 2%, 80% 18%, 95% 15%, 92% 32%, 100% 42%, 88% 50%, 100% 58%, 92% 68%, 95% 85%, 80% 82%, 75% 98%, 61% 88%, 50% 100%, 39% 88%, 25% 98%, 20% 82%, 5% 85%, 8% 68%, 0% 58%, 12% 50%, 0% 42%, 8% 32%, 5% 15%, 20% 18%, 25% 2%, 39% 12%)",
                    transform: "rotate(-10deg)",
                    boxShadow: "0 12px 26px rgba(0,0,0,0.35)",
                  }}
                />
                {/* Inner dashed ring */}
                <div
                  style={{
                    position: "absolute",
                    inset: 7,
                    border: `2px dashed ${badge.textColor}50`,
                    clipPath:
                      "polygon(50% 0%, 61% 12%, 75% 2%, 80% 18%, 95% 15%, 92% 32%, 100% 42%, 88% 50%, 100% 58%, 92% 68%, 95% 85%, 80% 82%, 75% 98%, 61% 88%, 50% 100%, 39% 88%, 25% 98%, 20% 82%, 5% 85%, 8% 68%, 0% 58%, 12% 50%, 0% 42%, 8% 32%, 5% 15%, 20% 18%, 25% 2%, 39% 12%)",
                    transform: "rotate(-10deg)",
                  }}
                />
                {/* Text */}
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
                      fontSize: 24,
                      lineHeight: 1,
                      letterSpacing: "-0.03em",
                      color: badge.textColor,
                      textShadow: "0 1px 2px rgba(0,0,0,.12)",
                    }}
                  >
                    {badge.text}
                  </div>
                  <div
                    style={{
                      fontWeight: 800,
                      fontSize: 12,
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
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* Brand outro (last 20 frames) */}
      <Sequence from={Math.max(durationInFrames - 20, 0)}>
        <AbsoluteFill
          style={{
            background: primary,
            opacity: outroO,
            alignItems: "center",
            justifyContent: "center",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div
            style={{
              fontSize: 18,
              fontWeight: 900,
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: accent,
            }}
          >
            {brandName}
          </div>
          <div
            style={{
              fontSize: 9,
              letterSpacing: "0.16em",
              color: textCol,
              opacity: 0.4,
            }}
          >
            {website}
          </div>
        </AbsoluteFill>
      </Sequence>
    </AbsoluteFill>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Registration (unchanged)
// ──────────────────────────────────────────────────────────────────────────

function RemotionRoot() {
  return (
    <Composition
      id="PromoVideo"
      component={PromoVideo}
      durationInFrames={360}
      fps={30}
      width={1080}
      height={1350}
      defaultProps={DEFAULT_PROPS}
    />
  );
}

registerRoot(RemotionRoot);