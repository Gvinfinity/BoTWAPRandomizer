// Run against --tracker-only plus a headless Chrome with --remote-debugging-port=9223.
// Requires Node 22+ (built-in fetch/WebSocket); no browser automation dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
(async () => {
  const tabs = await (await fetch('http://127.0.0.1:9223/json/list')).json();
  const socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve,reject) => { socket.onopen=resolve; socket.onerror=reject; });
  let sequence=0; const pending=new Map();
  socket.onmessage = event => { const value=JSON.parse(event.data); if(value.id && pending.has(value.id)) { const {resolve,reject}=pending.get(value.id); pending.delete(value.id); value.error?reject(Error(JSON.stringify(value.error))):resolve(value.result); } };
  const send = (method,params={}) => new Promise((resolve,reject) => { const id=++sequence; pending.set(id,{resolve,reject}); socket.send(JSON.stringify({id,method,params})); });
  const evaluate = async expression => {
    const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  try {
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate',{url:'http://127.0.0.1:38282/'});
    let ready=false;
    for(let attempt=0;attempt<100;attempt++) {
      await new Promise(resolve=>setTimeout(resolve,100));
      try { ready=await evaluate("Boolean(image && locations.length && state.identity)"); } catch {}
      if(ready) break;
    }
    assert(ready,'Actual game map and catalog should load');
    const initial=await evaluate(`({width:image.width,height:image.height,checks:locations.length,mapped:locations.filter(l=>l.position).length,personalControls:document.querySelectorAll('#stars,#accent,#background,#export,#import').length,error:!$('map-error').hidden})`);
    assert.equal(initial.width,6720); assert.equal(initial.height,5600); assert(initial.mapped>350); assert.equal(initial.personalControls,0); assert.equal(initial.error,false);
    assert(await evaluate(`(() => { const p=world(200,300); zoomAt(1.5,200,300); const q=world(200,300); return Math.hypot(p[0]-q[0],p[1]-q[1])<1e-7; })()`),'Zoom must preserve world coordinates beneath cursor');
    assert(await evaluate(`(() => { $('search').value='Ja Baij'; $('search').dispatchEvent(new Event('input')); return visible.length>0 && visible.every(l=>l.name.includes('Ja Baij')); })()`),'Search should filter checks');
    assert(await evaluate(`(() => { $('search').value=''; $('kind').value='shrine'; $('kind').dispatchEvent(new Event('input')); return visible.length>0 && visible.every(l=>l.kind==='shrine'); })()`),'Type filter should work');
    assert(await evaluate(`(() => { $('kind').value=''; render(); $('reset').click(); const h=hits.find(h=>h.group.length>1); if(!h)return false; const r=canvas.getBoundingClientRect(); canvas.dispatchEvent(new PointerEvent('pointerup',{clientX:r.left+h.x,clientY:r.top+h.y})); return !$('detail').hidden && document.querySelectorAll('.group-check').length===h.group.length; })()`),'Clicking an entrance should list grouped checks');
    assert(await evaluate(`(() => { document.querySelector('.group-check').click(); return selected && $('detail').textContent.includes(selected.name); })()`),'Grouped checks should be individually selectable');
    await evaluate(`$('detail').querySelector('.close').click(); $('reset').click();`);
    await fs.mkdir('out/tracker',{recursive:true});
    let screenshot=await send('Page.captureScreenshot',{format:'png'}); await fs.writeFile('out/tracker/preview-desktop.png',Buffer.from(screenshot.data,'base64'));
    await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    await new Promise(resolve=>setTimeout(resolve,200));
    assert(await evaluate('document.documentElement.scrollWidth<=390'),'Mobile layout should fit viewport');
    screenshot=await send('Page.captureScreenshot',{format:'png'}); await fs.writeFile('out/tracker/preview-mobile.png',Buffer.from(screenshot.data,'base64'));
    console.log('PASS: actual offline game map, entrance overlays, no personalization controls, search/type filters, zoom alignment, grouped marker selection, and mobile layout',initial);
  } finally { socket.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
