import React, { useEffect, useState } from "react";

import { api, dollars, label, money } from "../api";
import { serviceNames } from "./Enrollment";
import OperatingRulesDraft from "./OperatingRulesDraft";
import Availability from "./Availability";

export default function Team({ profile }) {
  // Change the tab and its payload together. A response from a previous tab
  // cannot render against another tab's data shape or overwrite its result.
  const [screen, setScreen] = useState({ tab: profile.owner ? "enrollments" : "visits", data: null });
  const { tab, data } = screen;
  const setTab = (tab) => setScreen({ tab, data: null });
  const setData = (data) =>
    setScreen((current) =>
      current.tab === tab ? { ...current, data } : current,
    );
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [scheduleHelper, setScheduleHelper] = useState(null);
  useEffect(() => { setNotice(""); setScheduleHelper(null); }, [tab]);

  const [version, setVersion] = useState(0);

  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    api("/" + tab)
      .then((v) => {
        if (active) setData(v);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [tab, version]);

  const run = async (task) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
      setNotice("Change saved.");
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const loadMore = async () => {
    setBusy(true);
    setError("");
    try {
      const more = await api(
        "/" + tab + "?cursor=" + encodeURIComponent(data.nextCursor),
      );
      setData({ ...more, [tab]: [...data[tab], ...more[tab]] });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const enrollmentLink = new URL(location.href);
  enrollmentLink.hash = "enroll";
  enrollmentLink.search = "";
  const copyEnrollment = async () => {
    try {
      await navigator.clipboard.writeText(enrollmentLink.href);
      setNotice("Enrollment link copied. You can paste it into a text or email.");
    } catch {
      setNotice("The link was not copied. Select and copy it from the field below.");
    }
  };
  const review = (event, id) => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    run(() =>
      api("/helpers/" + id + "/review", {
        method: "POST",
        body: {
          enabled: f.has("enabled"),
          cooking: f.has("cooking"),
          cleaning: f.has("cleaning"),
          reviewConfirmed: f.has("reviewConfirmed"),
        },
      }),
    );
  };

  const saveRates = (event) => {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    run(() =>
      api("/pricing", {
        method: "POST",
        body: {
          previousId: data.activeId,
          currency: "usd",
          rates: {
            cookingHourlyCents: dollars(f.get("cooking")),
            cleaningHourlyCents: dollars(f.get("cleaning")),
          },
          customerFeeBps: dollars(f.get("fee")),
          helperCommissionBps: dollars(f.get("commission")),
          materialsCapCents: dollars(f.get("cap")),
          quoteValidMinutes: Number(f.get("validity")),
        },
      }),
    );
  };

  return (
    <section className="page">
      <p className="eyebrow">Private CookCredit operations</p>
      <h1>Home service desk</h1>
      <nav className="tabs" aria-label="Service desk">
        {[
          ...(profile.owner ? ["enrollments"] : []),
          "visits",
          "callbacks",
          "helpers",
          "pricing",
          ...(profile.owner ? ["operating-rules", "operations", "audit"] : []),
        ].map((value) => (
          <button
            className={tab === value ? "selected" : "text"}
            aria-current={tab === value ? "page" : undefined}
            key={value}
            onClick={() => setTab(value)}
          >
            {value === "operating-rules" ? "Operating rules" : label(value)}
          </button>
        ))}
      </nav>
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {!data && !error && <p role="status">Loading…</p>}
      {error && !data && <button onClick={() => setVersion(v => v + 1)}>Try again</button>}

      {data && tab === "enrollments" && profile.owner && <>
        <section className="section">
          <h2>Invite people to enroll</h2>
          <p>Share this link by text or email. People sign in and choose the services they need. Signing up does not book or charge for a visit.</p>
          {profile.environment === "staging" && <p className="quiet">This is currently a restricted staging link. Public invitations follow launch acceptance.</p>}
          <label>Enrollment link<input readOnly value={enrollmentLink.href} /></label>
          <button onClick={copyEnrollment}>Copy enrollment link</button>
        </section>
        <h2>People enrolled</h2>
        <button className="secondary" disabled={busy} onClick={() => setVersion(v => v + 1)}>Refresh people</button>
        <p>Only the Home owner can open this directory. Account-only entries have signed in but have not saved their service needs.</p>
        {!data.enrollments.length && <p>No enrollments yet.</p>}
        {data.enrollments.map(row => <article className="section" key={row.id}>
          <h3>{row.name}</h3>
          <p>{row.withdrawn ? "Service interest withdrawn — do not contact about enrollment" : row.service ? serviceNames[row.service] : "Account only — service needs not provided"}</p>
          <p><a href={"mailto:" + row.email}>{row.email}</a>{row.phone && <> · <a href={"tel:" + row.phone}>{row.phone}</a></>}</p>
          <p className="quiet">Joined {new Date(row.joinedAt).toLocaleDateString()}{row.updatedAt && " · Needs updated " + new Date(row.updatedAt).toLocaleDateString()}</p>
        </article>)}
        {data.nextCursor && <button disabled={busy} onClick={loadMore}>More people</button>}
      </>}

      {data && tab === "operating-rules" && profile.owner && <OperatingRulesDraft key={data.version} data={data} run={run} busy={busy} />}

      {data && tab === "visits" && (
        <>
          {data.visits.length === 0 && <p>No visit requests yet.</p>}
          {data.visits.map((v) => (
            <a className="visit-row" href={"#visit/" + v.id} key={v.id}>
              <div>
                <h2>{label(v.service)}</h2>
                <p>
                  {v.date} · {v.time.slice(0, 5)}
                </p>
              </div>
              <span>{label(v.status)} →</span>
            </a>
          ))}
          {data.nextCursor && (
            <button disabled={busy} onClick={loadMore}>
              More requests
            </button>
          )}
        </>
      )}

      {data && tab === "callbacks" && (
        <>
          {!data.callbacks.length && <p>No open callbacks.</p>}
          {data.callbacks.map((row) => (
            <article className="section" key={row.id}>
              <h2>{row.name}</h2>
              <p>
                <a href={"tel:" + row.phone}>{row.phone}</a> ·{" "}
                {row.preferredTime}
              </p>
              <p>{label(row.status)}</p>
              <div className="actions">
                {row.status === "requested" && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      run(() =>
                        api("/callbacks/" + row.id, {
                          method: "POST",
                          body: { version: row.version, status: "contacting" },
                        }),
                      )
                    }
                  >
                    Mark contacting
                  </button>
                )}
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    run(() =>
                      api("/callbacks/" + row.id, {
                        method: "POST",
                        body: { version: row.version, status: "closed" },
                      }),
                    )
                  }
                >
                  Close callback
                </button>
              </div>
            </article>
          ))}
        </>
      )}

      {data && tab === "helpers" && (
        <>
          {!data.helpers.length && <p>No helper applications yet.</p>}
          {data.helpers.map((row) => (
            <article className="section" key={row.id}>
              <h2>{row.name}</h2>
              <p>{row.bio}</p>
              <p>Requested services: {row.requestedServices.join(", ")}</p>
              {row.enabled && <button type="button" className="secondary" aria-expanded={scheduleHelper === row.id}
                onClick={() => setScheduleHelper(value => value === row.id ? null : row.id)}>
                {scheduleHelper === row.id ? "Hide" : "View"} availability for {row.name}
              </button>}
              {scheduleHelper === row.id && <Availability key={row.id} helperId={row.id} />}
              {profile.owner ? (
                <form onSubmit={(event) => review(event, row.id)}>
                  <label className="check">
                    <input
                      type="checkbox"
                      name="enabled"
                      defaultChecked={row.enabled}
                    />
                    Enable Home helper access
                  </label>
                  <label className="check">
                    <input
                      type="checkbox"
                      name="cooking"
                      defaultChecked={row.cooking}
                    />
                    Cooking reviewed and approved
                  </label>
                  <label className="check">
                    <input
                      type="checkbox"
                      name="cleaning"
                      defaultChecked={row.cleaning}
                    />
                    Cleaning reviewed and approved
                  </label>
                  <label className="check">
                    <input type="checkbox" name="reviewConfirmed" required />I
                    reviewed this helper and the service capabilities above.
                  </label>
                  <button disabled={busy}>Save reviewed permissions</button>
                </form>
              ) : (
                <p>Owner review is required to grant or change access.</p>
              )}
            </article>
          ))}
        </>
      )}

      {data && tab === "pricing" && (
        <>
          <p>
            New prices affect new quotes. Existing quotes and approvals keep
            their original amounts.
          </p>
          {profile.owner && (
            <details>
              <summary>Create a pricing version</summary>
              <form className="narrow left" onSubmit={saveRates}>
                <div className="two">
                  <label>
                    Cooking per hour, USD
                    <input name="cooking" inputMode="decimal" required />
                  </label>
                  <label>
                    Cleaning per hour, USD
                    <input name="cleaning" inputMode="decimal" required />
                  </label>
                  <label>
                    Customer service fee, %
                    <input name="fee" inputMode="decimal" required />
                  </label>
                  <label>
                    Helper commission, %
                    <input name="commission" inputMode="decimal" required />
                  </label>
                  <label>
                    Maximum materials allowance, USD
                    <input name="cap" inputMode="decimal" required />
                  </label>
                  <label>
                    Quote validity, minutes
                    <input
                      name="validity"
                      type="number"
                      min="60"
                      max="10080"
                      step="1"
                      required
                    />
                  </label>
                </div>
                <button disabled={busy}>Save a new version</button>
              </form>
            </details>
          )}
          {data.versions.map((card) => (
            <article className="section" key={card.id}>
              <h2>
                {card.id === data.activeId
                  ? "Active prices"
                  : "Saved pricing version"}
              </h2>
              <p>{new Date(card.createdAt).toLocaleString()}</p>
              <dl>
                <div>
                  <dt>Cooking / hour</dt>
                  <dd>{money(card.rates.cookingHourlyCents)}</dd>
                </div>
                <div>
                  <dt>Cleaning / hour</dt>
                  <dd>{money(card.rates.cleaningHourlyCents)}</dd>
                </div>
                <div>
                  <dt>Customer fee / helper commission</dt>
                  <dd>
                    {card.customerFeeBps / 100}% /{" "}
                    {card.helperCommissionBps / 100}%
                  </dd>
                </div>
              </dl>
              {profile.owner &&
                card.id !== data.activeId &&
                card.previousId === data.activeId && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      run(() =>
                        api("/pricing/" + card.id + "/activate", {
                          method: "POST",
                          body: {},
                        }),
                      )
                    }
                  >
                    Activate these prices
                  </button>
                )}
            </article>
          ))}
        </>
      )}

      {data && tab === "operations" && (
        <>
          <p>
            Provider operations are reviewed here. A Stripe transfer is not a
            confirmed bank payout. Uncertain operations require provider
            reconciliation before retry.
          </p>
          <div className="operation-list">
            {data.operations.map((row) => (
              <article className="section" key={row.id}>
                <h3>{label(row.kind)}</h3>
                <p>
                  {label(row.status)}
                  {row.lastError ? " · " + label(row.lastError) : ""}
                </p>
                <p className="quiet">
                  {new Date(row.createdAt).toLocaleString()}
                </p>
                {row.bookingId && (
                  <a href={"#visit/" + row.bookingId}>Open private visit</a>
                )}
              </article>
            ))}
          </div>
        </>
      )}

      {data && tab === "audit" && (
        <ol className="activity">
          {data.events.map((row, i) => (
            <li key={i}>
              <strong>{label(row.action)}</strong>
              <small>
                {new Date(row.at).toLocaleString()} · actor {row.actorId} ·
                record {row.subjectId}
              </small>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
