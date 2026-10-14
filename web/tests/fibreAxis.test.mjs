import {readFileSync} from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
const code=ts.transpileModule(readFileSync(new URL('../src/fibreAxis.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {fibreAxis,profileOrder,heatOrder,geographicSections}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const axis=fibreAxis([{start:108,end:100,label:'Southern section'},{start:0,end:8,label:'Northern section'}],8);
test('two sections retain native IDs while reversing the southern section',()=>{
 assert.deepEqual([108,104,100,0,4,8].map(axis.position),[0,4,8,16,20,24]);
 assert.equal(axis.position(50),null);assert.equal(axis.position(null),null);
});
test('profile reordering retains extrema alignment and missing-data breaks',()=>{
 const channels=[0,4,8,null,100,null,104,108];
 const order=profileOrder(channels,axis);
 assert.deepEqual(order.map(i=>i===null?null:channels[i]),[null,108,104,null,100,null,null,0,4,8,null]);
 const values=[1,2,3,null,4,null,5,6];
 assert.deepEqual(order.filter(i=>i!==null).map(i=>values[i]),[6,5,4,1,2,3]);
});
test('heat bins reverse intact, preserve width and insert a blank section separator',()=>{
 const ordered=heatOrder([-2,2,6,10,98,102,106,110],axis);
 assert.deepEqual(ordered.indices,[6,5,4,null,0,1,2]);
 assert.deepEqual(ordered.edges,[-2,2,6,10,14,18,22,26]);
});

test('geographic endpoints orient sections without sorting bends by latitude',()=>{
 const f=(channel,latitude)=>({properties:{recording_channel:channel},geometry:{coordinates:[14,latitude]}});
 const sections=geographicSections([{start:0,end:8},{start:100,end:108}],
  [f(0,68.1),f(4,68.4),f(8,68.3),f(100,68.1),f(104,67.9),f(108,68.0)]);
 assert.deepEqual(sections.map(s=>[s.start,s.end]),[[108,100],[0,8]]);
 assert.deepEqual([108,104,100,0,4,8].map(fibreAxis(sections).position),[0,4,8,1508,1512,1516]);
 assert.deepEqual(geographicSections([{start:0,end:8}],[]),[]);
});
