import React, { useEffect, useState } from "react";

import { api, dollars, label, money } from "../api";
import OperatingRulesDraft from "./OperatingRulesDraft";
import Availability from "./Availability";
import Outreach from "./Outreach";
import CustomerWorklist from "./CustomerWorklist";
import { visitSchedule, visitStatusLabel, serviceNames } from "../visitPresentation";

const deskGroups = [
  { title: "Daily work", sections: [
    { id: "enrollments", title: "Customers", owner: true, intro: "Who needs help, what they asked for, and your next step." },
    { id: "visits", title: "Visits", intro: "Review requests, assign helpers and follow each visit through its approvals." },
    { id: "callbacks", title: "Callbacks", hideForOwner: true, intro: "Follow up with people who have asked CookCredit to call them." },
    { id: "outreach", title: "Outreach", owner: true, intro: "Prepare clear food invitations for email, text and print." },
    { id: "helpers", title: "Helpers", intro: "Review experience, service permissions and each helper’s own availability." },
  ] },
  { title: "Service settings", collapsible: true, sections: [
    { id: "pricing", title: "Pricing", intro: "Manage prices for new quotes. Existing offers keep their original amounts." },
    { id: "operating-rules", title: "Hours and scheduling", owner: true, intro: "Review operating hours, notice and travel buffers before activating a saved revision." },
    { id: "operations", title: "Payment operations", owner: true, intro: "Review provider processing and any operations that need attention." },
    { id: "audit", title: "Activity log", owner: true, intro: "Review the recorded changes and access activity for CookCredit Home." },
  ] },
];

