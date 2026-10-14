import {useEffect,useRef,useState} from 'react';
import {Activity,CheckCircle2,Link2,LoaderCircle,Wifi} from 'lucide-react';
import brandIcon from './brand-icon.svg';
import {normalizeAddress} from './data';
export function savedServiceAddress():string|null{try{const value=localStorage.getItem('bsdt-address');return value?normalizeAddress(value):null}catch{return null}}
export function ConnectionSetup({onConfigured}:{onConfigured:(address:string)=>void}){
 const [value,setValue]=useState(''),[working,setWorking]=useState(false),[result,setResult]=useState<{error:boolean;text:string}|null>(null);
 const request=useRef<AbortController|null>(null);
 useEffect(()=>()=>request.current?.abort(),[]);
 async function connect(save:boolean){
  if(working)return;
  let address:string;try{address=normalizeAddress(value.trim())}catch{setResult({error:true,text:'请输入有效的服务地址，如 http://192.168.1.10:8765。'});return}
  const controller=new AbortController();request.current=controller;const timer=setTimeout(()=>controller.abort(),5000);
  setWorking(true);setResult({error:false,text:'正在测试连接…'});
  try{
   const response=await fetch(address+'/api/health',{signal:controller.signal,cache:'no-store'});
   if(!response.ok)throw Error('unreachable');
   const health=await response.json();if(health.api_version!==2) {setResult({error:true,text:'服务版本不兼容，请联系管理员。'});return}
   if(save){try{localStorage.setItem('bsdt-address',address)}catch{setResult({error:true,text:'无法保存连接配置，请检查客户端存储权限后重试。'});return}onConfigured(address)}
   else setResult({error:false,text:'连接成功'});
  }catch{if(request.current===controller)setResult({error:true,text:'无法连接，请检查服务地址和网络连接。'})}
  finally{clearTimeout(timer);if(request.current===controller){request.current=null;setWorking(false)}}
 }
 return <div className="setup-page"><section className="setup-card" aria-labelledby="setup-title"><div className="setup-brand"><img src={brandIcon} alt="BSDT"/><span>BSDT<small>研究工作台</small></span></div><h1 id="setup-title">配置服务连接</h1><p className="setup-intro">首次使用，请配置数据服务连接。</p><form onSubmit={event=>{event.preventDefault();void connect(true)}}><label htmlFor="setup-address">服务地址</label><div className="address-input"><Link2 size={17}/><input id="setup-address" type="text" autoFocus autoComplete="url" spellCheck={false} placeholder="请输入提供的数据服务地址" value={value} disabled={working} onChange={event=>{setValue(event.target.value);setResult(null)}}/></div><div className="setup-feedback" role="status" aria-live="polite">{result&&<div className={`test-result ${result.error?'error':working?'loading':'success'}`}>{working?<LoaderCircle size={16} className="spinning"/>:result.error?<Activity size={16}/>:<CheckCircle2 size={16}/>}<span>{result.text}</span></div>}</div><div className="setup-actions"><button type="button" onClick={()=>void connect(false)} disabled={working||!value.trim()}><Wifi size={16}/>测试连接</button><button type="submit" className="primary" disabled={working||!value.trim()}>{working?<LoaderCircle size={16} className="spinning"/>:null}保存并进入</button></div></form></section><div className="setup-footer">BSDT 内部研究工作台</div></div>
}