import React, { useEffect, useRef, useState, Suspense, lazy } from "react";
import { onAuthStateChanged, signOut } from "firebase/auth";
import { auth, getAppCheckHeaders } from "../src/firebase";
import { api } from "./api";
import { safeHomeRoute } from "./navigation";
import Account from "./screens/Account";
import RequestVisit from "./screens/RequestVisit";
import Visit from "./screens/Visit";
import SavedDetails from "./screens/SavedDetails";
import Enrollment, { serviceNames } from "./screens/Enrollment";
import { visitSchedule, visitStatusLabel } from "./visitPresentation";
import "./style.css";

const Team = lazy(() => import("./screens/Team"));
const Payout = lazy(() => import("./screens/Payout"));
const Availability = lazy(() => import("./screens/Availability"));
const navigate = (route) => {
  location.hash = route;
};
const publicRoutes = ["home", "how", "help", "callback"];
const readRoute = () => {
  const route = location.hash.slice(1) || "home", page = route.split("?")[0];
  return publicRoutes.includes(page) ? page : route;
};

export default function App() {
  const [route, setRoute] = useState(readRoute),
    [user, setUser] = useState(undefined),
    [profile, setProfile] = useState(null);
  const [profileError, setProfileError] = useState(""),
    [sessionVersion, setSessionVersion] = useState(0);
  const [profileErrorCode, setProfileErrorCode] = useState("");
  const [sessionBusy, setSessionBusy] = useState(false), [sessionError, setSessionError] = useState("");
  const [visitService, setVisitService] = useState(null);
  const enrollmentOnly = profile ? profile.enrollmentOnly === true : import.meta.env.VITE_HOME_ENROLLMENT_ONLY === "1";
  const main = useRef();
  useEffect(() => {
    const change = () => setRoute(readRoute());
    addEventListener("hashchange", change);
    return () => removeEventListener("hashchange", change);
  }, []);
  useEffect(
    () =>
      onAuthStateChanged(auth, (next) => {
        setUser(next);
        setProfile(null);
        setProfileError("");
        setProfileErrorCode("");
        setVisitService(null);
      }),
    [],
  );
  useEffect(() => {
    let active = true;
    if (user?.emailVerified) {
      setProfile(null);
      setProfileError("");
      setProfileErrorCode("");
      api("/me")
        .then((value) => {
          if (active) setProfile(value);
        })
        .catch((error) => {
          if (active) { setProfileError(error.message); setProfileErrorCode(error.code || ""); }
        });
    }
    return () => {
      active = false;
    };
  }, [user, sessionVersion]);
  useEffect(() => {
    main.current?.focus();
    window.scrollTo(0, 0);
  }, [route]);
  const refresh = async () => {
    await auth.currentUser?.reload();
    await auth.currentUser?.getIdToken(true);
    setUser(auth.currentUser);
    setSessionVersion((v) => v + 1);
  };
  const leaveAccount = async (target) => {
    setSessionBusy(true); setSessionError("");
    try {
      await signOut(auth);
      navigate(target);
    } catch {
      setSessionError("We could not sign you out. Check your connection and try again.");
    } finally {
      setSessionBusy(false);
    }
  };
  const requiresAccount =
    !publicRoutes.includes(route) &&
    !route.startsWith("account/action");
  let content;
  if (user === undefined && requiresAccount)
    content = <p role="status">Checking your account…</p>;
  else if (route === "home") content = <Home enrollmentOnly={enrollmentOnly} />;
  else if (route === "how") content = <How enrollmentOnly={enrollmentOnly} />;
  else if (route === "help" || route === "callback") content = <Help key={route} user={user} profile={profile}
    accessErrorCode={profileErrorCode} busySwitching={sessionBusy} returnTo={route}
    privateAcceptance={import.meta.env.VITE_HOME_PRIVATE_ACCEPTANCE === "1"}
    enrollmentOnly={enrollmentOnly}
    switchAccount={() => leaveAccount("sign-in?next=" + encodeURIComponent(route))} />;
  else if (
    route.startsWith("account/action") ||
    route.split("?")[0] === "sign-in" ||
    (requiresAccount && (!user || !user.emailVerified))
  )
    content = (
      <Account
        key={route}
        user={user}
        refresh={refresh}
        enrollmentOnly={enrollmentOnly}
        next={safeHomeRoute(route.split("?")[0] === "sign-in" ? new URLSearchParams(route.split("?")[1] || "").get("next") : route, enrollmentOnly)}
      />
    );
  else if (user === undefined || (!profile && !profileError))
    content = <p role="status">Opening your account…</p>;
  else if (profileError)
    content = (
      <section className="narrow">
        <h1>{profileErrorCode === "private_acceptance" ? "This account can’t open Home yet." : "We couldn’t open your account."}</h1>
        {user?.email && <p>Signed in as <strong>{user.email}</strong>.</p>}
        {profileErrorCode === "private_acceptance" && <p>Your sign-in worked. Access to this Home environment is currently limited to enabled accounts.</p>}
        <p role="alert">{profileErrorCode === "private_acceptance" ? "Contact CookCredit to request access, or choose a different account." : profileError}</p>
        <button onClick={() => refresh().catch(() =>
          setProfileError("We could not refresh your sign-in. Check your connection and try again."),
        )}>Try again</button>
        <button className="secondary" disabled={sessionBusy} onClick={() => leaveAccount(route)}>
          Use a different account
        </button>
        <p><a href="#help">Get help</a> or <a href="#home">return to Home</a>.</p>
      </section>
    );
  else if (profile.enrollmentOnly && safeHomeRoute(route, true) !== route) content = <EnrollmentEntry />;
  else if (route === "enroll") content = <Enrollment profile={profile} onArrange={setVisitService} />;
  else if (route === "request") content = <RequestVisit profile={profile} initialService={visitService} />;
  else if (route === "visits") content = <Visits />;
  else if (/^visit\/[a-f0-9-]{36}$/.test(route))
    content = <Visit key={route} id={route.split("/")[1]} profile={profile} />;
  else if (route === "team" && profile.operator)
    content = <Team profile={profile} />;
  else if (route === "payout" && profile.helper) content = <Payout />;
  else if (route === "availability" && profile.helper) content = <Availability />;
  else if (route === "helping") content = <Payout applying />;
  else
    content = (
      <section className="narrow">
        <h1>Page not found</h1>
        <a className="button" href="#home">
          Back to Home
        </a>
      </section>
    );
  const workspace = Boolean(user?.emailVerified && profile &&
    !["home", "how", "sign-in"].includes(route.split("?")[0]) && !route.startsWith("account/action"));
  return (
    <div className={workspace ? "home-workspace" : "home-public"}>
      {import.meta.env.DEV && import.meta.env.VITE_HOME_AUTH_EMULATOR_URL && (
        <div className="local-note">
          Local walkthrough · Example accounts and visits. No real messages,
          charges or bank transfers.
        </div>
      )}
      <a
        className="skip"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          main.current?.focus();
        }}
      >
        Skip to content
      </a>
      {workspace ? <aside className="home-workspace-rail" aria-label="Home workspace">
        <a className="brand" href="#home" aria-label="CookCredit Home">
          <img src="/assets/cookcredit-mark-orange.svg" alt="" />
          <span>CookCredit<small>At-home services</small></span>
        </a>
        <a className="button home-workspace-primary" href={enrollmentOnly ? "#enroll" : "#request"}>{enrollmentOnly ? "Choose service needs" : "Arrange a visit"}</a>
        <nav className="home-workspace-nav" aria-label="Your workspace">
          {profile.operator && <div className="home-workspace-group">
            <p className="home-workspace-label">CookCredit operations</p>
            <a href="#team" aria-current={route === "team" ? "page" : undefined}>Service desk</a>
          </div>}
          <div className="home-workspace-group">
            <p className="home-workspace-label">Your home</p>
            {!enrollmentOnly && <a href="#visits" aria-current={route === "visits" || route.startsWith("visit/") ? "page" : undefined}>My visits</a>}
            <a href="#enroll" aria-current={route === "enroll" ? "page" : undefined}>Service needs</a>
          </div>
          {profile.helper && !enrollmentOnly && <div className="home-workspace-group">
            <p className="home-workspace-label">Your work</p>
            <a href="#availability" aria-current={route === "availability" ? "page" : undefined}>Availability</a>
            <a href="#payout" aria-current={route === "payout" ? "page" : undefined}>My earnings</a>
          </div>}
          <div className="home-workspace-group">
            <a href="#help" aria-current={route === "help" || route === "callback" ? "page" : undefined}>Help</a>
          </div>
        </nav>
        <div className="home-workspace-account">
          <div><span className="home-workspace-label">Signed in as</span><p>{profile.name || user.email}</p></div>
          <button className="text" disabled={sessionBusy} onClick={() => leaveAccount("home")}>Sign out</button>
        </div>
      </aside> : <header>
        <a className="brand" href="#home" aria-label="CookCredit Home">
          <img src="/assets/cookcredit-mark-orange.svg" alt="" />
          <span>
            CookCredit<small>At-home services</small>
          </span>
        </a>
        <nav aria-label="Main">
          <a href="#how">How it works</a>
          {!enrollmentOnly && <a href="#visits">My visits</a>}
          <a href="#enroll">Service needs</a>
          {profile?.operator && <a href="#team">Team</a>}
          {profile?.helper && !enrollmentOnly && <a href="#payout">My earnings</a>}
          {profile?.helper && !enrollmentOnly && <a href="#availability">Availability</a>}
          <a href="#help">Help</a>
          {user ? (
            <button
              className="text"
              disabled={sessionBusy}
              onClick={() => leaveAccount("home")}
            >
              Sign out
            </button>
          ) : (
            <a href={enrollmentOnly ? "#sign-in?next=enroll" : "#sign-in"}>Sign in</a>
          )}
        </nav>
      </header>}
      {sessionError && <p className="error" role="alert">{sessionError}</p>}
      <main id="main" tabIndex="-1" ref={main} className={workspace ? "home-workspace-main" : undefined}>
        <Suspense fallback={<p role="status">Opening…</p>}>{content}</Suspense>
      </main>
      <footer>
        <a href="#home">CookCredit Home</a>
        {!enrollmentOnly && <a href="#helping">Work with us</a>}
        <a href="mailto:connectwithus@cookcredit.com">
          connectwithus@cookcredit.com
        </a>
        <a href="https://cookcredit.com/privacy.html">Privacy</a>
        <a href="https://cookcredit.com/terms.html">Terms</a>
      </footer>
    </div>
  );
}

