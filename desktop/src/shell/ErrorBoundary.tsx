/** FB-4: a crash shows a recovery screen, never a blank window. */

import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/Button";
import { logFromUi } from "@/ipc/client";
import { TitleBar } from "@/shell/TitleBar";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    logFromUi("error", `UI crash: ${error.message}\n${info.componentStack ?? ""}`);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      // The window is frameless (D-055), so even a crashed surface needs a drag region and a
      // way out — otherwise the only remaining controls are the tray and the taskbar.
      <div className="window">
        <TitleBar title="Discord AutoRPC" />

        <div className="crash">
          <h1 className="t-title">The interface hit an error</h1>
          <p className="t-secondary" style={{ maxWidth: "46ch" }}>
            Your settings and the engine are unaffected — “Try again” usually clears it.
          </p>
          <pre>{error.message}</pre>
          <Button variant="primary" onClick={() => this.setState({ error: null })}>
            Try again
          </Button>
        </div>
      </div>
    );
  }
}
