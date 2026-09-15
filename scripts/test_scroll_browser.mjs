import { readFileSync, mkdtempSync } from 'node:fs';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import assert from 'node:assert/strict';

const root = fileURLToPath(new URL('../extension', import.meta.url));
const original = readFileSync(root + '/dist/notebook-webview.js', 'utf8');
function runCases() {
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const results = [];
  const source = (tag = 'main', extra = '', nested = false) => `<style>body{margin:0}p{margin:0;height:100px}.pane{height:500px;overflow:auto}</style><${tag} id="report">${extra}${nested ? '<div class="pane" id="pane">' : ''}${Array.from({length:60}, (_,i) => `<p id="row${i}">row ${i}</p>`).join('')}${nested ? '</div>' : ''}</${tag}>`;
  const send = (html, type = 'update') => window.dispatchEvent(new MessageEvent('message', {data:{type, sourceHtml:html, sourceKind:'html', interactions:{}, theme:{kind:'light',flavor:'latte'}}}));
  const snapshot = () => ({y:scrollY, row:document.getElementById('row20')?.getBoundingClientRect().top, nested:document.getElementById('pane')?.scrollTop});
  async function initial(html) { send(html, 'state'); await wait(100); window.scrollTo({top:2000,behavior:'instant'}); await wait(100); }
  async function test(name, before, after, action) {
    await initial(before);
    if (action) action();
    const pre = snapshot(); send(after); await wait(180); results.push({name,before:pre,after:snapshot()});
  }
  (async () => {
    await test('text-only',source(),source().replace('row 0','new 0'));
    await test('replace container same height',source(),source('article'));
    await test('insert 500px above reading position',source(),source('main','<aside style="height:500px">new</aside>'));
    await test('replace nested scroller',source('main','',true),source('article','',true),() => {document.getElementById('pane').scrollTop=2000;});
    await initial(source());
    const before = snapshot();
    send(source()+'<script id="new-script" src="/slow.js"></script>');
    await wait(60);
    window.dispatchEvent(new WheelEvent('wheel', {deltaY:400}));
    window.scrollTo({top:2400,behavior:'instant'});
    await wait(450);
    results.push({name:'reader scrolls during delayed script',before,intendedY:2400,after:snapshot()});
    await initial(source());
    // Runtime-derived content briefly disappears, then an async render hook recreates it.
    const restoreLater = () => { setTimeout(() => {document.getElementById('report').innerHTML = Array.from({length:60},(_,i)=>`<p id="row${i}">row ${i}</p>`).join('');}, 100); };
    document.addEventListener('tressoir:render', restoreLater, {once:true});
    const pre = snapshot();
    send('<style>body{margin:0}p{margin:0;height:100px}</style><main id="report"></main>');
    await wait(220);
    results.push({name:'async render temporarily empties report',before:pre,after:snapshot()});
    await initial(source());
    const keyed = snapshot();
    send(source());
    window.dispatchEvent(new KeyboardEvent('keydown', {key:'PageDown'}));
    window.scrollTo({top:2400,behavior:'instant'});
    await wait(80);
    results.push({name:'keyboard cancels queued correction',before:keyed,intendedY:2400,after:snapshot()});
    await initial(source());
    const superseded = snapshot();
    const slow = '<script id="slow-newer" src="/slow.js?newer"></script>';
    send(source()+slow);
    await wait(40);
    window.dispatchEvent(new WheelEvent('wheel', {deltaY:400}));
    window.scrollTo({top:2400,behavior:'instant'});
    send(source()+slow);
    await wait(400);
    results.push({name:'newer update supersedes delayed update',before:superseded,intendedY:2400,after:snapshot()});
    await initial(source());
    const bounded = snapshot();
    send(source());
    await wait(1300);
    window.scrollTo({top:2400,behavior:'instant'});
    document.getElementById('row0').textContent='later layout change';
    await wait(80);
    results.push({name:'preservation expires',before:bounded,intendedY:2400,after:snapshot()});
    document.body.innerHTML = '<pre id="results"></pre>';
    document.getElementById('results').textContent=JSON.stringify(results);
    await fetch('/results', {method:'POST',body:JSON.stringify(results)});
  })().catch(e => {document.body.textContent = 'ERROR: '+e.stack;});
}

let finish;
const server = createServer((req,res) => {
  if(req.url==='/results') {let body='';req.on('data',c=>body+=c);req.on('end',()=>{res.end('ok');finish(JSON.parse(body));});return;}
  if(req.url==='/bundle.js') {res.setHeader('Content-Type','text/javascript');res.end(original);return;}
  if(req.url.startsWith('/slow.js')) {res.setHeader('Content-Type','text/javascript');setTimeout(()=>res.end('// delayed dependency'),250);return;}
  res.setHeader('Content-Type','text/html');
  res.end(`<!doctype html><html><body data-artifact-base-uri="http://127.0.0.1:${server.address().port}/" data-csp-nonce="test"><div id="app"></div><script>let saved={};window.acquireVsCodeApi=()=>({getState:()=>saved,setState:s=>saved=s,postMessage:()=>{}});</script><script src="/bundle.js"></script><script>(${runCases.toString().replaceAll('</script', '<\\/script')})();</script></body></html>`);
});
await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
try {
  for(const mode of ['fixed']) {
    const profile=mkdtempSync(join(tmpdir(), 'tressoir-scroll-test-'));
    const done=new Promise(resolve=>finish=resolve);
    const proc=spawn(process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-background-timer-throttling','--user-data-dir='+profile,'--window-size=1100,800',`http://127.0.0.1:${server.address().port}/${mode}`]);
    let output='',errors='';proc.stdout.on('data',s=>output+=s);proc.stderr.on('data',s=>errors+=s);
    const timeout=setTimeout(()=>finish(null),20000);
    const results=await done;clearTimeout(timeout);proc.kill('SIGKILL');
    assert.ok(results, 'Browser did not finish: '+errors.slice(-1500));
    for (const result of results) {
      const expected = result.intendedY !== undefined ? 2400 : result.name.startsWith('insert 500px') ? 2500 : result.before.y;
      assert.equal(result.after.y, expected, result.name+' page offset');
      if (result.before.nested !== undefined) assert.equal(result.after.nested, result.before.nested, result.name);
      if (result.intendedY === undefined) assert.equal(result.after.row, result.before.row, result.name+' reading anchor');
    }
    console.log(JSON.stringify({mode, results, profile}));
  }
} finally {server.close();}
