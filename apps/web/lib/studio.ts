export type Route = "motion" | "standard" | "hero";
export type Scene = {id: string; title: string; script: string; duration: number; motion: number; route: Route | "auto"; approved: boolean; art: string; status: "draft" | "ready" | "rendering" | "review" | "approved"};
export type Project = {id: string; title: string; description: string; ratio: "16:9" | "9:16" | "1:1"; budget: number; revision: number; scenes: Scene[]; createdAt: string};
export type Line = {sceneId: string; route: Route; base: number; ceiling: number; reason: string};
export type Quote = {id: string; projectId: string; revision: number; fingerprint: string; createdAt: number; expiresAt: number; lines: Line[]; base: number; ceiling: number; retry: boolean};
export type Run = {id: string; projectId: string; quoteId: string; state: "running" | "review" | "completed" | "cancelled"; ceiling: number; held: number; spent: number; sceneIds: string[]; createdAt: number};
export type Ledger = {id: string; runId: string; type: "HOLD" | "SETTLE" | "RELEASE"; amount: number; at: string};
export type Studio = {version: 1; projects: Project[]; runs: Run[]; ledger: Ledger[]; workspaceBudget: number};
export const routeLabels: Record<Route, string> = {motion: "Ảnh có chuyển động", standard: "Video AI tiêu chuẩn", hero: "Cảnh chất lượng cao"};
export const money = (micro: number) => new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", maximumFractionDigits: 2}).format(micro / 1_000_000);
export function routeScene(scene: Scene): {route: Route; reason: string} {
  if(scene.route !== "auto") return {route: scene.route, reason: "Phương án anh chọn cho cảnh này."};
  if(scene.motion <= 1) return {route: "motion", reason: "Chuyển động nhẹ: dùng ảnh và camera để tiết kiệm chi phí."};
  if(scene.motion === 2) return {route: "standard", reason: "Cần chuyển động nhân vật: chọn video AI tiêu chuẩn."};
  return {route: "hero", reason: "Hành động phức tạp: ưu tiên chất lượng và độ nhất quán."};
}
export function fingerprint(project: Project): string {return JSON.stringify({revision: project.revision, ratio: project.ratio, scenes: project.scenes.map(({id,title,script,duration,motion,route,approved,art})=>({id,title,script,duration,motion,route,approved,art}))});}
// These rates are illustrative only. Paid runs use authoritative FastAPI quotes.
export function estimate(project: Project, retry: boolean, now = Date.now()): Quote {
  if(!project.scenes.length || project.scenes.some(s=>!s.approved || s.duration<2 || s.duration>15)) throw new Error("Duyệt storyboard và đặt thời lượng mỗi cảnh từ 2 đến 15 giây.");
  const lines = project.scenes.map(s=>{const {route,reason}=routeScene(s); const base = route === "motion" ? 20_000 : s.duration * (route === "standard" ? 80_000 : 200_000); return {sceneId:s.id,route,reason,base,ceiling:base*(retry && route!=="motion" ? 2 : 1)};});
  return {id:crypto.randomUUID(),projectId:project.id,revision:project.revision,fingerprint:fingerprint(project),createdAt:now,expiresAt:now+900_000,lines,base:lines.reduce((a,l)=>a+l.base,0),ceiling:lines.reduce((a,l)=>a+l.ceiling,0),retry};
}
export function budget(studio: Studio, projectId?: string) {
  const runs=studio.runs.filter(r=>!projectId || r.projectId===projectId); const spent=runs.reduce((a,r)=>a+r.spent,0); const held=runs.reduce((a,r)=>a+r.held,0);
  const limit=projectId ? studio.projects.find(p=>p.id===projectId)?.budget ?? 0 : studio.workspaceBudget;
  return {limit,spent,held,available:limit-spent-held};
}
export function accept(studio: Studio, quote: Quote, now=Date.now()): Studio {
  const duplicate=studio.runs.find(r=>r.quoteId===quote.id); if(duplicate) return studio;
  const p=studio.projects.find(p=>p.id===quote.projectId);
  if(!p || now>=quote.expiresAt || fingerprint(p)!==quote.fingerprint) throw new Error("Dự toán đã thay đổi hoặc hết hạn. Hãy dự toán lại.");
  if(budget(studio).available<quote.ceiling || budget(studio,p.id).available<quote.ceiling) throw new Error("Ngân sách khả dụng không đủ để giữ mức trần này.");
  const id=crypto.randomUUID(); const run:Run={id,projectId:p.id,quoteId:quote.id,state:"running",ceiling:quote.ceiling,held:quote.ceiling,spent:0,sceneIds:quote.lines.map(l=>l.sceneId),createdAt:now};
  return {...studio,runs:[run,...studio.runs],ledger:[{id:crypto.randomUUID(),runId:id,type:"HOLD",amount:quote.ceiling,at:new Date(now).toISOString()},...studio.ledger]};
}
export function finishSimulation(studio: Studio, runId: string): Studio {
  const run=studio.runs.find(r=>r.id===runId); if(!run || run.state!=="running") return studio;
  return {...studio,runs:studio.runs.map(r=>r.id===runId?{...r,state:"review",held:0,spent:0}:r),projects:studio.projects.map(p=>p.id===run.projectId?{...p,scenes:p.scenes.map(s=>run.sceneIds.includes(s.id)?{...s,status:"review"}:s)}:p),ledger:[{id:crypto.randomUUID(),runId,type:"RELEASE",amount:run.held,at:new Date().toISOString()},...studio.ledger]};
}
export function cancelRun(studio: Studio, runId: string): Studio {
  const run=studio.runs.find(r=>r.id===runId); if(!run || run.state!=="running")return studio;
  return {...studio,runs:studio.runs.map(r=>r.id===runId?{...r,state:"cancelled",held:0}:r),ledger:[{id:crypto.randomUUID(),runId,type:"RELEASE",amount:run.held,at:new Date().toISOString()},...studio.ledger]};
}
export function seed(): Studio {
  const scenes:Scene[]=[
    {id:"scene-1",title:"Một buổi sáng mới",script:"Khi thành phố còn đang ngủ, Mây đã bắt đầu chuyến phiêu lưu của mình.",duration:5,motion:1,route:"auto",approved:true,art:"dawn",status:"ready"},
    {id:"scene-2",title:"Người bạn trong rừng",script:"Ở cuối con đường nhỏ, một người bạn bất ngờ đang chờ Mây.",duration:6,motion:2,route:"auto",approved:true,art:"forest",status:"ready"},
    {id:"scene-3",title:"Chạm tới những vì sao",script:"Chỉ cần một chút can đảm, những điều tưởng như không thể sẽ trở thành có thể.",duration:5,motion:3,route:"auto",approved:true,art:"stars",status:"ready"},
    {id:"scene-4",title:"Cùng nhau trở về",script:"Và Mây nhận ra: hành trình đẹp nhất là hành trình có bạn đồng hành.",duration:5,motion:1,route:"auto",approved:true,art:"sunset",status:"ready"}
  ];
  return {version:1,projects:[{id:"project-may",title:"Mây và khu rừng nhỏ",description:"Một câu chuyện về tình bạn và những điều kỳ diệu.",ratio:"16:9",budget:15_000_000,revision:1,scenes,createdAt:new Date().toISOString()}],runs:[],ledger:[],workspaceBudget:50_000_000};
}
