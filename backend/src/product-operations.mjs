import { readFileSync } from 'node:fs';
import { ApiError } from './errors.mjs';

const fixture = JSON.parse(readFileSync(new URL('../../data/analytics/fixture.json', import.meta.url), 'utf8'));
const knownProducts = new Set(fixture.products.map((product) => product.product_id));
const links = JSON.parse(readFileSync(new URL('../../data/operations/product-links.json', import.meta.url), 'utf8'));
if (links.source !== 'SYNTHETIC_OPERATION_LINKS_NOT_ANALYTICS_EPISODES' ||
  links.scope !== 'LOCAL_CURRENT_ALL_DEMO_TEAMS' ||
  links.provenance?.analytics_episode_equivalence !== false ||
  [...Object.values(links.scenario_products), ...Object.values(links.order_products)].some((id) => !knownProducts.has(id))) {
  throw new Error('Invalid isolated product operations mapping');
}

function linkedProduct(ticket) {
  if (ticket.rag) {
    // A RAG case must use its verified order, never inherit its fallback scenario.
    const order = ticket.evidence?.order;
    if (!order?.id || order.customerRef !== ticket.customerRef) return null;
    return links.order_products[order.id] ?? null;
  }
  return links.scenario_products[ticket.scenarioId] ?? null;
}

/** Read-only projection. This mapping never joins or rewrites analytical episodes. */
export function getProductOperations(state, revision, productId) {
  if (!knownProducts.has(productId)) throw new ApiError(404, 'PRODUCT_NOT_FOUND', '등록된 합성 상품을 찾을 수 없습니다.');
  const matched = state.tickets.filter((ticket) => linkedProduct(ticket) === productId);
  const tickets = matched.map(({ id, subject, status, cycle, version, team }) => ({ id, subject, status, cycle, version, team }));
  const followups = matched.flatMap((ticket) => ticket.followups.map(({ id, title, status, blocking, dueAt }) =>
    ({ id, ticketId: ticket.id, title, status, blocking, dueAt })));
  return { productId, revision, source: links.source, mappingVersion: links.mapping_version, scope: links.scope,
    tickets, followups, counts: { tickets: tickets.length, openTickets: tickets.filter((ticket) => ticket.status !== 'RESOLVED').length,
      followups: followups.length, openFollowups: followups.filter((followup) => ['OPEN', 'IN_PROGRESS'].includes(followup.status)).length } };
}
