import { Activity, GitBranch, Search, ShieldCheck, RefreshCw, Cpu } from "lucide-react";
import Link from "next/link";

export default function Sidebar() {
  const items = [
    { name: "Dashboard", icon: Activity, href: "/dashboard" },
    { name: "Workflow", icon: GitBranch, href: "#" },
    { name: "Retrieval", icon: Search, href: "#" },
    { name: "Grounding", icon: ShieldCheck, href: "#" },
    { name: "Reflection", icon: RefreshCw, href: "#" },
    { name: "Decision Trace", icon: Cpu, href: "#" },
  ];

  return (
    <div className="w-64 bg-secondary/50 border-r border-border h-screen flex flex-col p-4">
      <div className="flex items-center gap-3 mb-10 px-2">
        <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground font-bold">
          A
        </div>
        <div>
          <h1 className="font-semibold text-sm">Aegis Intelligence</h1>
          <p className="text-xs text-muted-foreground">Observability System</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1">
        {items.map((item) => (
          <Link
            key={item.name}
            href={item.href}
            className="flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          >
            <item.icon className="w-4 h-4" />
            {item.name}
          </Link>
        ))}
      </nav>

      <div className="pt-4 border-t border-border mt-auto">
        <div className="flex items-center gap-2 px-2 py-2">
          <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          <span className="text-xs text-muted-foreground font-medium">System Online</span>
        </div>
      </div>
    </div>
  );
}
