import { BrandMark } from "@/components/brand/BrandMark";

export function AuthHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="mb-6 space-y-2 text-center">
      <div className="mb-4 flex items-center justify-center">
        <BrandMark height={36} />
      </div>
      <h1 className="text-[22px] font-semibold tracking-tight text-text-primary">
        {title}
      </h1>
      {subtitle ? (
        <p className="text-[13px] text-text-secondary">{subtitle}</p>
      ) : null}
    </div>
  );
}
