import EmbeddedPostgres from 'embedded-postgres';
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {mkdirSync,writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {Client}=require('pg');
if(process.platform==='win32'){
  const root='./data/test-postgres-utf8';mkdirSync('./data',{recursive:true});
  const native='./node_modules/@embedded-postgres/windows-x64/native/bin/';
  if(!existsSync(root+'/PG_VERSION')){
    writeFileSync('./data/test-password','local-test-only');
    execFileSync(native+'initdb.exe',['-D',root,'-U','postgres','--pwfile=./data/test-password','-E','UTF8','--locale=C'],{stdio:'ignore',windowsHide:true,timeout:30000});
  }
  execFileSync(native+'pg_ctl.exe',['-D',root,'-l','./data/test-postgres.log','-o','-p 55433 -h 127.0.0.1 -c max_connections=100','-w','start'],{stdio:'ignore',windowsHide:true,timeout:30000});
  try{
    const client=new Client({host:'127.0.0.1',port:55433,user:'postgres',password:'local-test-only',database:'postgres'});await client.connect();
    const result=await client.query("SELECT 1 FROM pg_database WHERE datname='studio_test'");if(!result.rows.length)await client.query('CREATE DATABASE studio_test');await client.end();
    const cmd=process.env.PYTHON_EXECUTABLE||'.venv/Scripts/python.exe';
    const env={...process.env,DATABASE_URL:'postgresql://postgres:local-test-only@127.0.0.1:55433/studio_test',PYTHONPATH:[process.env.PYTHONPATH,'services/api'].filter(Boolean).join(';')};
    const child=spawn(cmd,['-m','pytest','services/api/tests','-q'],{env,stdio:'inherit',windowsHide:true});
    process.exitCode=await new Promise((resolve,reject)=>{child.on('exit',resolve);child.on('error',reject);});
  }finally{execFileSync(native+'pg_ctl.exe',['-D',root,'-m','fast','-w','stop'],{stdio:'ignore',windowsHide:true,timeout:30000});}
  process.exit(process.exitCode??0);
}
const pg=new EmbeddedPostgres({databaseDir:'./data/test-postgres',user:'postgres',password:'local-test-only',port:55432,persistent:true,postgresFlags:['-h','127.0.0.1','-c','max_connections=100'],onLog:()=>{},onError:()=>{}});
if(!existsSync('./data/test-postgres/PG_VERSION'))await pg.initialise();
await pg.start();
try{
  const client=pg.getPgClient();await client.connect();
  const exists=await client.query("SELECT 1 FROM pg_database WHERE datname='studio_test_utf8'");
  if(!exists.rows.length)await client.query("CREATE DATABASE studio_test_utf8 WITH ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C'");
  await client.end();
  const cmd=process.env.PYTHON_EXECUTABLE || (process.platform==='win32'?'.venv/Scripts/python.exe':'python');
  const env={...process.env,DATABASE_URL:'postgresql://postgres:local-test-only@127.0.0.1:55432/studio_test_utf8',PYTHONPATH:[process.env.PYTHONPATH,'services/api'].filter(Boolean).join(process.platform==='win32'?';':':')};
  const child=spawn(cmd,['-m','pytest','services/api/tests','-q'],{env,stdio:'inherit'});
  const code=await new Promise((resolve,reject)=>{child.on('exit',resolve);child.on('error',reject);});process.exitCode=code;
}finally{await pg.stop();}
