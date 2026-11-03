const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('knowledge_app/static/app.js','utf8');
const ctx={};vm.createContext(ctx);
vm.runInContext(source.split('// BEGIN selected SQL builder (pure; no credentials or source text)')[1].split('// END selected SQL builder')[0],ctx);
const build=ctx.buildSelectedSql;
const id='00000000-0000-0000-0000-000000000001',rev='00000000-0000-0000-0000-000000000002';
test('historical revision stays exact, owner defaults to NULL and source content is excluded',()=>{
 const sql=build('knowledge',{knowledge_id:id,revision_id:rev,title:'SECRET TITLE',text:'SECRET BODY'});
 assert.ok(sql.includes(`:revision_id := '${rev}'`));
 assert.ok(sql.includes('r.id = :revision_id'));
 assert.ok(sql.includes('i.owner_id = :owner_id'));
 assert.ok(sql.includes(':owner_id := NULL'));
 assert.ok(!sql.includes('SECRET'));
 assert.ok(!sql.includes('i.active_revision_id = r.id'));
});
test('memory and both relation endpoints remain owner scoped',()=>{
 const sql=build('memory',{memory_id:'a'.repeat(64)});
 for(const clause of ['user_id = :owner_id','source_memory_user_id = :owner_id','target_memory_user_id = :owner_id','source_memory_id = :memory_id OR target_memory_id = :memory_id'])assert.ok(sql.includes(clause));
});
test('SQL metacharacters and unsupported identifiers are rejected',()=>{
 for(const value of ["x'; DELETE FROM vk_item; --",'a'.repeat(65),'../../x','',null]) {
  assert.throws(()=>build('memory',{memory_id:value}));
  assert.throws(()=>build('knowledge',{knowledge_id:id,revision_id:value}));
 }
 assert.throws(()=>build('other',{}));
});
