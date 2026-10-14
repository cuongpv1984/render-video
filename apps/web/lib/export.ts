import type { Project } from "./studio";
export function download(data: Blob, name: string) {
  const url=URL.createObjectURL(data); const a=document.createElement("a"); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),10000);
}
export async function renderWebm(project: Project, onProgress: (progress:number)=>void, signal: AbortSignal) {
  if(!("MediaRecorder" in window)) throw new Error("Trình duyệt chưa hỗ trợ xuất video. Hãy dùng Chrome hoặc Edge.");
  const mime=["video/webm;codecs=vp9","video/webm;codecs=vp8","video/webm"].find(t=>MediaRecorder.isTypeSupported(t));
  if(!mime) throw new Error("Trình duyệt chưa hỗ trợ WebM. Hãy dùng Chrome hoặc Edge.");
  const images=await Promise.all(project.scenes.map(s=>new Promise<HTMLImageElement>((resolve,reject)=>{const img=new Image(); img.onload=()=>resolve(img); img.onerror=()=>reject(new Error("Không tải được hình storyboard.")); img.src=`/art/${s.art}.svg`;})));
  const canvas=document.createElement("canvas"); const [w,h]=project.ratio==="9:16"?[720,1280]:project.ratio==="1:1"?[1080,1080]:[1280,720]; canvas.width=w;canvas.height=h;
  const ctx=canvas.getContext("2d"); if(!ctx)throw new Error("Không khởi tạo được trình dựng video.");
  const stream=canvas.captureStream(24); const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:4_000_000}); const chunks:BlobPart[]=[];
  recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
  const done=new Promise<Blob>((resolve,reject)=>{recorder.onstop=()=>signal.aborted?reject(new Error("Đã dừng xuất video.")):resolve(new Blob(chunks,{type:mime})); recorder.onerror=()=>reject(new Error("Không ghi được video."));});
  const total=project.scenes.reduce((n,s)=>n+s.duration,0); let raf=0; let stopped=false;
  const stop=()=>{if(stopped)return;stopped=true;cancelAnimationFrame(raf);if(recorder.state!=="inactive")recorder.stop();}; signal.addEventListener("abort",stop,{once:true});
  recorder.start(250); const start=performance.now();
  const draw=()=>{
    const elapsed=(performance.now()-start)/1000; let i=0,offset=0;
    while(i<project.scenes.length-1 && elapsed>=offset+project.scenes[i].duration){offset+=project.scenes[i].duration;i++;}
    const scene=project.scenes[i],img=images[i]; const t=Math.min(1,(elapsed-offset)/scene.duration); const scale=Math.max(w/img.width,h/img.height)*(1+0.05*t); const iw=img.width*scale,ih=img.height*scale;
    ctx.fillStyle="#171d19";ctx.fillRect(0,0,w,h);ctx.drawImage(img,(w-iw)/2+(t-.5)*18,(h-ih)/2,iw,ih);
    const grad=ctx.createLinearGradient(0,h*.55,0,h);grad.addColorStop(0,"transparent");grad.addColorStop(1,"rgba(6,14,11,.8)");ctx.fillStyle=grad;ctx.fillRect(0,h*.55,w,h*.45);
    ctx.fillStyle="white";ctx.textAlign="center";ctx.font=`500 ${Math.round(w/37)}px Arial`;const words=scene.script.split(/\s+/);const lines:string[]=[];let line="";
    for(const word of words){const next=(line+" "+word).trim();if(ctx.measureText(next).width>w*.8&&line){lines.push(line);line=word;}else line=next;}if(line)lines.push(line);
    lines.slice(0,4).forEach((l,j)=>ctx.fillText(l,w/2,h*.83+j*w/27));ctx.font=`${Math.round(w/65)}px Arial`;ctx.fillStyle="rgba(255,255,255,.65)";ctx.fillText(project.title,w/2,h*.08);
    onProgress(Math.min(100,Math.round(elapsed/total*100))); if(elapsed>=total)stop();else raf=requestAnimationFrame(draw);
  }; draw();
  try{return await done;}finally{cancelAnimationFrame(raf);stream.getTracks().forEach(t=>t.stop());signal.removeEventListener("abort",stop);}
}
