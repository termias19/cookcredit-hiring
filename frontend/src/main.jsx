import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { LangProvider } from "./context/LangContext";
import App from "./App";
import StagingNotice from './components/StagingNotice'
import AppUpdateNotice from './components/AppUpdateNotice'
import "./index.css"
import "./styles/business-theme.css"
import './utils/pwaInstall'

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <LangProvider>
        {import.meta.env.PROD && <AppUpdateNotice />}
        <AuthProvider>
          <StagingNotice />
          <App />
        </AuthProvider>
      </LangProvider>
    </BrowserRouter>
  </StrictMode>
);
