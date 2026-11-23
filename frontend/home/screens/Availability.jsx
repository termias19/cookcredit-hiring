import React, { useEffect, useState } from "react";
import { api } from "../api";

const days = [["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"],
  ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"]];
const zones = [["America/New_York", "Eastern time"], ["America/Chicago", "Central time"],
  ["America/Denver", "Mountain time"], ["America/Phoenix", "Arizona time"],
  ["America/Los_Angeles", "Pacific time"], ["America/Anchorage", "Alaska time"], ["Pacific/Honolulu", "Hawaii time"]];
const hour = value => value === 24 ? "Midnight at end of day" : `${value % 12 || 12}:00 ${value < 12 ? "AM" : "PM"}`;
function localDay(zone) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: zone,
    year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date()).map(p => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function ScheduleForm({ data, save, busy }) {
  const [open, setOpen] = useState(Object.fromEntries(days.map(([day]) => [day, data.weeklyHours.some(w => w.day === day)])));
  const [blocked, setBlocked] = useState(data.blockedDates), [candidate, setCandidate] = useState("");
  const [zone, setZone] = useState(data.timeZone);
  const today = localDay(zone), lastDay = new Date(Date.parse(today + "T00:00:00Z") + 365 * 86400000).toISOString().slice(0, 10);
  return <form onSubmit={event => {
    event.preventDefault(); const f = new FormData(event.currentTarget);
    return save({ version: data.version, timeZone: zone, blockedDates: blocked,
      weeklyHours: days.filter(([day]) => f.has(day)).map(([day]) => ({ day,
        startHour: Number(f.get(day + "-start")), endHour: Number(f.get(day + "-end")),
      })),
    });
  }}>
    <label>Your schedule time zone<select name="zone" value={zone} disabled={busy} onChange={event => setZone(event.target.value)}>
      {zones.map(([value, title]) => <option key={value} value={value}>{title}</option>)}
      {!zones.some(([value]) => value === zone) && <option value={zone}>{zone}</option>}
    </select></label>
    <fieldset><legend>Hours you can work</legend>
      <p>Check the days you can work and choose your hours. Leave a day unchecked if you are unavailable. These are your hours, not a promise of paid work.</p>
      {days.map(([day, title]) => {
        const window = data.weeklyHours.find(w => w.day === day);
        return <div className="section" key={day}>
          <label className="check"><input type="checkbox" name={day} checked={open[day]} disabled={busy} onChange={event => setOpen(v => ({ ...v, [day]: event.target.checked }))} />{title}</label>
          <div className="two">
            <label>{title} from<select name={day + "-start"} defaultValue={window?.startHour ?? 9} disabled={!open[day] || busy}>
              {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{hour(h)}</option>)}
            </select></label>
            <label>{title} until<select name={day + "-end"} defaultValue={window?.endHour ?? 17} disabled={!open[day] || busy}>
              {Array.from({ length: 24 }, (_, i) => i + 1).map(h => <option key={h} value={h}>{hour(h)}</option>)}
            </select></label>
          </div>
        </div>;
      })}
    </fieldset>
    {!Object.values(open).some(Boolean) && <p>You have no available work days selected.</p>}
    <fieldset><legend>Dates you cannot work</legend>
      <p>These dates override your weekly hours. No reason is needed. Choose up to 60 dates within the next year.</p>
      <label>Unavailable date<input type="date" value={candidate} min={today} max={lastDay} disabled={busy} onChange={event => setCandidate(event.target.value)} /></label>
      <button className="secondary" type="button" disabled={busy || !candidate || candidate < today || candidate > lastDay || blocked.includes(candidate) || blocked.length >= 60}
        onClick={() => { setBlocked(v => [...v, candidate].sort()); setCandidate(""); }}>Add unavailable date</button>
      {blocked.length === 0 ? <p>No unavailable dates selected.</p> : <ul>{blocked.map(day => <li key={day}>{day} {" "}
        <button className="text" type="button" disabled={busy} onClick={() => setBlocked(v => v.filter(value => value !== day))}>Remove {day}</button>
      </li>)}</ul>}
    </fieldset>
    <p>Saving cannot cancel or move an assigned visit. Ask CookCredit to arrange a change first if a visit conflicts with your new hours.</p>
    <button disabled={busy}>{busy ? "Saving availability…" : "Save availability"}</button>
  </form>;
}

export default function Availability({ helperId = null }) {
  const [data, setData] = useState(null), [error, setError] = useState("");
  const [notice, setNotice] = useState(""), [busy, setBusy] = useState(false), [reload, setReload] = useState(0);
  const path = helperId ? "/helpers/" + encodeURIComponent(helperId) + "/availability" : "/availability";
  useEffect(() => {
    let active = true; setData(null); setError("");
    api(path).then(value => { if (active) setData(value); }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [path, reload]);
  const save = async body => {
    setBusy(true); setError(""); setNotice("");
    try {
      await api(path, { method: "PUT", body });
      setNotice("Availability saved."); setReload(v => v + 1);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  return <section className={helperId ? "section" : "page"}>
    {helperId ? <h3>Helper availability</h3> : <><p className="eyebrow">CookCredit helpers</p><h1>Your availability</h1></>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {!data && !error && <p role="status">Loading availability…</p>}
    {error && <button className="secondary" onClick={() => { setNotice(""); setReload(v => v + 1); }}>Refresh availability</button>}
    {data && <>
      {!data.configured && <p>No availability has been saved. Assignment stays unavailable until the helper saves their hours.</p>}
      {helperId ? <>
        <p>Read only. Only this helper can change their availability. Assignment also checks existing visits; these hours do not guarantee a booking.</p>
        <p>Time zone: {data.timeZone}</p>
        {data.weeklyHours.length ? <ul>{data.weeklyHours.map(w => <li key={w.day}>{days.find(([day]) => day === w.day)?.[1]}: {hour(w.startHour)} – {hour(w.endHour)}</li>)}</ul> : <p>No available work days.</p>}
        <p>Unavailable dates: {data.blockedDates.length ? data.blockedDates.join(", ") : "None saved"}.</p>
      </> : <ScheduleForm key={data.version} data={data} save={save} busy={busy} />}
    </>}
  </section>;
}
