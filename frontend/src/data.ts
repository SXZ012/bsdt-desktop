export type Kind='market'|'industries'|'stocks'|'reports';
export const kinds:Kind[]=['market','industries','stocks','reports'];
export type Row=Record<string,string|null>;
export type Meta={module:Kind;version_id:string;batch_id:string;as_of:string;revision:number;generated_at:string|null;published_at:string|null;received_at:string;sample:boolean;source:string;confirmed_by:string;count:number;legacy?:boolean};
export type Receipt={id:string;module:string;status:string;message:string;as_of:string;revision:number;imported_at:string};
export type Overview={api_version:number;modules:Record<Kind,Meta|null>;alerts:Receipt[];scan_error:string|null};
export type Market={weather:string|null;summary:string|null;metrics:{label:string;value:string|null}[]};
export type PageData={meta:Meta;data:Row[];page:number;page_size:number;total:number;statuses:string[]};
export type DetailData={meta:Meta;data:Row};
export type Resource={meta:Meta;data:Market};
export const missing=(value:string|number|null|undefined)=>value===null||value===undefined||value===''?'待补充':String(value);
export function normalizeAddress(value:string){const u=new URL(value);if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.pathname!=='/'||u.search||u.hash)throw Error('请输入后台地址，如 http://192.168.1.10:8765');return u.origin}
export function cacheKey(address:string){return `bsdt-v2:${address}`}
export function readSaved<T>(key:string):T|null{try{return JSON.parse(localStorage.getItem(key)||'null') as T|null}catch{return null}}
export function saveLocal(key:string,value:unknown){try{localStorage.setItem(key,JSON.stringify(value));return true}catch{return false}}
export async function getData<T>(address:string,path:string,signal:AbortSignal):Promise<T>{
 const key=cacheKey(address)+':'+path;const previous=readSaved<{etag:string|null;data:T}>(key);
 const response=await fetch(address+path,{signal,cache:'no-store',headers:previous?.etag?{'If-None-Match':previous.etag}:{}});
 if(response.status===304&&previous)return previous.data;
 if(!response.ok){const error=new Error(response.status===404?'该对象已移除或尚无发布数据':`后台返回 ${response.status}`);Object.assign(error,{status:response.status});throw error}
 const data=await response.json() as T;
 // Bound endpoint caches so 5,000 details are never duplicated indefinitely in localStorage.
 try{const prefixes=cacheKey(address)+':';const entries=Object.keys(localStorage).filter(k=>k.startsWith(prefixes)&&k!==key);if(entries.length>100)for(const old of entries.slice(0,entries.length-100))localStorage.removeItem(old)}catch{}
 saveLocal(key,{etag:response.headers.get('ETag'),data});return data;
}
export function endpointCache<T>(address:string,path:string){return readSaved<{data:T}>(cacheKey(address)+':'+path)?.data||null}