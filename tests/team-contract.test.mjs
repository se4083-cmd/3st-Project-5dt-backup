import test from 'node:test';
import assert from 'node:assert/strict';
import { toTeamCategory, toStaffCategory, legacyAnalysisInput, toEvidenceReference, toBackendBEnvelope } from '../shared/contracts/team-contract.mjs';

const options = { suggestionId:'7bc573b9-dc6e-46dc-8853-6abf54132ef4', ruleId:'d5ab3b2e-7282-4ab2-80ae-0ee203b5b5e3' };
const evidence = { documentId:'a253bcd2-5b21-435f-9055-a633c67e8354', version:1, contentHash:'a'.repeat(64), clauseId:'FAQ-1', scope:'DEMO_ONLY' };
const result = { reply:'문의 내역에서 답변을 확인합니다.', evidence:[evidence], category:'SHIPPING', eligible:true,
  scope:'DEMO_ONLY', mode:'RETRIEVAL_TEMPLATE', promptVersion:'local-template-v1', modelVersion:'NONE' };

test('category bridge keeps UNKNOWN/staff UNCLASSIFIED and SHIPPING/DELIVERY explicit', () => {
  assert.equal(toTeamCategory('SHIPPING'), 'DELIVERY');
  assert.equal(toStaffCategory('UNKNOWN'), 'UNCLASSIFIED');
  assert.equal(toTeamCategory('UNCLASSIFIED'), 'UNKNOWN');
  assert.throws(() => toTeamCategory('REVIEW'), /UNSUPPORTED_CATEGORY/);
});

test('long legacy inputs are not silently cut and supplementary Unicode counts as one character', () => {
  const query = '가'.repeat(4001);
  assert.deepEqual(legacyAnalysisInput(query), { status:'REQUIRES_LONG_INPUT_ADAPTER', query:null, originalLength:4001 });
  assert.equal(legacyAnalysisInput('😀'.repeat(4000)).status, 'READY');
  assert.throws(() => legacyAnalysisInput('가'.repeat(10001)), /INVALID_INQUIRY_LENGTH/);
});

test('evidence mapping requires UUID, positive version, SHA256 and clause', () => {
  assert.equal(toEvidenceReference(evidence).document_id, evidence.documentId);
  assert.throws(() => toEvidenceReference({...evidence,documentId:'DEMO-1'}), /INVALID_EVIDENCE/);
  assert.throws(() => toEvidenceReference({...evidence,contentHash:'bad'}), /INVALID_EVIDENCE/);
});

test('retrieval success and review signals do not authorize Backend B', () => {
  assert.equal(toBackendBEnvelope({...result,review_required:false}, options).allowed, false);
  assert.throws(() => toBackendBEnvelope(result, {...options,suggestionId:'DEMO-1'}), /TEAM_UUIDS_REQUIRED/);
});

test('demo evidence stays blocked even when a caller passes a backend decision', () => {
  const mapped = toBackendBEnvelope(result, {...options,backendDecision:{authority:'BACKEND_FINALIZATION_GATE',verdict:'ALLOW',cycle_no:1,expected_ticket_version:2}});
  assert.equal(mapped.allowed, false);
  assert.equal(mapped.blocked_reason, 'DEMO_EVIDENCE_NOT_PRODUCTION_APPROVAL');
});
