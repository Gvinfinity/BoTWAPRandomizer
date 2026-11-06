'use strict';
// Mirrors logic.py's safe grammar. These are item-condition hints, not region reachability.
const TrackerLogic = (() => {
  const champions = new Set(["Progressive Revali's Gale", "Progressive Daruk's Protection", "Progressive Mipha's Grace", "Progressive Urbosa's Fury", 'Vah Medoh Cleared', 'Vah Rudania Cleared', 'Vah Ruta Cleared', 'Vah Naboris Cleared']);
  function parse(expression) {
    if (!expression.trim()) return {op:'true'};
    const tokens=[]; const re=/\s*(\|[^|]+\||\(|\)|AND\b|OR\b)/iy; let offset=0;
    while(offset<expression.trimEnd().length) { re.lastIndex=offset; const m=re.exec(expression); if(!m) throw Error('Unsupported requirement'); tokens.push(m[1]); offset=re.lastIndex; }
    let pos=0;
    function atom() {
      const t=tokens[pos++]; if(t==='(') { const node=any(); if(tokens[pos++]!==')') throw Error('Missing closing parenthesis'); return node; }
      if(!t?.startsWith('|')) throw Error('Expected item');
      const parts=/^(.+?)(?::([1-9]\d*))?$/.exec(t.slice(1,-1)); if(!parts || parts[1].includes(':')) throw Error('Unsupported count');
      return {op:parts[1].startsWith('@')?'category':'item',name:parts[1].replace(/^@/,''),count:Number(parts[2]||1)};
    }
    function all() { const children=[atom()]; while(tokens[pos]?.toUpperCase()==='AND') { pos++; children.push(atom()); } return children.length===1?children[0]:{op:'all',children}; }
    function any() { const children=[all()]; while(tokens[pos]?.toUpperCase()==='OR') { pos++; children.push(all()); } return children.length===1?children[0]:{op:'any',children}; }
    const tree=any(); if(pos!==tokens.length) throw Error('Trailing requirement'); return tree;
  }
  function evaluate(expression, inventory, metadata, ballad=false) {
    const items=new Map(metadata.map(i=>[i.name,i])); items.set('Paraglider',{name:'Paraglider'});
    const categories=new Map();
    for(const item of metadata) for(const category of item.category||[]) { if(!categories.has(category)) categories.set(category,[]); categories.get(category).push(item.name); }
    function visit(node) {
      if(node.op==='true') return {met:true,text:'No local item requirement'};
      if(node.op==='all'||node.op==='any') { const children=node.children.map(visit); const met=node.op==='all'?children.every(c=>c.met===true)?true:children.some(c=>c.met===false)?false:null:children.some(c=>c.met===true)?true:children.every(c=>c.met===false)?false:null; return {met,text:'('+children.map(c=>c.text).join(node.op==='all'?' AND ':' OR ')+')'}; }
      const ignored=node.op==='item'&&(node.name.endsWith(' Tower') || (ballad&&champions.has(node.name)));
      if(ignored) return {met:true,text:`${node.name} (not required by current item rules)`};
      const known=node.op==='item'?items.has(node.name):categories.has(node.name);
      const count=node.op==='item'?(inventory[node.name]||0):(categories.get(node.name)||[]).reduce((sum,name)=>sum+(inventory[name]||0),0);
      return {met:known?count>=node.count:null,text:`${node.name}: ${count}/${node.count}${known?'':' (unknown requirement)'}`};
    }
    try { return visit(parse(expression||'')); } catch { return {met:null,text:'This requirement needs manual review.'}; }
  }
  return {parse,evaluate};
})();
if(typeof module!=='undefined') module.exports=TrackerLogic;
