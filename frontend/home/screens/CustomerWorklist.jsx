import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { followupNames, mergePeople } from "../customerWorklist";
import { visitStatusLabel, visitSchedule, serviceNames } from "../visitPresentation";
import "../customerWorklist.css";

export default function CustomerWorklist({ profile }) {
  const [scope, setScope] = useState("needs"), [query, setQuery] = useState("");
  const [data, setData] = useState({ people: [], nextCursor: null });
  const [loading, setLoading] = useState(true), [acting, setActing] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0), sequence = useRef(0);
  const [expanded, setExpanded] = useState(null);
  const busy = loading || acting;
  async function load(cursor) {
    const request = ++sequence.current;
    setLoading(true); setError("");
    try {
      const result = await api("/enrollments/search", { method: "POST", body: { query, scope, ...(cursor ? { cursor } : {}) } });
      if (request === sequence.current) setData(current => ({ ...result, people: cursor ? mergePeople(current.people, result.people) : result.people }));
    } catch (e) { if (request === sequence.current) setError(e.message); }
    finally { if (request === sequence.current) setLoading(false); }
  }
  useEffect(() => {
    setLoading(true); setError("");
    const timer = setTimeout(() => load(), query ? 300 : 0);
    return () => { clearTimeout(timer); sequence.current++; };
  }, [scope, query, refresh]);
  async function command(task, message) {
    sequence.current++; setActing(true); setError(""); setNotice("");
    try { await task(); await load(); setNotice(message); }
    catch (e) { setError(e.message); }
    finally { setActing(false); setLoading(false); }
  }
  function follow(row, status, name) {
    return command(() => api("/enrollments/" + encodeURIComponent(row.customerId) + "/follow-up", { method: "POST",
      body: { status, version: row.version, activityAt: row.activityAt, ...(name ? { name } : {}) } }), name ? "Confirmed name saved." : `${row.name}: ${followupNames[status].toLowerCase()}.`);
  }
  function callAction(row, action, extra = {}) {
    return command(() => api("/callbacks/" + row.callback.id + "/follow-up", { method: "POST", body: {
      action, groupVersion: row.callback.groupVersion, ...extra,
    } }), action === "link" ? "Call requests linked to the existing customer. No account was merged or created."
      : action === "unlink" ? "Call requests are separate again. Account access is unchanged."
        : action === "closed" ? "These call requests are closed. Their history is preserved." : "Call requests marked as being contacted.");
  }
  const enrollmentLink = location.origin + "/#enroll";
  return <div className="people-worklist">
    <div className="people-toolbar">
      <label>Find a person<input type="search" autoComplete="off" placeholder="Name, email or phone" maxLength={100}
        value={query} disabled={acting} onChange={event => setQuery(event.target.value)} /></label>
      <label>Show<select value={scope} disabled={acting} onChange={event => { setScope(event.target.value); setNotice(""); }}>
        <option value="needs">Needs follow-up</option><option value="all">All people</option><option value="accounts">Accounts without a request</option>
      </select></label>
      <button className="secondary" disabled={busy} onClick={() => setRefresh(value => value + 1)}>Refresh</button>
    </div>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status">{notice}</p>}
    <p className="people-list-summary" aria-live="polite">{loading ? "Opening the customer list…" : `${data.people.length} ${data.people.length === 1 ? "person" : "people"} shown${data.nextCursor ? " · more available" : ""}.`}</p>
    {!loading && !data.people.length && !error && <div className="people-empty">
      <h2>{query ? "No match in this list." : scope === "needs" ? "No one is waiting for follow-up." : "No people in this list yet."}</h2>
      <p>{query ? "Try a different name or choose All people." : "New service needs, visit requests and call requests will appear here."}</p>
      {scope !== "all" && <button className="secondary" onClick={() => setScope("all")}>View all people</button>}
    </div>}
    {!!data.people.length && <div className="people-table-wrap" aria-busy={busy}>
      <table className="people-table"><caption className="sr-only">Home customers and their follow-up work</caption>
        <thead><tr><th scope="col">Name and contact</th><th scope="col">Help requested</th><th scope="col">Latest activity</th><th scope="col">Follow-up</th><th scope="col">Review</th></tr></thead>
        <tbody>{data.people.map(row => <React.Fragment key={row.id}><tr>
          <th scope="row"><strong className="people-name">{row.name}</strong>
            {row.nameMissing && <span className="people-note">Ask the customer to add their name in Service needs.</span>}
            {row.email && (row.canContact ? <a className="people-contact" href={"mailto:" + row.email}>{row.email}</a> : <span className="people-contact">{row.email}</span>)}
            {row.phone && (row.canContact ? <a className="people-contact" href={"tel:" + row.phone}>{row.phone}</a> : <span className="people-contact">{row.phone}</span>)}
            {row.kind === "callback" && <span className="people-note">Call request · account not linked</span>}
          </th>
          <td data-label="Help requested"><strong>{serviceNames[row.service || row.visit?.service] || (row.callbackTotal ? "Help by phone" : row.withdrawn ? "Interest withdrawn" : "Not provided yet")}</strong>
            {row.callbackCount > 0 && <span className="people-note">{row.callbackCount} open call {row.callbackCount === 1 ? "request" : "requests"}</span>}
            {row.visit && <span className="people-note">{visitStatusLabel(row.visit.status)}</span>}
            {row.issueOpen && <span className="people-review">Visit issue needs review</span>}
            {row.withdrawn && <span className="people-note">Enrollment withdrawn</span>}
          </td>
          <td data-label="Latest activity"><time dateTime={row.activityAt}>{new Date(row.activityAt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</time>
            {row.callbackCount > 0 && row.callback && <span className="people-note">Call window: {row.callback.preferredTime}</span>}
          </td>
          <td data-label="Follow-up">{row.kind === "customer" ? <select aria-label={"Follow-up for " + row.name} value={row.status} disabled={busy} onChange={event => follow(row, event.target.value)}>
            {Object.entries(followupNames).map(([value, title]) => <option key={value} value={value} disabled={value === "done" && row.issueOpen}>{title}</option>)}
          </select> : <><span className={"people-status people-status-" + row.status}>{row.status === "new" ? "Call requested" : row.status === "done" ? "Calls closed" : "Contacting"}</span>
            {row.callbackCount > 0 && <div className="people-call-actions">{row.status === "new" && <button className="secondary" disabled={busy} onClick={() => callAction(row, "contacting")}>Mark contacting</button>}
              <button className="text" disabled={busy} onClick={() => callAction(row, "closed")}>Close calls</button></div>}</>}
          </td>
          <td data-label="Review"><button className="secondary" aria-expanded={expanded === row.id} aria-controls={"people-details-" + row.id}
            onClick={() => setExpanded(value => value === row.id ? null : row.id)}>{expanded === row.id ? "Close" : "Details"}</button></td>
        </tr>{expanded === row.id && <tr className="people-detail-row"><td colSpan={5} id={"people-details-" + row.id}><div className="people-detail-grid">
          <div><h3>{row.name}</h3>
            {row.visit && <><p>{visitSchedule(row.visit.date, row.visit.time, row.visit.timeZone).date}</p>
              {row.visit.recipientName && <p>Arranged for {row.visit.recipientName}</p>}
              <a className="button secondary" href={"#visit/" + row.visit.id}>View visit</a></>}
            {row.callback && <><p><strong>Call request</strong><br />{row.callback.name}<br />{row.callback.phone}<br />{row.callback.preferredTime}</p>
              <p>{row.callbackTotal} recorded {row.callbackTotal === 1 ? "request" : "requests"}. Repeat requests stay together; history is preserved.</p>
              {row.kind === "customer" && <button className="text" disabled={busy} onClick={() => callAction(row, "unlink")}>Separate this call contact</button>}
            </>}
            {row.kind === "customer" && <p className="people-note">Finishing follow-up closes existing call requests. It does not complete or cancel a visit, or change payment.</p>}
          </div>
            {row.kind === "callback" && <LinkCustomer row={row} busy={busy} link={(extra) => callAction(row, "link", extra)} />}
            {row.kind === "customer" && ["missing", "owner"].includes(row.nameSource) && <ContactName row={row} busy={busy} save={name => follow(row, row.status, name)} />}
          </div></td></tr>}</React.Fragment>)}</tbody>
      </table>
    </div>}
    {data.nextCursor && <button className="secondary" disabled={busy} onClick={() => load(data.nextCursor)}>More people</button>}
    <details className="people-explanation"><summary>About this list and sharing enrollment</summary>
      <p>Registered customers have one row per account. Repeat anonymous calls are grouped by the provided name and phone number. Shared names or phone numbers never merge accounts automatically.</p>
      <p>Only you can open this combined directory. Use Details to review an unlinked call and link it after confirming who the person is. New requests return a customer to Needs follow-up.</p>
      {profile.environment === "staging" && <p className="notice">This is a private staging link. Use the public service desk for real enrollment invitations.</p>}
      <label>Enrollment link<input readOnly value={enrollmentLink} /></label>
      <button className="secondary" onClick={async () => {
        try { await navigator.clipboard.writeText(enrollmentLink); setNotice("Enrollment link copied."); }
        catch { setNotice("Select the enrollment link above to copy it."); }
      }}>Copy enrollment link</button>
    </details>
  </div>;
}

function ContactName({ row, busy, save }) {
  const [name, setName] = useState(row.nameMissing ? "" : row.name);
  return <form onSubmit={event => { event.preventDefault(); save(name); }}>
    <label>Confirmed customer name<input autoComplete="off" required maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>
    <p className="people-note">Use the name the person gave you. This fills a missing contact name without changing their sign-in account.</p>
    <button className="secondary" disabled={busy}>Save confirmed name</button>
  </form>;
}

function LinkCustomer({ row, busy, link }) {
  const [query, setQuery] = useState(""), [matches, setMatches] = useState([]), [selected, setSelected] = useState("");
  const [searching, setSearching] = useState(false), [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [searched, setSearched] = useState(false);
  async function find(event) {
    event.preventDefault(); setSearching(true); setSearched(false); setError(""); setSelected(""); setConfirmed(false);
    try {
      const result = await api("/enrollments/search", { method: "POST", body: { scope: "all", query } });
      setMatches(result.people.filter(person => person.kind === "customer"));
      setSearched(true);
    } catch (e) { setError(e.message); }
    finally { setSearching(false); }
  }
  return <div className="people-link-customer"><h3>Link to an existing customer</h3>
    <p>Confirm the name and contact details first. This organizes your directory; it does not merge accounts or grant access.</p>
    <form onSubmit={find}><label>Find their account<input type="search" required minLength={2} maxLength={100} value={query} onChange={e => setQuery(e.target.value)} /></label>
      <button className="secondary" disabled={busy || searching}>{searching ? "Finding…" : "Find account"}</button></form>
    {error && <p role="alert">{error}</p>}
    {searched && !searching && !matches.length && <p>No matching account. Try the person's email, or ask them to sign in to Home first.</p>}
    {!!matches.length && <><label>Customer account<select value={selected} onChange={e => { setSelected(e.target.value); setConfirmed(false); }}>
      <option value="">Choose a confirmed match</option>{matches.map(person => <option key={person.customerId} value={person.customerId}>{person.name} · {person.email}</option>)}
    </select></label><label className="check"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I confirmed these call requests came from the same person.</label>
      <button disabled={busy || !selected || !confirmed} onClick={() => link({ customerId: selected, confirmedSamePerson: true })}>Link call requests</button></>}
  </div>;
}
