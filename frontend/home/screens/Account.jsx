import React, { useEffect, useRef, useState } from "react";
import {
  GoogleAuthProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  applyActionCode,
  checkActionCode,
  verifyPasswordResetCode,
  confirmPasswordReset,
} from "firebase/auth";
import { auth } from "../../src/firebase";
import { verifyAccountLink } from "../../src/utils/verifyAccountLink";
import { api } from "../api";

const safeNext = (value) =>
  /^(request|visits|payout|team|helping|visit\/[a-f0-9-]{36})$/.test(
    value || "",
  )
    ? value
    : "visits";
const friendly = (error) =>
  ({
    "auth/popup-blocked":
      "Your browser blocked the Google window. Allow popups for CookCredit, then retry.",
    "auth/popup-closed-by-user":
      "Google sign-in was closed. Try again, or use email below.",
    "auth/operation-not-supported-in-this-environment":
      "Open this page in Chrome, Safari or Edge to sign in with Google.",
    "auth/invalid-credential":
      "The email or password did not match. Check them, or reset your password.",
    "auth/email-already-in-use":
      "This email already has a CookCredit account. Choose Sign in or reset your password.",
    "auth/too-many-requests": "Please wait a few minutes before trying again.",
    "auth/weak-password":
      "Choose a stronger password. Use at least 10 characters.",
    "auth/expired-action-code": "This link has expired. Request another email.",
    "auth/invalid-action-code":
      "This link has already been used or is invalid. Try signing in, or request another email.",
  })[error.code] ||
  (error.code?.startsWith("auth/")
    ? "Sign-in could not finish. Please retry or contact customer service."
    : error.message);

