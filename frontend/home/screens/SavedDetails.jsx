import React, { useState } from "react";
import { api } from "../api";

export default function SavedDetails() {
  const [loaded, setLoaded] = useState(false),
    [household, setHousehold] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [removed, setRemoved] = useState(false);
  const load = async () => {
    setBusy(true);
    setError("");
    try {
      setHousehold((await api("/household")).household);
      setLoaded(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const forget = async () => {
    setBusy(true);
    setError("");
    try {
      await api("/household", { method: "DELETE", body: {} });
      setHousehold(null);
      setRemoved(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <details
      className="section"
      onToggle={(event) => {
        if (event.currentTarget.open && !loaded && !busy) load();
      }}
    >
      <summary>Saved address and preferences</summary>
      <p>
        Details are saved only when you choose to remember them. Removing them
        here stops their use for future requests; existing visit records stay
        unchanged.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {busy && <p role="status">Please wait…</p>}
      {loaded && !household && (
        <p role="status">
          {removed
            ? "Your saved address and preferences have been removed."
            : "You have no saved details."}
        </p>
      )}
      {household && (
        <>
          <p className="preserve">{household.address}</p>
          <p className="preserve">{household.instructions.visitNotes}</p>
          <button className="secondary" disabled={busy} onClick={forget}>
            Forget my saved details
          </button>
        </>
      )}
      {error && (
        <button className="secondary" disabled={busy} onClick={load}>
          Try again
        </button>
      )}
    </details>
  );
}
