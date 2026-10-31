import React, { useState } from "react";
import { api } from "../api";

const days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const dayNames = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const zones = [["America/New_York", "Eastern time"], ["America/Chicago", "Central time"],
  ["America/Denver", "Mountain time"], ["America/Phoenix", "Arizona time"],
  ["America/Los_Angeles", "Pacific time"], ["America/Anchorage", "Alaska time"], ["Pacific/Honolulu", "Hawaii time"]];
const clock = (value) => `${String(Math.floor((value % 1440) / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
const minutes = (value) => {
  const [hour, minute] = String(value).split(":").map(Number);
  return hour * 60 + minute;
};

export default function OperatingRulesDraft({ data, run, busy, reload }) {
  const rules = data.rules;
  const [open, setOpen] = useState(Object.fromEntries(days.map(day => [day, rules.weeklyHours.some(w => w.day === day)])));
  const [dirty, setDirty] = useState(false), [reviewed, setReviewed] = useState(false);
  const active = data.activePolicy;
  const complete = data.version > 0 && rules.weeklyHours.length > 0 && Number.isInteger(rules.bufferMinutes);
  const submit = (event) => {
    event.preventDefault();
    const f = new FormData(event.currentTarget), buffer = f.get("buffer");
    return run(() => api("/operating-rules", { method: "PUT", body: {
      version: data.version,
      rules: {
        states: String(f.get("states")).split(",").map(v => v.trim().toUpperCase()).filter(Boolean),
        timeZone: f.get("zone"), noticeHours: Number(f.get("notice")), shortNoticeHours: Number(f.get("short")),
        bufferMinutes: buffer == null || buffer === "" ? null : Number(buffer),
        weeklyHours: days.filter(day => f.has(day)).map(day => ({ day,
          startMinute: minutes(f.get(day + "-start")), endMinute: minutes(f.get(day + "-end")) || 1440,
        })),
      },
    }}));
  };
  const activate = () => run(() => api("/operating-rules/activate", { method: "POST", body: {
    version: data.version, reviewConfirmed: true,
  }}), "Operating rules activated. Visit requests still require review.");
  return <section className="section">
    <p className="eyebrow">Saved draft and active rules</p>
    <h2>Service area and operating rules</h2>
    <p>Plan where and when CookCredit can work. Saving this draft does not publish appointment slots or change existing visit requests.</p>
    {active ? <p className="notice" role="status">Active rules: version {active.version}, in {zones.find(([value]) => value === active.rules.timeZone)?.[1] || active.rules.timeZone}.
      {active.version === data.version ? " This saved draft is active." : " This draft has not replaced the active rules."}
    </p> : <p>No operating rules are active yet. Requests use the existing manual review flow until a saved draft is activated.</p>}
    <form onSubmit={submit} onChange={() => { setDirty(true); setReviewed(false); }}>
      <label>States to serve<input name="states" defaultValue={rules.states.join(", ")} maxLength="40" required disabled={busy} /></label>
      <p className="quiet">Use US postal abbreviations, such as GA. Additional states need approved helper coverage before launch.</p>
      <label>Service time zone<select name="zone" defaultValue={rules.timeZone} disabled={busy}>
        {zones.map(([value, title]) => <option key={value} value={value}>{title}</option>)}
        {!zones.some(([value]) => value === rules.timeZone) && <option value={rules.timeZone}>{rules.timeZone}</option>}
      </select></label>
      <div className="two">
        <label>Default booking notice, hours<input name="notice" type="number" min="6" max="168" step="1" defaultValue={rules.noticeHours} required disabled={busy} /></label>
        <label>Short-notice threshold to consider manually, hours<input name="short" type="number" min="6" max="168" step="1" defaultValue={rules.shortNoticeHours} required disabled={busy} /></label>
      </div>
      <p className="quiet">Short-notice requests need individual review. This setting does not guarantee a helper.</p>
      <label>Travel buffer between visits, minutes<input name="buffer" type="number" min="0" max="180" step="15" defaultValue={rules.bufferMinutes ?? ""} disabled={busy} /></label>
      <p className="quiet">Leave blank until a travel buffer has been agreed.</p>
      <fieldset><legend>Draft operating hours</legend>
        <p>Choose the days you plan to serve. Unchecked days stay closed in the draft. An ending time of 00:00 means midnight at the end of that day.</p>
        {days.map((day, i) => {
          const window = rules.weeklyHours.find(w => w.day === day);
          return <div className="section" key={day}>
            <label className="check"><input type="checkbox" name={day} checked={open[day]} disabled={busy} onChange={event => setOpen(v => ({ ...v, [day]: event.target.checked }))} />{dayNames[i]}</label>
            <div className="two">
              <label>{dayNames[i]} from<input name={day + "-start"} type="time" step="900" defaultValue={clock(window?.startMinute ?? 540)} disabled={!open[day] || busy} required={open[day]} /></label>
              <label>{dayNames[i]} until<input name={day + "-end"} type="time" step="900" defaultValue={clock(window?.endMinute ?? 1020)} disabled={!open[day] || busy} required={open[day]} /></label>
            </div>
          </div>;
        })}
      </fieldset>
      {!Object.values(open).some(Boolean) && <p>All days are currently closed in this draft.</p>}
      <p>These business hours are separate from each helper’s own availability. Saving does not reserve time, assign a helper or enable payments.</p>
      <button disabled={busy}>{busy ? "Saving draft…" : "Save operating draft"}</button>
    </form>
    {reload && <>
      {dirty && <p>Reloading replaces your unsaved edits with the saved draft.</p>}
      <button type="button" className="secondary" disabled={busy} onClick={reload}>Reload saved rules</button>
    </>}
    <section className="section">
      <h3>Apply the saved rules</h3>
      <p>Activation checks requests and scheduling changes against these hours, notice and travel buffer. Every visit still needs review of the exact service area, route, current traffic and weather, helper and price. Suggested times are not reserved or automatically confirmed. Activation does not open public bookings or enable payments.</p>
      {!complete && <p>Save operating hours and a travel buffer before activation.</p>}
      {dirty && <p>Save your changes before activating this draft.</p>}
      <label className="check"><input type="checkbox" checked={reviewed} disabled={busy || dirty || !complete || active?.version === data.version}
        onChange={event => setReviewed(event.target.checked)} />I reviewed the saved rules and want them applied to the manual visit-request and assignment flow.</label>
      <button type="button" disabled={busy || dirty || !complete || !reviewed || active?.version === data.version} onClick={activate}>
        Activate saved rules
      </button>
    </section>
  </section>;
}
