import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn,execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
const root=path.resolve('../..'),output=path.join(root,'outputs/verification/live-update');await fs.mkdir(output,{recursive:true});
const inbox=path.join(output,'inbox'),python=path.join(root,'.venv/Scripts/python.exe');await fs.mkdir(inbox,{recursive:true});
const log=await fs.open(path.join(output,'backend.log'),'w');const server=spawn(python,['-m','uvicorn','backend.app:app','--host','127.0.0.1','--port','18766'],{cwd:root,env:{...process.env,BSDT_INBOX:inbox,BSDT_DATA_DIR:path.join(output,'db')},windowsHide:true,stdio:['ignore',log.fd,log.fd]});
const browser=await chromium.launch({headless:true});
try{
 for(let i=0;i<30;i++){try{if((await fetch('http://127.0.0.1:18766/api/health')).ok)break}catch{}await new Promise(r=>setTimeout(r,300))}
 const page=await browser.newPage();await page.addInitScript(()=>{localStorage.setItem('bsdt-address','http://127.0.0.1:18766');localStorage.setItem('bsdt-interval','15')});await page.goto('http://127.0.0.1:5173');await page.getByText('等待首次发布',{exact:true}).waitFor();
 const upload=(id,date,state,csv=false)=>execFileSync(python,['-c',`from pathlib import Path; from scripts.demo_upload import make_batch; make_batch(Path(${JSON.stringify(inbox)}),${JSON.stringify(id)},${JSON.stringify(date)},${JSON.stringify(state)},${csv?'True':'False'})`],{cwd:root,windowsHide:true});
 upload('poll-a','2026-09-24','published',true);await page.getByText('防御观察（模拟）',{exact:true}).waitFor({timeout:45000});assert.match(await page.locator('.notice').innerText(),/2026-09-24/);
 upload('poll-b','2026-09-28','pending');await page.getByText('poll-b',{exact:true}).waitFor({timeout:45000});assert.match(await page.locator('.notice').innerText(),/2026-09-24/);
 upload('poll-b','2026-09-28','published',true);await page.locator('.notice').getByText(/数据日期 2026-09-28/).waitFor({timeout:45000});await page.screenshot({path:path.join(output,'published-update.png'),fullPage:true});
 const state=(await(await fetch('http://127.0.0.1:18766/api/snapshot')).json());assert.equal(state.data.meta.batch_id,'poll-b');assert.equal(state.data.stocks[0].code,'000001');await fs.writeFile(path.join(output,'result.json'),JSON.stringify({passed:true,checks:['empty state','automatic scan and refresh','pending preserves prior date','confirmation publishes same batch','CSV code leading zeros']},null,2));console.log('Automatic update checks passed');
}finally{await browser.close();server.kill();await log.close()}
