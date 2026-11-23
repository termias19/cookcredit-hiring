import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { reportClientError } from "../../src/utils/errorReporting";

const clock = value => {
  const [hour, minute] = value.split(":").map(Number);
  return `${hour % 12 || 12}:${String(minute).padStart(2, "0")} ${hour < 12 ? "AM" : "PM"}`;
};

export default function SuggestedTimes({ date, service, durationMinutes, state, timeZone, selectedTime, onChoose, onTimeZone, disabled = false }) {
  const [view, setView] = useState(null), request = useRef(0);
  const query = `${date}:${service}:${durationMinutes}:${state || ""}`;
  // Changing the request invalidates the old suggestions and late responses.
  // It does not start a network request or reserve a time.
  useEffect(() => {
    request.current += 1; setView(null);
    return () => { request.current += 1; };
  }, [query]);
  const current = view?.query === query ? view : null;
  const check = async () => {
    const ticket = ++request.current;
    setView({ query, busy: true });
    try {
      const value = await api(`/slots?date=${encodeURIComponent(date)}&durationMinutes=${durationMinutes}&service=${encodeURIComponent(service)}` +
        (state ? `&state=${encodeURIComponent(state)}` : ""));
      if (value.date !== date || typeof value.timeZone !== "string" || !Number.isInteger(value.policyVersion) || value.policyVersion < 1 ||
          value.reviewRequired !== true || value.reservesTime !== false || value.areaReviewRequired !== true ||
          !Array.isArray(value.slots) || value.slots.length > 48 || value.slots.some(slot =>
            !slot || typeof slot.time !== "string" || !/^([01]\d|2[0-3]):[0-5]\d$/.test(slot.time) || slot.durationMinutes !== durationMinutes)) {
        reportClientError("api_response_invalid");
        throw new Error("We could not read these suggestions. Retry, or send a preferred time for review.");
      }
      if (request.current === ticket) {
        onTimeZone?.(value.timeZone);
        setView({ query, value, busy: false });
      }
    } catch (error) {
      if (request.current === ticket) setView({ query, busy: false, error: error.code === "operating_rules_required"
        ? "Suggested times aren’t available yet. You can still send a preferred-time request for CookCredit review."
        : error.message });
    }
  };
  return <section className="section" aria-label="Suggested visit times">
    <h2>Help choosing a time</h2>
    <p>Check starting times for your selected date and amount of work. Your address, travel route, helper and full price still need review. No time is reserved.</p>
    <button type="button" className="secondary" disabled={disabled || current?.busy || !/^\d{4}-\d{2}-\d{2}$/.test(date) || durationMinutes < 60 || durationMinutes > 480}
      onClick={check}>{current?.busy ? "Checking times…" : "Check suggested times"}</button>
    {!date && <p className="quiet">Choose a preferred date first.</p>}
    {current?.error && <p className="error" role="alert">{current.error}</p>}
    {current?.value && <>
      <p role="status">{current.value.slots.length ? "Suggested starting times" : "No suggested times were found for this date"} in {current.value.timeZone}.</p>
      {current.value.slots.length ? <div className="actions" role="group" aria-label="Suggested starting times">
        {current.value.slots.map(slot => <button type="button" key={slot.time} disabled={disabled}
          className={selectedTime === slot.time ? "" : "secondary"} aria-pressed={selectedTime === slot.time}
          onClick={() => onChoose(slot.time)}>{clock(slot.time)}</button>)}
      </div> : <p>Try another date, or <a href="#callback">ask us to call you</a> to discuss a different time. CookCredit must review your request before a visit can be arranged.</p>}
      <p className="quiet">Selecting a suggestion only fills in your preferred start time. It does not book a visit or charge you.</p>
    </>}
    {!current?.value && timeZone && <p className="quiet">Your form uses {timeZone}.</p>}
  </section>;
}
