import { FileText, Home as HomeIcon, Package, Plus, Presentation, Ticket, UserRound } from "lucide-react";
import { lazy, Suspense, useEffect } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { useCatalog, useLang, useMe, useT } from "./lib/app";
import { ApiError } from "./lib/api";
import { closeApp, haptic, inTelegram, inTelegramWithoutUser, openChat } from "./lib/tg";
import { Home } from "./screens/Home";
import { LangPick } from "./screens/LangPick";
import { Button, Empty } from "./ui";
import { NowBar } from "./ui/NowBar";
import { PointsFly, usePointsGain } from "./ui/PointsFly";

// Главная — в основной сборке, остальные экраны догружаются при переходе (быстрее первый экран)
const Done = lazy(() => import("./screens/Done").then((m) => ({ default: m.Done })));
const Help = lazy(() => import("./screens/Help").then((m) => ({ default: m.Help })));
const Invite = lazy(() => import("./screens/Invite").then((m) => ({ default: m.Invite })));
const Demo = lazy(() => import("./screens/Demo").then((m) => ({ default: m.Demo })));
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
/** Где над меню видна плашка «заказ готовится»: везде, кроме списка заказов — там он и так на виду. */
const NOW_TABS = ["/", "/packages", "/profile"];

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
          <Route path="/invite" element={<Invite />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
      {NOW_TABS.includes(location.pathname) && <NowBar />}
      {TABS.includes(location.pathname) && (
        <TabBar activeOrders={me.data?.active_orders ?? 0} vouchers={me.data?.vouchers ?? 0} />
      )}
    </>
  );
}

function TabBar({ activeOrders, vouchers }: { activeOrders: number; vouchers: number }) {
  const t = useT();
  const nav = useNavigate();
  const pts = usePointsGain();
  const tab = ({
    to,
    icon: Icon,
    label,
    badge,
  }: {
    to: string;
    icon: typeof HomeIcon;
    label: string;
    badge?: number | string;
  }) => (
    <NavLink key={to} to={to} end replace onClick={() => haptic.select()}>
      <span className="tab-in">
        <Icon strokeWidth={1.9} />
        <span>{label}</span>
      </span>
      {!!badge && <span className={`dot${typeof badge === "string" ? " gold" : ""}`}>{badge}</span>}
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
        {/* купон: есть оплаченная презентация от отменённого заказа */}
        {vouchers > 0 && (
          <b className="tab-plus-coupon" aria-label={t("voucher_card_one")}>
            <Ticket strokeWidth={2.4} />
            {vouchers > 1 && <span>{vouchers}</span>}
          </b>
        )}
        {/* подпись видна только в боковом меню на широком экране */}
        <span className="tab-plus-label">{t("cta_order")}</span>
      </button>
      {tab({ to: "/packages", icon: Package, label: t("tab_packages"), badge: pts.gain ? `+${pts.gain}` : undefined })}
      {pts.flying > 0 && <PointsFly gain={pts.flying} onDone={pts.done} />}
      {tab({ to: "/profile", icon: UserRound, label: t("tab_profile") })}
    </nav>
  );
}

function OutsideTelegram() {
  const t = useT();
  const catalog = useCatalog();
  if (inTelegramWithoutUser) {
    return (
      <div className="page no-tabbar" style={{ display: "grid", minHeight: "var(--app-h, 100dvh)", alignContent: "center" }}>
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
    <div className="page no-tabbar" style={{ display: "grid", minHeight: "var(--app-h, 100dvh)", alignContent: "center" }}>
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
