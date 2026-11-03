import React from "react";
import { reportClientError } from "../src/utils/errorReporting";
import { homeSiteLinks } from "./navigation";

function moduleLoadFailure(error) {
  try {
    const name = typeof error?.name === "string" ? error.name.slice(0, 40) : "";
    const message = typeof error?.message === "string" ? error.message.slice(0, 240) : "";
    return name === "ChunkLoadError" || /^(Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module)/i.test(message);
  } catch {
    return false;
  }
}

export default class HomeErrorBoundary extends React.Component {
  state = { failed: false, moduleFailure: false };
  static getDerivedStateFromError(error) {
    return { failed: true, moduleFailure: moduleLoadFailure(error) };
  }
  componentDidCatch(error) {
    // Never print component props, exception messages or household instructions.
    console.error(moduleLoadFailure(error)
      ? "CookCredit Home screen unavailable (home_ui_module_load_failed)"
      : "CookCredit Home screen unavailable (home_ui_render_failed)");
    this.setState({ reference: reportClientError("render_error") });
  }
  returnHome = () => {
    const links = homeSiteLinks(import.meta.env);
    if (links.publicOverview) {
      location.assign(links.overview);
      return;
    }
    location.hash = "home";
    this.setState({ failed: false, moduleFailure: false });
  };
  render() {
    if (!this.state.failed) return this.props.children;
    if (this.props.fallback) return typeof this.props.fallback === "function"
      ? this.props.fallback({ reference: this.state.reference }) : this.props.fallback;
    return (
      <main className="narrow">
        <a
          className="brand"
          href={homeSiteLinks(import.meta.env).overview}
          onClick={(event) => { event.preventDefault(); this.returnHome(); }}
        >
          CookCredit Home
        </a>
        <h1>{this.state.moduleFailure ? "Part of this page couldn’t load." : "We couldn’t open that screen."}</h1>
        <p>
          {this.state.moduleFailure
            ? "A site update or interrupted connection may have stopped this screen from loading. Reload to get the latest version."
            : "Reload the page to try again, return Home, or contact customer service."}
        </p>
        <p>Reloading clears unsent form entries. If you already sent a request, check My visits before sending it again.</p>
        <button onClick={() => location.reload()}>Reload latest version</button>
        <button className="secondary" onClick={this.returnHome}>
          Return Home
        </button>
        {this.state.reference && (
          <p className="quiet">Support reference: {this.state.reference}</p>
        )}
        <p>
          <a href="mailto:connectwithus@cookcredit.com">
            connectwithus@cookcredit.com
          </a>
        </p>
      </main>
    );
  }
}
