import { Dices, Home, Info, Network } from "lucide-react";
import { NavLink } from "react-router-dom";

const navigationItems = [
  { to: "/", label: "首页", icon: Home },
  { to: "/random", label: "随机博客", icon: Dices },
  { to: "/visualization", label: "可视化", icon: Network },
  { to: "/about", label: "About", icon: Info },
];

/**
 * Render the shared top-right navigation used across the routed frontend.
 *
 * @returns Floating route navigation bar.
 */
export function Navigation() {
  return (
    <nav className="fixed right-6 top-6 z-40">
      <div className="flex items-center gap-2 rounded-2xl border border-white/70 bg-white/92 p-1.5 shadow-[0_20px_60px_rgba(15,23,42,0.14)] backdrop-blur-md">
        {navigationItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                [
                  "flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm transition-all",
                  isActive
                    ? "bg-slate-900 text-white shadow-lg"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
                ].join(" ")
              }
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
