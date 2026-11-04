/**
 * Isolated, fictional operations cases for the L2/L3 v2 walkthrough.
 * These are not imported customer records, live policies, or backend results.
 */
export const DEMO_POLICY_SOURCE = 'ISOLATED_SYNTHETIC_FIXTURE';

export const demoPolicies = Object.freeze({
  shipping: Object.freeze({
    id: 'DEMO-POLICY-SHIPPING', title: '합성 배송 상태 안내 정책', version: 1,
    clause: '배송-01', active: true,
    text: '소유권이 확인된 합성 주문의 현재 배송 상태만 안내한다. 도착 예정일이 없으면 미정으로 안내한다.',
  }),
  faq: Object.freeze({
    id: 'DEMO-POLICY-FAQ', title: '합성 문의 확인 FAQ', version: 1,
    clause: 'FAQ-01', active: true,
    text: '고객은 접수한 문의 상세에서 현재 진행 단계와 확정된 답변을 확인한다.',
  }),
  returns: Object.freeze({
    id: 'DEMO-POLICY-RETURN', title: '합성 반품 절차 안내 정책', version: 1,
    clause: '반품-01', active: true,
    text: '주문 상세에서 신청 내용을 등록하고 처리 상태를 확인하는 절차만 안내한다. 승인, 금액 및 기한 예외는 사람이 검토한다.',
  }),
  general: Object.freeze({
    id: 'DEMO-POLICY-GENERAL', title: '합성 일반 문의 접수 정책', version: 1,
    clause: '접수-01', active: true,
    text: '주문과 관계 없는 일반 문의는 주문 선택 없이 접수할 수 있다. 주문 상태 조회에는 별도의 소유권 확인이 필요하다.',
  }),
});

const common = {
  owned: true, customerActive: true, policyValid: true, queryAgeSeconds: 0,
  ruleSnapshotMismatch: false, requiresFollowup: false, highRisk: false,
  orderRelevant: true, priority: 'NORMAL', category: 'SHIPPING', policyKey: 'shipping',
  allowKind: 'ORDER_STATUS', templateKey: 'DEMO_SHIPPING_STATUS_V1',
};

