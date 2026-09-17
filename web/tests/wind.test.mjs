import {readFileSync} from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import ts from "typescript";
const code = ts.transpileModule(readFileSync(new URL("../src/wind.ts", import.meta.url), "utf8"), {
  compilerOptions: {module: ts.ModuleKind.ESNext}
}).outputText;
const {windArrow} = await import("data:text/javascript;base64," + Buffer.from(code).toString("base64"));
test("calm, missing and invalid wind never produce arrows", () => {
  for (const pair of [[0,0],[-1,90],[null,90],[3,null],[NaN,0],[2,Infinity],[2,361]])
    assert.equal(windArrow(...pair), null);
});
test("length grows from a legible minimum and saturates at 30 m/s", () => {
  assert.equal(windArrow(15,0).length, 45);
  assert.equal(windArrow(30,0).length, 72);
  assert.equal(windArrow(45,0).length, 72);
});
test("color boundaries and meteorological directions", () => {
  assert.equal(windArrow(8,0).color, "#8ee06b");
  assert.equal(windArrow(8.01,0).color, "#ffd15c");
  assert.equal(windArrow(18,0).color, "#ffd15c");
  assert.equal(windArrow(18.01,0).color, "#ff6b72");
  assert.deepEqual([0,90,180,270,360].map(d => windArrow(5,d).rotation), [180,270,0,90,180]);
});
