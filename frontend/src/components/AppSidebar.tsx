import {
  Cloud,
  LayoutDashboard,
  TrendingUp,
  Target,
  FileText,
} from "lucide-react";
import { NavLink } from "@/components/NavLink";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const navItems = [
  { title: "Dashboard", url: "/", icon: LayoutDashboard },
  { title: "Cost Analysis", url: "/cost-analysis", icon: TrendingUp },
  { title: "Budget Alerts", url: "/budget", icon: Target },
  { title: "Reports", url: "/reports", icon: FileText },
];

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";

  return (
    <Sidebar collapsible="icon" className="border-r border-sidebar-border">
      <SidebarHeader className="p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary">
            <Cloud
              className="h-5 w-5 text-primary-foreground"
              strokeWidth={1.5}
            />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <h1 className="truncate text-sm font-bold tracking-tight text-sidebar-foreground">
                Azure Cost Analyzer
              </h1>
              <p className="text-[10px] text-muted-foreground">
                Cloud spending insights
              </p>
            </div>
          )}
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <SidebarMenuButton asChild>
                        <NavLink
                          to={item.url}
                          end={item.url === "/"}
                          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                          activeClassName="bg-sidebar-accent text-sidebar-primary font-medium"
                        >
                          <item.icon
                            className="h-4 w-4 shrink-0"
                            strokeWidth={1.5}
                          />
                          {!collapsed && <span>{item.title}</span>}
                        </NavLink>
                      </SidebarMenuButton>
                    </TooltipTrigger>
                    {collapsed && (
                      <TooltipContent side="right">{item.title}</TooltipContent>
                    )}
                  </Tooltip>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
