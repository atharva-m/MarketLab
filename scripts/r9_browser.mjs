// Actual local UI readback/capture, using the locked frontend Playwright runtime.
import {chromium} from '../frontend/node_modules/playwright/index.mjs';
import {readFile, writeFile, mkdir, stat} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const base = path.join(project, 'artifacts', 'r9-20261027');
const inputPath = path.resolve(process.argv[2] ?? '');
if (!inputPath.startsWith(base + path.sep)) throw new Error('Input must be owned R9 evidence');
const bytes = await readFile(inputPath);
const input = JSON.parse(bytes.toString('utf8'));
if (!/^r9-[a-z0-9][a-z0-9-]{0,59}$/.test(input.prefix)) throw new Error('Invalid invocation identity');
if (!['empty', 'manual', 'catalog', 'provenance', 'retained', 'copilot-inspect', 'create', 'answer', 'run-inspect'].includes(input.mode)) throw new Error('Unknown browser mode');
const holdSeconds=input.hold_seconds??2;
if(!Number.isInteger(holdSeconds)||holdSeconds<0||holdSeconds>45)throw new Error('Capture hold must be an integer from 0 to 45 seconds');
const output = path.join(base, `${input.prefix}-browser.json`);
const python = path.join(project, '.venv', 'Scripts', 'python.exe');
const captureDir = path.join(base, 'captures', input.prefix);
let browser = null;
let context = null;
let page = null;
const errors = [];
const mutations = [];
const evidence = {schema:'r9-browser-v1',status:'running',stage:'setup',mode:input.mode,hold_seconds:holdSeconds,input_sha256:createHash('sha256').update(bytes).digest('hex'),cases:[],mutations,page_errors:errors};
await writeFile(output, JSON.stringify(evidence,null,2), {flag: 'wx'});
const sorted = value => Array.isArray(value) ? value.map(sorted) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key=>[key,sorted(value[key])])) : value;
const hash = value => createHash('sha256').update(JSON.stringify(sorted(value))).digest('hex');
const uuid = value => {if(!/^[a-f0-9-]{36}$/.test(value??''))throw new Error('Invalid run/request identity');return value;};
const require = (value, message) => {if(!value)throw new Error(message);};
const inspect = async (run, requireMemo) => {
  const suffixes = ['summary','results','memo'];
  const pending = suffixes.map(suffix=>page.waitForResponse(r=>r.request().method()==='GET'&&r.url().endsWith(`/v1/research/runs/${run}/${suffix}`),{timeout:120000}));
  await page.goto(`http://127.0.0.1:5173/#/runs/${uuid(run)}`);
  const responses = await Promise.all(pending);
  require(responses[0].status()===200&&responses[1].status()===200,'Actual numerical read failed');
  const summary = await responses[0].json();
  const results = await responses[1].json();
  await page.getByTestId('numerical-summary').waitFor();
  const memo = responses[2].status()===200 ? await responses[2].json() : null;
  if(requireMemo){
    require(memo?.content,'Ready memo unavailable');
    const paragraphs=page.getByTestId('memo-panel').locator('.memo-content p');
    await paragraphs.first().waitFor();
    require((await paragraphs.allTextContents()).join('\n\n')===memo.content&&await paragraphs.count()===3,'Visible memo differs from stored paragraphs');
  }
  return {summary,results,memo,summary_sha256:hash(summary),results_sha256:hash(results),memo_status:responses[2].status(),cache:responses[0].headers()['x-cache']};
};
const began=performance.now();
try {
  evidence.stage='owned-process-guard';
  const guard = spawnSync(python, ['-c', "import sys,json;sys.path.insert(0,'scripts');from r9_common import settings,owned_process;settings();print(json.dumps({k:owned_process(k,p) for k,p in [('api',58007),('ui',5173)]}))"], {cwd: project, encoding: 'utf8', timeout: 90000});
  require(guard.status===0,'Owned API/UI process guard failed');
  evidence.owned_processes=JSON.parse(guard.stdout);
  evidence.stage='capture-setup';
  await mkdir(path.dirname(captureDir), {recursive: true});
  await mkdir(captureDir, {recursive: false});
  evidence.stage='browser-launch';
  browser = await chromium.launch({headless: true});
  context = await browser.newContext({viewport:{width:1920,height:1080}, recordVideo:{dir:captureDir,size:{width:1920,height:1080}}});
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin === 'http://127.0.0.1:5173' || ['about:', 'data:', 'blob:'].includes(url.protocol)) return route.continue();
    return route.abort('blockedbyclient');
  });
  page = await context.newPage();
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => {if(message.type()==='error')errors.push(message.text());});
  page.on('request', request => {if(request.method()==='POST')mutations.push({url:request.url(),body:request.postData(),idempotency_key:request.headers()['idempotency-key']});});
  evidence.stage='browser-scenario';
  if(input.mode==='empty'||input.mode==='catalog'){
    const pending=page.waitForResponse(r=>r.request().method()==='GET'&&r.url().includes('/v1/datasets?'));
    await page.goto('http://127.0.0.1:5173/#/catalog');
    const response=await pending;require(response.status()===200,'Actual catalog request failed');
    const body=await response.json();
    await page.getByRole('heading',{name:'Dataset catalog',exact:true}).waitFor();
    if(input.mode==='empty'){
      require(body.items.length===0&&body.next_cursor===null,'Expected actually empty catalog');
      await page.getByText('No registered versions match this filter.',{exact:true}).waitFor();
      require(await page.getByRole('checkbox').count()===0,'Empty catalog rendered a dataset');
    }else{
      require(body.items.length>0,'Retained catalog is empty');
      if(input.version){
        require(/^[a-f0-9]{64}$/.test(input.version),'Invalid selected version');
        const row=body.items.find(item=>item.dataset_version_id===input.version);
        require(row,'Chosen version must appear on captured catalog page');
        const inspection=page.waitForResponse(r=>r.request().method()==='GET'&&r.url().endsWith(`/v1/datasets/${input.version}`),{timeout:1800000});
        await page.getByRole('button',{name:input.version,exact:true}).click();
        const detail=await inspection;require(detail.status()===200,'Actual dataset verification failed');
        const data=await detail.json();require(data.verification==='verified'&&data.dataset_version_id===input.version,'Dataset verification identity mismatch');
        await page.getByRole('heading',{name:'Dataset verification',exact:true}).scrollIntoViewIfNeeded();
        evidence.verified_dataset=data;
      }
    }
    evidence.cases.push({items:body.items,next_cursor:body.next_cursor,empty:body.items.length===0});
    require(mutations.length===0,'Catalog view unexpectedly mutated state');
  }else if(input.mode==='manual'){
    const spec=input.spec;
    require(spec?.schema==='research-spec-v1'&&['market_profile','cross_asset','volatility_cluster'].includes(spec.workflow),'Explicit known manual specification required');
    require(Array.isArray(spec.dataset_versions)&&spec.dataset_versions.length>0&&spec.dataset_versions.every(v=>/^[a-f0-9]{64}$/.test(v)),'Manual versions required');
    await page.goto('http://127.0.0.1:5173/#/research/new');
    await page.getByRole('combobox',{name:'Workflow',exact:true}).selectOption(spec.workflow);
    if(spec.workflow!=='cross_asset')await page.getByRole('combobox',{name:'Asset',exact:true}).selectOption(spec.symbols[0]);
    await page.getByTestId('evaluation-start').fill(spec.start);
    await page.getByTestId('evaluation-end').fill(spec.end);
    await page.getByTestId('history-start').fill(spec.history_start);
    await page.getByTestId('dataset-version-ids').fill(spec.dataset_versions.join('\n'));
    const allowed=spec.workflow==='cross_asset'?['profile','correlation','close_change_difference']:spec.workflow==='volatility_cluster'?['profile','clusters']:['profile'];
    for(const metric of allowed)await page.getByRole('checkbox',{name:metric.replaceAll('_',' '),exact:true}).setChecked(spec.metrics.includes(metric));
    await page.screenshot({path:path.join(captureDir,'manual-form.png'),fullPage:true});
    const accepted=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/v1/research/runs'),{timeout:1800000});
    await page.getByTestId('submit-research').click();
    const response=await accepted;
    evidence.manual_response={status:response.status(),body:(await response.text()).slice(0,32768)};
    await writeFile(output,JSON.stringify(evidence,null,2));
    require(response.status()===201,'Manual request was not freshly accepted');
    const data=await response.json();uuid(data.run_id);
    require(data.replayed===false,'Manual operation unexpectedly replayed');
    await page.waitForURL(`**/#/runs/${data.run_id}`);
    await page.getByTestId('run-id').waitFor();
    require((await page.getByTestId('run-id').textContent()).trim()===data.run_id,'Manual UI identity differs');
    require(mutations.length===1&&hash(JSON.parse(mutations[0].body))===hash(spec),'Browser submitted a different specification');
    const original=mutations[0];require(original.idempotency_key,'Manual operation key missing');
    await page.reload();
    await page.getByTestId('run-id').waitFor();
    require((await page.getByTestId('run-id').textContent()).trim()===data.run_id&&mutations.length===1,'Reload changed identity or resubmitted');
    const replay=await context.request.post('http://127.0.0.1:5173/v1/research/runs',{headers:{'Content-Type':'application/json','Idempotency-Key':original.idempotency_key},data:original.body,maxRedirects:0,timeout:120000});
    const replayed=await replay.json();
    require(replay.status()===200&&replayed.replayed===true&&replayed.run_id===data.run_id,'Exact-key manual replay changed identity');
    evidence.cases.push({spec,run_id:data.run_id,accepted_http:response.status(),reload_mutation_count:mutations.length,replay_http:replay.status(),replay:replayed,idempotency_key:original.idempotency_key});
    evidence.replay_scope='Explicit same-key/body HTTP replay after UI reload; reload itself sent no mutation. Worker remains separately operator controlled.';
  }else if(input.mode==='retained'){
    const manifest = JSON.parse(await readFile(path.join(base,'retained-inputs.json'),'utf8'));
    const pinned=manifest.files.scenarios;
    const source=await readFile(pinned.path);
    require(createHash('sha256').update(source).digest('hex')===pinned.sha256,'Scenario input hash mismatch');
    const scenarios=JSON.parse(source).slice(0,5);
    require(scenarios.length===5,'Expected five retained scenarios');
    for(const scenario of scenarios){
      const current=await inspect(scenario.run_id,true);
      require(current.summary_sha256===scenario.result.summary_sha256&&current.results_sha256===scenario.result.results_sha256,'Retained numerical hash mismatch');
      require(createHash('sha256').update(current.memo.content).digest('hex')===scenario.memo.memo_sha256,'Retained memo hash mismatch');
      const exact = JSON.stringify(current.summary).match(/-?\d+\.\d{18}/)?.[0];
      require(exact&&(await page.getByTestId('numerical-summary').textContent()).includes(exact),'Exact decimal not displayed');
      evidence.cases.push({run_id:scenario.run_id,workflow:scenario.workflow,summary_sha256:current.summary_sha256,results_sha256:current.results_sha256,memo_sha256:scenario.memo.memo_sha256,visible_exact:exact});
      await page.screenshot({path:path.join(captureDir,`retained-${evidence.cases.length}.png`),fullPage:true});
      await page.waitForTimeout(1500);
    }
    const scenario=scenarios[0];
    await page.goto(`http://127.0.0.1:5173/#/runs/${uuid(scenario.run_id)}`);
    await page.getByRole('heading',{name:'Price and base volume',exact:true}).waitFor({timeout:120000});
    await page.getByLabel('Chart start (UTC)',{exact:true}).fill('2025-01-01T23:30:00Z');
    await page.getByLabel('Chart end (UTC, exclusive)',{exact:true}).fill('2025-01-02T00:30:00Z');
    evidence.charts=[];
    for(const interval of ['1m','5m']){
      await page.getByRole('combobox',{name:/^Chart interval/}).selectOption(interval);
      const metadata=page.waitForResponse(r=>r.request().method()==='GET'&&r.url().includes('/v1/datasets?'));
      await page.getByRole('button',{name:'Use pinned versions for window',exact:true}).click();
      require((await metadata).status()===200,'Pinned catalog unavailable');
      const versions=page.getByRole('textbox',{name:/^Chart dataset version IDs/});
      await versions.waitFor();
      await page.waitForFunction(()=>document.querySelector('[aria-label="Chart dataset version IDs"]')?.value?.split(/\s+/).filter(Boolean).length===2,{},{timeout:10000}).catch(async()=>{
        require((await versions.inputValue()).split(/\s+/).filter(Boolean).length===2,'Chart requires two explicit day versions');
      });
      const pending=page.waitForResponse(r=>r.request().method()==='GET'&&r.url().includes('/v1/bars?')&&new URL(r.url()).searchParams.get('interval')===interval,{timeout:180000});
      await page.getByRole('button',{name:'Load chart window',exact:true}).click();
      const response=await pending;require(response.status()===200,'Actual chart request failed');
      const body=await response.json();
      require(body.expected_buckets===(interval==='1m'?60:12)&&body.bars.length===body.expected_buckets&&body.dataset_versions.length===2,'Bounded cross-day chart coverage mismatch');
      await page.getByText('Exact chart values and units',{exact:true}).click();
      require((await page.getByRole('table').last().textContent()).includes(body.bars[0].close),'Exact chart close missing');
      evidence.charts.push({interval,body,cache:response.headers()['x-cache']});
      await page.screenshot({path:path.join(captureDir,`chart-${interval}.png`),fullPage:true});
      await page.waitForTimeout(1500);
    }
    require(mutations.length===0,'Readback unexpectedly mutated state');
  }else if(input.mode==='copilot-inspect'){
    const id=uuid(input.request_id);
    const pending=page.waitForResponse(r=>r.request().method()==='GET'&&r.url().endsWith(`/v1/copilot/requests/${id}`));
    await page.goto(`http://127.0.0.1:5173/#/copilot/${id}`);
    const state=await(await pending).json();
    require(state.outcome===input.outcome,'Actual copilot outcome differs');
    if(state.outcome==='submitted')await page.getByRole('link',{name:'Open research run'}).waitFor();
    if(state.outcome==='needs_clarification')await page.getByLabel('Clarification answer',{exact:true}).waitFor();
    evidence.cases.push(state);
    require(mutations.length===0,'Inspection unexpectedly mutated state');
  }else if(input.mode==='create'){
    require(Array.isArray(input.versions)&&input.versions.every(v=>/^[0-9a-f]{64}$/.test(v)),'Explicit versions required');
    await page.goto('http://127.0.0.1:5173/#/copilot/new');
    await page.getByRole('textbox',{name:/^Research request/}).fill(input.text);
    await page.getByTestId('dataset-version-ids').fill(input.versions.join('\n'));
    const pending=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/v1/copilot/requests'),{timeout:120000});
    await page.getByRole('button',{name:'Submit copilot request',exact:true}).click();
    const response=await pending;require(response.status()===201,'Actual create failed');
    const data=await response.json();
    await page.waitForURL(`**/#/copilot/${uuid(data.request_id)}`);
    await page.reload();
    await page.getByRole('heading',{name:'Copilot request',exact:true}).waitFor();
    require(mutations.length===1,'Reload created duplicate mutation');
    evidence.cases.push(data);
  }else if(input.mode==='answer'){
    const id=uuid(input.request_id);
    const pending=page.waitForResponse(r=>r.request().method()==='GET'&&r.url().endsWith(`/v1/copilot/requests/${id}`));
    await page.goto(`http://127.0.0.1:5173/#/copilot/${id}`);
    const before=await(await pending).json();require(before.outcome==='needs_clarification','Request not answerable');
    await page.getByLabel('Clarification answer',{exact:true}).fill(input.text);
    const answered=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/clarifications'),{timeout:120000});
    await page.getByRole('button',{name:'Submit clarification',exact:true}).click();
    const response=await answered;const body=await response.json();
    require(response.status()===201&&body.revision===before.current_revision+1,'Actual clarification revision mismatch');
    evidence.cases.push(body);
  }else{
    const current=await inspect(uuid(input.run_id),Boolean(input.require_memo));
    evidence.cases.push({run_id:input.run_id,...current});
    if(input.expected_summary_sha256)require(current.summary_sha256===input.expected_summary_sha256,'Captured summary differs from pinned reference');
    if(input.expected_results_sha256)require(current.results_sha256===input.expected_results_sha256,'Captured results differ from pinned reference');
    if(input.mode==='provenance'){
      const details=page.getByText('Pinned specification, attempts and provenance',{exact:true});
      await details.click();await details.scrollIntoViewIfNeeded();
      require((await details.locator('..').textContent()).includes(input.run_id),'Displayed provenance lacks run identity');
    }else if(input.focus){
      require(['summary','memo','chart'].includes(input.focus),'Unknown run capture focus');
      const target=input.focus==='summary'?page.getByTestId('numerical-summary'):input.focus==='memo'?page.getByTestId('memo-panel'):page.getByRole('heading',{name:'Price and base volume',exact:true});
      await target.scrollIntoViewIfNeeded();
    }
    require(mutations.length===0,'Run inspection unexpectedly mutated state');
  }
  await page.screenshot({path:path.join(captureDir,'final.png'),fullPage:true});
  await page.waitForTimeout(holdSeconds*1000);
  require(errors.length===0,'Unexpected browser page error');
  evidence.status='passed';
}catch(error){evidence.status='failed';evidence.error=String(error);}
finally{
  evidence.seconds=(performance.now()-began)/1000;
  const cleanupErrors=[];
  let video=null;
  try{video=page?.video()??null;}catch(error){cleanupErrors.push({phase:'video-handle',error:String(error)});}
  try{if(context)await context.close();}catch(error){cleanupErrors.push({phase:'context-close',error:String(error)});}
  try{if(browser)await browser.close();}catch(error){cleanupErrors.push({phase:'browser-close',error:String(error)});}
  try{
    if(video){evidence.video=await video.path();const content=await readFile(evidence.video);evidence.video_sha256=createHash('sha256').update(content).digest('hex');evidence.video_bytes=(await stat(evidence.video)).size;}
  }catch(error){cleanupErrors.push({phase:'video-finalization',error:String(error)});}
  if(cleanupErrors.length){evidence.status='failed';evidence.cleanup_errors=cleanupErrors;}
  await writeFile(output,JSON.stringify(evidence,null,2));
}
console.log(JSON.stringify({status:evidence.status,cases:evidence.cases.length,output}));
if(evidence.status!=='passed')throw new Error('Browser gate failed; see retained invocation receipt');
