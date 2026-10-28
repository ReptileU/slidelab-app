import { FileText, Home as HomeIcon, Package, Plus, Presentation, UserRound } from "lucide-react";
import { lazy, Suspense, useEffect } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { useCatalog, useLang, useMe, useT } from "./lib/app";
import { ApiError } from "./lib/api";
import { closeApp, haptic, inTelegram, inTelegramWithoutUser, openChat } from "./lib/tg";
import { Home } from "./screens/Home";
import { LangPick } from "./screens/LangPick";
import { Button, Empty } from "./ui";

// Главная — в основной сборке, остальные экраны догружаются при переходе (быстрее первый экран)
const Done = lazy(() => import("./screens/Done").then((m) => ({ default: m.Done })));
const Help = lazy(() => import("./screens/Help").then((m) => ({ default: m.Help })));
const NewOrder = lazy(() => import("./screens/NewOrder").then((m) => ({ default: m.NewOrder })));
const OrderDetail = lazy(() => import("./screens/OrderDetail").then((m) => ({ default: m.OrderDetail })));
const Orders = lazy(() => import("./screens/Orders").then((m) => ({ default: m.Orders })));
const Packages = lazy(() => import("./screens/Packages").then((m) => ({ default: m.Packages })));
const Profile = lazy(() => import("./screens/Profile").then((m) => ({ default: m.Profile })));
const Styles = lazy(() => import("./screens/Styles").then((m) => ({ default: m.Styles })));

// Пока главная на экране — тихо подгружаем частые экраны, чтобы переход был мгновенным
function prefetchScreens() {
  void import("./screens/NewOrder");
  void import("./screens/Orders");
  void import("./screens/Packages");
  void import("./screens/Profile");
}

const TABS = ["/", "/orders", "/packages", "/profile"];

export function App() {
  const me = useMe();
  const { chosen } = useLang();
  const location = useLocation();

  useEffect(() => {
    const id = window.setTimeout(prefetchScreens, 1200);
    return () => window.clearTimeout(id);
  }, []);

  const unauthorized = me.error instanceof ApiError && me.error.status === 401;
  if (unauthorized && !inTelegram) return <OutsideTelegram />;
  if (me.isSuccess && !chosen) return <LangPick />;

  return (
    <>
      <Suspense fallback={<div className="page" />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/styles" element={<Styles />} />
          <Route path="/order" element={<NewOrder />} />
          <Route path="/order/done/:id" element={<Done />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/orders/:id" element={<OrderDetail />} />
          <Route path="/packages" element={<Packages />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/help" element={<Help />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
      {TABS.includes(location.pathname) && <TabBar activeOrders={me.data?.active_orders ?? 0} />}
    </>
  );
}

function TabBar({ activeOrders }: { activeOrders: number }) {
  const t = useT();
  const nav = useNavigate();
  const tab = ({ to, icon: Icon, label, badge }: { to: string; icon: typeof HomeIcon; label: string; badge?: number }) => (
    <NavLink key={to} to={to} end replace onClick={() => haptic.select()}>
      <Icon strokeWidth={1.8} />
      {label}
      {!!badge && <span className="dot">{badge}</span>}
    </NavLink>
  );
  return (
    <nav className="tabbar">
      {tab({ to: "/", icon: HomeIcon, label: t("tab_home") })}
      {tab({ to: "/orders", icon: FileText, label: t("tab_orders"), badge: activeOrders })}
      {/* Как в прежней витрине: большой «+» посередине — новый заказ в одно касание */}
      <button
        className="tab-plus"
        aria-label={t("cta_order")}
        onClick={() => {
          haptic.tap();
          nav("/order");
        }}
      >
        <i>
          <Plus strokeWidth={2.4} />
        </i>
      </button>
      {tab({ to: "/packages", icon: Package, label: t("tab_packages") })}
      {tab({ to: "/profile", icon: UserRound, label: t("tab_profile") })}
    </nav>
  );
}

function OutsideTelegram() {
  const t = useT();
  const catalog = useCatalog();
  if (inTelegramWithoutUser) {
    return (
      <div className="page no-tabbar" style={{ display: "grid", minHeight: "100vh", alignContent: "center" }}>
        <Empty
          icon={<Presentation />}
          title={t("wrong_button_t")}
          text={t("wrong_button_x")}
          action={<Button onClick={closeApp}>{t("close")}</Button>}
        />
      </div>
    );
  }
  return (
    <div className="page no-tabbar" style={{ display: "grid", minHeight: "100vh", alignContent: "center" }}>
      <Empty
        icon={<Presentation />}
        title={t("outside_tg")}
        text={t("hero_sub")}
        action={
          <Button onClick={() => openChat(catalog.data?.bot_username ?? "slidelab_order_bot")}>{t("open_tg")}</Button>
        }
      />
    </div>
  );
}
