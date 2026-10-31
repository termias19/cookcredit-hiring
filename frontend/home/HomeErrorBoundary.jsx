import React from "react";
import { reportClientError } from "../src/utils/errorReporting";

export default class HomeErrorBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    // Never print component props, exception messages or household instructions.
    console.error("CookCredit Home screen unavailable (home_ui_render_failed)");
    this.setState({ reference: reportClientError("render_error") });
  }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="narrow">
        <a
          className="brand"
          href="#home"
          onClick={() => this.setState({ failed: false })}
        >
          CookCredit Home
        </a>
        <h1>We couldn’t open that screen.</h1>
        <p>
          Your saved visit is still in your account. Return Home and try again,
          or contact customer service.
        </p>
        <button
          onClick={() => {
            location.hash = "home";
            this.setState({ failed: false });
          }}
        >
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
