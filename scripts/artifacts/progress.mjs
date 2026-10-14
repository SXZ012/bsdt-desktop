import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob,SpreadsheetFile} from '@oai/artifact-tool';
process.chdir(fileURLToPath(new URL('.',import.meta.url)));
const out='../../.cache/progress-preview';await fs.mkdir(out,{recursive:true});
const destination='../../../file/BSDT每日任务计划表_开发进度.xlsx';
await fs.access(destination); // This is the sole progress workbook; never recreate a duplicate.
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(destination));
const before=await wb.render({sheetName:'任务进度表',range:'A14:H27',scale:1.4,format:'png'});await fs.writeFile(`${out}/before.png`,new Uint8Array(await before.arrayBuffer()));
if(process.argv.includes('--preview'))process.exit(0);
const dateArg=process.argv.find(x=>x.startsWith('--date='))?.slice(7);
const today=dateArg||new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
if(!/^\d{4}-\d{2}-\d{2}$/.test(today)||new Date(today+'T00:00:00Z').toISOString().slice(0,10)!==today)throw Error('无效同步日期');
const sheet=wb.worksheets.getItem('任务进度表'),updates=JSON.parse(await fs.readFile('../../docs/progress.json','utf8'));
const rows=sheet.getRange('A2:H41').values;
for(let i=0;i<rows.length;i++){
 const item=updates[String(rows[i][0])];if(!item)continue;const n=i+2;
 sheet.getRange(`E${n}`).values=[[item.status]];
 if(item.status==='已完成'&&!rows[i][5])sheet.getRange(`F${n}`).values=[[new Date((item.completed_at||today)+'T00:00:00Z')]];
 sheet.getRange(`H${n}`).values=[[item.note]];
}
const daily=wb.worksheets.getItem('每日记录'),dailyRows=daily.getRange('A2:F61').values;
const key=value=>value instanceof Date?value.toISOString().slice(0,10):typeof value==='number'?new Date((value-25569)*86400000).toISOString().slice(0,10):String(value||'').slice(0,10);
let index=dailyRows.findIndex(row=>key(row[0])===today);
if(index<0){index=dailyRows.findIndex(row=>!row[0]);if(index<0)throw Error('每日记录无可用行，请扩展后重试');daily.getRange(`A${index+2}`).values=[[new Date(today+'T00:00:00Z')]];daily.getRange(`A${index+2}`).setNumberFormat('yyyy-mm-dd')}
const n=index+2;daily.getRange(`B${n}:D${n}`).values=[[updates.daily_stage||'内部演示版优化',updates.daily_task||'开发与验证',updates.summary]];daily.getRange(`F${n}`).values=[['真实输出与跨电脑验收待配合。工时留空。']];
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'任务进度表!E14:H27',maxChars:2200,tableMaxRows:14,tableMaxCols:4})).ndjson);
for(const [name,range,file] of [['任务进度表','A14:H27','after'],['每日记录',`A1:F${Math.min(4,n+1)}`,'daily']]){const img=await wb.render({sheetName:name,range,scale:1.4,format:'png'});await fs.writeFile(`${out}/${file}.png`,new Uint8Array(await img.arrayBuffer()));}
await(await SpreadsheetFile.exportXlsx(wb)).save(destination);
const sidecar=destination+'.inspect.ndjson';
if(await fs.access(sidecar).then(()=>true).catch(()=>false))await fs.rename(sidecar,out+'/workbook.inspect.ndjson');
console.log('Updated progress date',today);