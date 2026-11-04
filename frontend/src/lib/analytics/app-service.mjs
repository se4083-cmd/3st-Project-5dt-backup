import fixture from '../../../../data/analytics/fixture.json' with { type: 'json' };
import prepared from '../../../../data/analytics/prepared-suggestions.json' with { type: 'json' };
import { listScopes, getProductsForScope, getProductContext } from './adapter.mjs';
import { buildEvidenceBundle, generateRuleSuggestions, validateGeneratedSuggestions, evidenceSignatureInput, issueLabel } from './insights.mjs';
import { analyzeSeries } from './detector.mjs';
import { listScenarios, getScenario } from './scenarios.mjs';

export { issueLabel };
export const fixtureMetadata = Object.freeze({batch_id:fixture.default_batch_id, schema_version:fixture.schema_version});

export function statusLabel(status) {
  return ({NORMAL:'평소 범위',ALERT:'변화 감지',WATCH:'관찰 필요',LOW_BASELINE:'기준 표본 부족',INSUFFICIENT_HISTORY:'이력 부족',INCOMPLETE_DATA:'수집 누락',DATA_BLOCKED:'품질 확인 필요',INVALID_INPUT:'입력 확인 필요'})[status] ?? status;
}

export function getDashboardData(scopeKey = 'ALL4') {
  const products = getProductsForScope(fixture,scopeKey);
  return {
    scopes:listScopes(fixture), products,
    stats:{products:products.length,episodes:products.reduce((s,r)=>s+r.risk.metrics.C,0),unresolved:products.reduce((s,r)=>s+r.risk.metrics.U,0),eligible:products.filter(r=>r.risk.data_status==='ELIGIBLE').length,low_sample:products.filter(r=>r.risk.data_status==='LOW_SAMPLE').length},
  };
}

export function getProductAnalysis(scopeKey,productId,batchId=fixture.default_batch_id) {
  const context=getProductContext(fixture,{scope_key:scopeKey,product_id:productId,batch_id:batchId});
  const {risk}=context;
  const bundle=buildEvidenceBundle({...context,anomaly:null});
  const anomaly=analyzeSeries({batch_id:risk.batch_id,scope_key:risk.scope_key,product_id:risk.product_id,data_status:risk.data_status,source_as_of:risk.source_as_of,coverage:context.coverage,rows:context.daily});
  const issues=new Map();
  for(const row of context.daily) issues.set(row.primary_issue,(issues.get(row.primary_issue)??0)+row.episode_count);
  return {context,bundle,anomaly,suggestions:generateRuleSuggestions(bundle),daily:anomaly.daily_series,
    issues:[...issues].map(([issue,count])=>({issue,count})).sort((a,b)=>b.count-a.count||a.issue.localeCompare(b.issue))};
}

export async function resolvePreparedSuggestion(bundle) {
  const key=`${bundle.context.batch_id}|${bundle.context.scope_key}|${bundle.product.product_id}`;
  const entry=prepared.entries[key];
  if(!entry) return null;
  try {
    const bytes=new TextEncoder().encode(evidenceSignatureInput(bundle));
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
    if(hash!==entry.input_sha256) return null;
    const check=validateGeneratedSuggestions(entry.payload,bundle);
    if(!check.valid) return null;
    return {...check.value,mode:'CHATGPT_PREPARED',mode_label:'사전 작성 AI 제안',provenance:entry.provenance,input_sha256:hash,generation_status:'PREPARED_VALIDATED'};
  }catch{return null;}
}

export function scenarioOptions(){return listScenarios();}
export function runScenario(id){return analyzeSeries(getScenario(id));}