export default function Account({ user, refresh, next }) {
  const [mode, setMode] = useState("signin"),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0),
    [resetCode, setResetCode] = useState(null),
    started = useRef(null);
  const action = location.hash.startsWith("#account/action"),
    params = new URLSearchParams(location.hash.split("?")[1] || "");
  const code = params.get("oobCode"),
    kind = params.get("mode");
  const continueTo = () => {
    const target = safeNext(sessionStorage.getItem("homeReturn") || next);
    sessionStorage.removeItem("homeReturn");
    location.hash = target;
  };
  useEffect(() => {
    if (!action) sessionStorage.setItem("homeReturn", safeNext(next));
  }, [next, action]);
  useEffect(() => {
    if (!cooldown) return;
    const timer = setTimeout(
      () => setCooldown((c) => Math.max(0, c - 1)),
      1000,
    );
    return () => clearTimeout(timer);
  }, [cooldown]);
  useEffect(() => {
    if (!action || !code || started.current === code) return;
    started.current = code;
    setBusy(true);
    const run = async () => {
      if (kind === "resetPassword") {
        await verifyPasswordResetCode(auth, code);
        setResetCode(code);
        setNotice("Choose a new password for your CookCredit account.");
      } else if (kind === "verifyEmail") {
        const result = await verifyAccountLink({
          auth,
          code,
          checkCode: checkActionCode,
          applyCode: applyActionCode,
          complete: async () => {
            await refresh();
            const value = await api("/me");
            return { ...value, id: value.userId };
          },
        });
        history.replaceState(null, "", location.pathname + "#sign-in");
        if (result.profile) continueTo();
        else
          setNotice(
            "Your email is verified. Sign in with the email address that received this link to continue.",
          );
      } else
        throw new Error(
          "This account link is not supported. Request another email.",
        );
    };
    run()
      .catch((e) => setError(friendly(e)))
      .finally(() => setBusy(false));
  }, [action, code, kind]);
  const run = async (task) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
    } catch (e) {
      setError(friendly(e));
    } finally {
      setBusy(false);
    }
  };
  const resend = async () => {
    const value = await api("/account/verification", {
      method: "POST",
      body: {},
      protectedAccount: true,
    });
    setCooldown(value.retryAfterSeconds || 60);
    setNotice(
      value.alreadyVerified
        ? "Your email is already verified. Choose “I’ve verified my email”."
        : "Verification email queued. Check your inbox and spam folder.",
    );
  };
  const google = () => {
    // Start the popup in the actual click handler, before any await or App Check.
    const pending = signInWithPopup(auth, new GoogleAuthProvider());
    run(async () => {
      await pending;
      await refresh();
      continueTo();
    });
  };
  const submit = (event) => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    run(async () => {
      if (resetCode) {
        await confirmPasswordReset(auth, resetCode, f.get("password"));
        setResetCode(null);
        history.replaceState(null, "", location.pathname + "#sign-in");
        setNotice("Your password is updated. Sign in to continue.");
        return;
      }
      if (mode === "reset") {
        await api("/account/reset", {
          method: "POST",
          body: { email: f.get("email") },
          protectedAccount: true,
        });
        setNotice(
          "If this email has an account, a password reset link will arrive shortly.",
        );
        return;
      }
      if (mode === "signup") {
        await createUserWithEmailAndPassword(
          auth,
          f.get("email"),
          f.get("password"),
        );
        await resend();
      } else {
        const result = await signInWithEmailAndPassword(
          auth,
          f.get("email"),
          f.get("password"),
        );
        await refresh();
        if (result.user.emailVerified) continueTo();
      }
    });
  };
  if (user && !user.emailVerified && !resetCode && !action)
    return (
      <section className="narrow">
        <p className="eyebrow">One last step</p>
        <h1>Check your email.</h1>
        <p>
          Open the verification link sent to <strong>{user.email}</strong>. Your
          account will return to this visit after verification.
        </p>
        <p role="status">{notice}</p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="actions">
          <button
            disabled={busy}
            onClick={() =>
              run(async () => {
                await refresh();
                if (auth.currentUser?.emailVerified) continueTo();
                else
                  setNotice(
                    "Your account is not verified yet. Open the link in your email first.",
                  );
              })
            }
          >
            I’ve verified my email
          </button>
          <button
            className="secondary"
            disabled={busy || cooldown > 0}
            onClick={() => run(resend)}
          >
            {cooldown ? `Resend in ${cooldown}s` : "Resend verification email"}
          </button>
        </div>
        <button className="text" onClick={() => run(() => signOut(auth))}>
          Use a different account
        </button>
      </section>
    );
  return (
    <section className="narrow">
      <p className="eyebrow">CookCredit Home</p>
      <h1>
        {resetCode
          ? "Choose a new password"
          : mode === "signup"
            ? "Let’s make this easy."
            : mode === "reset"
              ? "Reset your password"
              : "Welcome back."}
      </h1>
      <p>
        {resetCode
          ? "Use a password you don’t use elsewhere."
          : "Use your existing CookCredit account, or create one. Your Home visits stay in your own account."}
      </p>
      {!resetCode && (
        <>
          <button className="google" disabled={busy} onClick={google}>
            <span aria-hidden="true">G</span> Continue with Google
          </button>
          <div className="divider">or use email</div>
        </>
      )}
      <form onSubmit={submit}>
        {!resetCode && (
          <label>
            Email address
            <input
              type="email"
              name="email"
              autoComplete="email"
              required
              maxLength="254"
            />
          </label>
        )}
        {(resetCode || mode !== "reset") && (
          <label>
            Password
            <input
              type="password"
              name="password"
              autoComplete={
                resetCode || mode === "signup"
                  ? "new-password"
                  : "current-password"
              }
              minLength={resetCode || mode === "signup" ? 10 : 1}
              maxLength="128"
              required
            />
            {(resetCode || mode === "signup") && (
              <small>At least 10 characters.</small>
            )}
          </label>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {notice && (
          <p role="status" className="notice">
            {notice}
          </p>
        )}
        <button disabled={busy}>
          {busy
            ? "Please wait…"
            : resetCode
              ? "Save password"
              : mode === "signup"
                ? "Create account"
                : mode === "reset"
                  ? "Email a reset link"
                  : "Sign in"}
        </button>
      </form>
      {!resetCode && (
        <div className="account-links">
          <button
            className="text"
            disabled={busy}
            onClick={() => {
              setMode(mode === "signup" ? "signin" : "signup");
              setError("");
            }}
          >
            {mode === "signup"
              ? "Already have an account? Sign in"
              : "New to CookCredit? Create an account"}
          </button>
          <button
            className="text"
            disabled={busy}
            onClick={() => {
              setMode(mode === "reset" ? "signin" : "reset");
              setError("");
            }}
          >
            {mode === "reset" ? "Back to sign in" : "Forgot password?"}
          </button>
        </div>
      )}
      <p className="quiet">
        Need a hand? <a href="#callback">Ask us to call you.</a>
      </p>
    </section>
  );
}
