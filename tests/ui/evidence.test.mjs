import test from 'node:test';
import assert from 'node:assert/strict';
import {plainIndicators, selectSourceRecords} from '../../src/bottleneck_analyzer/api/static/render.mjs';

test('station evidence uses plain explanations and never turns normalized scores into percentages', () => {
  const original=['High processing/fault occupancy: 0.9998','Input queue accumulation: 0.9826',
    'Upstream blocking: 0.2667','Downstream starvation: 0.2799'];
  const before=structuredClone(original), words=plainIndicators(original);
  assert.equal(words.length,3);
  assert.match(words[1],/Vehicles build up/);
  assert(!words.join(' ').includes('0.9998') && !words.join(' ').includes('%'));
  assert.deepEqual(original,before);
  assert.deepEqual(plainIndicators(['Unrecognized indicator: 0.123']),[]);
  assert.deepEqual(plainIndicators(),[]);
});
test('conflicting signals retain their meaning in everyday language', () => {
  assert.match(plainIndicators(['Substantial own blocking suggests downstream restriction'])[0],/later in the line/);
  assert.match(plainIndicators(['Queue occupancy unavailable'])[0],/unavailable/);
});
test('source examples stay short, diverse and prefer cited support', () => {
  const records=Array.from({length:10},(_,i)=>({evidence_id:'id'+i,source_system:i<5?'CMMS':'SCADA',
    text:'Passage '+i,source_id:'record'+i}));
  const bundle={records,assessments:[{evidence_ids:['id2','id6'],conflicting_evidence_ids:[]}]};
  const original=structuredClone(bundle), result=selectSourceRecords(bundle);
  assert.equal(result.length,3);
  assert.deepEqual(result.slice(0,2).map(r=>r.evidence_id),['id2','id6']);
  assert.equal(result[0].role,'supporting');
  assert.deepEqual(bundle,original);
});
test('a conflicting record is retained even when text duplicates a supporting record', () => {
  const bundle={records:[
    {evidence_id:'good',source_system:'CMMS',text:'Same note'},
    {evidence_id:'bad',source_system:'CMMS',text:'Same note'},
    {evidence_id:'other',source_system:'SCADA',text:'Different note'}
  ],assessments:[{evidence_ids:['good','other'],conflicting_evidence_ids:['bad']}]};
  const result=selectSourceRecords(bundle);
  assert(result.some(r=>r.evidence_id==='bad' && r.role==='limiting'));
  assert(result.length<=3);
});
test('duplicate passages are omitted while document versions remain distinct', () => {
  const records=[1,1,2].map((version,i)=>({evidence_id:'id'+i,source_system:'SOP',
    text:'Procedure',document_version:String(version)}));
  const result=selectSourceRecords({records});
  assert.equal(result.length,2);
  assert(result.every(r=>r.role==='related'));
  assert.deepEqual(selectSourceRecords(null),[]);
});
test('source diversity never promotes an uncited result ahead of cited evidence', () => {
  const records=[
    {evidence_id:'a',source_system:'CMMS',text:'One work order'},
    {evidence_id:'b',source_system:'CMMS',text:'Another work order'},
    {evidence_id:'c',source_system:'SCADA',text:'Uncited record'}
  ];
  const result=selectSourceRecords({records,assessments:[{evidence_ids:['a','b']}]});
  assert.deepEqual(result.slice(0,2).map(r=>r.evidence_id),['a','b']);
});
