"use client";
import {useEffect,useState} from "react";
import {CheckCircle2,Download,LoaderCircle,Play,Upload,Wallet} from "lucide-react";
import {fingerprint,money,type Project} from "../lib/studio";
type ServerQuote={quote_id:string;input_hash:string;base_micro_usd:number;ceiling_micro_usd:number;expires_at:string;dispatch_ready:boolean};
type ServerRun={id:string;state:string;held_micro:number;spent_micro:number;error_code?:string};
export default function BackendPanel({project}:{project:Project}){
  const [url,setUrl]=useState(""),[token,setToken]=useState(""),[busy,setBusy]=useState(false),[status,setStatus]=useState("");
  const [serverId,setServerId]=useState(""),[synced,setSynced]=useState(""),[quote,setQuote]=useState<ServerQuote|null>(null),[run,setRun]=useState<ServerRun|null>(null);
  const unchanged=synced===fingerprint(project);
  const base=()=>{const u=new URL(url);if(u.protocol!=="https:"&&!['localhost','127.0.0.1'].includes(u.hostname))throw new Error("Backend phải dùng HTTPS.");return u.toString().replace(/\/$/,"");};
  const request=async(path:string,method="GET",body?:unknown)=>{
    const response=await fetch(`${base()}/api/v1${path}`,{method,redirect:"error",headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json",...(method==="POST"?{"Idempotency-Key":crypto.randomUUID()}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000)});
    const data=await response.json();if(!response.ok)throw new Error(typeof data.message==="string"?data.message:"Backend từ chối yêu cầu. Kiểm tra cấu hình và dữ liệu.");return data;
  };
  const act=async(fn:()=>Promise<void>)=>{setBusy(true);try{await fn();}catch(e){setStatus((e as Error).message);}finally{setBusy(false);}};
  const sync=()=>act(async()=>{const snapshot=fingerprint(project);const data=await request("/projects","POST",{client_id:project.id,title:project.title,ratio:project.ratio,budget_micro_usd:project.budget,scenes:project.scenes.map(s=>({client_id:s.id,title:s.title,script:s.script,duration:s.duration,motion:s.motion,route:s.route,approved:s.approved,art:s.art}))});setServerId(data.project_id);setSynced(snapshot);setQuote(null);setRun(null);setStatus("Đã lưu dự án vào PostgreSQL.");});
  const estimate=()=>act(async()=>{const data=await request("/quotes","POST",{project_id:serverId,retry:false});setQuote(data);setStatus(data.dispatch_ready?"Dự toán sẵn sàng. Backend sẽ dựng MP4 bằng hình và chuyển động camera.":"Có cảnh video AI chưa có provider. Đổi các cảnh sang Ảnh có chuyển động để chạy backend hiện tại.");});
  const start=()=>act(async()=>{if(!quote)return;const result=await request(`/quotes/${quote.quote_id}/runs`,"POST",{accepted_ceiling_micro_usd:quote.ceiling_micro_usd,input_hash:quote.input_hash});setRun(await request(`/runs/${result.run_id}`));setStatus("Ngân sách đã được giữ trong PostgreSQL. Worker sẽ xử lý lượt chạy.");});
  useEffect(()=>{
    if(!run||!["queued","rendering"].includes(run.state))return;
    let closed=false;const timer=setInterval(async()=>{try{const result=await request(`/runs/${run.id}`);if(!closed)setRun(result);}catch(e){if(!closed)setStatus((e as Error).message);}},3000);
    return()=>{closed=true;clearInterval(timer);};
    // Credentials remain in memory; polling stops when this panel unmounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[run?.id,run?.state,url,token]);
  const restore=()=>act(async()=>{const runs=await request("/runs");const matching=runs.find((r:{project_id:string})=>r.project_id===serverId);if(matching)setRun(await request(`/runs/${matching.id}`));else setStatus("Chưa có lượt chạy cho dự án này.");});
  const downloadMp4=()=>act(async()=>{
    if(!run)return;const response=await fetch(`${base()}/api/v1/runs/${run.id}/download`,{headers:{Authorization:`Bearer ${token}`},redirect:"error",signal:AbortSignal.timeout(60000)});
    if(!response.ok)throw new Error("Video chưa sẵn sàng tải xuống.");
    if(response.headers.get("content-type")?.includes("application/json")){const data=await response.json();const signed=new URL(data.url);if(signed.protocol!=="https:")throw new Error("Đường dẫn tải không hợp lệ.");const a=document.createElement("a");a.href=signed.toString();a.target="_blank";a.rel="noreferrer";a.click();}
    else{const {download}=await import("../lib/export");download(await response.blob(),`${project.title}.mp4`);}
  });
  return <div className="panel"><h2>Backend FastAPI</h2><p>Dự án và ngân sách backend lưu trong PostgreSQL. Token chỉ giữ trong bộ nhớ của màn hình này.</p><label className="field">Địa chỉ API<input type="url" placeholder="https://api.example.com" value={url} onChange={e=>{setUrl(e.target.value);setServerId("");setQuote(null);setRun(null);}}/></label><label className="field">Token chủ workspace<input type="password" autoComplete="off" placeholder="Token backend của anh" value={token} onChange={e=>setToken(e.target.value)}/></label><div className="inline wrap"><button className="button primary" disabled={!url||!token||busy||!project.scenes.length} onClick={sync}>{busy?<LoaderCircle size={15} className="spinning"/>:<Upload size={15}/>}Đồng bộ dự án</button><button className="button secondary" disabled={!serverId||!unchanged||busy} onClick={estimate}><Wallet size={15}/>Dự toán backend</button></div>{quote&&unchanged&&<div className="server-quote"><strong>Mức trần backend {money(quote.ceiling_micro_usd)}</strong><p>Biểu phí render nội bộ, không phải hóa đơn cloud. AI chưa được bật.</p><button className="button primary" disabled={!quote.dispatch_ready||busy||Date.parse(quote.expires_at)<=Date.now()||!!run&&["queued","rendering"].includes(run.state)} onClick={start}><Play size={15}/>Dựng MP4 với trần này</button></div>}{serverId&&<button className="text-button" disabled={busy} onClick={restore}>Đọc lượt chạy gần nhất</button>}{run&&<div className="server-run"><span className="inline"><CheckCircle2 size={15}/>{run.state}</span><p>Đang giữ: {money(run.held_micro)} · Đã quyết toán nội bộ: {money(run.spent_micro)}</p>{run.error_code&&<p>{run.error_code}</p>}{run.state==="completed"&&<button className="button primary" disabled={busy} onClick={downloadMp4}><Download size={15}/>Tải MP4</button>}{["queued","rendering"].includes(run.state)&&<button className="button secondary" disabled={busy} onClick={()=>act(async()=>{await request(`/runs/${run.id}/cancel`,"POST");setStatus("Đã yêu cầu dừng. Giữ ngân sách đến khi worker xác nhận.");})}>Yêu cầu dừng</button>}</div>}{status&&<p className="connection-status" role="status">{status}</p>}</div>;
}
