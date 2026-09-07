import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdir,mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function connect(url){
  const ws=new WebSocket(url),pending=new Map();let id=0;
  ws.onmessage=event=>{const message=JSON.parse(event.data);const p=pending.get(message.id);if(p){clearTimeout(p.timer);pending.delete(message.id);message.error?p.reject(Error(JSON.stringify(message.error))):p.resolve(message.result)}};
  ws.onclose=()=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(Error('CDP connection closed'))}pending.clear()};
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
  return {close:()=>ws.close(),send:(method,params={})=>new Promise((resolve,reject)=>{
    const n=++id,timer=setTimeout(()=>{pending.delete(n);reject(Error(`CDP timeout: ${method}`))},30000);
    pending.set(n,{resolve,reject,timer});ws.send(JSON.stringify({id:n,method,params}));
  })};
}
async function evaluate(client,expression){const r=await client.send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value;}
async function settlePage(client){
  await evaluate(client,`(async()=>{
    const delay=ms=>new Promise(r=>setTimeout(r,ms));
    const bounded=promise=>Promise.race([promise,new Promise((_,reject)=>setTimeout(()=>reject(Error('Slide assets or animations did not settle in 6 seconds')),6000))]);
    await document.fonts.ready;
    await bounded(Promise.all([...document.images].map(img=>img.decode())));
    const animations=document.getAnimations().filter(a=>a.playState==='running'&&Number.isFinite(a.effect?.getComputedTiming().endTime));
    await bounded(Promise.all(animations.map(a=>a.finished.catch(()=>{}))));
    let previous='',since=performance.now();const deadline=since+6000;
    while(performance.now()<deadline){
      const signature=[...document.querySelectorAll('section,h1,h2,h3,p,li,table,img')].map(el=>{const b=el.getBoundingClientRect(),s=getComputedStyle(el);return [b.x,b.y,b.width,b.height,s.opacity,s.transform].map(x=>typeof x==='number'?Math.round(x*10)/10:x).join(',')}).join('|');
      if(signature!==previous){previous=signature;since=performance.now();}
      else if(performance.now()-since>=350)return true;
      await delay(100);
    }
    throw Error('Slide layout is still moving after 6 seconds');
  })()`);
}
async function main(){
  const cfg=JSON.parse(await readFile(process.argv[2],'utf8'));
  await mkdir(cfg.output,{recursive:true});const profile=await mkdtemp(path.join(tmpdir(),'narration-chrome-'));
  const chrome=spawn(cfg.chrome,['--headless=new','--hide-scrollbars','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--allow-file-access-from-files','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore'});
  let spawnError,client;chrome.on('error',e=>spawnError=e);
  try{
    let port;
    for(let i=0;i<100;i++){if(spawnError)throw spawnError;try{port=(await readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{}await wait(100)}
    if(!port)throw Error('Chrome failed to start');
    const url=pathToFileURL(cfg.deck).href;
    const response=await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`,{method:'PUT'});
    if(!response.ok)throw Error('Cannot open render tab');const tab=await response.json();client=await connect(tab.webSocketDebuggerUrl);
    await client.send('Page.enable');await client.send('Runtime.enable');
    await client.send('Emulation.setDeviceMetricsOverride',{width:cfg.width,height:cfg.height,deviceScaleFactor:1,mobile:false});
    await client.send('Page.navigate',{url});
    let ready=false;for(let i=0;i<150;i++){ready=await evaluate(client,'Boolean(window.setPresentationState || (window.Reveal && Reveal.isReady()))');if(ready)break;await wait(100)}
    if(!ready)throw Error('Deck requires window.setPresentationState(state) or Reveal.js');
    await evaluate(client,'document.fonts.ready.then(()=>true)');
    const reports=[];
    for(let i=0;i<cfg.states.length;i++){
      const state=JSON.stringify(cfg.states[i]);
      await evaluate(client,`(async()=>{const state=${state};if(window.setPresentationState){await window.setPresentationState(state);}else{const slide=Reveal.getSlide(state.h,state.v||0);if(!slide)throw Error('Unknown Reveal slide');if((state.f??-1)>=slide.querySelectorAll('.fragment').length)throw Error('Unknown Reveal fragment');Reveal.configure({transition:'none',controls:false,progress:false});Reveal.slide(state.h,state.v||0,state.f??-1);Reveal.layout();const actual=Reveal.getIndices();if(actual.h!==state.h||(actual.v||0)!==(state.v||0)||(actual.f??-1)!==(state.f??-1))throw Error('Reveal did not reach requested state');}await document.fonts.ready;await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const requested=state.slide&&document.getElementById(state.slide);if(requested){const box=requested.getBoundingClientRect(),style=getComputedStyle(requested);if(box.width<2||box.height<2||style.visibility==='hidden'||style.display==='none'||Number(style.opacity)===0)throw Error('Requested slide is not visible: '+state.slide);}return true})()`);
      if(cfg.settleMs)await wait(cfg.settleMs);
      await settlePage(client);
      const geometry=await evaluate(client,`(()=>{
        const out=[],seen=new Set(),walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
        let node;while(node=walker.nextNode()){
          const text=node.textContent.trim(),el=node.parentElement;if(!text||!el||['SCRIPT','STYLE','NOSCRIPT'].includes(el.tagName))continue;
          const box=el.getBoundingClientRect(),style=getComputedStyle(el);if(box.width<2||box.height<2||style.visibility==='hidden'||style.display==='none')continue;
          const parents=[];let hidden=false;for(let p=el;p;p=p.parentElement){const s=getComputedStyle(p);if(Number(s.opacity)===0){hidden=true;break;}parents.push([p,s,p.getBoundingClientRect()]);}if(hidden)continue;
          const range=document.createRange();range.selectNodeContents(node);
          for(const r of range.getClientRects()){
            let problem='';if(r.left< -3||r.right>innerWidth+3||r.top< -3||r.bottom>innerHeight+3)problem='outside viewport';
            for(const [p,s,b] of parents){
              if((['hidden','clip','auto','scroll'].includes(s.overflowX)&&(r.left<b.left-3||r.right>b.right+3))||(['hidden','clip','auto','scroll'].includes(s.overflowY)&&(r.top<b.top-3||r.bottom>b.bottom+3))){problem='text clipped by '+p.tagName.toLowerCase()+(p.id?'#'+p.id:'')+'; text bounds '+JSON.stringify({left:r.left,right:r.right,top:r.top,bottom:r.bottom})+'; container bounds '+JSON.stringify({left:b.left,right:b.right,top:b.top,bottom:b.bottom});break;}
            }
            if(problem&&!seen.has(text+problem)){seen.add(text+problem);out.push({text:text.slice(0,100),problem});}
          }
        }
        const expected=${JSON.stringify(cfg.expectedBackground||null)};
        if(expected){const c=document.createElement('canvas').getContext('2d');c.fillStyle=expected;const target=c.fillStyle;c.fillStyle=getComputedStyle(document.body).backgroundColor;if(c.fillStyle!==target)out.push({text:'template background',problem:'Expected '+target+', got '+c.fillStyle});}
        const presenter=${JSON.stringify(cfg.expectedPresenter||null)};
        if(presenter&&!document.body.textContent.includes(presenter))out.push({text:'template presenter',problem:'Missing '+presenter+'; preserve the reference cover, English subtitle, and large accent-colored title'});
        const logoHeight=${JSON.stringify(cfg.expectedLogoHeight||null)},logo=document.querySelector('#logo img');
        if(logoHeight&&(!logo||Math.abs(logo.getBoundingClientRect().height-logoHeight)>2))out.push({text:'template logo',problem:'Expected original logo height '+logoHeight+'px'});
        return out.slice(0,30);
      })()`);reports.push({state:cfg.states[i],issues:geometry});
      const shot=await client.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(path.join(cfg.output,`${String(i).padStart(4,'0')}.png`),Buffer.from(shot.data,'base64'));
    }
    if(cfg.layoutReport)await writeFile(cfg.layoutReport,JSON.stringify(reports,null,2));
    console.log(`Rendered ${cfg.states.length} narration-driven slide states`);
  }finally{
    if(client)client.close();chrome.kill('SIGTERM');await wait(500);if(chrome.exitCode===null)chrome.kill('SIGKILL');await wait(200);await rm(profile,{recursive:true,force:true});
  }
}
main().catch(e=>{console.error(e);process.exitCode=1});
