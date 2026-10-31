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

export default function OperatingRulesDraft({ data, run, busy }) {
  const rules = data.rules;
  const [open, setOpen] = useState(Object.fromEntries(days.map(day => [day, rules.weeklyHours.some(w => w.day === day)])));
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
  return <section className="section">
    <p className="eyebrow">Draft only</p>
    <h2>Service area and operating rules</h2>
    <p>Plan where and when CookCredit can work. Saving this draft does not publish appointment slots or change existing visit requests.</p>
    <form onSubmit={submit}>
      <label>States to serve<input name="states" defaultValue={rules.states.join(", ")} maxLength="40" required /></label>
      <p className="quiet">Use US postal abbreviations, such as GA. Additional states need approved helper coverage before launch.</p>
      <label>Service time zone<select name="zone" defaultValue={rules.timeZone}>
        {zones.map(([value, title]) => <option key={value} value={value}>{title}</option>)}
        {!zones.some(([value]) => value === rules.timeZone) && <option value={rules.timeZone}>{rules.timeZone}</option>}
      </select></label>
      <div className="two">
        <label>Default booking notice, hours<input name="notice" type="number" min="6" max="168" step="1" defaultValue={rules.noticeHours} required /></label>
        <label>Short-notice threshold to consider manually, hours<input name="short" type="number" min="6" max="168" step="1" defaultValue={rules.shortNoticeHours} required /></label>
      </div>
      <p className="quiet">Short-notice requests need individual review. This setting does not guarantee a helper.</p>
      <label>Travel buffer between visits, minutes<input name="buffer" type="number" min="0" max="180" step="15" defaultValue={rules.bufferMinutes ?? ""} /></label>
      <p className="quiet">Leave blank until a travel buffer has been agreed.</p>
      <fieldset><legend>Draft operating hours</legend>
        <p>Choose the days you plan to serve. Unchecked days stay closed in the draft. An ending time of 00:00 means midnight at the end of that day.</p>
        {days.map((day, i) => {
          const window = rules.weeklyHours.find(w => w.day === day);
          return <div className="section" key={day}>
            <label className="check"><input type="checkbox" name={day} checked={open[day]} onChange={event => setOpen(v => ({ ...v, [day]: event.target.checked }))} />{dayNames[i]}</label>
            <div className="two">
              <label>{dayNames[i]} from<input name={day + "-start"} type="time" step="900" defaultValue={clock(window?.startMinute ?? 540)} disabled={!open[day]} required={open[day]} /></label>
              <label>{dayNames[i]} until<input name={day + "-end"} type="time" step="900" defaultValue={clock(window?.endMinute ?? 1020)} disabled={!open[day]} required={open[day]} /></label>
            </div>
          </div>;
        })}
      </fieldset>
      {!Object.values(open).some(Boolean) && <p>All days are currently closed in this draft.</p>}
      <p>These planning hours are separate from each helper’s confirmed availability. Appointment slots remain closed.</p>
      <button disabled={busy}>{busy ? "Saving draft…" : "Save operating draft"}</button>
    </form>
  </section>;
}
