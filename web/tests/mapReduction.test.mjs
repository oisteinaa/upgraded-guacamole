import {readFileSync} from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
const code=ts.transpileModule(readFileSync(new URL('../src/mapReduction.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {reduceFibre,colorPosition}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const feature=(channel,value,run='1:0')=>({type:'Feature',id:channel,geometry:{type:'Point',coordinates:[1,1]},properties:{channel,value,run}});
const project=()=>({x:20,y:20});
test('screen reduction keeps actual extrema and positions',()=>{
 const points=[feature(0,5),feature(4,1),feature(8,100),feature(12,2)];
 const out=reduceFibre(points,project,100,100,6);
 assert.deepEqual(out.map(f=>f.id),[4,8]);assert.equal(out[1].properties.value,100);
 assert.equal(out[0].properties.bucket_count,4);assert.deepEqual(out[0].geometry,points[1].geometry);
});
test('excluded gaps and separate runs cannot merge',()=>{
 const out=reduceFibre([feature(0,1),feature(8,2),feature(12,3,'1:12')],project,100,100,6);
 assert.equal(out.length,3);assert.ok(out.every(f=>f.properties.bucket_count===1));
});
test('detail zoom reveals every channel; offscreen points are omitted',()=>{
 const points=[feature(0,1),feature(4,2),feature(8,3)];
 assert.equal(reduceFibre(points,project,100,100,1).length,3);
 assert.equal(reduceFibre(points,()=>({x:1000,y:1000}),100,100,6).length,0);
});
test('linear and logarithmic scales are stable and saturate',()=>{
 assert.equal(colorPosition(50,0,100,false),.5);assert.equal(colorPosition(1000,0,100,false),1);
 assert.equal(colorPosition(10,1,100,true),.5);assert.equal(colorPosition(0,1,100,true),0);
});
test('eight-channel sampling reduces extrema without merging gaps or runs',()=>{
 const points=[feature(0,5),feature(8,1),feature(16,100),feature(24,2),feature(40,3),feature(48,4,'1:48')];
 for (const f of points) f.properties.channel_step=8;
 const out=reduceFibre(points,project,100,100,6);
 assert.deepEqual(out.map(f=>f.id),[8,16,40,48]);
 assert.deepEqual(out.map(f=>f.properties.bucket_count),[4,4,1,1]);
});
