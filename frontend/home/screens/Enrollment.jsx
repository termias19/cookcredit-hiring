import React, { useEffect, useState } from "react";
import { api } from "../api";
import { contactName } from "../customerWorklist";
import SavedDetails from "./SavedDetails";
import { serviceNames } from "../visitPresentation";

export default function Enrollment({ profile, onArrange }) {
  const [ready, setReady] = useState(false), [version, setVersion] = useState(0);
  const [service, setService] = useState(""), [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [registered, setRegistered] = useState(false), [withdrawn, setWithdrawn] = useState(false);
  const [confirmRemoval, setConfirmRemoval] = useState(false);
  useEffect(() => {
    let active = true;
    setError("");
    api("/enrollment").then(({ enrollment }) => {
      if (!active) return;
      setService(enrollment?.service || "");
      setPhone(enrollment?.phone || "");
      setName(enrollment?.name || contactName(profile.name, profile.email));
      setRegistered(Boolean(enrollment?.service));
      setSaved(Boolean(enrollment?.service));
      setWithdrawn(enrollment?.status === "withdrawn");
      setReady(true);
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [version]);
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true); setError(""); setSaved(false);
    try {
      const fields = new FormData(event.currentTarget);
      await api("/enrollment", { method: "PUT", body: {
        service, phone, name, contactConsent: fields.has("contactConsent"),
      }});
      setSaved(true);
      setRegistered(true); setWithdrawn(false);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true); setError("");
    try {
      await api("/enrollment", { method: "DELETE", body: {} });
      setRegistered(false); setWithdrawn(true); setSaved(false); setService(""); setPhone(""); setConfirmRemoval(false);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  return <section className="narrow">
    <div className="customer-preferences-heading"><div>
    <p className="eyebrow">CookCredit at home</p>
    <h1>{profile.enrollmentOnly ? "What would help?" : "Service preferences"}</h1>
    </div>{saved && !profile.enrollmentOnly && <a className="button" href="#request" onClick={() => onArrange?.(service)}>Request a visit</a>}</div>
    <p>{profile.enrollmentOnly
      ? "Choose the kind of help you are interested in. Enrollment and call requests are open; visit booking, scheduling and payments are not available yet."
      : "Update your contact details and the help you’re interested in."}</p>
    {error && <p className="error" role="alert">{error}</p>}
    {withdrawn && <p role="status">Your service interest and its phone number have been removed. Existing visits stay unchanged.</p>}
    {!ready ? error
      ? <button onClick={() => setVersion(v => v + 1)}>Try again</button>
      : <p role="status">Opening your details…</p>
    : saved ? <div className="section customer-preferences-saved">
      <h2>{profile.enrollmentOnly ? "You’re on the list." : "Your preferences are saved."}</h2>
      <p role="status">Your interest in {serviceNames[service].toLowerCase()} is saved. A visit has not been booked or charged.</p>
      <dl className="customer-contact-facts">
        <div><dt>Name</dt><dd>{name || "Please add your name using Edit my needs."}</dd></div>
        <div><dt>Email</dt><dd>{profile.email}</dd></div>
        {phone && <div><dt>Phone</dt><dd>{phone}</dd></div>}
      </dl>
      <div className="actions">{profile.enrollmentOnly && <a className="button" href="#callback">Request a call</a>}
        <button className="secondary" onClick={() => setSaved(false)}>Edit my needs</button></div>
    </div> : <form onSubmit={submit}>
      <label>Your full name<input autoComplete="name" maxLength={120} required value={name} onChange={event => setName(event.target.value)} /></label>
      <fieldset><legend>Choose the help you need</legend>
        {Object.entries(serviceNames).map(([value, title]) => <label className="check" key={value}>
          <input type="radio" name="service" value={value} required checked={service === value} onChange={() => setService(value)} />{title}
        </label>)}
      </fieldset>
      <label>Phone number (optional)<input type="tel" autoComplete="tel" maxLength="40" value={phone} onChange={e => setPhone(e.target.value)} /></label>
      <p>We’ll use your account email: {profile.email}. Please do not include addresses, medical details or allergy instructions here.</p>
      <label className="check"><input type="checkbox" name="contactConsent" required />CookCredit may contact me about these services.</label>
      <button disabled={busy}>{busy ? "Saving…" : "Save my service needs"}</button>
    </form>}
    {!profile.enrollmentOnly && <SavedDetails />}
    <details><summary>Your information</summary>
      <p>Only the CookCredit Home owner can open the enrollment directory. It contains your account name and email, selected service interest and optional phone number, so CookCredit can follow up with your permission. This is service-contact permission, not advertising consent.</p>
      <p>Use “Remove my service needs” to withdraw your interest and remove the optional phone from this enrollment. Your CookCredit login remains. Email <a href="mailto:connectwithus@cookcredit.com">connectwithus@cookcredit.com</a> for account or data requests. Read our <a href="https://cookcredit.com/privacy.html">Privacy Policy</a>.</p>
      {registered && (confirmRemoval ? <div className="notice" role="status"><p>Remove your service interest and its contact details? Your account and existing visits will stay saved.</p>
        <div className="actions"><button className="secondary" disabled={busy} onClick={remove}>Confirm removal</button>
          <button className="text" disabled={busy} onClick={() => setConfirmRemoval(false)}>Keep my service needs</button></div></div>
        : <button className="text" disabled={busy} onClick={() => setConfirmRemoval(true)}>Remove my service needs</button>)}
    </details>
  </section>;
}
