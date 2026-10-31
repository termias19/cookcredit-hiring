import React, { useEffect, useState } from "react";
import { api, dollars, label, money } from "../../api";

export default function OperatorVisit({ visit, receipts, run, busy, action }) {
  const [helpers, setHelpers] = useState([]),
    [pricing, setPricing] = useState(null),
    [events, setEvents] = useState([]),
    [materials, setMaterials] = useState([]);
  const [error, setError] = useState("");
  const providerReview = visit.payment?.helperFunds === "provider_review_required" || visit.payment?.helperTransferBalanceKnown === false;
  useEffect(() => {
    let active = true;
    Promise.all([
      api("/helpers"),
      api("/pricing"),
      api(`/visits/${visit.id}/activity`),
    ])
      .then(([h, p, e]) => {
        if (active) {
          setHelpers(h.helpers);
          setPricing(p);
          setEvents(e.events);
        }
      })
      .catch((e) => setError(e.message));
    return () => {
      active = false;
    };
  }, [visit.id, visit.version]);
  const quote = (event) => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    run(async () => {
      await api(`/visits/${visit.id}/quotes`, {
        method: "POST",
        body: {
          version: visit.version,
          rateCardId: pricing.activeId,
          cookingMinutes:
            visit.service === "cleaning" ? 0 : Number(f.get("cooking")),
          cleaningMinutes:
            visit.service === "cooking" ? 0 : Number(f.get("cleaning")),
          materials: materials.map((line) => ({
            category: line.category,
            label: line.label,
            capCents: dollars(line.amount),
          })),
          tax: {
            amountCents: dollars(f.get("tax")),
            reviewConfirmed: f.get("reviewed") === "on",
            reviewReference: f.get("reference"),
          },
        },
      });
    });
  };
  const reconcile = (event) => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    run(() =>
      api(`/visits/${visit.id}/materials/reconcile`, {
        method: "POST",
        body: {
          version: visit.version,
          quoteId: visit.quote.id,
          receiptsReviewed: f.get("reviewed") === "on",
          lines: visit.quote.materials.map((line) => ({
            lineId: line.lineId,
            actualCents: dollars(f.get("amount-" + line.lineId)),
            receiptReference: f.get("receipt-" + line.lineId) || null,
          })),
          tax: {
            amountCents: dollars(f.get("tax")),
            reviewConfirmed: f.get("taxReviewed") === "on",
            reviewReference: f.get("reference"),
          },
        },
      }),
    );
  };
  const setMaterial = (index, field, value) =>
    setMaterials((rows) =>
      rows.map((line, i) => (i === index ? { ...line, [field]: value } : line)),
    );
  return (
    <section className="section operator">
      <p className="eyebrow">Private CookCredit operations</p>
      <h2>Manage this visit</h2>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {visit.issueOpen && <p>{providerReview
        ? "Reconcile the external transfer change with Stripe before resolving this issue. Additional fund releases are held."
        : "Resolve the reviewed issue before changing this visit."}</p>}
      <div className="actions">
        {visit.status === "requested" && !visit.reviewed && (
          <button disabled={busy || visit.issueOpen} onClick={() => action("review")}>
            Mark requirements reviewed
          </button>
        )}
        {visit.issueOpen && (
          <button
            disabled={busy || providerReview}
            className="secondary"
            onClick={() => action("resolve_issue")}
          >
            Resolve reviewed issue
          </button>
        )}
      </div>
      {visit.status === "requested" &&
        visit.reviewed &&
        !visit.helperAccepted && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              action("assign", {
                helperId: new FormData(event.currentTarget).get("helper"),
              });
            }}
          >
            <label>
              Assign an approved helper
              <select name="helper" required defaultValue="">
                <option value="" disabled>
                  Choose a helper
                </option>
                {helpers
                  .filter(
                    (h) =>
                      h.id !== visit.customerId &&
                      h.enabled &&
                      (visit.service === "cleaning" || h.cooking) &&
                      (visit.service === "cooking" || h.cleaning),
                  )
                  .map((h) => (
                    <option key={h.id} value={h.id}>
                      {h.name}
                    </option>
                  ))}
              </select>
            </label>
            <button disabled={busy || visit.issueOpen}>Save assignment</button>
          </form>
        )}
      {visit.status === "accepted" && !visit.payment.id && !visit.issueOpen && (
        <details>
          <summary>Prepare or update the full quote</summary>
          {!pricing?.activeId ? (
            <p>
              Activate a pricing version in <a href="#team">Team → Pricing</a>{" "}
              first.
            </p>
          ) : (
            <form onSubmit={quote}>
              <p>
                The helper and customer must accept a new quote. Tax needs a
                documented review; this tool does not determine taxability.
              </p>
              <div className="two">
                {visit.service !== "cleaning" && (
                  <label>
                    Cooking minutes
                    <input
                      name="cooking"
                      type="number"
                      min="30"
                      max="480"
                      step="30"
                      defaultValue={
                        visit.serviceMinutes?.cooking ||
                        (visit.service === "both"
                          ? visit.durationMinutes - 60
                          : visit.durationMinutes)
                      }
                      required
                    />
                  </label>
                )}
                {visit.service !== "cooking" && (
                  <label>
                    Cleaning minutes
                    <input
                      name="cleaning"
                      type="number"
                      min="30"
                      max="480"
                      step="30"
                      defaultValue={
                        visit.serviceMinutes?.cleaning ||
                        (visit.service === "both" ? 60 : visit.durationMinutes)
                      }
                      required
                    />
                  </label>
                )}
              </div>
              <h3>Materials at cost</h3>
              {materials.map((line, index) => (
                <div key={index} className="material">
                  <label>
                    Category
                    <select
                      value={line.category}
                      onChange={(e) =>
                        setMaterial(index, "category", e.target.value)
                      }
                    >
                      <option value="supplies">
                        Supplies, containers or labels
                      </option>
                      {visit.service !== "cleaning" && (
                        <option value="ingredients">Ingredients</option>
                      )}
                    </select>
                  </label>
                  <label>
                    What is included?
                    <input
                      value={line.label}
                      maxLength="120"
                      onChange={(e) =>
                        setMaterial(index, "label", e.target.value)
                      }
                      required
                    />
                  </label>
                  <label>
                    Maximum allowance, USD
                    <input
                      inputMode="decimal"
                      value={line.amount}
                      onChange={(e) =>
                        setMaterial(index, "amount", e.target.value)
                      }
                      required
                    />
                  </label>
                  <button
                    type="button"
                    className="text"
                    onClick={() =>
                      setMaterials((rows) => rows.filter((_, i) => i !== index))
                    }
                  >
                    Remove allowance
                  </button>
                </div>
              ))}
              <button
                className="secondary"
                type="button"
                disabled={materials.length >= 20}
                onClick={() =>
                  setMaterials((rows) => [
                    ...rows,
                    { category: "supplies", label: "", amount: "" },
                  ])
                }
              >
                Add a materials allowance
              </button>
              <label>
                Reviewed tax allowance, USD
                <input name="tax" inputMode="decimal" required />
              </label>
              <label>
                Tax review reference
                <input name="reference" maxLength="120" required />
              </label>
              <label className="check">
                <input type="checkbox" name="reviewed" required />I reviewed the
                applicable tax and this allowance.
              </label>
              <button disabled={busy}>Issue itemized quote</button>
            </form>
          )}
        </details>
      )}
      {visit.quote &&
        !visit.quote.reconciliation &&
        ["pending_confirmation", "completed"].includes(visit.status) &&
        !visit.issueOpen && (
          <details>
            <summary>Review receipts and final costs</summary>
            <form onSubmit={reconcile}>
              <p>
                Check every photo before approving reimbursement. Costs cannot
                exceed the customer’s approved caps.
              </p>
              {visit.quote.materials.map((line) => (
                <div className="material" key={line.lineId}>
                  <h3>
                    {line.label} · cap {money(line.capCents)}
                  </h3>
                  <label>
                    Actual cost, USD
                    <input
                      name={"amount-" + line.lineId}
                      inputMode="decimal"
                      required
                    />
                  </label>
                  <label>
                    Verified receipt photo
                    <select name={"receipt-" + line.lineId} defaultValue="">
                      <option value="">No purchase made ($0 only)</option>
                      {receipts
                        .filter(
                          (r) =>
                            r.status === "ready" &&
                            r.quoteId === visit.quote.id,
                        )
                        .map((r, i) => (
                          <option key={r.id} value={r.id}>
                            Receipt {i + 1} ·{" "}
                            {new Date(r.createdAt).toLocaleString()}
                          </option>
                        ))}
                    </select>
                  </label>
                </div>
              ))}
              <label className="check">
                <input type="checkbox" name="reviewed" required />I reviewed the
                purchase evidence and actual costs.
              </label>
              <label>
                Final reviewed tax, USD
                <input name="tax" inputMode="decimal" required />
              </label>
              <label>
                Tax review reference
                <input name="reference" maxLength="120" required />
              </label>
              <label className="check">
                <input type="checkbox" name="taxReviewed" required />I reviewed
                the final tax amount.
              </label>
              <button disabled={busy}>Save final costs</button>
            </form>
          </details>
        )}
      <details>
        <summary>Visit audit trail</summary>
        <ol className="activity">
          {events.map((e) => (
            <li key={e.version}>
              <strong>{label(e.action)}</strong>
              <small>
                {new Date(e.at).toLocaleString()} · version {e.version}
              </small>
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}
