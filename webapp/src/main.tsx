import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Component, StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";

import { App } from "./App";
import { LangProvider } from "./lib/app";
import { initTelegram } from "./lib/tg";
import "./styles.css";

initTelegram();

// Telegram открывает приложение с данными в хэше (#tgWebAppData=…), а HashRouter принял бы их за маршрут
// и показал пустой экран. telegram-web-app.js уже прочитал их — переводим адрес на главную.
if (!location.hash.startsWith("#/")) history.replaceState(null, "", `${location.pathname}${location.search}#/`);

declare global {
  interface Window {
    __slReport?: (message: unknown) => void;
  }
}

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    window.__slReport?.(error.stack ?? error.message);
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page no-tabbar center" style={{ paddingTop: 80 }}>
        <h1 className="title2">SlideLab</h1>
        <p className="subhead secondary">Что-то пошло не так. Закройте и откройте приложение ещё раз.</p>
        <p className="caption secondary" style={{ whiteSpace: "pre-wrap", textAlign: "left" }}>{this.state.error.message}</p>
      </div>
    );
  }
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: true }, mutations: { retry: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <LangProvider>
        {/* HashRouter: статика раздаётся как есть, без серверных маршрутов */}
        <HashRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <App />
        </HashRouter>
      </LangProvider>
    </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);
