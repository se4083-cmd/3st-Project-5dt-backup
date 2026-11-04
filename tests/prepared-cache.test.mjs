import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { getDashboardData, getProductAnalysis, resolvePreparedSuggestion } from '../frontend/src/lib/analytics/app-service.mjs';
import { evidenceSignatureInput } from '../frontend/src/lib/analytics/insights.mjs';
import { resolvePreparedSuggestions } from '../frontend/src/lib/prepared-suggestions.mjs';
import { sha256 } from '../frontend/src/lib/crypto/sha256.mjs';

test('portable SHA-256 and prepared results match Node and original resolver for all 20 products',async()=>{
  let preparedCount=0;
  for(const {product} of getDashboardData('ALL4').products){
    const {bundle}=getProductAnalysis('ALL4',product.product_id);
    const input=evidenceSignatureInput(bundle);
    assert.equal(sha256(input),createHash('sha256').update(input).digest('hex'));
    const portable=resolvePreparedSuggestions(bundle);
    assert.deepEqual(portable,await resolvePreparedSuggestion(bundle));
    if(portable)preparedCount++;
  }
  assert.equal(preparedCount,15);
});

test('portable cache works without Web Crypto and still rejects changed evidence',()=>{
  const {product}=getDashboardData('ALL4').products[0];
  const {bundle}=getProductAnalysis('ALL4',product.product_id);
  const descriptor=Object.getOwnPropertyDescriptor(globalThis,'crypto');
  try{
    Object.defineProperty(globalThis,'crypto',{value:undefined,configurable:true});
    assert.equal(resolvePreparedSuggestions(bundle)?.mode,'CHATGPT_PREPARED');
    const changed=structuredClone(bundle);
    changed.context.scope_key='T1';
    assert.equal(resolvePreparedSuggestions(changed),null);
    assert.equal(resolvePreparedSuggestions(null),null);
  }finally{
    if(descriptor)Object.defineProperty(globalThis,'crypto',descriptor);
    else delete globalThis.crypto;
  }
});
