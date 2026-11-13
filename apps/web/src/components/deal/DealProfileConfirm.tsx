"use client";

import { useState } from "react";
import { confirmDealProfileRequest, publishDatabookRequest, type DealProfile } from "@/lib/api";

const LABELS: Record<string, string> = {
  country: "Country",
  currency: "Currency",
  sector: "Sector",
  business_model: "Business model",
  deal_type: "Deal type",
};

function fieldValue(profile: DealProfile, key: string): string {
  const raw = profile.fields[key]?.value;
  return typeof raw === "string" ? raw : "";
}

function policyValue(profile: DealProfile, key: string): string {
  const raw = profile.fields.ebitda_policy?.value;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return "";
  const value = raw[key];
  if (typeof value === "boolean") return value ? "yes" : "no";
  return typeof value === "string" ? value : "";
}

function monthInput(value: string): string {
  return /^\d{4}-\d{2}/.test(value) ? value.slice(0, 7) : "";
}

export function DealProfileConfirm({
  dealId,
  accessToken,
  profile,
  onConfirmed,
  onError,
  onCancel,
}: {
  dealId: string;
  accessToken: string;
  profile: DealProfile;
  onConfirmed: (profile: DealProfile) => void;
  onError: (message: string | null) => void;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>(() => {
    const next: Record<string, string> = {};
    for (const key of Object.keys(LABELS)) {
      next[key] = fieldValue(profile, key);
    }
    const entities = profile.fields.legal_entities?.value;
    next.legal_entities = Array.isArray(entities) ? entities.join(", ") : "";
    next.fiscal_year_end = fieldValue(profile, "fiscal_year_end");
    next.latest_actual_month = monthInput(fieldValue(profile, "latest_actual_month"));
    next.sector_pack = fieldValue(profile, "sector_pack");
    next.include_other_operating_income = policyValue(profile, "include_other_operating_income");
    next.rent_basis = policyValue(profile, "rent_basis");
    next.bad_debt_in_ebitda = policyValue(profile, "bad_debt_in_ebitda");
    return next;
  });
  const [saving, setSaving] = useState(false);

  async function confirm() {
    setSaving(true);
    onError(null);
    try {
      const entities = draft.legal_entities
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean);
      const policy = {
        include_other_operating_income: draft.include_other_operating_income === "yes",
        rent_basis: draft.rent_basis,
        bad_debt_in_ebitda: draft.bad_debt_in_ebitda === "yes",
      };
      const databookReady = Boolean(
        draft.fiscal_year_end &&
          draft.latest_actual_month &&
          draft.sector_pack &&
          draft.include_other_operating_income &&
          draft.rent_basis &&
          draft.bad_debt_in_ebitda,
      );
      const res = await confirmDealProfileRequest(accessToken, dealId, {
        country: draft.country,
        currency: draft.currency,
        sector: draft.sector,
        business_model: draft.business_model,
        deal_type: draft.deal_type,
        legal_entities: entities,
        fiscal_year_end: draft.fiscal_year_end,
        latest_actual_month: draft.latest_actual_month,
        sector_pack: draft.sector_pack,
        ...(databookReady ? { ebitda_policy: policy } : {}),
      });
      if (databookReady) {
        await publishDatabookRequest(accessToken, dealId);
      }
      onConfirmed(res.data);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not confirm the deal profile");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded-[10px] border border-border-primary bg-white px-5 py-4">
      <h2 className="text-[16px] font-semibold text-text-primary">
        {profile.confirmed ? "Update the deal profile" : "Confirm the deal profile"}
      </h2>
      <p className="mt-1 text-[13px] text-text-secondary">
        {profile.confirmed
          ? "Correct country, currency, sector pack, or EBITDA policy, then save. Saving republishes the databook settings for this deal."
          : "Agents stay off until you confirm the country, currency, sector, business model, deal type, and legal entities read from this deal&apos;s documents. The databook stays unpublished until fiscal year end, the latest actual month, the sector pack, and the EBITDA policy are confirmed too."}
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {Object.entries(LABELS).map(([key, label]) => {
          const confidence = profile.fields[key]?.confidence ?? 0;
          const options = profile.choices[key] ?? [];
          const current = draft[key] ?? "";
          return (
            <label key={key} className="block text-[12px] text-text-secondary">
              {label}
              {confidence ? ` · ${Math.round(confidence * 100)}% from the documents` : " · not found in the documents"}
              <select
                className="mt-1 w-full rounded-lg border border-border-primary bg-white px-2 py-2 text-[13px] text-text-primary"
                value={options.includes(current) ? current : ""}
                onChange={(event) => setDraft((prev) => ({ ...prev, [key]: event.target.value }))}
              >
                <option value="">Select</option>
                {options.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          );
        })}
        <label className="block text-[12px] text-text-secondary sm:col-span-2">
          Legal entities
          <input
            className="mt-1 w-full rounded-lg border border-border-primary px-2 py-2 text-[13px] text-text-primary"
            value={draft.legal_entities}
            onChange={(event) => setDraft((prev) => ({ ...prev, legal_entities: event.target.value }))}
          />
        </label>
        <label className="block text-[12px] text-text-secondary">
          Fiscal year end
          <input
            className="mt-1 w-full rounded-lg border border-border-primary px-2 py-2 text-[13px] text-text-primary"
            placeholder="MM-DD"
            value={draft.fiscal_year_end}
            onChange={(event) => setDraft((prev) => ({ ...prev, fiscal_year_end: event.target.value }))}
          />
        </label>
        <label className="block text-[12px] text-text-secondary">
          Latest actual month
          <input
            type="month"
            className="mt-1 w-full rounded-lg border border-border-primary px-2 py-2 text-[13px] text-text-primary"
            value={draft.latest_actual_month}
            onChange={(event) => setDraft((prev) => ({ ...prev, latest_actual_month: event.target.value }))}
          />
        </label>
        <label className="block text-[12px] text-text-secondary">
          Sector pack
          <select
            className="mt-1 w-full rounded-lg border border-border-primary bg-white px-2 py-2 text-[13px] text-text-primary"
            value={(profile.choices.sector_pack ?? []).includes(draft.sector_pack) ? draft.sector_pack : ""}
            onChange={(event) => setDraft((prev) => ({ ...prev, sector_pack: event.target.value }))}
          >
            <option value="">Select</option>
            {(profile.choices.sector_pack ?? []).map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <div className="block text-[12px] text-text-secondary">
          EBITDA policy
          <label className="mt-1 block">
            Include other operating income
            <select
              className="mt-1 w-full rounded-lg border border-border-primary bg-white px-2 py-2 text-[13px] text-text-primary"
              value={draft.include_other_operating_income}
              onChange={(event) => setDraft((prev) => ({ ...prev, include_other_operating_income: event.target.value }))}
            >
              <option value="">Select</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </label>
          <label className="mt-2 block">
            Rent basis
            <select
              className="mt-1 w-full rounded-lg border border-border-primary bg-white px-2 py-2 text-[13px] text-text-primary"
              value={draft.rent_basis}
              onChange={(event) => setDraft((prev) => ({ ...prev, rent_basis: event.target.value }))}
            >
              <option value="">Select</option>
              <option value="GAAP">GAAP</option>
              <option value="CASH">Cash</option>
            </select>
          </label>
          <label className="mt-2 block">
            Bad debt in EBITDA
            <select
              className="mt-1 w-full rounded-lg border border-border-primary bg-white px-2 py-2 text-[13px] text-text-primary"
              value={draft.bad_debt_in_ebitda}
              onChange={(event) => setDraft((prev) => ({ ...prev, bad_debt_in_ebitda: event.target.value }))}
            >
              <option value="">Select</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </label>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={saving}
          onClick={() => void confirm()}
          className="rounded-lg bg-[#1e3a5f] px-3 py-2 text-[13px] font-medium text-white hover:bg-[#16304f] disabled:opacity-60"
        >
          {saving ? "Saving…" : profile.confirmed ? "Save profile" : "Confirm profile"}
        </button>
        {onCancel ? (
          <button
            type="button"
            disabled={saving}
            onClick={onCancel}
            className="text-[13px] font-medium text-text-secondary underline underline-offset-2 disabled:opacity-60"
          >
            Cancel
          </button>
        ) : null}
      </div>
    </section>
  );
}
