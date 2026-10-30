import React from "react";
import { createRoot } from "react-dom/client";
import { connectAuthEmulator } from "firebase/auth";
import { auth } from "../src/firebase";
import App from "./App";
import HomeErrorBoundary from "./HomeErrorBoundary";
import { startErrorReporting } from "../src/utils/errorReporting";
const stopReporting = startErrorReporting({
  enabled: location.protocol === "https:",
  apiOrigin: location.origin,
  product: "home",
  release: import.meta.env.VITE_SOURCE_REVISION,
});
if (import.meta.hot) import.meta.hot.dispose(stopReporting);
if (
  import.meta.env.DEV &&
  ["127.0.0.1", "localhost"].includes(location.hostname) &&
  import.meta.env.VITE_HOME_AUTH_EMULATOR_URL
) {
  const emulator = new URL(import.meta.env.VITE_HOME_AUTH_EMULATOR_URL);
  if (
    emulator.protocol !== "http:" ||
    !["127.0.0.1", "localhost"].includes(emulator.hostname)
  )
    throw new Error("Auth emulator must use loopback");
  if (!auth.emulatorConfig)
    connectAuthEmulator(auth, emulator.origin, { disableWarnings: true });
}

const root =
  import.meta.hot?.data.root || createRoot(document.getElementById("root"));
if (import.meta.hot) import.meta.hot.data.root = root;
root.render(
  <HomeErrorBoundary>
    <App />
  </HomeErrorBoundary>,
);
