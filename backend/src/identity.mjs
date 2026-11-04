import { ApiError } from './errors.mjs';

export const DEMO_CUSTOMERS = Object.freeze(['DEMO-CUSTOMER-001', 'DEMO-CUSTOMER-002']);
export const DEMO_ROLES = Object.freeze(['admin', 'agent', 'customer']);

/** Explicitly a local simulation selector, never a production authentication scheme. */
export function demoPrincipal(headers) {
  const role = headers['x-demo-role'];
  if (!DEMO_ROLES.includes(role)) throw new ApiError(401, 'DEMO_IDENTITY_REQUIRED', '로컬 시연 역할을 선택해 주세요.');
  const customerRef = headers['x-demo-customer'] ?? DEMO_CUSTOMERS[0];
  if (!DEMO_CUSTOMERS.includes(customerRef)) throw new ApiError(403, 'UNKNOWN_DEMO_CUSTOMER', '등록된 합성 고객만 사용할 수 있습니다.');
  return { role, customerRef, id: role === 'customer' ? customerRef : `DEMO-${role.toUpperCase()}` };
}

export function requireRole(principal, roles) {
  if (!roles.includes(principal.role)) throw new ApiError(403, 'ROLE_NOT_ALLOWED', '현재 시연 역할은 이 작업을 수행할 수 없습니다.');
}

export function requireOwnedTicket(state, id, principal) {
  const ticket = state.tickets.find((item) => item.id === id);
  // Return the same result for an unknown object and another customer's object.
  if (!ticket || (principal.role === 'customer' && ticket.customerRef !== principal.customerRef)) {
    throw new ApiError(404, 'TICKET_NOT_FOUND', '접근할 수 있는 문의를 찾을 수 없습니다.');
  }
  return ticket;
}
