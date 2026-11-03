import React, { useEffect, useState } from "react";
import { api, stripeLocation, label } from "../api";

export default function Payout({ applying = false }) {
  const [account, setAccount] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const load = () => api("/payout-account").then(setAccount);
  useEffect(() => {
    if (!applying) load().catch((e) => setError(e.message));
  }, [applying]);
  const run = async (task) => {
    setBusy(true);
    setError("");
    try {
      await task();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const apply = (event) => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    run(async () => {
      await api("/helpers/apply", {
        method: "POST",
        body: {
          bio: f.get("bio"),
          services: f.get("services"),
          contactConsent: f.has("consent"),
        },
      });
      setNotice(
        "Your experience is submitted for CookCredit review. This does not grant helper access yet.",
      );
    });
  };
  return (
    <section className="narrow">
      <p className="eyebrow">CookCredit helpers</p>
      <h1>{applying ? "Bring your skills home." : "Your payout account"}</h1>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {applying ? (
        <form onSubmit={apply}>
          <label>
            Services
            <select name="services">
              <option value="cooking">Cooking</option>
              <option value="cleaning">Cleaning</option>
              <option value="both">Cooking and cleaning</option>
            </select>
          </label>
          <label>
            Tell us about your experience
            <textarea name="bio" maxLength="1000" rows="6" required />
          </label>
          <label className="check">
            <input type="checkbox" name="consent" required />
            CookCredit may contact me to review my service experience.
          </label>
          <button disabled={busy}>Submit for review</button>
        </form>
      ) : (
        <>
          <p>
            Stripe securely manages your bank details. CookCredit transfers are
            released only after payment, completed work and expense review.
          </p>
          {account?.connected ? (
            <>
              <p>
                {account.payoutsEnabled
                  ? "Your Stripe account is ready to receive funds."
                  : "Your Stripe account needs more information."}
              </p>
              {account.requirements?.length > 0 && (
                <p>
                  Requirements: {account.requirements.map(label).join(", ")}
                </p>
              )}
              <div className="actions">
                <button
                  disabled={busy}
                  onClick={() =>
                    run(async () =>
                      stripeLocation(
                        (
                          await api("/payout-account/link", {
                            method: "POST",
                            body: { kind: "onboarding" },
                          })
                        ).url,
                      ),
                    )
                  }
                >
                  Complete Stripe setup
                </button>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    run(async () =>
                      stripeLocation(
                        (
                          await api("/payout-account/link", {
                            method: "POST",
                            body: { kind: "dashboard" },
                          })
                        ).url,
                      ),
                    )
                  }
                >
                  Open Stripe dashboard
                </button>
              </div>
            </>
          ) : account?.enabled ? (
            <button
              disabled={busy}
              onClick={() =>
                run(async () => {
                  await api("/payout-account", { method: "POST", body: {} });
                  setNotice(
                    "Your secure account setup is queued. Refresh in a moment to continue.",
                  );
                  await load();
                })
              }
            >
              Start secure payout setup
            </button>
          ) : (
            account && (
              <p>
                Payout account setup is not enabled yet. Contact CookCredit
                before taking a paid visit.
              </p>
            )
          )}
          <button className="text" disabled={busy} onClick={() => run(load)}>
            Refresh account status
          </button>
          <p className="quiet">
            A transfer to your Stripe balance is separate from a payout to your
            bank. Check actual bank payout status in Stripe.
          </p>
        </>
      )}
    </section>
  );
}
