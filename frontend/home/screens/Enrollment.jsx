import React, { useEffect, useState } from "react";
import { api } from "../api";

export const serviceNames = {
  cooking: "Cooking",
  cleaning: "Cleaning",
  both: "Cooking and cleaning",
  not_sure: "Help choosing",
};

export default function Enrollment({ profile }) {
  const [ready, setReady] = useState(false), [version, setVersion] = useState(0);
  const [service, setService] = useState(""), [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [registered, setRegistered] = useState(false), [withdrawn, setWithdrawn] = useState(false);
  useEffect(() => {
    let active = true;
    setError("");
    api("/enrollment").then(({ enrollment }) => {
      if (!active) return;
      setService(enrollment?.service || "");
      setPhone(enrollment?.phone || "");
      setRegistered(Boolean(enrollment?.service));
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
        service, phone, contactConsent: fields.has("contactConsent"),
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
      setRegistered(false); setWithdrawn(true); setSaved(false); setService(""); setPhone("");
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  return <section className="narrow">
    <p className="eyebrow">CookCredit at home</p>
    <h1>What would help?</h1>
    <p>Tell us what you need. CookCredit will contact you to discuss availability. No address, date or payment is needed yet.</p>
    {error && <p className="error" role="alert">{error}</p>}
    {withdrawn && <p role="status">Your service interest and its phone number have been removed. Existing visits stay unchanged.</p>}
    {!ready ? error
      ? <button onClick={() => setVersion(v => v + 1)}>Try again</button>
      : <p role="status">Opening your details…</p>
    : saved ? <div className="section">
      <h2>You’re on the list.</h2>
      <p role="status">Your request for {serviceNames[service].toLowerCase()} is saved. We can reach you at {profile.email}{phone ? " or " + phone : ""}.</p>
      <p>This does not reserve a visit or authorize a charge.</p>
      <div className="actions"><a className="button" href="#request">Arrange a visit</a>
        <button className="secondary" onClick={() => setSaved(false)}>Edit my needs</button></div>
    </div> : <form onSubmit={submit}>
      <fieldset><legend>Choose the help you need</legend>
        {Object.entries(serviceNames).map(([value, title]) => <label className="check" key={value}>
          <input type="radio" name="service" value={value} required checked={service === value} onChange={() => setService(value)} />{title}
        </label>)}
      </fieldset>
      <label>Phone number (optional)<input type="tel" autoComplete="tel" maxLength="40" value={phone} onChange={e => setPhone(e.target.value)} /></label>
      <p>We’ll use your account email: {profile.email}. You can discuss allergies or other requirements privately when arranging a visit.</p>
      <label className="check"><input type="checkbox" name="contactConsent" required />CookCredit may contact me about these services.</label>
      <button disabled={busy}>{busy ? "Saving…" : "Save my service needs"}</button>
    </form>}
    {registered && <button className="text" disabled={busy} onClick={remove}>Remove my service needs</button>}
  </section>;
}
