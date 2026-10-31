import React, { useEffect, useRef, useState, Suspense, lazy } from "react";
import { onAuthStateChanged, signOut } from "firebase/auth";
import { auth } from "../src/firebase";
import { api } from "./api";
import { safeHomeRoute } from "./navigation";
import Account from "./screens/Account";
import RequestVisit from "./screens/RequestVisit";
import Visit from "./screens/Visit";
import SavedDetails from "./screens/SavedDetails";
import Enrollment from "./screens/Enrollment";
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
  else if (route === "home") content = <Home />;
  else if (route === "how") content = <How />;
  else if (route === "help" || route === "callback") content = <Help key={route} user={user} profile={profile}
    accessErrorCode={profileErrorCode} busySwitching={sessionBusy} returnTo={route}
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
        next={route.split("?")[0] === "sign-in" ? safeHomeRoute(new URLSearchParams(route.split("?")[1] || "").get("next")) : route}
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
  return (
    <>
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
      <header>
        <a className="brand" href="#home" aria-label="CookCredit Home">
          <img src="/assets/cookcredit-mark-orange.svg" alt="" />
          <span>
            CookCredit<small>At-home services</small>
          </span>
        </a>
        <nav aria-label="Main">
          <a href="#how">How it works</a>
          <a href="#visits">My visits</a>
          <a href="#enroll">Service needs</a>
          {profile?.operator && <a href="#team">Team</a>}
          {profile?.helper && <a href="#payout">My earnings</a>}
          {profile?.helper && <a href="#availability">Availability</a>}
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
            <a href="#sign-in">Sign in</a>
          )}
        </nav>
      </header>
      {sessionError && <p className="error" role="alert">{sessionError}</p>}
      <main id="main" tabIndex="-1" ref={main}>
        <Suspense fallback={<p role="status">Opening…</p>}>{content}</Suspense>
      </main>
      <footer>
        <a href="#home">CookCredit Home</a>
        <a href="#helping">Work with us</a>
        <a href="mailto:connectwithus@cookcredit.com">
          connectwithus@cookcredit.com
        </a>
        <a href="https://cookcredit.com/privacy.html">Privacy</a>
        <a href="https://cookcredit.com/terms.html">Terms</a>
      </footer>
    </>
  );
}

function Home() {
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
            Arrange a cooking visit, help with cleaning, or both. Tell us what
            would make your day easier.
          </p>
          <a className="button" href="#request">
            Arrange a visit <span aria-hidden="true">→</span>
          </a>
          <p className="quiet">
            No charge for sending a request. You approve your helper and full
            price before paying.
          </p>
          <a href="#enroll">Not ready to book? Tell us what you need.</a>
          <a href="#callback">Prefer help by phone? Request a call.</a>
        </div>
      </section>
      <section className="intro">
        <h2>Your home. Your way.</h2>
        <div className="three">
          <div>
            <h3>Meals that suit you</h3>
            <p>
              Share food allergies, texture preferences or meal instructions you
              already follow.
            </p>
          </div>
          <div>
            <h3>The help you choose</h3>
            <p>
              Choose cooking, specific cleaning tasks and how much time you
              need.
            </p>
          </div>
          <div>
            <h3>Every cost explained</h3>
            <p>
              Review time, materials, service fees and tax before agreeing to a
              visit.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
function How() {
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
function Help({ user, profile, accessErrorCode, switchAccount, busySwitching = false, returnTo = "callback" }) {
  const [sent, setSent] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    id = useRef(crypto.randomUUID());
  const [denial, setDenial] = useState("");
  const restricted = accessErrorCode === "private_acceptance" || denial === "private_acceptance";
  const needsSignIn = denial === "sign_in_required" || (profile?.environment === "staging" && !user?.emailVerified);
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
        Request a call to discuss a visit or get help with your account. This
        service is not for emergencies.
      </p>
      {restricted || needsSignIn ? (
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
      {state.rows.map((row) => (
        <a className="visit-row" key={row.id} href={"#visit/" + row.id}>
          <div>
            <h2>
              {row.service === "both"
                ? "Cooking & cleaning"
                : row.service === "cooking"
                  ? "Cooking"
                  : "Cleaning"}
            </h2>
            <p>
              {row.date} · {row.time.slice(0, 5)} · {row.durationMinutes / 60}{" "}
              {row.durationMinutes === 60 ? "hour" : "hours"}
            </p>
          </div>
          <span>
            {row.status.replaceAll("_", " ")} <span aria-hidden="true">→</span>
          </span>
        </a>
      ))}
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
