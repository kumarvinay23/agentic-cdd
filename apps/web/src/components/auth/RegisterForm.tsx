"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { AUTH_ROUTES } from "@/lib/config";
import { ApiError, registerRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";

export function RegisterForm() {
  const router = useRouter();
  const { setAuth } = useAuth();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const res = await registerRequest({
        email,
        password,
        firstName,
        lastName,
        organizationName,
      });
      setAuth(res.data);
      router.push(AUTH_ROUTES.DASHBOARD);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setPending(false);
    }
  }

  const fieldClass =
    "w-full rounded-[var(--radius-md)] border border-border-secondary bg-white px-3 py-2 text-[13px] text-text-primary outline-none placeholder:text-text-secondary focus:border-text-info";
  const labelClass = "block text-[12px] font-medium text-text-secondary";

  return (
    <form onSubmit={onSubmit} className="space-y-3.5">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <label htmlFor="reg-first" className={labelClass}>
            First name
          </label>
          <input
            id="reg-first"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            className={fieldClass}
            placeholder="Alex"
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="reg-last" className={labelClass}>
            Last name
          </label>
          <input
            id="reg-last"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            className={fieldClass}
            placeholder="Analyst"
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="reg-org" className={labelClass}>
          Organization
        </label>
        <input
          id="reg-org"
          value={organizationName}
          onChange={(e) => setOrganizationName(e.target.value)}
          className={fieldClass}
          placeholder="Your firm"
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="reg-email" className={labelClass}>
          Email address
        </label>
        <input
          id="reg-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={fieldClass}
          placeholder="you@company.com"
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="reg-password" className={labelClass}>
          Password
        </label>
        <input
          id="reg-password"
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={fieldClass}
          placeholder="At least 8 characters"
        />
      </div>

      {error ? (
        <p className="text-[12px] text-text-danger" role="alert">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={pending}
        className="flex w-full items-center justify-center rounded-[var(--radius-md)] bg-accent px-3 py-2.5 text-[13px] font-medium text-white disabled:opacity-60"
      >
        {pending ? "Creating account…" : "Create account"}
      </button>

      <p className="pt-1 text-center text-[12px] text-text-secondary">
        Already have an account?{" "}
        <a href={AUTH_ROUTES.LOGIN} className="text-text-info hover:underline">
          Sign in
        </a>
      </p>
    </form>
  );
}
