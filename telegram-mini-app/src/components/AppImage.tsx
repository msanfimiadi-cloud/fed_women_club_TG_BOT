import { useEffect, useState } from "react";

interface AppImageProps {
  src?: string | null;
  alt?: string;
  className?: string;
  shellClassName?: string;
  placeholderClassName?: string;
  placeholder?: string;
  loading?: "eager" | "lazy";
  fit?: "cover" | "contain";
  onError?: () => void;
}

export function AppImage({
  src,
  alt = "",
  className,
  shellClassName = "",
  placeholderClassName = "image-placeholder",
  placeholder = "Bloom",
  loading = "lazy",
  fit = "cover",
  onError,
}: AppImageProps) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);
  const safeSrc = typeof src === "string" && src.trim() ? src : "";

  useEffect(() => {
    setIsLoaded(false);
    setHasError(false);
  }, [safeSrc]);

  if (!safeSrc || hasError) {
    return (
      <span className={placeholderClassName} aria-label="Изображение скоро появится">
        <span>{placeholder}</span>
      </span>
    );
  }

  return (
    <span className={["image-shell", isLoaded ? "image-shell--loaded" : "", `image-shell--${fit}`, shellClassName].filter(Boolean).join(" ")}>
      <span className="image-shell__skeleton" aria-hidden="true" />
      <span className="image-shell__overlay" aria-hidden="true" />
      <img
        className={className}
        src={safeSrc}
        alt={alt}
        loading={loading}
        decoding="async"
        onLoad={() => setIsLoaded(true)}
        onError={() => {
          setHasError(true);
          onError?.();
        }}
      />
    </span>
  );
}
