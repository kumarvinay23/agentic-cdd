import { product } from "@/lib/config";

export function AuthHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="mb-6 space-y-2 text-center">
      <div className="mb-4 flex items-center justify-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-md bg-accent text-white">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden>
            <path d="M13 2 4.5 13.5h6L11 22l8.5-11.5h-6L13 2z" />
          </svg>
        </span>
        <span className="text-[15px] font-semibold tracking-tight text-text-primary">
          {product.name}
        </span>
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
