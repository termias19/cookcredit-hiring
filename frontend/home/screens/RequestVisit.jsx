import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";

const preferences = [
  ["allergies", "Food allergies or ingredients to avoid"],
  ["provided_meal_instructions", "Follow meal instructions I already have"],
  ["easy_to_chew", "Easy-to-chew meals"],
  ["label_meals", "Label meals and dates"],
  ["storage_help", "Help putting meals away"],
  ["fragrance_free", "Avoid fragranced cleaning products"],
  ["customer_supplies", "Use my cleaning supplies"],
  ["phone_help", "Discuss my request by phone first"],
];
const tasks = [
  ["kitchen", "Kitchen surfaces"],
  ["dishes", "Dishes"],
  ["bathroom", "Bathroom"],
  ["floors", "Floors"],
  ["laundry", "Laundry"],
  ["general_tidy", "General tidying"],
];
export default function RequestVisit({ profile }) {
  const heading = useRef(null);
  const [service, setService] = useState("cooking"),
    [forOther, setForOther] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(null),
    [useSaved, setUseSaved] = useState(false),
    [step, setStep] = useState(0);
  useEffect(() => {
    api("/household")
      .then((value) => setSaved(value.household))
      .catch(() => {});
  }, []);
  useEffect(() => {
    heading.current?.focus();
    window.scrollTo(0, 0);
  }, [step]);
  const submit = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (step < 2) {
      setStep(step + 1);
      window.scrollTo(0, 0);
      return;
    }
    setBusy(true);
    setError("");
    const f = new FormData(form);
    const cooking = service === "cleaning" ? 0 : Number(f.get("cooking")),
      cleaning = service === "cooking" ? 0 : Number(f.get("cleaning"));
    const instructions = {
      preferences: f.getAll("preferences"),
      cleaningTasks: service === "cooking" ? [] : f.getAll("cleaningTasks"),
      visitNotes: f.get("notes"),
    };
    const body = {
      service,
      date: f.get("date"),
      time: f.get("time"),
      durationMinutes: cooking + cleaning,
      serviceMinutes: { cooking, cleaning },
      address: f.get("address"),
      instructions,
      consent: {
        version: profile.consentVersion,
        shareWithAssignedHelper: f.get("consent") === "on",
      },
    };
    if (forOther)
      body.arrangingFor = {
        name: f.get("recipient"),
        permissionConfirmed: f.get("permission") === "on",
      };
    try {
      const value = await api("/visits", { method: "POST", body });
      // Saving household details is a separate, explicit choice. A failure must
      // never make an already-created visit appear to have failed.
      if (f.get("remember") === "on")
        await api("/household", {
          method: "PUT",
          body: { address: body.address, instructions, remember: true },
        }).catch(() => {});
      location.hash = "visit/" + value.id;
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="narrow">
      <a href="#home">← Home</a>
      <p className="eyebrow">Step {step + 1} of 3</p>
      <h1 ref={heading} tabIndex="-1">
        {["What would help?", "Make it yours.", "Where and when?"][step]}
      </h1>
      <p>
        Sending a request is free. We’ll review availability and send you a full
        quote before you pay.
      </p>
      <form onSubmit={submit}>
        <fieldset hidden={step !== 0}>
          <legend>Choose your help</legend>
          <div className="service-choices">
            {[
              ["cooking", "Cooking"],
              ["cleaning", "Cleaning"],
              ["both", "Cooking & cleaning"],
            ].map(([value, title]) => (
              <label key={value} className="check">
                <input
                  type="radio"
                  name="service"
                  checked={service === value}
                  onChange={() => setService(value)}
                />
                {title}
              </label>
            ))}
          </div>
          {service !== "cleaning" && (
            <label>
              Cooking time
              <select name="cooking" defaultValue="120">
                {[60, 90, 120, 150, 180, 210, 240].map((v) => (
                  <option key={v} value={v}>
                    {v / 60} {v === 60 ? "hour" : "hours"}
                  </option>
                ))}
              </select>
            </label>
          )}
          {service !== "cooking" && (
            <label>
              Cleaning time
              <select name="cleaning" defaultValue="60">
                {[60, 90, 120, 150, 180, 210, 240].map((v) => (
                  <option key={v} value={v}>
                    {v / 60} {v === 60 ? "hour" : "hours"}
                  </option>
                ))}
              </select>
            </label>
          )}
          <p className="quiet">
            Need help choosing the right time? Select a phone discussion on the
            next step.
          </p>
        </fieldset>
        <fieldset hidden={step !== 1}>
          <legend>Preferences and instructions</legend>
          {saved && (
            <label className="check">
              <input
                type="checkbox"
                checked={useSaved}
                onChange={(e) => setUseSaved(e.target.checked)}
              />
              Use my saved address and preferences
            </label>
          )}
          <div key={useSaved ? "saved" : "fresh"}>
            {preferences.map(([value, title]) => (
              <label className="check" key={value}>
                <input
                  type="checkbox"
                  name="preferences"
                  value={value}
                  defaultChecked={
                    useSaved && saved?.instructions.preferences.includes(value)
                  }
                />
                {title}
              </label>
            ))}
            {service !== "cooking" && (
              <>
                <h2>What needs cleaning?</h2>
                {tasks.map(([value, title]) => (
                  <label className="check" key={value}>
                    <input
                      type="checkbox"
                      name="cleaningTasks"
                      value={value}
                      defaultChecked={
                        useSaved &&
                        saved?.instructions.cleaningTasks.includes(value)
                      }
                    />
                    {title}
                  </label>
                ))}
              </>
            )}
            <label>
              Anything we should know?
              <textarea
                name="notes"
                maxLength="1000"
                rows="5"
                defaultValue={useSaved ? saved?.instructions.visitNotes : ""}
                placeholder="For example: avoid peanuts; prepare softer meals; ring the doorbell and allow me time to answer."
              />
            </label>
          </div>
          <p className="quiet">
            Share only what your helper needs for this visit. We offer household
            help, not medical care or dietary advice. An allergen-free kitchen
            cannot be guaranteed.
          </p>
          <label className="check">
            <input
              type="checkbox"
              checked={forOther}
              onChange={(e) => setForOther(e.target.checked)}
            />
            I’m arranging this for someone else
          </label>
          {forOther && (
            <>
              <label>
                Their name
                <input name="recipient" maxLength="120" required={step === 1} />
              </label>
              <label className="check">
                <input
                  name="permission"
                  type="checkbox"
                  required={step === 1}
                />
                I have their permission to arrange this visit and share these
                details.
              </label>
            </>
          )}
        </fieldset>
        <fieldset hidden={step !== 2}>
          <legend>Your visit details</legend>
          <label>
            Service address
            <textarea
              key={useSaved ? "saved-address" : "new-address"}
              name="address"
              autoComplete="street-address"
              maxLength="400"
              rows="3"
              defaultValue={useSaved ? saved?.address : ""}
              required={step === 2}
            />
          </label>
          <div className="two">
            <label>
              Preferred date
              <input
                type="date"
                name="date"
                min={new Date().toLocaleDateString("en-CA")}
                required={step === 2}
              />
            </label>
            <label>
              Preferred start time
              <input
                type="time"
                name="time"
                defaultValue="10:00"
                step="1800"
                required={step === 2}
              />
            </label>
          </div>
          <p className="quiet">
            Times are in America/New_York. Your requested time is subject to
            availability.
          </p>
          <label className="check">
            <input name="consent" type="checkbox" required={step === 2} />
            {profile.consentText}
          </label>
          <label className="check">
            <input name="remember" type="checkbox" />
            Save my address and preferences for future visits on this account
          </label>
        </fieldset>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="actions">
          {step > 0 && (
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => setStep((s) => s - 1)}
            >
              Back
            </button>
          )}
          <button disabled={busy}>
            {busy
              ? "Sending request…"
              : step === 2
                ? "Send my request"
                : "Continue"}
          </button>
        </div>
      </form>
    </section>
  );
}
