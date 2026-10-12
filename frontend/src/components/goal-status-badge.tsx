const CONFIG: Record<string, { bg: string; text: string; key: string }> = {
  active: { bg: 'bg-emerald-100 dark:bg-emerald-500/20', text: 'text-emerald-700 dark:text-emerald-400', key: 'goals.statusActive' },
  completed: { bg: 'bg-blue-100 dark:bg-blue-500/20', text: 'text-blue-700 dark:text-blue-400', key: 'goals.statusCompleted' },
  paused: { bg: 'bg-amber-100 dark:bg-amber-500/20', text: 'text-amber-700 dark:text-amber-400', key: 'goals.statusPaused' },
  archived: { bg: 'bg-muted', text: 'text-muted-foreground', key: 'goals.statusArchived' },
  missed: { bg: 'bg-rose-100 dark:bg-rose-500/20', text: 'text-rose-700 dark:text-rose-400', key: 'goals.statusMissed' },
}

export function GoalStatusBadge({ status, t }: { status: string; t: (key: string) => string }) {
  const c = CONFIG[status] ?? CONFIG.active
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${c.bg} ${c.text}`}>
      {t(c.key)}
    </span>
  )
}
