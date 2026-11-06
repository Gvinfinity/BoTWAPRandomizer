const assert = require('node:assert/strict');
const {evaluate, parse} = require('../../src/client/Tracker/logic.js');
const metadata = [
  {name:'Magnesis'}, {name:'Cryonis'}, {name:'Progressive Stasis'},
  {name:'Warm Doublet',category:['Cold Resistance']},
  {name:'Snowquill Tunic',category:['Cold Resistance']},
  {name:'Great Plateau Tower'}, {name:"Progressive Revali's Gale"}
];
const test = (expression, inventory, expected, ballad=false) => assert.equal(evaluate(expression,inventory,metadata,ballad).met,expected,expression);
test('',{},true);
test('|Magnesis| OR |Cryonis| AND |Progressive Stasis|',{Magnesis:1},true);
test('|Magnesis| OR |Cryonis| AND |Progressive Stasis|',{Cryonis:1},false);
test('(|Magnesis| OR |Cryonis|) AND |Progressive Stasis|',{Magnesis:1},false);
test('|Progressive Stasis:2|',{'Progressive Stasis':1},false);
test('|Progressive Stasis:2|',{'Progressive Stasis':2},true);
test('|@Cold Resistance:2|',{'Warm Doublet':1,'Snowquill Tunic':1},true);
test('|@Cold Resistance:2|',{'Warm Doublet':1},false);
test('|Unknown Story Event|',{},null);
test('|Magnesis| OR |Unknown Story Event|',{Magnesis:1},true);
test('|Magnesis| AND |Unknown Story Event|',{},false);
test('|Great Plateau Tower|',{},true);
test("|Progressive Revali's Gale|",{},false);
test("|Progressive Revali's Gale|",{},true,true);
for (const bad of ['|Magnesis| AND','(|Magnesis|','|Magnesis:0|','|Magnesis:bad|','true','|Magnesis| trailing']) {
  assert.throws(()=>parse(bad),undefined,bad); test(bad,{},null);
}
console.log('PASS: tracker item hints, boolean precedence, progressive counts, category sums, ignored tower/champion items, unknown rules, and malformed input');
