"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import type { SectorOption } from "@/lib/deal-types";

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

type Props = {
  open: boolean;
  sectors: SectorOption[];
  onClose: () => void;
  onSubmit: (input: {
    name: string;
    slug: string;
    description: string;
    tags: string;
    industry: string;
  }) => Promise<void>;
};

export function CreateDealModal({ open, sectors, onClose, onSubmit }: Props) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [industry, setIndustry] = useState("generic");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const options = useMemo(
    () =>
      sectors.length
        ? sectors
        : [{ id: "generic", label: "Other / Generic" }],
    [sectors],
  );

  useEffect(() => {
    if (!open) return;
    setName("");
    setSlug("");
    setSlugTouched(false);
    setDescription("");
    setTags("");
    setIndustry(options[0]?.id || "generic");
    setError(null);
    setPending(false);
  }, [open, options]);

  useEffect(() => {
    if (!slugTouched) setSlug(slugify(name));
  }, [name, slugTouched]);

  if (!open) return null;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await onSubmit({
        name: name.trim(),
        slug: slug.trim() || slugify(name),
        description,
        tags,
        industry,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create dealroom");
    } finally {
      setPending(false);
    }
  }

  const field =
    "mt-1 w-full rounded-[var(--radius-md)] border border-border-secondary bg-white px-3 py-2 text-[13px] text-text-primary outline-none focus:border-[#1e3a5f]";
  const label = "text-[12px] font-medium text-text-secondary";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-modal-title"
        className="w-full max-w-lg rounded-[12px] border border-border-primary bg-background-secondary"
      >
        <div className="flex items-center justify-between border-b border-border-primary px-5 py-4">
          <h2 id="create-modal-title" className="text-[15px] font-semibold text-text-primary">
            Create investment portfolio
          </h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="rounded-md p-1 text-text-secondary hover:bg-background-tertiary"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 6l12 12M18 6 6 18" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3.5 px-5 py-4">
          <label className="block">
            <span className={label}>Portfolio name</span>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Growth Equity Fund IV"
              className={field}
            />
          </label>

          <label className="block">
            <span className={label}>Slug (auto-generated)</span>
            <input
              value={slug}
              onChange={(e) => {
                setSlugTouched(true);
                setSlug(e.target.value);
              }}
              placeholder="growth-equity-fund-iv"
              className={field}
            />
          </label>

          <label className="block">
            <span className={label}>Description</span>
            <textarea
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Primary growth equity and late-stage software portfolio details..."
              className={field}
            />
          </label>

          <label className="block">
            <span className={label}>Tags (comma separated)</span>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="e.g. Tech, Late-Stage, Software"
              className={field}
            />
          </label>

          <label className="block">
            <span className={label}>Industry</span>
            <select
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className={field}
            >
              {options.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>

          {error ? <p className="text-[12px] text-text-danger">{error}</p> : null}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-[var(--radius-md)] border border-border-secondary px-3 py-2 text-[13px] text-text-secondary hover:bg-background-tertiary"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={pending}
              className="rounded-[var(--radius-md)] bg-[#1e3a5f] px-3 py-2 text-[13px] font-medium text-white disabled:opacity-60 hover:bg-[#16304f]"
            >
              {pending ? "Creating…" : "Create workspace"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