const cases = [
  {
    id: 'shipping_status', title: '배송 상태 안내', group: 'L2',
    description: '본인 합성 주문의 현재 상태를 안내합니다. 없는 도착 예정일은 만들지 않습니다.',
    body: '배송 상태를 알려 주세요.',
    answer: '연결된 합성 주문의 현재 배송 상태는 배송 중입니다. 도착 예정일은 아직 확인되지 않았습니다.',
  },
  {
    id: 'general_faq', title: '주문 무관 FAQ', group: 'L2', category: 'ACCOUNT',
    description: '주문 정보가 필요 없는 사전 정의 FAQ를 유효한 근거로 안내합니다.',
    body: '접수한 문의의 답변은 어디에서 확인하나요?',
    answer: '접수한 문의 상세에서 현재 진행 단계와 확정된 답변을 확인할 수 있습니다.',
    orderRelevant: false, policyKey: 'faq', allowKind: 'GENERAL_FAQ', templateKey: 'DEMO_FAQ_V1',
  },
  {
    id: 'return_procedure', title: '교환·반품 절차 안내', group: 'L2', category: 'RETURN',
    description: '신청 절차만 안내하고 반품 승인이나 환불 금액을 확정하지 않습니다.',
    body: '반품 신청 절차를 알려 주세요.',
    answer: '합성 시연 정책의 반품 신청 절차는 주문 상세에서 신청 내용을 등록한 뒤 처리 상태를 확인하는 순서입니다. 반품 승인과 환불 여부는 별도로 확인해야 합니다.',
    policyKey: 'returns', allowKind: 'RETURN_PROCEDURE', templateKey: 'DEMO_RETURN_PROCEDURE_V1',
  },
  {
    id: 'policy_guidance', title: '명확한 정책 안내', group: 'L2', category: 'ACCOUNT',
    description: '주문 없는 일반 문의 접수에 대한 사전 정의 정책을 안내합니다.',
    body: '일반 문의도 주문 없이 접수할 수 있나요?',
    answer: '주문과 관계 없는 일반 문의는 주문 선택 없이 접수할 수 있습니다. 주문 상태 확인이 필요한 문의는 본인 주문 확인을 거쳐 안내합니다.',
    orderRelevant: false, policyKey: 'general', allowKind: 'POLICY_GUIDANCE', templateKey: 'DEMO_GENERAL_POLICY_V1',
  },
  {
    id: 'refund_request', title: '환불 승인 요청', group: 'L3', category: 'REFUND', priority: 'HIGH',
    description: '환불 권리·금액의 자동 결정을 차단하고 반품환불팀으로 넘깁니다.',
    body: '지금 바로 환불을 승인해 주세요.', highRisk: true, allowKind: null, policyKey: 'returns',
  },
  {
    id: 'compensation_request', title: '보상 확정 요청', group: 'L3', category: 'REFUND', priority: 'HIGH',
    description: '보상 지급을 자동으로 약속하지 않고 사람 검토로 전환합니다.',
    body: '불편했으니 보상금을 확정해 주세요.', highRisk: true, allowKind: null, policyKey: 'returns',
  },
  {
    id: 'account_rights', title: '계정 권리 변경 요청', group: 'L3', category: 'ACCOUNT', priority: 'HIGH',
    description: '계정 제한 해제 같은 권리 변경을 자동 실행하지 않습니다.',
    body: '계정의 이용 제한을 지금 해제해 주세요.', highRisk: true, allowKind: null,
    orderRelevant: false, policyKey: 'general',
  },
  {
    id: 'ownership_unverified', title: '주문 소유권 미확인', group: 'EXCEPTION',
    description: '연결 권한을 확인할 수 없는 주문은 존재나 상태를 노출하지 않고 이관합니다.',
    body: '이 주문의 배송 상태를 확인해 주세요.', owned: false,
  },
  {
    id: 'missing_policy', title: '정책 근거 없음', group: 'EXCEPTION', category: 'RETURN',
    description: '유효한 정책을 확보하지 못하면 자동 답변을 만들지 않습니다.',
    body: '이 경우의 반품 절차를 알려 주세요.', policyKey: 'returns', policyValid: false,
    allowKind: 'RETURN_PROCEDURE', templateKey: 'DEMO_RETURN_PROCEDURE_V1',
  },
  {
    id: 'stale_lookup', title: '오래된 주문 조회', group: 'EXCEPTION',
    description: '조회한 지 60초가 지난 합성 주문 정보로 자동 안내하지 않습니다.',
    body: '현재 배송 상태를 확인해 주세요.', queryAgeSeconds: 120,
  },
  {
    id: 'rule_changed', title: '처리 중 규칙 변경', group: 'EXCEPTION',
    description: '작업 준비 당시 규칙과 현재 규칙이 다르면 자동 답변을 차단합니다.',
    body: '배송 중인지 알려 주세요.', ruleSnapshotMismatch: true,
  },
  {
    id: 'required_followup', title: '필수 후속 확인', group: 'EXCEPTION',
    description: '담당자가 확인해야 하는 업무가 있으면 안내만으로 종료하지 않습니다.',
    body: '배송 상태를 담당자가 추가로 확인해 주세요.', requiresFollowup: true,
  },
];

export const scenarioDefinitions = Object.freeze(Object.fromEntries(cases.map((item) => [
  item.id, Object.freeze({ ...common, ...item }),
])));

export const scenarioCatalog = Object.freeze(cases.map(({ id, title, group, description, body }) =>
  Object.freeze({ id, title, group, description, defaultBody: body }),
));

export function getScenario(id) {
  return typeof id === 'string' && Object.hasOwn(scenarioDefinitions, id)
    ? scenarioDefinitions[id] : null;
}
