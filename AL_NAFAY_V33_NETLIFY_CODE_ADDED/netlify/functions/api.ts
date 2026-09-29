import type { Config } from "@netlify/functions";
import { getStore } from "@netlify/blobs";

type Rec = Record<string, any>;
const ORDER_STATUSES = ["Pending", "Confirmed", "Completed", "Cancelled"];
const SEED_PRODUCT = { name:"Premium Black", code:"AN-SC-BLK-001", fabric:"Premium Gents Unstitched", color:"Black", thaan:3843, suit:5243, sale_thaan:0, sale_suit:0, image:JSON.stringify(["/media/fabric_1.png","/media/fabric_2.png","/media/fabric_3.png","/media/fabric_4.png"]), description:"Premium black fabric. Four product views are shown on the card and product page.", sale_on:false, new_arrival:true, stock:true };
const DEFAULT_SETTINGS = { id:1, name:"AL NAFAY", tagline:"Quality · Comfort · Style", wa:"", phone:"", ig:"" };
const store = () => getStore({name:"alnafay", consistency:"strong"});
const json=(obj:unknown,status=200)=>Response.json(obj,{status});
const notFound=(error="Not found")=>json({error},404);
const readJson=async(req:Request):Promise<Rec>=>{try{return await req.json()}catch{return {}}};
const num=(v:unknown)=>Number(v)||0;
const str=(v:unknown)=>(v==null?"":String(v));
const now=()=>new Date().toISOString().slice(0,19).replace("T"," ");
const key=(kind:string,id:number)=>`${kind}/${String(id).padStart(10,"0")}`;
const nextId=async(kind:string)=>{const s=store();const current=((await s.get(`counters/${kind}`,{type:"json"})) as number|null)??0;const id=current+1;await s.setJSON(`counters/${kind}`,id);return id;};
const listAll=async(kind:string):Promise<Rec[]>=>{const s=store();const {blobs}=await s.list({prefix:`${kind}/`});const rows=await Promise.all(blobs.map(b=>s.get(b.key,{type:"json"})));return (rows.filter(Boolean) as Rec[]).sort((a,b)=>a.id-b.id);};
const ensureSeeded=async()=>{const s=store();if(await s.get("meta/seeded"))return;const id=await nextId("products");await s.setJSON(key("products",id),{id,...SEED_PRODUCT});await s.set("meta/seeded","1");};
const productValues=(d:Rec)=>({name:str(d.name)||"Unnamed Product",code:str(d.code),fabric:str(d.fabric),color:str(d.color),thaan:num(d.thaan),suit:num(d.suit),sale_thaan:num(d.sale_thaan),sale_suit:num(d.sale_suit),image:str(d.image),description:str(d.description),sale_on:Boolean(d.sale_on),new_arrival:Boolean(d.new_arrival),stock:d.stock===undefined?true:Boolean(d.stock)});
export default async(req:Request)=>{const path=new URL(req.url).pathname.replace(/\/+$/,'');const [, , resource,idPart]=path.split('/');const id=idPart?parseInt(idPart,10):undefined;const method=req.method;const s=store();
if(resource==='products'){await ensureSeeded();if(method==='GET'&&!idPart)return json(await listAll('products'));if(method==='POST'&&!idPart){const newId=await nextId('products');const row={id:newId,...productValues(await readJson(req))};await s.setJSON(key('products',newId),row);return json(row,201);}if(id&&method==='PUT'){if(!(await s.get(key('products',id))))return notFound('Product not found');const row={id,...productValues(await readJson(req))};await s.setJSON(key('products',id),row);return json(row);}if(id&&method==='DELETE'){await s.delete(key('products',id));return json({ok:true});}}
if(resource==='orders'){if(method==='GET'&&!idPart)return json((await listAll('orders')).reverse());if(method==='POST'&&!idPart){const d=await readJson(req);const newId=await nextId('orders');const row={id:newId,created_at:now(),product_id:num(d.product_id),product:str(d.product),tone:str(d.tone),option:str(d.option),unit_price:num(d.unit_price),quantity:Math.max(1,Math.trunc(num(d.quantity))||1),total:num(d.total),name:str(d.name),email:str(d.email),phone:str(d.phone),city:str(d.city),address:str(d.address),note:str(d.note),status:'Pending'};await s.setJSON(key('orders',newId),row);return json(row,201);}if(id&&method==='PUT'){const status=str((await readJson(req)).status)||'Pending';if(!ORDER_STATUSES.includes(status))return json({error:'Invalid status'},400);const row=(await s.get(key('orders',id),{type:'json'})) as Rec|null;if(!row)return notFound('Order not found');row.status=status;await s.setJSON(key('orders',id),row);return json(row);}}
if(resource==='customers'&&method==='GET'&&!idPart){const groups=new Map<string,Rec>();for(const o of await listAll('orders')){if(!o.name)continue;const k=JSON.stringify([o.name,o.phone,o.email,o.city,o.address]);const g=groups.get(k);if(g){g.order_count++;if(o.created_at>g.last_order_at)g.last_order_at=o.created_at;}else groups.set(k,{name:o.name,phone:o.phone,email:o.email,city:o.city,address:o.address,order_count:1,last_order_at:o.created_at});}return json([...groups.values()].sort((a,b)=>b.last_order_at.localeCompare(a.last_order_at)));}
if(resource==='settings'&&!idPart){if(method==='GET')return json(((await s.get('settings',{type:'json'})) as Rec|null)??DEFAULT_SETTINGS);if(method==='POST'){const d=await readJson(req);const row={id:1,name:str(d.name)||DEFAULT_SETTINGS.name,tagline:str(d.tagline)||DEFAULT_SETTINGS.tagline,wa:str(d.wa),phone:str(d.phone),ig:str(d.ig)};await s.setJSON('settings',row);return json(row);}}
return notFound();};
export const config:Config={path:'/api/*'};
