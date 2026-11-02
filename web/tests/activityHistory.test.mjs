import {readFileSync} from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
const code=ts.transpileModule(readFileSync(new URL('../src/activityHistory.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {historyHeatmap}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const row=(start)=>({start,end:start+10,raw:[4,9],raw_channels:[0,4],calm:[8,null],calm_channels:[4,null],calm_raw:[9,null],medians:[1,null]});
test('successive files become distinct ten-second rows with explicit time gaps',()=>{
 const history={channel_edges:[-2,2,6],rows:[row(1000),row(1010),row(1040)]};
 const heat=historyHeatmap(history,false);
 assert.deepEqual(heat.time_edges,[1000,1010,1020,1040,1050]);
 assert.deepEqual(heat.values,[[4,9],[4,9],[null,null],[4,9]]);
 assert.deepEqual(heat.peak_channels[2],[null,null]);
 const calm=historyHeatmap(history,true);
 assert.deepEqual(calm.time_edges,heat.time_edges);
 assert.deepEqual(calm.values[0],[8,null]);assert.deepEqual(calm.peak_channels[0],[4,null]);
 assert.deepEqual(calm.raw[0],[9,null]);assert.deepEqual(calm.medians[0],[1,null]);
});
test('no collected history is explicit, never a stretched current-file row',()=>{
 assert.equal(historyHeatmap(undefined,true).status,'unavailable');
 assert.equal(historyHeatmap({rows:[]},false).status,'unavailable');
});
test('sub-sample positive and negative timing jitter never becomes a blank stripe',()=>{
 for (const jitter of [-.00102,.00102]) {
  const heat=historyHeatmap({sample_interval:.00204,channel_edges:[-2,2,6],rows:[row(1000),row(1010+jitter)]},true);
  assert.equal(heat.values.length,2);
  assert.deepEqual(heat.time_edges,[1000,1010+jitter,1020+jitter]);
 }
 const missing=historyHeatmap({sample_interval:.00204,channel_edges:[-2,2,6],rows:[row(1000),row(1020)]},true);
 assert.deepEqual(missing.values[1],[null,null]);
});
