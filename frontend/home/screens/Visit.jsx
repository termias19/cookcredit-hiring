import React, { useEffect, useRef, useState, lazy, Suspense } from "react";
import { api, downloadReceipt, label, money, stripeLocation } from "../api";
const OperatorVisit = lazy(() => import("./operator/OperatorVisit"));

const serviceNames = {
  cooking: "Cooking",
  cleaning: "Cleaning",
  both: "Cooking & cleaning",
};
const statusCopy = {
  requested: "CookCredit is reviewing your request and availability.",
  accepted:
    "Your helper has accepted the visit. Review the full quote when it is ready.",
  confirmed: "Your payment is confirmed. Your visit is arranged.",
  in_progress: "Your helper has started the visit.",
  pending_confirmation:
    "Your helper has finished. Please review the work before confirming.",
  completed: "Your visit is completed. Materials and funds are shown below.",
  cancelled: "This visit is cancelled. Any verified refund appears below.",
};
export default function Visit({ id, profile }) {
  const [visit, setVisit] = useState(null),
    [receipts, setReceipts] = useState([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [cancel, setCancel] = useState(false);
  const [notice, setNotice] = useState(""),
    timer = useRef(null),
    mounted = useRef(true);
  const load = async () => {
    const value = await api("/visits/" + id);
    if (mounted.current) setVisit(value);
    return value;
  };
  useEffect(() => {
    mounted.current = true;
    setVisit(null);
    setError("");
    load().catch((e) => setError(e.message));
    api(`/visits/${id}/receipts`)
      .then((v) => setReceipts(v.receipts))
      .catch(() => {});
    return () => {
      mounted.current = false;
      clearTimeout(timer.current);
    };
  }, [id]);
  const run = async (task) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const action = (name, extra = {}) =>
    run(() =>
      api(`/visits/${id}/actions`, {
        method: "POST",
        body: { action: name, version: visit.version, ...extra },
      }),
    );
  const approval = (decision) =>
    run(() =>
      api(`/visits/${id}/quotes/${visit.quote.id}/${decision}`, {
        method: "POST",
        body: { version: visit.version, digest: visit.quote.digest },
      }),
    );
  const waitCheckout = async () => {
    for (let tries = 0; tries < 10; tries++) {
      const current = await load();
      if (!mounted.current) return;
      if (current.payment.checkoutUrl) {
        stripeLocation(current.payment.checkoutUrl);
        return;
      }
      if (!["creating", "processing"].includes(current.payment.status)) break;
      await new Promise((resolve) => {
        timer.current = setTimeout(resolve, 2000);
      });
    }
    setNotice(
      "Checkout is still being prepared. Use Refresh below in a moment; your request is saved.",
    );
  };
  const pay = () =>
    run(async () => {
      if (visit.payment.checkoutUrl) {
        stripeLocation(visit.payment.checkoutUrl);
        return;
      }
      await api(`/visits/${id}/checkout`, {
        method: "POST",
        body: {
          version: visit.version,
          quoteId: visit.quote.id,
          digest: visit.quote.digest,
        },
      });
      await waitCheckout();
    });
  const upload = (event) => {
    event.preventDefault();
    const form = event.currentTarget,
      data = new FormData(form);
    run(async () => {
      await api(`/visits/${id}/receipts`, {
        method: "POST",
        body: data,
        form: true,
      });
      const result = await api(`/visits/${id}/receipts`);
      setReceipts(result.receipts);
      form.reset();
      setNotice("Receipt photo uploaded privately.");
    });
  };
  if (!visit)
    return (
      <section className="narrow">
        <h1>Your visit</h1>
        {error ? (
          <>
            <p role="alert" className="error">
              {error}
            </p>
            <a href="#visits">Back to visits</a>
          </>
        ) : (
          <p role="status">Opening your visit…</p>
        )}
      </section>
    );
  const q = visit.quote,
    p = visit.payment,
    closed = visit.status === "cancelled",
    held = visit.issueOpen;
  return (
    <section className="page">
      <a href="#visits">← My visits</a>
      <div className="heading">
        <div>
          <p className="eyebrow">{label(visit.status)}</p>
          <h1>{serviceNames[visit.service]} visit</h1>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() =>
            run(async () => {
              if (p.id)
                await api(`/visits/${id}/payment/refresh`, {
                  method: "POST",
                  body: {},
                });
            })
          }
        >
          Refresh
        </button>
      </div>
      <p className="lead">{statusCopy[visit.status]}</p>
      {held && (
        <p className="notice" role="status">
          An issue is open for CookCredit review. New helper transfers are on
          hold.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      <div className="columns">
        <div>
          <section className="section">
            <h2>The plan</h2>
            <dl>
              <div>
                <dt>Date and time</dt>
                <dd>
                  {visit.date} at {visit.time.slice(0, 5)}
                  <small>{visit.timeZone}</small>
                </dd>
              </div>
              <div>
                <dt>Time arranged</dt>
                <dd>{visit.durationMinutes / 60} hours</dd>
              </div>
              <div>
                <dt>Address</dt>
                <dd>{visit.address}</dd>
              </div>
              {visit.arrangingFor && (
                <div>
                  <dt>Arranged for</dt>
                  <dd>{visit.arrangingFor.name}</dd>
                </div>
              )}
              <div>
                <dt>Helper</dt>
                <dd>{visit.helperName || "Not assigned yet"}</dd>
              </div>
            </dl>
            <h3>Your instructions</h3>
            <ul>
              {visit.instructions.preferences.map((v) => (
                <li key={v}>{label(v)}</li>
              ))}
              {visit.instructions.cleaningTasks.map((v) => (
                <li key={v}>{label(v)}</li>
              ))}
            </ul>
            <p className="preserve">
              {visit.instructions.visitNotes || "No additional instructions."}
            </p>
          </section>
          {q && (
            <section className="section">
              <h2>Your full quote</h2>
              <dl className="prices">
                {q.labor.map((line) => (
                  <div key={line.service}>
                    <dt>
                      {serviceNames[line.service]} · {line.minutes / 60} hours
                      <small>{money(line.rateCentsPerHour)} per hour</small>
                    </dt>
                    <dd>{money(line.amountCents)}</dd>
                  </div>
                ))}
                {q.materials.map((line) => (
                  <div key={line.lineId}>
                    <dt>
                      {line.label}
                      <small>
                        Maximum materials allowance · charged at cost
                      </small>
                    </dt>
                    <dd>{money(line.capCents)}</dd>
                  </div>
                ))}
                <div>
                  <dt>Service fee</dt>
                  <dd>{money(q.serviceFeeCents)}</dd>
                </div>
                <div>
                  <dt>Reviewed tax allowance</dt>
                  <dd>{money(q.taxCapCents)}</dd>
                </div>
                <div className="total">
                  <dt>Maximum total</dt>
                  <dd>{money(q.maximumTotalCents)}</dd>
                </div>
              </dl>
              <p>
                You pay this approved maximum through Stripe. Unused material
                and tax allowance is refunded after the visit and receipt
                review.
              </p>
              <p className="quiet">
                {q.approved
                  ? "You approved this quote."
                  : q.expired
                    ? "This quote has expired. CookCredit needs to update it."
                    : `Quote valid until ${new Date(q.expiresAt).toLocaleString()}.`}{" "}
                {q.helperAcceptedQuote
                  ? "Your helper accepted the work and earnings."
                  : "Awaiting helper review."}
              </p>
              {!closed && !held && !q.expired && (
                <div className="actions">
                  {visit.isAssignedHelper && !q.helperAcceptedQuote && (
                    <button disabled={busy} onClick={() => approval("accept")}>
                      Accept work and earnings
                    </button>
                  )}
                  {visit.isCustomer && !q.approved && q.helperAcceptedQuote && (
                    <button disabled={busy} onClick={() => approval("approve")}>
                      Approve this full quote
                    </button>
                  )}
                  {visit.isCustomer &&
                    q.approved &&
                    [
                      "unpaid",
                      "expired",
                      "cancelled",
                      "open",
                      "creating",
                    ].includes(p.status) &&
                    profile.paymentsAvailable && (
                      <button disabled={busy} onClick={pay}>
                        {busy
                          ? "Preparing…"
                          : p.checkoutUrl
                            ? "Continue secure checkout"
                            : `Pay up to ${money(q.maximumTotalCents)} securely`}
                      </button>
                    )}
                </div>
              )}
              {q.approved &&
                !profile.paymentsAvailable &&
                p.status === "unpaid" && (
                  <p>
                    Online payment is not enabled yet. CookCredit will contact
                    you before any charge.
                  </p>
                )}
              {q.helperEarnings && (
                <div className="notice">
                  <h3>Helper earnings</h3>
                  <p>
                    Labor after platform commission:{" "}
                    <strong>{money(q.helperEarnings.laborNetCents)}</strong>.
                    Commission: {money(q.helperEarnings.commissionCents)}.
                    Materials are reimbursed at reviewed cost, up to{" "}
                    {money(q.helperEarnings.materialsMaximumCents)}.
                  </p>
                  <p className="quiet">
                    Transfers require verified payment, customer confirmation,
                    reviewed receipts, available funds and a ready Stripe
                    account.
                  </p>
                </div>
              )}
              {q.reconciliation && (
                <>
                  <h3>Final costs</h3>
                  <dl>
                    <div>
                      <dt>Materials used</dt>
                      <dd>{money(q.reconciliation.materialsActualCents)}</dd>
                    </div>
                    <div>
                      <dt>Final tax</dt>
                      <dd>{money(q.reconciliation.taxActualCents)}</dd>
                    </div>
                    <div>
                      <dt>Final total</dt>
                      <dd>{money(q.reconciliation.customerFinalCents)}</dd>
                    </div>
                    <div>
                      <dt>Unused allowance</dt>
                      <dd>{money(q.reconciliation.unusedAllowanceCents)}</dd>
                    </div>
                  </dl>
                </>
              )}
            </section>
          )}
          <section className="section">
            <h2>Receipts</h2>
            <p>
              Purchase evidence is private to this visit. JPEG and PNG photos
              only, up to 8 MB each.
            </p>
            {receipts
              .filter((r) => r.status === "ready")
              .map((r) => (
                <button
                  key={r.id}
                  className="text receipt"
                  disabled={busy}
                  onClick={() => run(() => downloadReceipt(id, r.id))}
                >
                  Download receipt ·{" "}
                  {new Date(r.createdAt).toLocaleDateString()}
                </button>
              ))}
            {!closed && (visit.isAssignedHelper || profile.operator) && q && (
              <form onSubmit={upload}>
                <label>
                  Receipt photo
                  <input
                    type="file"
                    name="file"
                    accept="image/jpeg,image/png"
                    required
                  />
                </label>
                <button className="secondary" disabled={busy}>
                  Upload privately
                </button>
              </form>
            )}
          </section>
        </div>
        <aside>
          <section className="section">
            <h2>Payment and next steps</h2>
            <p>
              Status: <strong>{label(p.status)}</strong>
            </p>
            {p.amountCents !== undefined && (
              <p>
                Approved maximum: {money(p.amountCents)}
                <br />
                Verified refunds: {money(p.refundedCents)}
              </p>
            )}
            <p>
              {p.helperFunds === "transferred_to_stripe"
                ? "Helper funds transferred to Stripe. This does not confirm a bank payout."
                : p.helperFunds === "held_after_reversal"
                  ? "Helper funds returned for review."
                  : "Helper funds have not been released."}
            </p>
            {!closed && !held && (
              <div className="stack">
                {visit.isAssignedHelper &&
                  visit.status === "requested" &&
                  visit.assigned && (
                    <button disabled={busy} onClick={() => action("accept")}>
                      Accept this visit
                    </button>
                  )}
                {visit.isAssignedHelper && visit.status === "confirmed" && (
                  <button disabled={busy} onClick={() => action("start")}>
                    Start this visit
                  </button>
                )}
                {visit.isAssignedHelper && visit.status === "in_progress" && (
                  <button disabled={busy} onClick={() => action("finish")}>
                    Mark work finished
                  </button>
                )}
                {visit.isCustomer &&
                  visit.status === "pending_confirmation" && (
                    <>
                      <p>
                        Only confirm after you have checked the work. You can
                        report a problem below.
                      </p>
                      <button disabled={busy} onClick={() => action("confirm")}>
                        Confirm work completed
                      </button>
                    </>
                  )}
              </div>
            )}
            {!closed && !held && (
              <button
                className="text"
                disabled={busy}
                onClick={() => action("report_issue")}
              >
                Report an issue for CookCredit review
              </button>
            )}
            {!closed &&
              (visit.isCustomer || profile.operator) &&
              ["requested", "accepted", "confirmed"].includes(visit.status) && (
                <div className="cancel">
                  <button
                    className="text"
                    disabled={busy}
                    onClick={() => setCancel(!cancel)}
                  >
                    Cancel this visit
                  </button>
                  {cancel && (
                    <>
                      <p>
                        Cancel this visit? Any payment refund will be verified
                        separately.
                      </p>
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() => action("cancel")}
                      >
                        Confirm cancellation
                      </button>
                    </>
                  )}
                </div>
              )}
            <p>
              Need help?{" "}
              <a href="mailto:connectwithus@cookcredit.com">
                Contact CookCredit
              </a>
              .
            </p>
          </section>
        </aside>
      </div>
      {profile.operator && (
        <Suspense fallback={<p>Opening operations…</p>}>
          <OperatorVisit
            visit={visit}
            receipts={receipts}
            run={run}
            busy={busy}
            action={action}
          />
        </Suspense>
      )}
    </section>
  );
}
