import * as React from "react"
import {
  Calculator,
  Calendar,
  MessageSquare,
  Plus,
  Search,
  Settings,
  Users,
  Webhook,
  Clock,
  Globe,
  Shield,
  Archive,
  Play,
  Pause,
  TestTube,
  History,
  Code,
  FileText,
} from "lucide-react"
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import { Kbd } from "@/components/ui/kbd"

/**
 * Command definition for the command palette
 */
interface Command {
  id: string
  label: string
  icon: React.ComponentType<{ className?: string }>
  category: CommandCategory
  keywords: string[]
  action: () => void
  shortcut?: string
}

/**
 * Command categories for grouping
 */
type CommandCategory = 
  | "Channels" 
  | "Sessions" 
  | "Webhooks" 
  | "Cron" 
  | "Browser" 
  | "Security"
  | "Navigation"

/**
 * Recent command stored in localStorage
 */
interface RecentCommand {
  id: string
  timestamp: number
}

const RECENT_COMMANDS_KEY = "commandPalette.recentCommands"
const MAX_RECENT_COMMANDS = 5

/**
 * CommandPalette component provides quick access to all gateway management actions
 * 
 * Features:
 * - Triggered with Cmd+K (Mac) or Ctrl+K (Windows/Linux)
 * - Search all available commands
 * - Show recent commands
 * - Group commands by category
 * - Display keyboard shortcuts
 * - Execute command on selection
 * 
 * @example
 * ```tsx
 * <CommandPalette 
 *   onNavigate={(tab) => setActiveTab(tab)}
 *   onOpenDialog={(dialog) => setOpenDialog(dialog)}
 * />
 * ```
 */
export interface CommandPaletteProps {
  /**
   * Callback when navigating to a tab
   */
  onNavigate?: (tab: string) => void
  
  /**
   * Callback when opening a dialog
   */
  onOpenDialog?: (dialog: string) => void
}

