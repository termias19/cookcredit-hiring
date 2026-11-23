import React, { useState } from "react";
import { api } from "../api";
import { outreachPictures, outreachDestinations, outreachTemplates, outreachLink, outreachText, emailDraftLink } from "../outreach";

const newDraft = (template = outreachTemplates[0]) => ({ ...template, postalAddress: "", design: { ...template.design } });
const payload = (draft) => ({ subject: draft.subject, body: draft.body, postalAddress: draft.postalAddress, design: draft.design });

export default function Outreach({ data, reload, profile }) {
  const [draft, setDraft] = useState(() => newDraft());
  const [channel, setChannel] = useState("text"), [busy, setBusy] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [email, setEmail] = useState(null);
  const base = location.origin + "/", picture = outreachPictures[draft.design.image];
  const link = outreachLink(base, draft.design.destination);
  const update = (changes) => { setDraft(value => ({ ...value, ...changes })); setEmail(null); setNotice(""); setError(""); };
  const choose = (value) => { setDraft(value); setEmail(null); setNotice(""); setError(""); };
  async function run(task) {
    setBusy(true); setError(""); setNotice("");
    try { await task(); } catch (e) { setError(e.message || "We could not finish. Please retry."); }
    finally { setBusy(false); }
  }
  async function copy(text, success) {
    try { await navigator.clipboard.writeText(text); setNotice(success); }
    catch { throw new Error("Copying is unavailable in this browser. Select the text in the message box and copy it, or download the email."); }
  }
  async function save(action = "save", item = draft) {
    await run(async () => {
      const body = action === "save" ? { ...payload(item), action, ...(item.id ? { revision: item.revision } : {}) } : { action, revision: item.revision };
      const value = await api("/outreach" + (item.id ? "/" + item.id : ""), { method: item.id ? "PUT" : "POST", body });
      if (action === "save") setDraft(current => ({ ...current, ...value }));
      else if (item.id === draft.id) choose(newDraft());
      await reload();
      setNotice(action === "save" ? "Draft saved. Nothing was sent." : action === "trash" ? "Draft moved to trash." : "Draft restored.");
    });
  }
  function download(content, type, filename) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename;
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    setNotice("Download requested. Check your browser’s Downloads.");
  }
  const text = outreachText(draft, base);
  return <div className="home-outreach">
    <p>Prepare a message, preview it, then share it yourself. Only your owner account can open this workspace. Saving a draft never sends it.</p>
    {profile.environment === "staging" && <p className="notice">Private staging links are for checks only. Use the public service desk for customer invitations.</p>}
    {error && <p className="error" role="alert">{error}</p>}{notice && <p className="notice" role="status">{notice}</p>}
    <div className="outreach-templates" aria-label="Start with a message">
      {outreachTemplates.map(template => <button className="secondary" disabled={busy} key={template.title} onClick={() => choose(newDraft(template))}>{template.title}</button>)}
    </div>
    <div className="outreach-layout">
      <div className="outreach-editor">
        <h2>Make it yours</h2>
        <form onSubmit={event => { event.preventDefault(); save(); }}>
          <label>Headline / email subject<input required maxLength={150} value={draft.subject} onChange={e => update({ subject: e.target.value })} /></label>
          <label>Your message<textarea required rows={6} maxLength={3000} value={draft.body} onChange={e => update({ body: e.target.value })} /></label>
          <label>Food picture<select value={draft.design.image} onChange={e => update({ design: { ...draft.design, image: e.target.value } })}>
            <option value="dinner">Chicken and vegetables</option><option value="stew">Vegetable and bean stew</option>
          </select></label>
          <label>Where the button takes people<select value={draft.design.destination} onChange={e => update({ design: { ...draft.design, destination: e.target.value } })}>
            {Object.entries(outreachDestinations).map(([key, title]) => <option key={key} value={key}>{title}</option>)}
          </select></label>
          <p className="quiet">These are illustrative meals. Confirm ingredients and any allergy requirements privately for each visit.</p>
          <div className="actions"><button disabled={busy}>{busy ? "Working…" : "Save draft"}</button><button type="button" className="secondary" disabled={busy} onClick={() => choose(newDraft())}>Start a new draft</button></div>
        </form>
      </div>
      <div className="outreach-preview-wrap">
        <p className="eyebrow">What people will see</p>
        <article className="outreach-preview" id="home-outreach-print">
          <div className="outreach-brand"><img src="/assets/cookcredit-mark-orange.svg" alt="" /><span>CookCredit<small>At home</small></span></div>
          <img className="outreach-photo" src={picture.file} alt={picture.alt} width="1536" height="1024" />
          <div className="outreach-preview-copy"><h2>{draft.subject}</h2><p className="outreach-message">{draft.body}</p>
            <a className="button" href={link} target="_blank" rel="noopener">{outreachDestinations[draft.design.destination]}</a>
            <p className="outreach-payment-note">Enrollment is free. Review your full quote before paying for a visit.</p>
            <p>Prefer a conversation? <a href={base + "#help"} target="_blank" rel="noopener">Ask us to call you</a>.</p>
            <p className="outreach-print-link">{link}</p>
            <p className="quiet">connectwithus@cookcredit.com</p>
            <p className="outreach-photo-note">Illustrative meal. Meals and ingredients are agreed for each visit.</p>
          </div>
        </article>
      </div>
    </div>
    <section className="outreach-sharing" aria-label="Share your message">
      <h2>Choose how to share</h2>
      <div className="outreach-channels" role="group" aria-label="Sharing format">
        {[['text','Text or WhatsApp'],['email','Email'],['print','Printed flyer']].map(([key,title]) => <button key={key} className={channel === key ? "selected" : "secondary"} aria-pressed={channel === key} onClick={() => { setChannel(key); setNotice(""); setError(""); }}>{title}</button>)}
      </div>
      {channel === "text" && <div className="outreach-share-panel">
        <p>Send to people who agreed to receive your message. If someone asks you to stop, remove them from your outreach list. No automated texting or new texting subscription is used here.</p>
        <label>Ready-to-share message<textarea readOnly rows={8} value={text} /></label>
        <div className="actions"><button disabled={busy} onClick={() => run(() => copy(text, "Message and link copied. Paste them into your conversation."))}>Copy message and link</button>
          <a className="button secondary" href={picture.file} download={"cookcredit-" + draft.design.image + ".jpg"}>Download food picture</a>
          {typeof navigator.share === "function" && <button className="secondary" disabled={busy} onClick={() => run(async () => {
            try { await navigator.share({ title: draft.subject, text: `${draft.body}\n\nEnrollment is free. Review your full quote before paying for a visit.`, url: link }); setNotice("Sharing opened. Choose the conversation yourself."); }
            catch (e) { if (e.name !== "AbortError") throw e; }
          })}>Share on this device</button>}
        </div><p className="quiet">Attach the downloaded food picture to the same message. The service link works even if the picture is not displayed.</p>
      </div>}
      {channel === "email" && <div className="outreach-share-panel">
        <p>You manage this through your owner account. When sending, choose your verified <strong>connectwithus@cookcredit.com</strong> From address in Gmail. Keep a list of permissions and honor unsubscribe replies.</p>
        <label>Business mailing address (email footer only)<textarea rows={2} maxLength={500} value={draft.postalAddress} onChange={e => update({ postalAddress: e.target.value })} /></label>
        <p className="quiet">Commercial email needs a valid postal address. You can use a registered business mailbox or PO box. This field is private to the owner and appears in the email you prepare; it is not published on the website.</p>
        <button disabled={busy || !draft.postalAddress.trim()} onClick={() => run(async () => {
          const value = await api("/outreach/email-preview", { method: "POST", body: payload(draft) }); setEmail(value); setNotice("Email prepared. Review it below. Nothing was sent.");
        })}>Prepare email</button>
        {email && <>
          <iframe className="outreach-email-frame" title="Prepared advertising email" sandbox="" srcDoc={email.html} />
          <div className="actions">
            {typeof ClipboardItem !== "undefined" && navigator.clipboard?.write && <button disabled={busy} onClick={() => run(async () => {
              await navigator.clipboard.write([new ClipboardItem({ "text/html": new Blob([email.html], { type: "text/html" }), "text/plain": new Blob([email.plain], { type: "text/plain" }) })]);
              setNotice("Formatted email copied. Paste into Gmail, select connectwithus as From, and review the recipient before sending.");
            })}>Copy formatted email</button>}
            <button className="secondary" onClick={() => download(email.html, "text/html;charset=utf-8", "cookcredit-home-email.html")}>Download email HTML</button>
            <a className="button secondary" href={emailDraftLink(email.subject, email.plain)}>Open text-only email draft</a>
          </div><p className="quiet">The text-only draft includes the link and opt-out instructions. Attach the food picture yourself. Email apps may shorten long drafts; check the footer before sending.</p>
        </>}
      </div>}
      {channel === "print" && <div className="outreach-share-panel"><p>Print the food design with its service link. Use your browser’s print menu to choose a printer or save a PDF.</p><button onClick={() => window.print()}>Print flyer / save PDF</button><button className="secondary" disabled={busy} onClick={() => run(() => copy(link, "Service link copied."))}>Copy service link</button></div>}
    </section>
    <section className="outreach-library"><h2>Saved drafts</h2><button className="secondary" disabled={busy} onClick={() => run(reload)}>Refresh drafts</button>
      {!data.drafts.length && <p>No saved drafts yet.</p>}
      {data.drafts.map(item => <article className="home-desk-record" key={item.id}><h3>{item.subject}</h3><p>{item.status === "trashed" ? "In trash" : "Draft · Nothing sent"}</p>
        <div className="actions">{item.status === "trashed" ? <button disabled={busy} onClick={() => save("restore", item)}>Restore draft</button> : <><button className="secondary" disabled={busy} onClick={() => choose({ ...item, design: { image: "dinner", destination: "enroll", ...item.design } })}>Open draft</button><button className="text" disabled={busy} onClick={() => save("trash", item)}>Move to trash</button></>}</div>
      </article>)}
      {data.nextCursor && <button className="secondary" disabled={busy} onClick={() => run(() => reload(data.nextCursor))}>More drafts</button>}
    </section>
  </div>;
}
