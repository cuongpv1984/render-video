import {Container} from '@cloudflare/containers';
interface Env {
  STUDIO_API: DurableObjectNamespace<StudioAPI>;
  DATABASE_URL: string; STUDIO_OWNER_TOKEN: string; WEB_ORIGIN: string;
  R2_ENDPOINT: string; R2_BUCKET: string; R2_ACCESS_KEY_ID: string; R2_SECRET_ACCESS_KEY: string;
}
export class StudioAPI extends Container<Env> {
  defaultPort=8080;
  sleepAfter='10m';
  override envVars={
    DATABASE_URL:this.env.DATABASE_URL,STUDIO_OWNER_TOKEN:this.env.STUDIO_OWNER_TOKEN,
    WEB_ORIGIN:this.env.WEB_ORIGIN,R2_ENDPOINT:this.env.R2_ENDPOINT,R2_BUCKET:this.env.R2_BUCKET,
    R2_ACCESS_KEY_ID:this.env.R2_ACCESS_KEY_ID,R2_SECRET_ACCESS_KEY:this.env.R2_SECRET_ACCESS_KEY
  };
}
async function tokenMatches(actual:string,expected:string){
  const enc=new TextEncoder();
  const [a,b]=await Promise.all([crypto.subtle.digest('SHA-256',enc.encode(actual)),crypto.subtle.digest('SHA-256',enc.encode(expected))]);
  const left=new Uint8Array(a),right=new Uint8Array(b);let diff=0;for(let i=0;i<left.length;i++)diff|=left[i]^right[i];return diff===0;
}
export default {
  async fetch(request:Request,env:Env):Promise<Response>{
    const origin=request.headers.get('Origin');
    const cors={'Access-Control-Allow-Origin':env.WEB_ORIGIN,'Vary':'Origin','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'Authorization,Content-Type,Idempotency-Key'};
    if(origin && origin!==env.WEB_ORIGIN)return new Response('Origin not allowed',{status:403});
    if(request.method==='OPTIONS')return new Response(null,{status:204,headers:cors});
    if(!env.STUDIO_OWNER_TOKEN || env.STUDIO_OWNER_TOKEN.length<32 || !env.DATABASE_URL || !env.R2_ENDPOINT || !env.R2_BUCKET || !env.R2_ACCESS_KEY_ID || !env.R2_SECRET_ACCESS_KEY)return Response.json({code:'NOT_CONFIGURED',message:'Backend secrets, PostgreSQL hoặc R2 chưa được cấu hình.'},{status:503,headers:cors});
    // Authenticate before waking a billable container.
    if(!await tokenMatches(request.headers.get('Authorization')??'',`Bearer ${env.STUDIO_OWNER_TOKEN}`))return Response.json({code:'UNAUTHORIZED',message:'Token không hợp lệ.'},{status:401,headers:cors});
    const response=await env.STUDIO_API.getByName('owner-pilot').fetch(request);
    const result=new Response(response.body,response);for(const [key,value] of Object.entries(cors))result.headers.set(key,value);return result;
  }
};
