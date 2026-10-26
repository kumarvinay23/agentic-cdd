export function BrandMark({
  height = 28,
  className = "",
}: {
  height?: number;
  className?: string;
}) {
  return (
    <img
      src="/diligenceiq-logo.jpg"
      alt="DiligenceIQ"
      height={height}
      className={`block w-auto ${className}`}
      style={{ height }}
    />
  );
}
