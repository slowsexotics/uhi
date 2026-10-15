const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const {webcrypto} = require('node:crypto');
const root=path.resolve(__dirname,'../..');
const code=fs.readFileSync(path.join(root,'dashboard/assets/creator-briefing.js'),'utf8');
class Element {
  constructor(tag='div'){ this.tag=tag; this.children=[]; this.listeners={}; this.value=''; this.hidden=false; this.disabled=false; this.textContent=''; }
  append(...children){ this.children.push(...children); }
  replaceChildren(...children){ this.children=[...children]; }
  addEventListener(type,fn){ this.listeners[type]=fn; }
}
function setup(backend){
  const elements=new Map();
  const element=id=>{ if(!elements.has(id)) elements.set(id,new Element()); return elements.get(id); };
  const storage=new Map(); const requests=[]; const events={};
  const context={document:{getElementById:element,createElement:tag=>new Element(tag)},
    crypto:webcrypto, sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    window:{addEventListener:(name,fn)=>events[name]=fn},
    fetch:async(url,options={})=>{requests.push({url,options});return backend(url,options);},Date,JSON,Error};
  vm.runInNewContext(code,context);
  return {element,storage,requests,events,context};
}
const response=(data,ok=true)=>({ok,json:async()=>data});
const row={id:'saved-1',created_at:'2026-10-13T12:00:00Z',generation_status:'generated',completion_status:'in_progress',
  content:{personal_context:'Cooking',recommended_action:'<img src=x onerror=attack()>',why:'Matches your interest',
  steps:['Film a recipe step'],done_when:'Clip saved',question:'How much time do you have?'},user_response:'',feedback:''};
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('saved briefing uses text nodes, progress saves, and next generation gets fresh request id',async()=>{
  let current=null;
  const app=setup(async(url,opts)=>{
    if(url==='/api/creator/briefings') return response({status:'ok',briefings:current?[current]:[]});
    if(url.endsWith('/generate')){current=structuredClone(row);return response({status:'ok',briefing:current});}
    if(url.endsWith('/feedback')){
      const data=JSON.parse(opts.body);current={...current,user_response:data.response,feedback:data.feedback,completion_status:data.completion_status};
      return response({status:'ok',briefing:current});
    }
  });
  await tick();
  await app.element('creator-generate').listeners.click();
  const first=JSON.parse(app.requests.find(x=>x.url.endsWith('/generate')).options.body);
  const sections=app.element('creator-briefing-content').children;
  assert.equal(sections[1].children[1].textContent,row.content.recommended_action);
  assert.equal(app.element('creator-feedback').hidden,false);
  app.element('creator-response').value='I prefer hands-only videos';
  app.element('creator-obstacle').value='Ten minutes available';
  app.element('creator-progress').value='skipped';
  await app.element('creator-feedback').listeners.submit({preventDefault(){}});
  assert.equal(current.completion_status,'skipped');
  assert.equal(current.user_response,'I prefer hands-only videos');
  assert.match(app.element('creator-message').textContent,/saved/);
  await app.element('creator-generate').listeners.click();
  const generated=app.requests.filter(x=>x.url.endsWith('/generate'));
  assert.notEqual(first.request_id,JSON.parse(generated[1].options.body).request_id);
});

test('failed generation preserves retry id and never shows success',async()=>{
  const app=setup(async(url)=>url.endsWith('/generate')?response({status:'error',message:'Model not approved'},false):response({status:'ok',briefings:[]}));
  await tick();
  await app.element('creator-generate').listeners.click();
  const first=app.storage.get('uhi-generation-request');
  assert.ok(first);
  assert.equal(app.element('creator-message').textContent,'Model not approved');
  assert.equal(app.element('creator-generate').disabled,false);
  await app.element('creator-generate').listeners.click();
  assert.equal(app.storage.get('uhi-generation-request'),first);
  app.events['uhi-profile-saved']();
  assert.equal(app.storage.get('uhi-generation-request'),undefined);
});

test('existing onboarding can continue with no AI startup or accounts',()=>{
  const html=fs.readFileSync(path.join(root,'dashboard/index.html'),'utf8');
  const start=html.indexOf('    async function checkOrStartLocalAiSetup()');
  const end=html.indexOf('    async function completeOnboarding()',start);
  const piece=html.slice(start,end);
  assert.ok(!piece.includes('/api/ai/setup-runtime'));
  assert.ok(!piece.includes('setInterval'));
  assert.ok(!html.includes('tg_tested'));
  assert.ok(!html.includes('tg_found'));
  assert.ok(!html.match(/\d{7,15}:[A-Za-z0-9_-]{30,}/));
  const app=setup(async()=>response({status:'ok',briefings:[]}));
  let step=null;
  Object.assign(app.context,{obState:{selectedAi:'qwen'},goToObStep:x=>step=x,alert:()=>assert.fail('unexpected block')});
  vm.runInNewContext(piece,app.context);
  app.context.saveStep6AndNext();
  assert.equal(step,7);
});