function EnrollmentEntry() {
  return <section className="narrow">
    <p className="eyebrow">CookCredit Home</p>
    <h1>Start with your service needs.</h1>
    <p>Enrollment and call requests are open. Visit booking, scheduling and payments are not available in this launch.</p>
    <div className="actions"><a className="button" href="#enroll">Choose service needs</a><a className="button secondary" href="#callback">Request a call</a></div>
  </section>;
}

function Home({ enrollmentOnly = false } = {}) {
  return (
    <>
      <section className="hero">
        <div className="hero-photo">
          <img
            src="/assets/cooking-visit.jpg"
            alt="Preparing fresh ingredients at a kitchen counter"
            fetchPriority="high"
          />
        </div>
        <div className="hero-copy">
          <p className="eyebrow">A little help at home</p>
          <h1>
            Good food.
            <br />A home cared for.
          </h1>
          <p>
            {enrollmentOnly ? "Tell us whether you need cooking, cleaning or both. Join our service-interest list, or ask CookCredit to call you." : "Arrange a cooking visit, help with cleaning, or both. Tell us what would make your day easier."}
          </p>
          <a className="button" href={enrollmentOnly ? "#enroll" : "#request"}>
            {enrollmentOnly ? "Choose service needs" : "Arrange a visit"} <span aria-hidden="true">→</span>
          </a>
          <p className="quiet">
            {enrollmentOnly ? "Enrollment is free. Visit booking, scheduling and payments are not available in this launch." : "No charge for sending a request. You approve your helper and full price before paying."}
          </p>
          {!enrollmentOnly && <a href="#enroll">Not ready to book? Tell us what you need.</a>}
          <a href="#callback">Prefer help by phone? Request a call.</a>
        </div>
      </section>
      <section className="intro">
        <h2>Your home. Your way.</h2>
        <div className="three">
          <div>
            <h3>{enrollmentOnly ? "Choose what you need" : "Meals that suit you"}</h3>
            <p>
              {enrollmentOnly ? "Choose cooking, cleaning, both or help deciding. No address or health details are needed." : "Share food allergies, texture preferences or meal instructions you already follow."}
            </p>
          </div>
          <div>
            <h3>{enrollmentOnly ? "Talk with CookCredit" : "The help you choose"}</h3>
            <p>
              {enrollmentOnly ? "Request a call to ask questions about our service plans." : "Choose cooking, specific cleaning tasks and how much time you need."}
            </p>
          </div>
          <div>
            <h3>{enrollmentOnly ? "Stay in control" : "Every cost explained"}</h3>
            <p>
              {enrollmentOnly ? "Enrollment does not reserve a visit or authorize payment. You can remove your service needs." : "Review time, materials, service fees and tax before agreeing to a visit."}
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
function How({ enrollmentOnly = false } = {}) {
  if (enrollmentOnly) return <section className="narrow">
    <p className="eyebrow">How it works</p><h1>A simple way to get started.</h1>
    <ol className="steps">
      <li><h2>Create your account</h2><p>Use Google or verify your email to save your service needs.</p></li>
      <li><h2>Choose what would help</h2><p>Select cooking, cleaning, both or help choosing. Your phone number is optional for enrollment.</p></li>
      <li><h2>Talk with CookCredit</h2><p>Request a call if you prefer. Enrollment and call requests do not book a visit or authorize a payment.</p></li>
    </ol>
    <p>Visit booking and scheduling are not available yet. Please do not include addresses, medical details or allergy instructions in enrollment or call requests.</p>
    <a className="button" href="#enroll">Choose service needs</a>
  </section>;
  return (
    <section className="narrow">
      <p className="eyebrow">How it works</p>
      <h1>One visit, clearly arranged.</h1>
      <ol className="steps">
        <li>
          <h2>Tell us what you need</h2>
          <p>
            Choose a day and the cooking or cleaning help you’d like. You can
            arrange a visit for someone else with their permission.
          </p>
        </li>
        <li>
          <h2>Review your helper and price</h2>
          <p>
            CookCredit reviews availability. Your quote lists the work, time and
            maximum materials cost. Nothing is charged when you send your
            request.
          </p>
        </li>
        <li>
          <h2>Pay securely, then welcome your helper</h2>
          <p>
            After approval, pay the agreed maximum through Stripe. After the
            visit, review receipts and confirm the work. Unused materials and
            tax allowance are refunded after review.
          </p>
        </li>
      </ol>
      <p>
        We provide household help, not medical care or dietary treatment. We
        review allergies with you, but cannot guarantee an allergen-free
        kitchen.
      </p>
      <a className="button" href="#request">
        Arrange a visit
      </a>
    </section>
  );
}
function Help({ user, profile, accessErrorCode, switchAccount, busySwitching = false, returnTo = "callback", privateAcceptance = false, enrollmentOnly = false }) {
  const [sent, setSent] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    id = useRef(crypto.randomUUID());
  const [denial, setDenial] = useState("");
  const restricted = accessErrorCode === "private_acceptance" || denial === "private_acceptance";
  const checkingIdentity = privateAcceptance && user === undefined;
  const needsSignIn = denial === "sign_in_required" || ((privateAcceptance || profile?.environment === "staging") && !user?.emailVerified);
  useEffect(() => {
    if (checkingIdentity || restricted || needsSignIn || sent) return;
    // Warm the existing attestation while the person fills in the form. This
    // sends no callback details and never submits a request in the background.
    getAppCheckHeaders().catch(() => {});
  }, [checkingIdentity, restricted, needsSignIn, sent]);
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(event.currentTarget);
    try {
      await api("/callbacks", {
        method: "POST",
        protectedAccount: true,
        body: {
          requestId: id.current,
          name: f.get("name"),
          phone: f.get("phone"),
          preferredTime: f.get("time"),
          contactConsent: f.get("consent") === "on",
          website: "",
        },
      });
      setSent(true);
    } catch (e) {
      if (e.code === "private_acceptance") setDenial("private_acceptance");
      else if (e.status === 401 || e.code === "email_unverified") setDenial("sign_in_required");
      else setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="narrow">
      <p className="eyebrow">A person to help</p>
      <h1>Let’s talk it through.</h1>
      <p>
        {enrollmentOnly ? "Request a call about your service needs or account. Visit booking is not available yet." : "Request a call to discuss a visit or get help with your account."} This service is not for emergencies.
      </p>
      {checkingIdentity ? <p role="status">Checking your account…</p> : restricted || needsSignIn ? (
        <div className="notice" role="status">
          <h2>{restricted ? "This account cannot send a callback request here yet." : "Sign in before sending this callback request."}</h2>
          <p>{restricted
            ? "Your sign-in worked, but this private Home site only accepts enabled accounts. No callback request was submitted."
            : "This Home site requires a verified account for callback requests. No callback request was submitted."}</p>
          {user?.email && <p>Signed in as <strong>{user.email}</strong>.</p>}
          {restricted && user && switchAccount
            ? <button disabled={busySwitching} onClick={switchAccount}>Use a different account</button>
            : <a className="button" href={"#sign-in?next=" + encodeURIComponent(safeHomeRoute(returnTo))}>Sign in to continue</a>}
          <p>You can also email CookCredit using the address below.</p>
        </div>
      ) : sent ? (
        <div role="status" className="notice">
          <h2>Your callback request is received.</h2>
          <p>
            CookCredit will contact you at the number you provided. A visit has
            not been booked.
          </p>
          <a href="#home">Return to Home</a>
          <button className="secondary" onClick={() => {
            id.current = crypto.randomUUID(); setSent(false); setError("");
          }}>Request another call</button>
        </div>
      ) : (
        <form onSubmit={submit}>
          <label>
            Your name
            <input name="name" autoComplete="name" maxLength="120" required />
          </label>
          <label>
            Phone number
            <input
              name="phone"
              type="tel"
              autoComplete="tel"
              maxLength="40"
              required
            />
          </label>
          <label>
            When is a good time to call?
            <input
              name="time"
              placeholder="For example, weekday afternoons"
              maxLength="100"
              required
            />
            <small>Please give a call window only. Do not include addresses, medical details or allergy instructions.</small>
          </label>
          <label className="check">
            <input type="checkbox" name="consent" required />
            CookCredit may call me about this request.
          </label>
          <ErrorMessage error={error} />
          <button disabled={busy}>
            {busy ? "Sending…" : "Request a call"}
          </button>
        </form>
      )}
      <details><summary>Your information</summary>
        <p>Your name, phone number and preferred call time are available to authorized CookCredit Home staff so they can respond to this request. This permission is for service contact, not advertising.</p>
        <p>Email <a href="mailto:connectwithus@cookcredit.com">connectwithus@cookcredit.com</a> to change or withdraw a callback request or ask about your data. Read our <a href="https://cookcredit.com/privacy.html">Privacy Policy</a>.</p>
      </details>
      <p>
        Or email{" "}
        <a href="mailto:connectwithus@cookcredit.com">
          connectwithus@cookcredit.com
        </a>
        .
      </p>
    </section>
  );
}
function Visits() {
  const [state, setState] = useState({
    rows: [],
    loading: true,
    error: "",
    cursor: null,
  });
  const load = async (more) => {
    setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const value = await api(
        "/visits" +
          (more && state.cursor
            ? "?cursor=" + encodeURIComponent(state.cursor)
            : ""),
      );
      setState((s) => ({
        rows: more ? [...s.rows, ...value.visits] : value.visits,
        loading: false,
        error: "",
        cursor: value.nextCursor,
      }));
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: e.message }));
    }
  };
  useEffect(() => {
    load(false);
  }, []);
  return (
    <section className="page">
      <div className="heading">
        <div>
          <p className="eyebrow">Your account</p>
          <h1>My visits</h1>
        </div>
        <a className="button" href="#request">
          Arrange a visit
        </a>
      </div>
      <SavedDetails />
      <ErrorMessage error={state.error} />
      {state.error && !state.loading && (
        <button className="secondary" onClick={() => load(false)}>
          Refresh visits
        </button>
      )}
      {!state.loading && !state.error && !state.rows.length && (
        <p>
          No visits yet. Start with a request and we’ll help arrange the rest.
        </p>
      )}
      {state.rows.map((row) => {
        const schedule = visitSchedule(row.date, row.time, row.timeZone);
        return (
        <a className="visit-row" key={row.id} href={"#visit/" + row.id}>
          <div>
            <h2>{serviceNames[row.service] || "Home visit"}</h2>
            <p className="visit-schedule">
              <span>{schedule.date}</span>
              <span>{schedule.time} · {schedule.zone} · {row.durationMinutes / 60}{" "}
                {row.durationMinutes === 60 ? "hour" : "hours"}</span>
            </p>
          </div>
          <span className="visit-state">
            {visitStatusLabel(row.status)} <span aria-hidden="true">→</span>
          </span>
        </a>
        );
      })}
      {state.loading ? (
        <p role="status">Loading visits…</p>
      ) : (
        state.cursor && <button onClick={() => load(true)}>More visits</button>
      )}
    </section>
  );
}
function ErrorMessage({ error }) {
  return error ? (
    <p role="alert" className="error">
      {error}
    </p>
  ) : null;
}
