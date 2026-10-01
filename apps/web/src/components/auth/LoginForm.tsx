"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { AUTH_ROUTES } from "@/lib/config";
import { ApiError, loginRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";

export function LoginForm() {
  const router = useRouter();
  const { setAuth } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const res = await loginRequest(email, password);
      setAuth(res.data);
      if (!rememberMe) {
        // Still persist for session; rememberMe reserved for longer refresh later
      }
      router.push(AUTH_ROUTES.DASHBOARD);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Invalid credentials. Please try again.";
      setError(message);
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <label
          htmlFor="login-email"
          className="block text-[12px] font-medium text-text-secondary"
        >
          Email address
        </label>
        <input
          id="login-email"
          type="email"
          autoComplete="email"
          required
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-[var(--radius-md)] border border-border-secondary bg-white px-3 py-2 text-[13px] text-text-primary outline-none placeholder:text-text-secondary focus:border-text-info"
        />
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label
            htmlFor="login-password"
            className="block text-[12px] font-medium text-text-secondary"
          >
            Password
          </label>
          <button
            type="button"
            className="text-[11px] text-text-info hover:underline"
          >
            Forgot password?
          </button>
        </div>
        <div className="relative">
          <input
            id="login-password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            required
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-[var(--radius-md)] border border-border-secondary bg-white px-3 py-2 pr-10 text-[13px] text-text-primary outline-none placeholder:text-text-secondary focus:border-text-info"
          />
          <button
            type="button"
            tabIndex={-1}
            aria-label={showPassword ? "Hide password" : "Show password"}
            onClick={() => setShowPassword((v) => !v)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-text-secondary"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
              {showPassword ? (
                <path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.1A9.8 9.8 0 0 1 12 5c5 0 9.3 3.1 11 7-0.5 1.2-1.2 2.3-2.1 3.2M6.1 6.1C4.2 7.4 2.7 9.1 1.9 12c1.7 3.9 6 7 10.1 7 1.4 0 2.8-.3 4-.8" />
              ) : (
                <>
                  <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
                  <circle cx="12" cy="12" r="3" />
                </>
              )}
            </svg>
          </button>
        </div>
      </div>

      <label className="flex items-center gap-2 text-[12px] text-text-secondary">
        <input
          type="checkbox"
          checked={rememberMe}
          onChange={(e) => setRememberMe(e.target.checked)}
          className="h-3.5 w-3.5 rounded border-border-secondary"
        />
        Remember me
      </label>

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
        {pending ? "Signing in…" : "Sign in"}
      </button>

      <p className="pt-1 text-center text-[12px] text-text-secondary">
        No account?{" "}
        <a href={AUTH_ROUTES.REGISTER} className="text-text-info hover:underline">
          Create one
        </a>
      </p>
    </form>
  );
}
