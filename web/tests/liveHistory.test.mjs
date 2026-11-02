import {readFileSync} from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
const code=ts.transpileModule(readFileSync(new URL('../src/liveHistory.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {liveHistoryQuery,mergeLiveHistory}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const row=start=>({start,end:start+10,raw:[start],raw_channels:[4],calm:[2],calm_channels:[8],calm_raw:[3],medians:[1]});
const history=(rows,key='a')=>({key,channel_edges:[0,4],window_seconds:900,rows});
test('incremental history retains all rows through duplicates, skipped updates and cursor retries',()=>{
 let prev=history([row(0),row(10)]);
 assert.equal(liveHistoryQuery(),'/live?compact=true');
 assert.equal(liveHistoryQuery(prev),'/live?compact=true&history_key=a&history_after=20');
 const delta={history:history([row(10),row(20),row(40)]),history_delta:true,history_latest_end:50};
 const merged=mergeLiveHistory(prev,delta);
 assert.deepEqual(merged.rows,[row(0),row(10),row(20),row(40)]);
 assert.deepEqual(mergeLiveHistory(merged,delta),merged);
 assert.deepEqual(mergeLiveHistory(merged,{history:history([]),history_delta:true,history_latest_end:50}),merged);
 assert.deepEqual(mergeLiveHistory(merged,{history:history([row(1000)]),history_delta:true,history_latest_end:1010}).rows,[row(1000)]);
});
test('configuration changes, replay rewinds and full responses replace previous history',()=>{
 const previous=history([row(500)]);
 for(const next of [{history:history([row(0)]),history_delta:false},{history:history([row(0)],'b'),history_delta:true}])
  assert.deepEqual(mergeLiveHistory(previous,next),next.history);
 assert.equal(mergeLiveHistory(previous,{}),undefined);
});