export function CommandPalette({ onNavigate, onOpenDialog }: CommandPaletteProps) {
  const [open, setOpen] = React.useState(false)
  const [recentCommands, setRecentCommands] = React.useState<RecentCommand[]>([])

  // Load recent commands from localStorage
  React.useEffect(() => {
    const stored = localStorage.getItem(RECENT_COMMANDS_KEY)
    if (stored) {
      try {
        setRecentCommands(JSON.parse(stored))
      } catch (error) {
        console.error("Failed to parse recent commands:", error)
      }
    }
  }, [])

  // Save recent commands to localStorage
  const saveRecentCommand = React.useCallback((commandId: string) => {
    setRecentCommands((prev) => {
      // Remove existing entry if present
      const filtered = prev.filter((cmd) => cmd.id !== commandId)
      
      // Add new entry at the beginning
      const updated = [
        { id: commandId, timestamp: Date.now() },
        ...filtered,
      ].slice(0, MAX_RECENT_COMMANDS)
      
      localStorage.setItem(RECENT_COMMANDS_KEY, JSON.stringify(updated))
      return updated
    })
  }, [])

  // Handle keyboard shortcut (Cmd+K or Ctrl+K)
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((open) => !open)
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [])

  // Execute command and track in recent commands
  const executeCommand = React.useCallback((command: Command) => {
    command.action()
    saveRecentCommand(command.id)
    setOpen(false)
  }, [saveRecentCommand])

  // Define all available commands
  const commands: Command[] = React.useMemo(() => [
    // Navigation
    {
      id: "nav-channels",
      label: "View Channels",
      icon: MessageSquare,
      category: "Navigation",
      keywords: ["channels", "view", "list", "messaging"],
      action: () => onNavigate?.("gateway"),
    },
    {
      id: "nav-sessions",
      label: "View Sessions",
      icon: Users,
      category: "Navigation",
      keywords: ["sessions", "view", "list", "conversations"],
      action: () => onNavigate?.("gateway"),
    },
    {
      id: "nav-webhooks",
      label: "View Webhooks",
      icon: Webhook,
      category: "Navigation",
      keywords: ["webhooks", "view", "list", "http"],
      action: () => onNavigate?.("gateway"),
    },
    {
      id: "nav-cron",
      label: "View Cron Jobs",
      icon: Clock,
      category: "Navigation",
      keywords: ["cron", "jobs", "view", "list", "scheduled"],
      action: () => onNavigate?.("gateway"),
    },
    
    // Channels
    {
      id: "channel-add",
      label: "Add Channel",
      icon: Plus,
      category: "Channels",
      keywords: ["add", "create", "new", "channel", "slack", "telegram", "discord"],
      action: () => onOpenDialog?.("add-channel"),
      shortcut: "⌘N",
    },
    {
      id: "channel-test",
      label: "Test Channel Connection",
      icon: TestTube,
      category: "Channels",
      keywords: ["test", "channel", "connection", "verify"],
      action: () => onOpenDialog?.("test-channel"),
    },
    
    // Sessions
    {
      id: "session-send",
      label: "Send Message",
      icon: MessageSquare,
      category: "Sessions",
      keywords: ["send", "message", "session", "chat"],
      action: () => onOpenDialog?.("send-message"),
      shortcut: "⌘M",
    },
    {
      id: "session-archive",
      label: "Archive Session",
      icon: Archive,
      category: "Sessions",
      keywords: ["archive", "session", "close", "end"],
      action: () => onOpenDialog?.("archive-session"),
    },
    {
      id: "session-history",
      label: "View Session History",
      icon: History,
      category: "Sessions",
      keywords: ["history", "session", "messages", "view"],
      action: () => onOpenDialog?.("session-history"),
    },
    
    // Webhooks
    {
      id: "webhook-create",
      label: "Create Webhook",
      icon: Plus,
      category: "Webhooks",
      keywords: ["create", "webhook", "new", "http", "endpoint"],
      action: () => onOpenDialog?.("create-webhook"),
    },
    {
      id: "webhook-test",
      label: "Test Webhook",
      icon: TestTube,
      category: "Webhooks",
      keywords: ["test", "webhook", "payload", "trigger"],
      action: () => onOpenDialog?.("test-webhook"),
    },
    {
      id: "webhook-logs",
      label: "View Webhook Logs",
      icon: FileText,
      category: "Webhooks",
      keywords: ["logs", "webhook", "history", "execution"],
      action: () => onOpenDialog?.("webhook-logs"),
    },
    
    // Cron Jobs
    {
      id: "cron-create",
      label: "Create Cron Job",
      icon: Plus,
      category: "Cron",
      keywords: ["create", "cron", "job", "schedule", "new"],
      action: () => onOpenDialog?.("create-cron"),
    },
    {
      id: "cron-execute",
      label: "Execute Job Now",
      icon: Play,
      category: "Cron",
      keywords: ["execute", "run", "cron", "job", "now", "trigger"],
      action: () => onOpenDialog?.("execute-cron"),
    },
    {
      id: "cron-pause",
      label: "Pause Cron Job",
      icon: Pause,
      category: "Cron",
      keywords: ["pause", "stop", "cron", "job", "disable"],
      action: () => onOpenDialog?.("pause-cron"),
    },
    {
      id: "cron-history",
      label: "View Execution History",
      icon: History,
      category: "Cron",
      keywords: ["history", "cron", "execution", "logs"],
      action: () => onOpenDialog?.("cron-history"),
    },
    
    // Browser
    {
      id: "browser-view",
      label: "View Browser Instances",
      icon: Globe,
      category: "Browser",
      keywords: ["browser", "instances", "view", "automation"],
      action: () => onOpenDialog?.("browser-instances"),
    },
    {
      id: "browser-close",
      label: "Close All Browsers",
      icon: Archive,
      category: "Browser",
      keywords: ["close", "browser", "all", "cleanup"],
      action: () => onOpenDialog?.("close-browsers"),
    },
    
    // Security
    {
      id: "security-audit",
      label: "View Audit Log",
      icon: Shield,
      category: "Security",
      keywords: ["audit", "log", "security", "events"],
      action: () => onOpenDialog?.("audit-log"),
    },
    {
      id: "security-approval",
      label: "Generate Approval Code",
      icon: Code,
      category: "Security",
      keywords: ["approval", "code", "generate", "dm", "pairing"],
      action: () => onOpenDialog?.("generate-approval"),
    },
    {
      id: "security-pending",
      label: "View Pending Approvals",
      icon: Clock,
      category: "Security",
      keywords: ["pending", "approvals", "dm", "pairing", "users"],
      action: () => onOpenDialog?.("pending-approvals"),
    },
  ], [onNavigate, onOpenDialog])

  // Get recent commands with full command data
  const recentCommandsData = React.useMemo(() => {
    return recentCommands
      .map((recent) => commands.find((cmd) => cmd.id === recent.id))
      .filter((cmd): cmd is Command => cmd !== undefined)
  }, [recentCommands, commands])

  // Group commands by category
  const commandsByCategory = React.useMemo(() => {
    const grouped = new Map<CommandCategory, Command[]>()
    
    commands.forEach((command) => {
      const existing = grouped.get(command.category) || []
      grouped.set(command.category, [...existing, command])
    })
    
    return grouped
  }, [commands])

  return (
    <>
      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput placeholder="Type a command or search..." />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>
          
          {/* Recent Commands */}
          {recentCommandsData.length > 0 && (
            <>
              <CommandGroup heading="Recent">
                {recentCommandsData.map((command) => (
                  <CommandItem
                    key={command.id}
                    onSelect={() => executeCommand(command)}
                  >
                    <command.icon className="mr-2 h-4 w-4" />
                    <span>{command.label}</span>
                    {command.shortcut && (
                      <Kbd className="ml-auto">{command.shortcut}</Kbd>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
              <CommandSeparator />
            </>
          )}
          
          {/* Commands by Category */}
          {Array.from(commandsByCategory.entries()).map(([category, categoryCommands]) => (
            <React.Fragment key={category}>
              <CommandGroup heading={category}>
                {categoryCommands.map((command) => (
                  <CommandItem
                    key={command.id}
                    onSelect={() => executeCommand(command)}
                    keywords={command.keywords}
                  >
                    <command.icon className="mr-2 h-4 w-4" />
                    <span>{command.label}</span>
                    {command.shortcut && (
                      <Kbd className="ml-auto">{command.shortcut}</Kbd>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
              {category !== "Security" && <CommandSeparator />}
            </React.Fragment>
          ))}
        </CommandList>
      </CommandDialog>
    </>
  )
}
