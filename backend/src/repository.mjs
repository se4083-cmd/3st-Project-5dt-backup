import { DatabaseSync } from 'node:sqlite';
import { readFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { createHash } from 'node:crypto';
import { createInitialState } from '../../shared/operations/engine.mjs';
import { ApiError } from './errors.mjs';

const schema = readFileSync(new URL('../../database/schema.sql', import.meta.url), 'utf8');
const demoOrders = JSON.parse(readFileSync(new URL('../../database/demo-orders.json', import.meta.url), 'utf8'));
const hash = (text) => createHash('sha256').update(text).digest('hex');
function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  return value;
}
export const payloadHash = (value) => hash(JSON.stringify(stable(value)));

function forStorage(state) {
  const next = structuredClone(state);
  next.storage = 'SQLITE_LOCAL';
  next.runtimeMode = 'LOCAL_SYNTHETIC_REFERENCE';
  return next;
}

export class RuntimeRepository {
  constructor({ databasePath = ':memory:', clock = Date.now } = {}) {
    if (databasePath !== ':memory:') mkdirSync(dirname(databasePath), { recursive: true });
    this.clock = clock;
    this.db = new DatabaseSync(databasePath);
    this.closed = false;
    this.db.exec('PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000;');
    this.db.exec(schema);
    const now = this.clock();
    this.db.exec('BEGIN IMMEDIATE');
    try {
      if (!this.db.prepare('SELECT id FROM runtime_state WHERE id = 1').get()) {
        const state = forStorage(createInitialState(now));
        this.db.prepare('INSERT INTO runtime_state(id,revision,epoch,payload,updated_at) VALUES(1,1,1,?,?)')
          .run(JSON.stringify(state), new Date(now).toISOString());
        this.recordLedger(state, 1);
      }
      const insertOrder = this.db.prepare('INSERT OR IGNORE INTO demo_orders(id,customer_ref,status,version,eta) VALUES(?,?,?,?,?)');
      for (const order of demoOrders) {
        if (!/^DEMO-ORDER-\d{3}$/.test(order.id) || !['DEMO-CUSTOMER-001', 'DEMO-CUSTOMER-002'].includes(order.customer_ref) ||
          !['IN_TRANSIT', 'DELIVERED', 'PREPARING'].includes(order.status) || !Number.isSafeInteger(order.version) || order.version < 1 ||
          (order.eta !== null && !/^\d{4}-\d{2}-\d{2}$/.test(order.eta))) throw new Error('Invalid synthetic order seed');
        insertOrder.run(order.id, order.customer_ref, order.status, order.version, order.eta);
      }
      this.db.exec('COMMIT');
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }

  read() {
    const row = this.db.prepare('SELECT revision,epoch,payload FROM runtime_state WHERE id = 1').get();
    return { state: JSON.parse(row.payload), revision: row.revision, epoch: row.epoch };
  }

  orders(customerRef, now = this.clock()) {
    return this.db.prepare('SELECT * FROM demo_orders WHERE customer_ref = ? ORDER BY id').all(customerRef)
      .map((row) => this.orderValue(row, now));
  }

  ownedOrder(id, customerRef, now = this.clock()) {
    if (!id) return null;
    const row = this.db.prepare('SELECT * FROM demo_orders WHERE id = ? AND customer_ref = ?').get(id, customerRef);
    return row ? this.orderValue(row, now) : null;
  }

  orderValue(row, now) {
    const labels = { IN_TRANSIT: '배송 중', DELIVERED: '배송 완료', PREPARING: '상품 준비 중' };
    return { id: row.id, reference: row.id, customerRef: row.customer_ref, status: row.status,
      statusLabel: labels[row.status] ?? '확인 중', version: row.version, eta: row.eta,
      fetchedAt: new Date(now).toISOString() };
  }

  replay({ scope, requestId, payload }) {
    if (typeof requestId !== 'string') return null;
    this.db.exec('BEGIN');
    try {
      const current = this.read();
      const existing = this.db.prepare('SELECT * FROM command_receipts WHERE scope = ? AND request_id = ?').get(scope, requestId);
      if (!existing) { this.db.exec('COMMIT'); return null; }
      if (existing.payload_hash !== payloadHash(payload)) throw new ApiError(409, 'IDEMPOTENCY_CONFLICT', '같은 요청 식별자를 다른 내용에 사용할 수 없습니다.');
      if (existing.epoch !== current.epoch) throw new ApiError(409, 'REQUEST_FROM_RESET_SESSION', '초기화 이전 요청입니다. 화면을 새로 확인하고 다시 실행해 주세요.');
      this.db.exec('COMMIT');
      return { ...current, receipt: JSON.parse(existing.receipt_json), replayed: true };
    } catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }

  /** Validate an earlier lookup under the same SQLite write lock as finalization. */
  orderSnapshotValid(order, customerRef, now = this.clock()) {
    if (!order) return false;
    const current = this.ownedOrder(order.id, customerRef, now);
    const age = now - Date.parse(order.fetchedAt);
    return Boolean(current && current.version === order.version && current.status === order.status &&
      current.eta === order.eta && Number.isFinite(age) && age >= 0 && age <= 60000);
  }

  recordLedger(state, epoch) {
    const eventInsert = this.db.prepare('INSERT OR IGNORE INTO runtime_events(epoch,event_id,ticket_id,cycle,event_type,created_at) VALUES(?,?,?,?,?,?)');
    for (const event of state.events) eventInsert.run(epoch, event.id, event.ticketId, event.cycle, event.type, event.createdAt);
    const findFinal = this.db.prepare('SELECT * FROM final_replies WHERE epoch = ? AND ticket_id = ? AND cycle = ?');
    const addFinal = this.db.prepare('INSERT INTO final_replies(epoch,ticket_id,cycle,message_id,content_hash,author,created_at) VALUES(?,?,?,?,?,?,?)');
    const seen = new Set();
    for (const ticket of state.tickets) {
      for (const message of ticket.messages.filter((item) => item.final && item.author !== 'CUSTOMER')) {
        const key = `${ticket.id}:${message.cycle}`;
        if (seen.has(key)) throw new ApiError(409, 'FINAL_REPLY_ALREADY_EXISTS', '한 회차에는 최종 답변을 한 건만 확정할 수 있습니다.');
        seen.add(key);
        const existing = findFinal.get(epoch, ticket.id, message.cycle);
        const digest = hash(message.text);
        if (existing && (existing.message_id !== message.id || existing.content_hash !== digest || existing.author !== message.author)) {
          throw new ApiError(409, 'FINAL_REPLY_IMMUTABLE', '확정한 답변은 덮어쓸 수 없습니다. 새 회차를 사용해 주세요.');
        }
        if (!existing) addFinal.run(epoch, ticket.id, message.cycle, message.id, digest, message.author, message.createdAt);
      }
    }
    const previous = this.db.prepare('SELECT ticket_id,cycle FROM final_replies WHERE epoch = ?').all(epoch);
    if (previous.some((row) => !seen.has(`${row.ticket_id}:${row.cycle}`))) {
      throw new ApiError(409, 'FINAL_REPLY_IMMUTABLE', '기존 회차의 확정 답변은 이력에서 제거할 수 없습니다.');
    }
  }

  /** No await, model call, or remote HTTP is allowed inside this transaction. */
  command({ scope, requestId, payload, expectedRevision, reset = false }, execute) {
    if (typeof requestId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/.test(requestId)) {
      throw new ApiError(422, 'INVALID_REQUEST_ID', 'requestId는 8~128자의 영문·숫자 식별자로 전달해 주세요.');
    }
    if (!Number.isSafeInteger(expectedRevision) || expectedRevision < 1) {
      throw new ApiError(422, 'EXPECTED_REVISION_REQUIRED', '현재 상태의 expectedStateRevision이 필요합니다.');
    }
    const digest = payloadHash(payload);
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const current = this.read();
      const existing = this.db.prepare('SELECT * FROM command_receipts WHERE scope = ? AND request_id = ?').get(scope, requestId);
      if (existing) {
        if (existing.payload_hash !== digest) throw new ApiError(409, 'IDEMPOTENCY_CONFLICT', '같은 요청 식별자를 다른 내용에 사용할 수 없습니다.');
        if (existing.epoch !== current.epoch) throw new ApiError(409, 'REQUEST_FROM_RESET_SESSION', '초기화 이전 요청입니다. 화면을 새로 확인하고 다시 실행해 주세요.');
        const receipt = JSON.parse(existing.receipt_json);
        this.db.exec('COMMIT');
        return { ...current, receipt, replayed: true };
      }
      if (current.revision !== expectedRevision) {
        throw new ApiError(409, 'STALE_STATE_REVISION', '다른 작업으로 상태가 변경되었습니다. 최신 내용을 확인하고 다시 실행해 주세요.', { revision: current.revision });
      }
      const now = this.clock();
      const outcome = execute(current.state, now);
      if (!outcome || typeof outcome.then === 'function' || !outcome.state) throw new Error('Synchronous state outcome required');
      if (outcome.state.notice?.kind === 'error') throw new ApiError(409, 'INVALID_TRANSITION', outcome.state.notice.message);
      const state = forStorage(outcome.state);
      const revision = current.revision + 1;
      const epoch = reset ? current.epoch + 1 : current.epoch;
      this.recordLedger(state, epoch);
      const result = this.db.prepare('UPDATE runtime_state SET revision=?,epoch=?,payload=?,updated_at=? WHERE id=1 AND revision=?')
        .run(revision, epoch, JSON.stringify(state), new Date(now).toISOString(), current.revision);
      if (result.changes !== 1) throw new ApiError(409, 'STALE_STATE_REVISION', '저장 직전 상태가 변경되어 결과를 적용하지 않았습니다.');
      const receipt = { appliedRevision: revision, epoch, ticketId: outcome.ticketId ?? null,
        notice: state.notice, ...(outcome.result ? { result: outcome.result } : {}) };
      this.db.prepare('INSERT INTO command_receipts(scope,request_id,payload_hash,epoch,applied_revision,receipt_json,created_at) VALUES(?,?,?,?,?,?,?)')
        .run(scope, requestId, digest, epoch, revision, JSON.stringify(receipt), new Date(now).toISOString());
      this.db.exec('COMMIT');
      return { state, revision, epoch, receipt, replayed: false };
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }

  counts() {
    return { events: this.db.prepare('SELECT COUNT(*) AS n FROM runtime_events').get().n,
      finals: this.db.prepare('SELECT COUNT(*) AS n FROM final_replies').get().n,
      receipts: this.db.prepare('SELECT COUNT(*) AS n FROM command_receipts').get().n };
  }

  close() { if (!this.closed) { this.closed = true; this.db.close(); } }
}