export default function Team({ profile }) {
  // Change the tab and its payload together. A response from a previous tab
  // cannot render against another tab's data shape or overwrite its result.
  const [screen, setScreen] = useState({ tab: profile.owner ? "enrollments" : profile.enrollmentOnly ? "callbacks" : "visits", data: null });
  const { tab, data } = screen;
  const peopleTab = tab === "enrollments" && profile.owner;
  const groups = deskGroups.map(group => ({ ...group,
    title: group.title,
    sections: group.sections.filter(item => (!item.owner || profile.owner) && (!item.hideForOwner || !profile.owner) &&
      (!profile.enrollmentOnly || ["enrollments", "callbacks", "audit", "outreach"].includes(item.id) || (profile.owner && ["pricing", "operations"].includes(item.id)))),
  })).filter(group => group.sections.length);
  const currentSection = groups.flatMap(group => group.sections).find(item => item.id === tab) ||
    { title: "Home service desk", intro: "Choose an available section." };
  const setTab = (tab) => setScreen(current => current.tab === tab ? current : { tab, data: null });
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
    if (peopleTab) return;
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
  }, [tab, version, peopleTab]);

  const run = async (task, successNotice = "Change saved.") => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
      setNotice(successNotice);
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
    <section className="page home-desk">
      <div className="home-desk-heading">
        <p className="eyebrow">Home service desk</p>
        <h1>{currentSection.title}</h1>
        <p>{currentSection.intro}</p>
      </div>
      <nav className="home-desk-navigation" aria-label="Service desk">
        {groups.map(group => {
          const links = <div className="home-desk-links">{group.sections.map(item => (
          <button
            disabled={busy}
            className={tab === item.id ? "selected" : ""}
            aria-current={tab === item.id ? "page" : undefined}
            aria-controls="home-desk-content"
            key={item.id}
            onClick={() => setTab(item.id)}
          >
            {item.title}
          </button>
          ))}</div>;
          return group.collapsible
            ? <details className="home-desk-group home-desk-settings" key={group.title} open={group.sections.some(item => item.id === tab)}>
                <summary>{group.title}</summary>{links}
              </details>
            : <div className="home-desk-group" key={group.title}><p className="home-workspace-label">{group.title}</p>{links}</div>;
        })}
      </nav>
      <section id="home-desk-content" className="home-desk-content" aria-label={currentSection.title}>
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
      {!peopleTab && !data && !error && <p role="status">Loading…</p>}
      {error && !data && <button onClick={() => setVersion(v => v + 1)}>Try again</button>}

      {data && tab === "outreach" && profile.owner && <Outreach data={data} profile={profile} reload={async (cursor) => {
        const value = await api("/outreach" + (cursor ? "?cursor=" + encodeURIComponent(cursor) : ""));
        setData(cursor ? { ...value, drafts: [...data.drafts, ...value.drafts] } : value);
      }} />}

      {peopleTab && <CustomerWorklist profile={profile} />}

      {data && tab === "operating-rules" && profile.owner && <OperatingRulesDraft key={data.version} data={data} run={run} busy={busy}
        reload={() => setVersion(value => value + 1)} />}

      {data && tab === "visits" && (
        <>
          {data.visits.length === 0 && <p>No visit requests yet.</p>}
          {data.visits.map((v) => {
            const schedule = visitSchedule(v.date, v.time, v.timeZone);
            return (
            <a className="visit-row" href={"#visit/" + v.id} key={v.id}>
              <div>
                <h2>{serviceNames[v.service] || "Home visit"}</h2>
                <p className="visit-schedule">
                  <span>{schedule.date}</span>
                  <span>{schedule.time} · {schedule.zone}</span>
                </p>
              </div>
              <span className="visit-state">{visitStatusLabel(v.status)} <span aria-hidden="true">→</span></span>
            </a>
            );
          })}
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
            <article className="home-desk-record" key={row.id}>
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
            <article className="home-desk-record" key={row.id}>
              <h2>{row.name}</h2>
              <p>{row.bio}</p>
              <p>Requested services: {row.requestedServices.map(value => serviceNames[value] || "Service review").join(", ")}</p>
              {row.enabled && <button type="button" className="secondary" aria-expanded={scheduleHelper === row.id}
                onClick={() => setScheduleHelper(value => value === row.id ? null : row.id)}>
                {scheduleHelper === row.id ? "Hide" : "View"} availability for {row.name}
              </button>}
              {scheduleHelper === row.id && <Availability key={row.id} helperId={row.id} />}
              {profile.owner ? (
                <details className="home-desk-disclosure">
                <summary>Review helper access</summary>
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
                </details>
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
            their original amounts. Save a version, then activate it when you are ready to use those prices.
          </p>
          {profile.enrollmentOnly && <p className="notice">You can prepare and activate prices here. Customers are currently enrolling and requesting calls. Saving prices does not charge anyone or open visit booking.</p>}
          {profile.owner && (
            <details>
              <summary>Create a pricing version</summary>
              <form className="narrow left" onSubmit={saveRates}>
                <div className="two">
                  <label>
                    Cooking per hour, USD
                    <input name="cooking" inputMode="decimal" placeholder="45.00" maxLength="12" required />
                  </label>
                  <label>
                    Cleaning per hour, USD
                    <input name="cleaning" inputMode="decimal" placeholder="35.00" maxLength="12" required />
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
            <details className="home-desk-disclosure" key={card.id} open={card.id === data.activeId}>
              <summary>
                {card.id === data.activeId
                  ? "Active prices"
                  : "Saved pricing version"}{" "}
                <span className="quiet">· {new Date(card.createdAt).toLocaleString()}</span>
              </summary>
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
            </details>
          ))}
        </>
      )}

      {data && tab === "operations" && (
        <>
          {data.configuration && <section className="section" aria-label="Payment configuration">
            <h2>Payment setup</h2>
            <dl className="visit-facts">
              <div><dt>Stripe mode</dt><dd>{label(data.configuration.mode)}</dd></div>
              <div><dt>Secure checkout</dt><dd>{data.configuration.checkoutEnabled ? "Enabled for approved quotes" : "Disabled"}</dd></div>
              <div><dt>Signed webhook</dt><dd>{data.configuration.webhookConfigured ? "Configured" : "Needs setup"}</dd></div>
              <div><dt>Cancellation refunds</dt><dd>{data.configuration.refundsEnabled ? "Enabled" : "Disabled"}</dd></div>
              <div><dt>Helper transfers</dt><dd>{data.configuration.transfersEnabled ? "Enabled after completion and review" : "Disabled"}</dd></div>
            </dl>
            <p>These are configuration checks. A completed customer payment, received confirmation and helper payout must be verified separately.</p>
            {data.enrollmentOnly && <p>Visit booking is closed. You can prepare prices before opening it.</p>}
          </section>}
          <p>
            Provider operations are reviewed here. A Stripe transfer is not a
            confirmed bank payout. Uncertain operations require provider
            reconciliation before retry.
          </p>
          <div className="operation-list">
            {data.operations.map((row) => (
              <article className="home-desk-record" key={row.id}>
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
    </section>
  );
}
