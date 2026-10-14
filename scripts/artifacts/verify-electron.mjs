import {fileURLToPath} from 'node:url';
process.chdir(fileURLToPath(new URL('.',import.meta.url)));
import {_electron as electron} from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve('../..');const args=process.argv.includes('--installed')?[]:[root];const executablePath=process.argv.includes('--installed')?path.join(root,'outputs/verification/test-install/BSDT内部工作台.exe'):path.join(root,'node_modules/electron/dist/electron.exe');
const app=await electron.launch({executablePath:process.env.BSDT_TEST_EXECUTABLE||executablePath,args,cwd:root,timeout:30000});
try{const page=await app.firstWindow();await page.getByText('防御观察（模拟）',{exact:true}).waitFor({timeout:20000});assert.match(await page.locator('.notice').innerText(),/2026-09-24/);const backendData=await page.evaluate(async()=>{const r=await fetch('http://127.0.0.1:8765/api/overview');return r.json()});assert.equal(backendData.api_version,2);assert.equal(backendData.modules.market.sample,true);await fs.mkdir(path.join(root,'outputs/verification'),{recursive:true});const suffix=process.argv.includes('--installed')?'installed':'electron';await page.screenshot({path:path.join(root,`outputs/verification/${suffix}.png`),fullPage:true});await fs.writeFile(path.join(root,`outputs/verification/${suffix}-test.json`),JSON.stringify({passed:true,checks:['native Electron launch','file origin fetch','confirmed sample display','as-of preserved']},null,2));console.log(`${suffix} runtime checks passed`)}finally{await app.close()}
