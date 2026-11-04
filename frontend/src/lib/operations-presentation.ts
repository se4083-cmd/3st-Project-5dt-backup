/** Read-only view calculations. All decisions and mutations run on the API. */
type Data = Record<string, any>;

export function deriveMetrics(state: Data) {
  const tickets: Data[] = state.tickets ?? [];
  return {
    total: tickets.length,
    autoCompleted: tickets.filter(ticket => ticket.status === "RESOLVED" && ticket.resolutionMode === "AUTO").length,
    openFollowups: tickets.reduce((total, ticket) => total + (ticket.followups ?? []).filter((followup: Data) => ["OPEN", "IN_PROGRESS"].includes(followup.status)).length, 0),
  };
}
