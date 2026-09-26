import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught a render error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="auth-shell">
          <section className="auth-card">
            <div className="brand-mark">!</div>
            <h1>Something went wrong</h1>
            <p className="muted">
              The app hit an unexpected error. Reloading usually fixes it.
            </p>
            <button className="primary full" onClick={() => window.location.reload()}>
              Reload
            </button>
          </section>
        </div>
      );
    }
    return this.props.children;
  }
}