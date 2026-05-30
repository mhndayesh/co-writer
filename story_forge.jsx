import { useState, useEffect, useRef } from "react";
import * as d3 from "d3";

/* ── palette ── */
const C = {
  bg:"#0a0806", surface:"#151009", surface2:"#1c1610", surface3:"#23190e",
  border:"#2a2016", borderLight:"#342a1a",
  text:"#e8dcc8", text2:"#9a8468", text3:"#54473a",
  gold:"#c89830", goldLight:"#d8aa40", goldFaint:"rgba(200,152,48,0.12)",
  red:"#b34535", redFaint:"rgba(179,69,53,0.15)",
  green:"#3d6b41", greenFaint:"rgba(61,107,65,0.2)",
  ink:"#060402",
};

const COVER_PALETTES = [
  { bg:"#1a1008", accent:"#c89830" }, { bg:"#0e1810", accent:"#4a7c4e" },
  { bg:"#180e14", accent:"#8b5060" }, { bg:"#0c1020", accent:"#5a6aad" },
  { bg:"#181008", accent:"#a06030" }, { bg:"#101018", accent:"#7a609a" },
];

/* ── utils ── */
const uid = () => Math.random().toString(36).slice(2, 9);
const wc  = t => t ? t.trim().split(/\s+/).filter(Boolean).length : 0;
const safe = s => (s||"").replace(/[^a-z0-9]/gi,"_").toLowerCase();
const timeAgo = ts => { const s = (Date.now()-ts)/1000; if(s<60)return "just now"; if(s<3600)return `${~~(s/60)}m ago`; if(s<86400)return `${~~(s/3600)}h ago`; return `${~~(s/86400)}d ago`; };
const defaultWorld = () => ({ title:"",genre:"",logline:"",timePeriod:"",setting:"",rules:[],themes:[],lore:"",seeds:"" });

/* ── storage ── */
/* ════════════════════════════════════════════════════════════════
   STORAGE LAYER  —  local now, cloud-ready later

   Everything persists through `DB` (get / set / del / keys).
   • In Claude / the app it uses window.storage.
   • Run standalone (your own host) and it falls back to IndexedDB.
   • To go CLOUD later: implement the same 4 methods against your
     backend (see makeCloudDB stub) and change ONE line:
        const DB = makeLocalDB();   ->   const DB = makeCloudDB(session);
     Nothing else in the app changes.
═══════════════════════════════════════════════════════════════════ */
function idbAdapter() {
  const DBN = "storyforge_db", ST = "kv";
  const open = () => new Promise((res, rej) => { const rq = indexedDB.open(DBN, 1); rq.onupgradeneeded = () => rq.result.createObjectStore(ST); rq.onsuccess = () => res(rq.result); rq.onerror = () => rej(rq.error); });
  const run = (mode, op) => open().then(db => new Promise((res, rej) => { const t = db.transaction(ST, mode); const req = op(t.objectStore(ST)); req.onsuccess = () => res(req.result); req.onerror = () => rej(req.error); }));
  return {
    mode: "local (IndexedDB)",
    get:  async k => { try { const v = await run("readonly", s => s.get(k)); return v ?? null; } catch { return null; } },
    set:  async (k, v) => { try { await run("readwrite", s => s.put(v, k)); } catch {} },
    del:  async k => { try { await run("readwrite", s => s.delete(k)); } catch {} },
    keys: async pre => { try { const all = await run("readonly", s => s.getAllKeys()); return (all || []).filter(k => !pre || String(k).startsWith(pre)); } catch { return []; } },
  };
}
function makeLocalDB() {
  const hasWS = typeof window !== "undefined" && window.storage && typeof window.storage.get === "function";
  if (hasWS) return {
    mode: "local (this device)",
    get:  async k => { try { const r = await window.storage.get(k); return r ? JSON.parse(r.value) : null; } catch { return null; } },
    set:  async (k, v) => { try { await window.storage.set(k, JSON.stringify(v)); } catch {} },
    del:  async k => { try { await window.storage.delete(k); } catch {} },
    keys: async pre => { try { const r = await window.storage.list(pre); return (r && r.keys) || []; } catch { return []; } },
  };
  return idbAdapter();
}
/* CLOUD LATER — fill this in (e.g. Supabase/Firebase) with the same 4 methods:
function makeCloudDB(session) {
  const base = "https://your-api.example.com";
  const h = { "Content-Type":"application/json", "Authorization":`Bearer ${session.token}` };
  return {
    mode: "cloud",
    get:  async k => (await fetch(`${base}/kv/${encodeURIComponent(k)}`, { headers:h })).json().then(r=>r.value??null).catch(()=>null),
    set:  async (k,v) => { await fetch(`${base}/kv/${encodeURIComponent(k)}`, { method:"PUT", headers:h, body:JSON.stringify({value:v}) }); },
    del:  async k => { await fetch(`${base}/kv/${encodeURIComponent(k)}`, { method:"DELETE", headers:h }); },
    keys: async pre => (await fetch(`${base}/kv?prefix=${encodeURIComponent(pre||"")}`, { headers:h })).json().then(r=>r.keys||[]).catch(()=>[]),
  };
}
*/
const DB = makeLocalDB();

/* ── app-level storage helpers (the only place keys are named) ── */
const STUDIO_KEY = "sf_studio_v2";
const projKey = id => `sf_proj_${id}`;
const loadStudio   = async () => (await DB.get(STUDIO_KEY)) || { projects: [] };
const saveStudio   = d => DB.set(STUDIO_KEY, d);
const loadProject  = id => DB.get(projKey(id));
const saveProject  = (id, d) => DB.set(projKey(id), d);
const deleteProject = id => DB.del(projKey(id));

/* ── backup / restore (portable local data; also your bridge to cloud) ── */
async function exportAllData() {
  const studio = await loadStudio();
  const projects = {};
  for (const p of (studio.projects || [])) projects[p.id] = await loadProject(p.id);
  return { app: "StoryForge", version: 1, exportedAt: Date.now(), studio, projects };
}
async function importAllData(bundle) {
  if (!bundle || !bundle.studio || !Array.isArray(bundle.studio.projects)) throw new Error("Not a valid Story Forge backup");
  await saveStudio(bundle.studio);
  for (const [id, data] of Object.entries(bundle.projects || {})) if (data) await saveProject(id, data);
}

/* ── context builder ── */
const buildCtx = (world, chars, chaps) => `
=== WORLD: "${world.title||'Untitled'}" | ${world.genre||'?'} | ${world.timePeriod||'?'} ===
Logline: ${world.logline||'None'}
Setting: ${world.setting||'None'}
Rules: ${(world.rules||[]).filter(Boolean).join(' | ')||'None'}
Themes: ${(world.themes||[]).filter(Boolean).join(', ')||'None'}
Lore: ${world.lore||'None'}
CHARACTERS:
${chars.map(c=>`• ${c.name} [${c.role}/${c.status||'alive'}] — ${c.personality||''} | Drives: ${c.motivation||''} | Weakness: ${c.flaw||''}`).join('\n')||'None'}
STORY SO FAR:
${chaps.map(c=>`Ch.${c.number} "${c.title}": ${c.summary||c.content?.slice(0,150)||'empty'}`).join('\n')||'None'}`;

async function callAI(system, user) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({ model:"claude-sonnet-4-20250514", max_tokens:1000, system, messages:[{role:"user",content:user}] })
  });
  const d = await res.json(); if(d.error) throw new Error(d.error.message); return d.content[0].text;
}

/* ── export ── */
function dl(content, filename) { const a=document.createElement("a"); a.href=URL.createObjectURL(new Blob([content],{type:"text/plain;charset=utf-8"})); a.download=filename; document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(a.href); }
function exportChapter(chap,chars,world){const pov=chars.find(c=>c.id===chap.pov);let t=`${world.title||'Untitled'}\n${"─".repeat(48)}\n\nChapter ${chap.number}: ${chap.title}\n`;if(pov)t+=`\n     — ${pov.name}'s perspective —\n`;if(chap.location)t+=`     ${chap.location}\n`;t+=`\n${"─".repeat(48)}\n\n${chap.content||''}`;dl(t,`ch${chap.number}_${safe(chap.title)}.txt`);}
function exportFull(world,chars,chaps){let t=`${"═".repeat(52)}\n\n${(world.title||"UNTITLED").toUpperCase()}\n${world.genre||''}\n\n${"═".repeat(52)}\n\n`;if(world.logline)t+=`"${world.logline}"\n\n`;[...chaps].sort((a,b)=>a.number-b.number).forEach(ch=>{t+=`\n\n\n${"─".repeat(48)}\n\nChapter ${ch.number}\n${ch.title}\n\n${"─".repeat(48)}\n\n${ch.content||'[No content yet]'}\n`;});dl(t,`${safe(world.title||"story")}_manuscript.txt`);}
function exportBible(world,chars,chaps){let t=`STORY BIBLE — ${world.title||'Untitled'}\n${"═".repeat(52)}\n\nGenre: ${world.genre||'—'}\nTime: ${world.timePeriod||'—'}\n\n`;if(world.logline)t+=`Logline:\n${world.logline}\n\n`;if(world.setting)t+=`World:\n${world.setting}\n\n`;if((world.rules||[]).filter(Boolean).length)t+=`Rules:\n${world.rules.filter(Boolean).map(r=>`• ${r}`).join('\n')}\n\n`;t+=`${"─".repeat(48)}\nCHARACTERS\n${"─".repeat(48)}\n\n`;chars.forEach(c=>{t+=`${c.name}  |  ${c.role}  |  ${c.status||'alive'}\n`;['age','appearance','personality','motivation','flaw','backstory'].forEach(k=>{if(c[k])t+=`${k}: ${c[k]}\n`;});if((c.relationships||[]).length)t+=`Relationships: ${c.relationships.map(r=>`${chars.find(x=>x.id===r.targetId)?.name||'?'} (${r.type})`).join(', ')}\n`;t+='\n';});t+=`${"─".repeat(48)}\nCHAPTER SUMMARIES\n${"─".repeat(48)}\n\n`;chaps.forEach(c=>{t+=`Chapter ${c.number}: ${c.title}\n${c.summary||'—'}\n${wc(c.content)} words\n\n`;});dl(t,`${safe(world.title||"story")}_bible.txt`);}

/* ── shared UI ── */
const lblSt = { display:"block", fontSize:11, color:C.text2, marginBottom:6, fontFamily:"Lora,Georgia,serif", fontStyle:"italic" };
const inpBase = { width:"100%", background:C.ink, border:`1px solid ${C.border}`, borderRadius:8, color:C.text, fontSize:13, padding:"10px 13px", fontFamily:"Lora,Georgia,serif", outline:"none", transition:"border-color .2s" };
function Inp({val,set,ph,onKey,style}){ return <input style={{...inpBase,...style}} value={val||""} onChange={e=>set(e.target.value)} placeholder={ph||""} onKeyDown={onKey} onFocus={e=>e.target.style.borderColor=C.gold} onBlur={e=>e.target.style.borderColor=C.border} />; }
function Ta({val,set,ph,style,rows}){ return <textarea style={{...inpBase,resize:"vertical",lineHeight:1.7,minHeight:rows?rows*22:80,...style}} value={val||""} onChange={e=>set(e.target.value)} placeholder={ph||""} onFocus={e=>e.target.style.borderColor=C.gold} onBlur={e=>e.target.style.borderColor=C.border} />; }
function Sel({val,set,children}){ return <select style={{...inpBase,cursor:"pointer"}} value={val||""} onChange={e=>set(e.target.value)}>{children}</select>; }
function FG({label,children,style}){ return <div style={{marginBottom:14,...style}}><label style={lblSt}>{label}</label>{children}</div>; }
function Btn({primary,ghost,danger,small,children,onClick,disabled,style}){
  const base={fontFamily:"Lora,Georgia,serif",fontSize:small?12:13,cursor:disabled?"not-allowed":"pointer",border:"none",borderRadius:8,transition:"all .2s",opacity:disabled?0.4:1,fontWeight:500,...style};
  const pad=small?"6px 13px":"10px 20px";
  const v=primary?{background:C.gold,color:"#0a0806",padding:pad,fontWeight:700}:danger?{background:C.redFaint,color:C.red,padding:pad,border:`1px solid ${C.red}40`}:{background:"transparent",color:C.text2,padding:pad,border:`1px solid ${C.border}`};
  return <button onClick={disabled?undefined:onClick} style={{...base,...v}}>{children}</button>;
}
function Card({title,icon,children,style}){ return <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:12,padding:20,...style}}>{title&&<div style={{fontFamily:'"Playfair Display",Georgia,serif',fontSize:15,color:C.gold,marginBottom:14,display:"flex",alignItems:"center",gap:8}}>{icon&&<span>{icon}</span>}{title}</div>}{children}</div>; }
function PageHdr({title,sub,children}){ return <div style={{padding:"20px 30px 16px",borderBottom:`1px solid ${C.border}`,background:C.bg,flexShrink:0,display:"flex",alignItems:"center",justifyContent:"space-between"}}><div><h1 style={{fontFamily:'"Playfair Display",Georgia,serif',fontSize:24,color:C.text,fontWeight:700,lineHeight:1.2}}>{title}</h1>{sub&&<p style={{fontSize:12,color:C.text3,marginTop:4,fontFamily:"Lora,serif",fontStyle:"italic"}}>{sub}</p>}</div>{children&&<div style={{display:"flex",gap:8,alignItems:"center"}}>{children}</div>}</div>; }

/* ══════════════════════════════════════════
   STUDIO — project hub
═══════════════════════════════════════════ */
function Studio({ projects, onCreate, onOpen, onDelete, onImport, toast }) {
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newGenre, setNewGenre] = useState("");
  const [confirmDel, setConfirmDel] = useState(null);
  const fileRef = useRef(null);

  const totalWords = projects.reduce((a, p) => a + (p.stats?.words||0), 0);

  const handleCreate = () => {
    if (!newTitle.trim()) return;
    onCreate(newTitle.trim(), newGenre.trim());
    setNewTitle(""); setNewGenre(""); setCreating(false);
  };

  const handleBackup = async () => {
    const bundle = await exportAllData();
    dl(JSON.stringify(bundle, null, 2), `storyforge_backup_${new Date().toISOString().slice(0,10)}.json`);
    toast("Backup downloaded ✓");
  };
  const handleRestoreFile = (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      try { await onImport(JSON.parse(reader.result)); }
      catch (err) { toast(err.message || "Couldn't read that file", "error"); }
    };
    reader.readAsText(file); e.target.value = "";
  };

  return (
    <div style={{ height:"100vh", background:C.bg, overflowY:"auto", display:"flex", flexDirection:"column" }}>
      {/* header */}
      <div style={{ textAlign:"center", padding:"60px 40px 40px", borderBottom:`1px solid ${C.border}` }}>
        <div style={{ fontFamily:'"Playfair Display",Georgia,serif', fontSize:42, fontWeight:700, color:C.gold, letterSpacing:1, lineHeight:1 }}>Story Forge</div>
        <div style={{ fontSize:14, color:C.text3, marginTop:10, fontFamily:"Lora,serif", fontStyle:"italic", letterSpacing:0.5 }}>Your writing studio</div>
        {projects.length > 0 && (
          <div style={{ marginTop:18, display:"flex", gap:32, justifyContent:"center" }}>
            {[[projects.length, "project" + (projects.length!==1?"s":"")], [totalWords.toLocaleString(), "words written"], [projects.reduce((a,p)=>a+(p.stats?.chapters||0),0), "chapters"]].map(([n, l]) => (
              <div key={l} style={{ textAlign:"center" }}>
                <div style={{ fontFamily:'"Playfair Display",serif', fontSize:22, color:C.text, fontWeight:600 }}>{n}</div>
                <div style={{ fontSize:11, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic", marginTop:2 }}>{l}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ flex:1, padding:"36px 48px", maxWidth:1100, margin:"0 auto", width:"100%" }}>
        {/* new project panel */}
        {creating ? (
          <div style={{ background:C.surface, border:`1px solid ${C.gold}50`, borderRadius:14, padding:"28px 32px", marginBottom:32 }}>
            <div style={{ fontFamily:'"Playfair Display",serif', fontSize:20, color:C.text, marginBottom:20, fontWeight:700 }}>Begin a new story</div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16, marginBottom:20 }}>
              <FG label="What is this story called?" style={{margin:0}}>
                <Inp val={newTitle} set={setNewTitle} ph="Give it a name..." onKey={e=>e.key==="Enter"&&handleCreate()} />
              </FG>
              <FG label="What kind of story is it?" style={{margin:0}}>
                <Inp val={newGenre} set={setNewGenre} ph="Fantasy, thriller, literary fiction..." onKey={e=>e.key==="Enter"&&handleCreate()} />
              </FG>
            </div>
            <div style={{ display:"flex", gap:10 }}>
              <Btn primary onClick={handleCreate} disabled={!newTitle.trim()}>Open the page →</Btn>
              <Btn ghost onClick={() => { setCreating(false); setNewTitle(""); setNewGenre(""); }}>Cancel</Btn>
            </div>
          </div>
        ) : (
          <div style={{ marginBottom:32, display:"flex", justifyContent:"space-between", alignItems:"center" }}>
            <div style={{ display:"flex", gap:8 }}>
              <Btn ghost small onClick={handleBackup}>⬇ Back up all</Btn>
              <Btn ghost small onClick={() => fileRef.current?.click()}>⬆ Restore</Btn>
              <input ref={fileRef} type="file" accept="application/json,.json" style={{ display:"none" }} onChange={handleRestoreFile} />
            </div>
            <Btn primary onClick={() => setCreating(true)} style={{ fontSize:14, padding:"11px 24px" }}>✦ New Story</Btn>
          </div>
        )}

        {/* empty state */}
        {projects.length === 0 && !creating && (
          <div style={{ textAlign:"center", padding:"80px 40px", color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic" }}>
            <div style={{ fontSize:52, marginBottom:20, color:C.border }}>❧</div>
            <div style={{ fontSize:18, color:C.text2, marginBottom:12, fontFamily:'"Playfair Display",serif', fontWeight:600 }}>Every great story starts somewhere.</div>
            <div style={{ fontSize:14, lineHeight:1.8 }}>Click "New Story" to begin your first project.</div>
          </div>
        )}

        {/* project grid */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(300px, 1fr))", gap:20 }}>
          {projects.map(proj => {
            const pal = COVER_PALETTES[proj.paletteIdx || 0];
            const isConfirming = confirmDel === proj.id;
            return (
              <div key={proj.id} style={{ background:pal.bg, border:`1px solid ${C.border}`, borderRadius:14, overflow:"hidden", transition:"transform .2s, border-color .2s", cursor:"pointer" }}
                onMouseEnter={e => { e.currentTarget.style.transform="translateY(-2px)"; e.currentTarget.style.borderColor=C.borderLight; }}
                onMouseLeave={e => { e.currentTarget.style.transform="translateY(0)"; e.currentTarget.style.borderColor=C.border; }}>

                {/* color bar */}
                <div style={{ height:3, background:pal.accent, opacity:0.7 }} />

                <div style={{ padding:"22px 22px 18px" }}>
                  {/* title & genre */}
                  <div style={{ marginBottom:14 }}>
                    <div style={{ fontFamily:'"Playfair Display",serif', fontSize:20, color:C.text, fontWeight:700, lineHeight:1.3, marginBottom:5 }}>{proj.title||"Untitled"}</div>
                    {proj.genre && <div style={{ fontSize:12, color:pal.accent, fontFamily:"Lora,serif", fontStyle:"italic" }}>{proj.genre}</div>}
                  </div>

                  {/* stats */}
                  <div style={{ display:"flex", gap:18, marginBottom:16 }}>
                    {[[proj.stats?.words?.toLocaleString()||"0","words"],[proj.stats?.chapters||0,"chapters"],[proj.stats?.chars||0,"characters"]].map(([n,l])=>(
                      <div key={l}>
                        <div style={{ fontFamily:'"Playfair Display",serif', fontSize:16, color:C.text, fontWeight:600 }}>{n}</div>
                        <div style={{ fontSize:10, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic" }}>{l}</div>
                      </div>
                    ))}
                  </div>

                  {/* last edited */}
                  <div style={{ fontSize:11, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic", marginBottom:16 }}>Last edited {timeAgo(proj.updatedAt||proj.createdAt)}</div>

                  {/* actions */}
                  {isConfirming ? (
                    <div style={{ background:C.redFaint, border:`1px solid ${C.red}30`, borderRadius:8, padding:"12px 14px" }}>
                      <div style={{ fontSize:12, color:C.red, fontFamily:"Lora,serif", marginBottom:10, lineHeight:1.6 }}>Delete "{proj.title}"? This cannot be undone.</div>
                      <div style={{ display:"flex", gap:8 }}>
                        <Btn danger small onClick={e => { e.stopPropagation(); onDelete(proj.id); setConfirmDel(null); }}>Yes, delete</Btn>
                        <Btn ghost small onClick={e => { e.stopPropagation(); setConfirmDel(null); }}>Keep it</Btn>
                      </div>
                    </div>
                  ) : (
                    <div style={{ display:"flex", gap:8 }}>
                      <Btn primary onClick={() => onOpen(proj)} style={{ flex:1, textAlign:"center" }}>Open →</Btn>
                      <Btn ghost small onClick={e => { e.stopPropagation(); setConfirmDel(proj.id); }} style={{ color:C.text3 }}>✕</Btn>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div style={{ textAlign:"center", marginTop:48, paddingTop:24, borderTop:`1px solid ${C.border}`, fontSize:11, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic", lineHeight:1.8 }}>
          ✓ Saved {DB.mode} — your work stays private on this machine.<br/>
          Back up regularly; restore your file on any device to bring everything with you.
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════
   WRITING SYSTEM — sidebar + tabs
═══════════════════════════════════════════ */
const TABS = [
  { id:"flow",  sym:"❦", label:"Flow Writing", star:true },
  { id:"write", sym:"❧", label:"Chapters" },
  { id:"chars", sym:"◈", label:"Characters" },
  { id:"world", sym:"✦", label:"Your World" },
  { id:"graph", sym:"◎", label:"Story Map" },
  { id:"check", sym:"◇", label:"Story Check" },
];

function Sidebar({ tab, setTab, world, stats, chars, chaps, toast, onBackToStudio }) {
  const [showExport, setShowExport] = useState(false);
  return (
    <aside style={{ width:220, background:C.surface, borderRight:`1px solid ${C.border}`, display:"flex", flexDirection:"column", flexShrink:0 }}>
      {/* back to studio */}
      <button onClick={onBackToStudio} style={{ display:"flex", alignItems:"center", gap:8, padding:"16px 18px 14px", background:"none", border:"none", borderBottom:`1px solid ${C.border}`, cursor:"pointer", color:C.text3, fontSize:12, fontFamily:"Lora,serif", fontStyle:"italic", transition:"color .15s", textAlign:"left", width:"100%" }}
        onMouseEnter={e=>e.currentTarget.style.color=C.gold} onMouseLeave={e=>e.currentTarget.style.color=C.text3}>
        ← Studio
      </button>

      <div style={{ padding:"18px 18px 14px", borderBottom:`1px solid ${C.border}` }}>
        <div style={{ fontFamily:'"Playfair Display",Georgia,serif', fontSize:17, fontWeight:700, color:C.gold, lineHeight:1.2 }}>{world.title||"Untitled"}</div>
        {world.genre && <div style={{ fontSize:11, color:C.text3, marginTop:4, fontFamily:"Lora,serif", fontStyle:"italic" }}>{world.genre}</div>}
      </div>

      <nav style={{ flex:1, padding:"10px 0" }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{ display:"flex", alignItems:"center", gap:12, width:"100%", padding:"11px 18px", background:tab===t.id?C.surface2:"transparent", border:"none", borderLeft:`2px solid ${tab===t.id?C.gold:"transparent"}`, color:tab===t.id?C.goldLight:C.text3, fontSize:14, cursor:"pointer", transition:"all .15s", textAlign:"left", fontFamily:"Lora,Georgia,serif", fontStyle:"italic" }}>
            <span style={{ fontSize:12, color:tab===t.id?C.gold:C.text3, fontStyle:"normal", width:16 }}>{t.sym}</span>
            {t.label}
            {t.star && tab!==t.id && <span style={{ marginLeft:"auto", width:5, height:5, borderRadius:"50%", background:C.gold, opacity:0.8 }} />}
          </button>
        ))}
      </nav>

      <div style={{ borderTop:`1px solid ${C.border}`, padding:"16px 18px" }}>
        <div style={{ fontSize:11, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic", lineHeight:2.2, marginBottom:12 }}>
          <div>{stats.chars} character{stats.chars!==1?"s":""}</div>
          <div>{stats.chaps} chapter{stats.chaps!==1?"s":""}</div>
          <div style={{ color:C.text2 }}>{stats.words.toLocaleString()} words</div>
        </div>
        <div style={{ position:"relative" }}>
          <Btn ghost small onClick={() => setShowExport(p=>!p)} style={{ width:"100%", textAlign:"left" }}>⬇ Export</Btn>
          {showExport && (
            <div style={{ position:"absolute", bottom:"calc(100% + 6px)", left:0, right:0, background:C.surface2, border:`1px solid ${C.borderLight}`, borderRadius:10, overflow:"hidden", zIndex:50 }}>
              {[["Full Manuscript", ()=>{exportFull(world,chars,chaps);setShowExport(false);toast("Exported ✓");}],
                ["Story Bible",    ()=>{exportBible(world,chars,chaps);setShowExport(false);toast("Bible exported ✓");}]].map(([l,fn])=>(
                <button key={l} onClick={fn} style={{ display:"block", width:"100%", padding:"10px 14px", background:"none", border:"none", color:C.text2, fontSize:12, cursor:"pointer", textAlign:"left", fontFamily:"Lora,serif", fontStyle:"italic", borderBottom:`1px solid ${C.border}` }}
                  onMouseEnter={e=>e.target.style.background=C.surface3} onMouseLeave={e=>e.target.style.background="none"}>{l}</button>
              ))}
              <button onClick={()=>setShowExport(false)} style={{ display:"block", width:"100%", padding:"8px 14px", background:"none", border:"none", color:C.text3, fontSize:11, cursor:"pointer", textAlign:"center", fontFamily:"Lora,serif" }}>cancel</button>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

/* ── WORLD TAB ── */
function WorldTab({ world, onSave, toast }) {
  const [f,setF]=useState(world); const [rIn,setRIn]=useState(""); const [tIn,setTIn]=useState("");
  useEffect(()=>setF(world),[world]);
  // autosave — never lose work
  useEffect(()=>{ if(JSON.stringify(f)===JSON.stringify(world))return; const t=setTimeout(()=>onSave(f),900); return ()=>clearTimeout(t); },[f,world]);
  const upd=(k,v)=>setF(p=>({...p,[k]:v}));
  const addRule=()=>{if(!rIn.trim())return;upd("rules",[...(f.rules||[]),rIn.trim()]);setRIn("");};
  const addTheme=()=>{if(!tIn.trim())return;upd("themes",[...(f.themes||[]),tIn.trim()]);setTIn("");};
  return (
    <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
      <PageHdr title="Your World" sub="The foundation your story is built upon."><Btn primary onClick={()=>{onSave(f);toast("Saved ✓");}}>Save</Btn></PageHdr>
      <div style={{flex:1,overflowY:"auto",padding:"24px 30px"}}>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:20}}>
          <div style={{display:"flex",flexDirection:"column",gap:16}}>
            <Card title="The Story" icon="📖">
              <FG label="Title"><Inp val={f.title} set={v=>upd("title",v)} ph="The name of your story..." /></FG>
              <FG label="Genre"><Inp val={f.genre} set={v=>upd("genre",v)} ph="Fantasy, literary fiction, thriller..." /></FG>
              <FG label="When does it take place?"><Inp val={f.timePeriod} set={v=>upd("timePeriod",v)} ph="Medieval, 2147 AD, 1920s Paris..." /></FG>
              <FG label="The one-sentence pitch"><Ta val={f.logline} set={v=>upd("logline",v)} ph="A [protagonist] must [goal] before [stakes]..." rows={3} /></FG>
            </Card>
            <Card title="The World" icon="🌍"><FG label="Describe where your story lives"><Ta val={f.setting} set={v=>upd("setting",v)} ph="Atmosphere, geography, how society works..." style={{minHeight:130}} /></FG></Card>
            <Card title="Lore & History" icon="📜"><Ta val={f.lore} set={v=>upd("lore",v)} ph="Ancient events, myths, secrets..." style={{minHeight:100}} /></Card>
          </div>
          <div style={{display:"flex",flexDirection:"column",gap:16}}>
            <Card title="The Rules" icon="⚖️">
              <p style={{fontSize:12,color:C.text3,marginBottom:12,fontFamily:"Lora,serif",fontStyle:"italic",lineHeight:1.7}}>Laws of your world the AI will always respect.</p>
              <div style={{display:"flex",gap:8,marginBottom:12}}><Inp val={rIn} set={setRIn} ph="Add a world rule..." onKey={e=>e.key==="Enter"&&addRule()} /><Btn ghost onClick={addRule}>Add</Btn></div>
              {(f.rules||[]).map((r,i)=><div key={i} style={{display:"flex",alignItems:"center",gap:10,padding:"9px 13px",background:C.ink,borderRadius:8,marginBottom:6,border:`1px solid ${C.border}`}}><span style={{fontSize:11,color:C.text2,flex:1,fontFamily:"Lora,serif",lineHeight:1.5}}>{r}</span><span onClick={()=>upd("rules",(f.rules||[]).filter((_,j)=>j!==i))} style={{cursor:"pointer",color:C.text3,fontSize:16}}>×</span></div>)}
            </Card>
            <Card title="Themes" icon="💡">
              <div style={{display:"flex",gap:8,marginBottom:12}}><Inp val={tIn} set={setTIn} ph="Identity, power, grief, redemption..." onKey={e=>e.key==="Enter"&&addTheme()} /><Btn ghost onClick={addTheme}>Add</Btn></div>
              <div style={{display:"flex",flexWrap:"wrap",gap:7}}>{(f.themes||[]).map((t,i)=><span key={i} style={{background:C.goldFaint,border:`1px solid ${C.gold}40`,color:C.goldLight,borderRadius:20,padding:"4px 14px",fontSize:12,fontFamily:"Lora,serif",fontStyle:"italic",display:"flex",alignItems:"center",gap:8}}>{t}<span onClick={()=>upd("themes",(f.themes||[]).filter((_,j)=>j!==i))} style={{cursor:"pointer",color:C.gold,fontSize:14}}>×</span></span>)}</div>
            </Card>
            <Card title="Seeds to Pay Off" icon="🌱">
              <p style={{fontSize:12,color:C.text3,marginBottom:10,fontFamily:"Lora,serif",fontStyle:"italic",lineHeight:1.7}}>Track planted foreshadowing so nothing goes forgotten.</p>
              <Ta val={f.seeds} set={v=>upd("seeds",v)} ph="One planted seed per line..." style={{minHeight:100}} />
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── CHARACTERS TAB ── */
const ROLES=["Protagonist","Antagonist","Supporting","Minor","Mentor","Love Interest","Foil"];
const STATUSES=["alive","dead","unknown","missing","transformed"];
const REL_TYPES=["ally","enemy","lover","mentor","rival","family","friend","complicated"];
const CICONS=["◈","✦","⚔","✿","❧","◎","⊕","◆","◇","⌘","✜","△","▽","⊗","⊘"];

function CharactersTab({ chars, onSave, toast }) {
  const [selId,setSelId]=useState(null); const [f,setF]=useState(null);
  const charsRef=useRef(chars); useEffect(()=>{charsRef.current=chars;},[chars]);
  useEffect(()=>{const c=chars.find(x=>x.id===selId);if(c)setF({...c});},[selId]);
  // autosave — never lose work
  useEffect(()=>{ if(!f)return; const saved=charsRef.current.find(c=>c.id===f.id); if(saved&&JSON.stringify(saved)===JSON.stringify(f))return; const t=setTimeout(()=>onSave(charsRef.current.map(c=>c.id===f.id?f:c)),900); return ()=>clearTimeout(t); },[f]);
  const newChar=()=>{const c={id:uid(),name:"New Character",role:"Supporting",icon:CICONS[~~(Math.random()*CICONS.length)],age:"",appearance:"",personality:"",backstory:"",motivation:"",flaw:"",arc:"",status:"alive",relationships:[]};onSave([...chars,c]);setSelId(c.id);setF({...c});};
  const saveF=()=>{if(!f)return;onSave(chars.map(c=>c.id===f.id?f:c));toast("Character saved ✓");};
  const delChar=id=>{onSave(chars.filter(c=>c.id!==id));if(selId===id){setSelId(null);setF(null);}toast("Removed");};
  const addRel=()=>{const others=chars.filter(c=>c.id!==f?.id);if(!others.length||!f)return;setF(p=>({...p,relationships:[...(p.relationships||[]),{targetId:others[0].id,type:"ally",desc:""}]}));};
  const sc=s=>({alive:{bg:C.greenFaint,color:"#5a9960",border:"#3d6b4130"},dead:{bg:C.redFaint,color:C.red,border:`${C.red}30`},unknown:{bg:`${C.gold}15`,color:C.gold,border:`${C.gold}30`},missing:{bg:"#1a1a2a",color:"#7a7acd",border:"#7a7acd30"},transformed:{bg:"#1a0f2a",color:"#a07ad4",border:"#a07ad430"}}[s]||{bg:`${C.gold}15`,color:C.gold,border:`${C.gold}30`});
  return (
    <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
      <PageHdr title="Characters" sub={`${chars.length} character${chars.length!==1?"s":""} in your story`}><Btn primary onClick={newChar}>+ New Character</Btn></PageHdr>
      <div style={{flex:1,overflow:"hidden",display:"flex"}}>
        <div style={{width:210,borderRight:`1px solid ${C.border}`,overflowY:"auto",padding:"12px 10px",flexShrink:0}}>
          {chars.length===0&&<div style={{textAlign:"center",padding:"40px 14px",color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic",fontSize:13,lineHeight:1.8}}>Your cast will appear here.</div>}
          {chars.map(c=>{const s=sc(c.status||"alive");return(
            <div key={c.id} onClick={()=>setSelId(c.id)} style={{padding:"14px 12px",borderRadius:10,marginBottom:6,cursor:"pointer",background:selId===c.id?C.surface2:C.surface,border:`1px solid ${selId===c.id?C.gold:C.border}`,transition:"all .2s"}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
                <div><div style={{fontSize:18,marginBottom:6,color:C.gold}}>{c.icon}</div><div style={{fontFamily:'"Playfair Display",serif',fontSize:15,color:C.text,fontWeight:600}}>{c.name}</div><div style={{fontSize:11,color:C.text3,marginTop:2,fontFamily:"Lora,serif",fontStyle:"italic"}}>{c.role}</div><span style={{display:"inline-block",marginTop:8,padding:"3px 10px",borderRadius:20,fontSize:10,background:s.bg,color:s.color,border:`1px solid ${s.border}`,fontFamily:"Lora,serif"}}>{c.status||"alive"}</span></div>
                <span onClick={e=>{e.stopPropagation();delChar(c.id);}} style={{color:C.text3,cursor:"pointer",fontSize:17}}>×</span>
              </div>
            </div>
          );})}
        </div>
        <div style={{flex:1,overflowY:"auto",padding:"28px 30px"}}>
          {!f?(<div style={{textAlign:"center",padding:"80px 40px",color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic"}}><div style={{fontSize:36,marginBottom:16,color:C.border}}>◈</div><div style={{fontSize:15,lineHeight:1.8}}>Select or create a character to begin.</div></div>):(
            <>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:22}}><h2 style={{fontFamily:'"Playfair Display",serif',fontSize:22,color:C.text,fontWeight:700}}>{f.icon} {f.name}</h2><Btn primary onClick={saveF}>Save Character</Btn></div>
              <div style={{display:"flex",gap:6,marginBottom:16,flexWrap:"wrap"}}>{CICONS.map(ic=><span key={ic} onClick={()=>setF(p=>({...p,icon:ic}))} style={{fontSize:16,cursor:"pointer",opacity:f.icon===ic?1:0.2,color:C.gold,transition:"opacity .15s"}}>{ic}</span>)}</div>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:12,marginBottom:4}}>
                <FG label="Name" style={{margin:0}}><Inp val={f.name} set={v=>setF(p=>({...p,name:v}))} /></FG>
                <FG label="Role" style={{margin:0}}><Sel val={f.role} set={v=>setF(p=>({...p,role:v}))}>{ROLES.map(r=><option key={r}>{r}</option>)}</Sel></FG>
                <FG label="Status" style={{margin:0}}><Sel val={f.status||"alive"} set={v=>setF(p=>({...p,status:v}))}>{STATUSES.map(s=><option key={s}>{s}</option>)}</Sel></FG>
              </div>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12,marginBottom:4}}>
                <FG label="Age" style={{margin:0}}><Inp val={f.age} set={v=>setF(p=>({...p,age:v}))} ph="27, early thirties..." /></FG>
                <FG label="How they look" style={{margin:0}}><Inp val={f.appearance} set={v=>setF(p=>({...p,appearance:v}))} ph="Tall, dark hair, watchful eyes..." /></FG>
              </div>
              {[["personality","How they are","Curious, sardonic, secretly tender..."],["backstory","Where they come from","What shaped who they are..."],["motivation","What drives them","What they want above all else..."],["flaw","Their fatal flaw","What holds them back..."],["arc","Their arc","How they change by the end..."]].map(([k,l,ph])=>(<FG key={k} label={l}><Ta val={f[k]} set={v=>setF(p=>({...p,[k]:v}))} ph={ph} rows={3} /></FG>))}
              <div style={{borderTop:`1px solid ${C.border}`,margin:"22px 0 18px",display:"flex",justifyContent:"space-between",alignItems:"center",paddingTop:18}}>
                <span style={{fontFamily:'"Playfair Display",serif',fontSize:16,color:C.gold}}>Relationships</span>
                {chars.length>1&&<Btn ghost small onClick={addRel}>+ Add</Btn>}
              </div>
              {chars.length<=1&&<p style={{fontSize:12,color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic"}}>Add more characters to define relationships.</p>}
              {(f.relationships||[]).map((rel,i)=>(
                <div key={i} style={{background:C.ink,border:`1px solid ${C.border}`,borderRadius:10,padding:14,marginBottom:10}}>
                  <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10,marginBottom:10}}>
                    <FG label="With" style={{margin:0}}><Sel val={rel.targetId} set={v=>{const r=[...f.relationships];r[i]={...r[i],targetId:v};setF(p=>({...p,relationships:r}));}}>{chars.filter(c=>c.id!==f.id).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</Sel></FG>
                    <FG label="The nature of it" style={{margin:0}}><Sel val={rel.type} set={v=>{const r=[...f.relationships];r[i]={...r[i],type:v};setF(p=>({...p,relationships:r}));}}>{REL_TYPES.map(t=><option key={t}>{t}</option>)}</Sel></FG>
                  </div>
                  <div style={{display:"flex",gap:8}}><Inp val={rel.desc} set={v=>{const r=[...f.relationships];r[i]={...r[i],desc:v};setF(p=>({...p,relationships:r}));}} ph="The texture of their dynamic..." /><span onClick={()=>setF(p=>({...p,relationships:p.relationships.filter((_,j)=>j!==i)}))} style={{color:C.red,cursor:"pointer",fontSize:20,lineHeight:"38px"}}>×</span></div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── WRITING TAB ── */
function WritingTab({ chaps, chars, world, onSave, toast }) {
  const [selId,setSelId]=useState(null); const [f,setF]=useState(null);
  const [prompt,setPrompt]=useState(""); const [output,setOutput]=useState("");
  const [busy,setBusy]=useState(false); const [showAI,setShowAI]=useState(false);
  const chapsRef=useRef(chaps); useEffect(()=>{chapsRef.current=chaps;},[chaps]);
  useEffect(()=>{const c=chaps.find(x=>x.id===selId);if(c)setF({...c});},[selId]);
  // autosave — never lose work
  useEffect(()=>{ if(!f)return; const saved=chapsRef.current.find(c=>c.id===f.id); if(saved&&JSON.stringify(saved)===JSON.stringify(f))return; const t=setTimeout(()=>onSave(chapsRef.current.map(c=>c.id===f.id?f:c)),900); return ()=>clearTimeout(t); },[f]);
  const newChap=()=>{const c={id:uid(),number:chaps.length+1,title:`Chapter ${chaps.length+1}`,content:"",summary:"",pov:"",location:"",characters:[],seeds:""};onSave([...chaps,c]);setSelId(c.id);setF({...c});};
  const saveF=()=>{if(!f)return;onSave(chaps.map(c=>c.id===f.id?f:c));toast("Saved ✓");};
  const generate=async()=>{if(!prompt.trim())return;setBusy(true);setOutput("");try{const sys=`You are a master novelist writing ${world.genre||"literary"} fiction. Write with vivid prose, authentic dialogue, and emotional depth. Stay consistent with the established world and characters.\n\n${buildCtx(world,chars,chaps)}`;const txt=await callAI(sys,`Write this scene:\n\n${prompt}`);setOutput(txt);}catch(e){toast("Error: "+e.message,"error");}setBusy(false);};
  const appendOut=()=>{if(!output||!f)return;setF(p=>({...p,content:p.content+(p.content?"\n\n":"")+output}));setOutput("");setPrompt("");toast("Added to chapter ✓");};
  return (
    <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
      <PageHdr title="Write" sub={`${chaps.length} chapter${chaps.length!==1?"s":""} · ${chaps.reduce((a,c)=>a+wc(c.content),0).toLocaleString()} words`}>
        <div style={{display:"flex",gap:8}}>
          {f&&<><Btn ghost small onClick={()=>exportChapter(f,chars,world)}>Export Chapter</Btn><Btn primary onClick={saveF}>Save</Btn></>}
          <Btn ghost onClick={newChap}>+ Chapter</Btn>
        </div>
      </PageHdr>
      <div style={{flex:1,overflow:"hidden",display:"flex"}}>
        <div style={{width:230,borderRight:`1px solid ${C.border}`,overflowY:"auto",flexShrink:0,background:C.surface}}>
          <div style={{padding:"14px 16px 8px",fontSize:10,color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic",letterSpacing:1}}>Chapters</div>
          {chaps.length===0&&<div style={{padding:"20px 16px",fontSize:12,color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic",lineHeight:1.8}}>Your first chapter awaits.</div>}
          {chaps.map(c=>{const excerpt=c.content?.trim().slice(0,55);return(
            <div key={c.id} onClick={()=>setSelId(c.id)} style={{padding:"13px 16px",borderBottom:`1px solid ${C.border}`,cursor:"pointer",background:selId===c.id?C.surface2:"transparent",transition:"background .15s"}}>
              <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:4}}>
                <span style={{fontFamily:"Lora,serif",fontStyle:"italic",fontSize:10,color:C.gold}}>Chapter {c.number}</span>
                <span style={{fontSize:10,color:C.text3,fontFamily:"Lora,serif"}}>{wc(c.content).toLocaleString()}w</span>
              </div>
              <div style={{fontSize:13,color:C.text,fontFamily:'"Playfair Display",serif',marginBottom:excerpt?4:0,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{c.title}</div>
              {excerpt&&<div style={{fontSize:11,color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{excerpt}…</div>}
              <span onClick={e=>{e.stopPropagation();onSave(chaps.filter(x=>x.id!==c.id));if(selId===c.id){setSelId(null);setF(null);}toast("Removed");}} style={{color:C.text3,cursor:"pointer",fontSize:14,float:"right"}}>×</span>
            </div>
          );})}
        </div>
        <div style={{flex:1,overflowY:"auto",padding:"28px 40px",background:C.bg}}>
          {!f?(<div style={{textAlign:"center",padding:"80px 40px",color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic",lineHeight:2}}><div style={{fontSize:36,marginBottom:16,color:C.border}}>❧</div><div style={{fontSize:15}}>Select a chapter to open it,<br/>or begin a new one.</div></div>):(
            <div style={{maxWidth:760,margin:"0 auto"}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:24,gap:16}}>
                <div style={{flex:1}}>
                  <div style={{fontFamily:"Lora,serif",fontStyle:"italic",fontSize:11,color:C.gold,marginBottom:6}}>Chapter {f.number}</div>
                  <input value={f.title} onChange={e=>setF(p=>({...p,title:e.target.value}))} style={{background:"none",border:"none",outline:"none",fontFamily:'"Playfair Display",serif',fontSize:26,color:C.text,fontWeight:700,width:"100%",borderBottom:`1px solid ${C.border}`,paddingBottom:8}} placeholder="Chapter title..." />
                </div>
              </div>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:20}}>
                <FG label="Point of view" style={{margin:0}}><Sel val={f.pov} set={v=>setF(p=>({...p,pov:v}))}><option value="">— Omniscient narrator —</option>{chars.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</Sel></FG>
                <FG label="Where we are" style={{margin:0}}><Inp val={f.location} set={v=>setF(p=>({...p,location:v}))} ph="A rain-soaked street, the palace library..." /></FG>
              </div>
              <FG label="Who's in this chapter">
                <div style={{display:"flex",flexWrap:"wrap",gap:7}}>{chars.map(c=>(<span key={c.id} onClick={()=>setF(p=>({...p,characters:p.characters?.includes(c.id)?p.characters.filter(x=>x!==c.id):[...(p.characters||[]),c.id]}))} style={{fontSize:12,cursor:"pointer",padding:"5px 13px",borderRadius:20,border:"1px solid",borderColor:f.characters?.includes(c.id)?C.gold:C.border,color:f.characters?.includes(c.id)?C.goldLight:C.text3,background:f.characters?.includes(c.id)?C.goldFaint:"transparent",fontFamily:"Lora,serif",fontStyle:"italic",transition:"all .2s"}}>{c.icon} {c.name}</span>))}</div>
              </FG>
              <div style={{position:"relative",marginBottom:20}}>
                <div style={{display:"flex",justifyContent:"space-between",marginBottom:8,alignItems:"center"}}>
                  <label style={{...lblSt,marginBottom:0}}>Your writing</label>
                  <span style={{fontSize:11,color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic"}}>{wc(f.content).toLocaleString()} words</span>
                </div>
                <textarea value={f.content||""} onChange={e=>setF(p=>({...p,content:e.target.value}))} placeholder={"The cursor blinks.\n\nWrite the scene, or let the Writing Companion draft it below..."} style={{width:"100%",background:C.ink,border:`1px solid ${C.border}`,borderRadius:10,color:C.text,fontSize:16,padding:"24px 28px",fontFamily:"Georgia,'Times New Roman',serif",lineHeight:2.0,outline:"none",minHeight:360,resize:"vertical"}} onFocus={e=>e.target.style.borderColor=C.gold} onBlur={e=>e.target.style.borderColor=C.border} />
              </div>
              <FG label="Chapter summary (feeds AI context)"><Ta val={f.summary} set={v=>setF(p=>({...p,summary:v}))} ph="What happens in this chapter, briefly..." rows={3} /></FG>
              <div style={{marginTop:8}}>
                <button onClick={()=>setShowAI(p=>!p)} style={{display:"flex",alignItems:"center",gap:10,background:"none",border:"none",cursor:"pointer",color:C.gold,fontFamily:"Lora,serif",fontStyle:"italic",fontSize:13,padding:0,marginBottom:showAI?14:0}}>
                  <span style={{fontSize:10,animation:busy?"pulse 1s infinite":"none",color:C.gold}}>✦</span>
                  Writing Companion
                  <span style={{fontSize:10,color:C.text3}}>{showAI?"▲":"▼"}</span>
                </button>
                {showAI&&(
                  <div style={{background:C.surface,border:`1px solid ${C.borderLight}`,borderRadius:12,padding:20}}>
                    <p style={{fontSize:12,color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic",marginBottom:14,lineHeight:1.7}}>Describe the scene in your own words and let the AI draft it. You decide what stays.</p>
                    <Ta val={prompt} set={setPrompt} ph={`What should happen? (e.g. "The moment ${chars[0]?.name||'the protagonist'} discovers the truth — use subtext, they don't say it directly")`} style={{minHeight:90}} />
                    <div style={{display:"flex",gap:8,marginTop:12}}>
                      <Btn primary onClick={generate} disabled={busy||!prompt.trim()}>{busy?"Writing...":"✦ Write this scene"}</Btn>
                      {output&&<><Btn ghost onClick={appendOut}>↓ Add to chapter</Btn><Btn ghost onClick={()=>setOutput("")}>Clear</Btn></>}
                    </div>
                    {output&&<div style={{marginTop:16,background:C.ink,border:`1px solid ${C.border}`,borderRadius:10,padding:"20px 24px",fontSize:15,lineHeight:2.0,color:C.text2,fontFamily:"Georgia,serif",whiteSpace:"pre-wrap",maxHeight:400,overflowY:"auto"}}>{output}</div>}
                  </div>
                )}
              </div>
              <FG label="Seeds planted in this chapter" style={{marginTop:20}}><Ta val={f.seeds} set={v=>setF(p=>({...p,seeds:v}))} ph="Hints and foreshadowing that need paying off later..." rows={3} /></FG>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── FLOW WRITING TAB ── */
function FlowTab({ world, chars, chaps, onIntegrate, toast }) {
  const [stage, setStage] = useState("writing"); // writing | review | done
  const [raw, setRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [notes, setNotes] = useState("");
  const [showNotes, setShowNotes] = useState(false);
  const [selNew, setSelNew] = useState({});
  const [done, setDone] = useState(null);

  const process = async (revisionNotes) => {
    if (!raw.trim()) return;
    setBusy(true);
    try {
      // Call 1 — polish into professional prose
      const polishSys = `You are a master ghostwriter helping a person who has vivid imagination but limited writing craft. They give you raw, unpolished free-writing — possibly messy, with typos, fragments, or shorthand. Rewrite it into polished, professional, vivid prose. PRESERVE their ideas, plot, characters, and emotional intent exactly — but elevate the craft: sensory detail, natural dialogue, rhythm, show-don't-tell, strong scene-setting. Match the tone of ${world.genre||"their story"}. Keep their voice; don't invent major new plot. Output ONLY the finished prose — no preamble, no notes.

${buildCtx(world, chars, chaps)}`;
      const polishUser = revisionNotes
        ? `The raw writing:\n\n${raw}\n\nThe writer reviewed the previous draft and asked for these changes:\n${revisionNotes}\n\nRewrite the polished prose applying their notes.`
        : `Polish this raw writing into a finished scene:\n\n${raw}`;
      const prose = await callAI(polishSys, polishUser);

      // Call 2 — extract structured story elements
      const known = chars.map(c => c.name).join(", ") || "none";
      const extractSys = `You are a story analyst. Read the scene and extract its elements. Characters already in the story (do NOT list these as new): ${known}. Only list genuinely NEW characters. Return ONLY valid JSON, nothing else:
{"suggestedTitle":"a short evocative chapter title","summary":"1-2 sentence summary","povCharacter":"name of the viewpoint character or empty string","newCharacters":[{"name":"","role":"Protagonist|Antagonist|Supporting|Minor|Mentor|Love Interest","personality":"","motivation":"","appearance":"","flaw":"","status":"alive"}],"existingInvolved":["names of already-known characters present"],"locations":["place names"],"events":["key things that happen"],"themes":["themes touched"]}

${buildCtx(world, chars, chaps)}`;
      const extractTxt = await callAI(extractSys, `Scene:\n\n${prose}`);
      let ex;
      try { ex = JSON.parse(extractTxt.replace(/```json|```/g, "").trim()); }
      catch { ex = { suggestedTitle:`Chapter ${chaps.length+1}`, summary:"", povCharacter:"", newCharacters:[], existingInvolved:[], locations:[], events:[], themes:[] }; }

      setResult({ polishedProse: prose, raw, ...ex });
      const s = {}; (ex.newCharacters||[]).forEach((_,i)=>s[i]=true); setSelNew(s);
      setStage("review"); setShowNotes(false); setNotes("");
    } catch(e) { toast("Error: " + e.message, "error"); }
    setBusy(false);
  };

  const approve = () => {
    const newChars = (result.newCharacters||[]).filter((_,i)=>selNew[i]);
    const chapNum = chaps.length + 1;
    onIntegrate({ ...result, newCharacters: newChars });
    setDone({ title: result.suggestedTitle || `Chapter ${chapNum}`, chapNum, newCharCount: newChars.length, themeCount: (result.themes||[]).length, locations: result.locations||[] });
    setStage("done"); setResult(null);
  };

  const reset = () => { setStage("writing"); setRaw(""); setResult(null); setDone(null); setNotes(""); setShowNotes(false); };

  /* ---- busy overlay ---- */
  if (busy) {
    return (
      <div style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden" }}>
        <PageHdr title="Flow Writing" sub="Shaping your words..." />
        <div style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", flexDirection:"column", gap:18 }}>
          <div style={{ fontSize:36, color:C.gold, animation:"pulse 1.4s infinite" }}>❦</div>
          <div style={{ fontFamily:'"Playfair Display",serif', fontSize:20, color:C.text, fontWeight:600 }}>{stage==="review" ? "Revising with your notes..." : "Crafting your scene..."}</div>
          <div style={{ fontFamily:"Lora,serif", fontStyle:"italic", fontSize:13, color:C.text3, textAlign:"center", lineHeight:1.8, maxWidth:380 }}>The AI is polishing your prose and discovering the characters, places, and events inside it. This takes a few moments.</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden" }}>
      <PageHdr title="Flow Writing" sub="Write freely — the AI turns it into polished prose and files everything away" />
      <div style={{ flex:1, overflowY:"auto" }}>

        {/* ── WRITING STAGE ── */}
        {stage === "writing" && (
          <div style={{ maxWidth:780, margin:"0 auto", padding:"36px 40px" }}>
            <div style={{ textAlign:"center", marginBottom:28 }}>
              <h2 style={{ fontFamily:'"Playfair Display",serif', fontSize:28, color:C.text, fontWeight:700, marginBottom:10 }}>Just write.</h2>
              <p style={{ fontFamily:"Lora,serif", fontStyle:"italic", fontSize:14, color:C.text2, lineHeight:1.8, maxWidth:560, margin:"0 auto" }}>
                Don't worry about grammar, spelling, or how it sounds. Pour out what you imagine — who's there, what happens, how it feels. When you're done, the AI shapes it into professional prose and quietly files away the characters, places, and events it finds.
              </p>
            </div>
            <textarea value={raw} onChange={e=>setRaw(e.target.value)} autoFocus
              placeholder={"so theres this girl, shes really angry at her brother because he lied about their dad... they meet in the old train station at night, its raining. she wants to tell him she knows the truth but shes scared. he shows up late and..."}
              style={{ width:"100%", background:C.ink, border:`1px solid ${C.border}`, borderRadius:12, color:C.text, fontSize:16, padding:"26px 30px", fontFamily:"Georgia,serif", lineHeight:2.0, outline:"none", minHeight:380, resize:"vertical" }}
              onFocus={e=>e.target.style.borderColor=C.gold} onBlur={e=>e.target.style.borderColor=C.border} />
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginTop:16 }}>
              <span style={{ fontSize:12, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic" }}>{wc(raw).toLocaleString()} words</span>
              <Btn primary onClick={()=>process()} disabled={!raw.trim()} style={{ fontSize:14, padding:"12px 26px" }}>✦ Shape this into a scene →</Btn>
            </div>
          </div>
        )}

        {/* ── REVIEW STAGE ── */}
        {stage === "review" && result && (
          <div style={{ maxWidth:1000, margin:"0 auto", padding:"28px 36px" }}>
            <div style={{ display:"grid", gridTemplateColumns:"1.5fr 1fr", gap:24, alignItems:"start" }}>
              {/* polished prose */}
              <div>
                <div style={{ display:"flex", justifyContent:"space-between", alignItems:"baseline", marginBottom:12 }}>
                  <h2 style={{ fontFamily:'"Playfair Display",serif', fontSize:22, color:C.text, fontWeight:700 }}>{result.suggestedTitle||"Your scene"}</h2>
                  <span style={{ fontSize:11, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic" }}>{wc(result.polishedProse).toLocaleString()} words</span>
                </div>
                <div style={{ background:C.ink, border:`1px solid ${C.border}`, borderRadius:12, padding:"28px 32px", fontFamily:"Georgia,serif", fontSize:15.5, lineHeight:2.05, color:C.text, whiteSpace:"pre-wrap", maxHeight:560, overflowY:"auto" }}>
                  {result.polishedProse}
                </div>
              </div>

              {/* extracted elements */}
              <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
                <div style={{ fontFamily:"Lora,serif", fontStyle:"italic", fontSize:13, color:C.gold }}>Here's what we found inside it:</div>

                {(result.newCharacters||[]).length > 0 && (
                  <Card title="New characters" icon="◈" style={{ padding:16 }}>
                    <p style={{ fontSize:11, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic", marginBottom:12, lineHeight:1.6 }}>Uncheck any you don't want added.</p>
                    {result.newCharacters.map((nc, i) => (
                      <div key={i} onClick={()=>setSelNew(p=>({...p,[i]:!p[i]}))} style={{ display:"flex", gap:10, padding:"10px 12px", borderRadius:8, marginBottom:6, cursor:"pointer", background:selNew[i]?C.goldFaint:C.surface2, border:`1px solid ${selNew[i]?C.gold+"40":C.border}` }}>
                        <div style={{ width:16, height:16, borderRadius:4, border:`1.5px solid ${selNew[i]?C.gold:C.text3}`, background:selNew[i]?C.gold:"transparent", flexShrink:0, marginTop:2, display:"flex", alignItems:"center", justifyContent:"center", color:"#0a0806", fontSize:11 }}>{selNew[i]?"✓":""}</div>
                        <div>
                          <div style={{ fontFamily:'"Playfair Display",serif', fontSize:14, color:C.text }}>{nc.name} <span style={{ fontSize:11, color:C.text3, fontStyle:"italic", fontFamily:"Lora,serif" }}>· {nc.role}</span></div>
                          {nc.personality && <div style={{ fontSize:11, color:C.text2, fontFamily:"Lora,serif", marginTop:3, lineHeight:1.5 }}>{nc.personality}</div>}
                          {nc.motivation && <div style={{ fontSize:11, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic", marginTop:3, lineHeight:1.5 }}>Wants: {nc.motivation}</div>}
                        </div>
                      </div>
                    ))}
                  </Card>
                )}

                {(result.existingInvolved||[]).length > 0 && (
                  <Card title="Characters who appear" icon="✦" style={{ padding:16 }}>
                    <div style={{ display:"flex", flexWrap:"wrap", gap:6 }}>
                      {result.existingInvolved.map((n,i)=><span key={i} style={{ fontSize:12, color:C.goldLight, background:C.goldFaint, border:`1px solid ${C.gold}40`, borderRadius:16, padding:"3px 12px", fontFamily:"Lora,serif", fontStyle:"italic" }}>{n}</span>)}
                    </div>
                  </Card>
                )}

                {((result.locations||[]).length > 0 || (result.events||[]).length > 0 || (result.themes||[]).length > 0) && (
                  <Card title="Also captured" icon="◇" style={{ padding:16 }}>
                    {(result.locations||[]).length>0 && <div style={{ marginBottom:10 }}><div style={{ fontSize:10, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic", marginBottom:4 }}>Places</div><div style={{ fontSize:12, color:C.text2, fontFamily:"Lora,serif" }}>{result.locations.join(" · ")}</div></div>}
                    {(result.events||[]).length>0 && <div style={{ marginBottom:10 }}><div style={{ fontSize:10, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic", marginBottom:4 }}>Events</div>{result.events.map((e,i)=><div key={i} style={{ fontSize:12, color:C.text2, fontFamily:"Lora,serif", lineHeight:1.6 }}>• {e}</div>)}</div>}
                    {(result.themes||[]).length>0 && <div><div style={{ fontSize:10, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic", marginBottom:4 }}>Themes</div><div style={{ fontSize:12, color:C.text2, fontFamily:"Lora,serif" }}>{result.themes.join(" · ")}</div></div>}
                  </Card>
                )}

                <div style={{ fontSize:11, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic", lineHeight:1.6, padding:"0 4px" }}>
                  This will become <span style={{ color:C.gold }}>Chapter {chaps.length+1}</span>. Selected characters and themes are added to your story automatically.
                </div>
              </div>
            </div>

            {/* actions */}
            <div style={{ marginTop:24, borderTop:`1px solid ${C.border}`, paddingTop:20 }}>
              {!showNotes ? (
                <div style={{ display:"flex", gap:10, alignItems:"center" }}>
                  <Btn primary onClick={approve} style={{ fontSize:14, padding:"12px 24px" }}>✓ Looks great — add it to my story</Btn>
                  <Btn ghost onClick={()=>setShowNotes(true)}>Add notes & revise</Btn>
                  <Btn ghost onClick={reset} style={{ marginLeft:"auto", color:C.text3 }}>Start over</Btn>
                </div>
              ) : (
                <div style={{ background:C.surface, border:`1px solid ${C.borderLight}`, borderRadius:12, padding:18 }}>
                  <label style={lblSt}>Tell the AI what to change</label>
                  <Ta val={notes} set={setNotes} ph="e.g. 'make her angrier', 'the brother should be older', 'add more rain and tension', 'cut the dialogue at the end'..." rows={3} />
                  <div style={{ display:"flex", gap:10, marginTop:12 }}>
                    <Btn primary onClick={()=>process(notes)} disabled={!notes.trim()}>↻ Revise with these notes</Btn>
                    <Btn ghost onClick={()=>setShowNotes(false)}>Cancel</Btn>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── DONE STAGE ── */}
        {stage === "done" && done && (
          <div style={{ maxWidth:540, margin:"0 auto", padding:"60px 40px", textAlign:"center" }}>
            <div style={{ fontSize:44, color:C.green, marginBottom:20 }}>✓</div>
            <h2 style={{ fontFamily:'"Playfair Display",serif', fontSize:24, color:C.text, fontWeight:700, marginBottom:14 }}>It's all filed away.</h2>
            <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:"22px 26px", textAlign:"left", marginBottom:24 }}>
              <div style={{ fontSize:14, color:C.text2, fontFamily:"Lora,serif", lineHeight:2 }}>
                <div>📖 <span style={{ color:C.text }}>"{done.title}"</span> saved as Chapter {done.chapNum}</div>
                {done.newCharCount>0 && <div>◈ {done.newCharCount} new character{done.newCharCount!==1?"s":""} added to your cast</div>}
                {done.themeCount>0 && <div>💡 {done.themeCount} theme{done.themeCount!==1?"s":""} woven into your world</div>}
                {done.locations.length>0 && <div>◇ {done.locations.length} location{done.locations.length!==1?"s":""} noted</div>}
              </div>
            </div>
            <p style={{ fontSize:13, color:C.text3, fontFamily:"Lora,serif", fontStyle:"italic", marginBottom:24, lineHeight:1.7 }}>Find it polished and editable in the Chapters tab, with everyone added to Characters and mapped in your Story Map.</p>
            <Btn primary onClick={reset} style={{ fontSize:14, padding:"12px 28px" }}>✦ Write another scene</Btn>
          </div>
        )}

      </div>
    </div>
  );
}

/* ── STORY MAP (GRAPH) ── */
function GraphTab({ chars, chaps, world }) {
  const ref = useRef(null);
  useEffect(()=>{
    if(!ref.current)return;
    const W=ref.current.clientWidth||900,H=ref.current.clientHeight||600;
    const nodes=[],links=[];
    chars.forEach(c=>nodes.push({id:c.id,t:"char",label:c.name,sub:c.role,icon:c.icon||"◈"}));
    chaps.forEach(c=>nodes.push({id:c.id,t:"chap",label:`Chapter ${c.number}`,sub:c.title}));
    (world.themes||[]).filter(Boolean).forEach(t=>nodes.push({id:"th_"+t,t:"theme",label:t}));
    chars.forEach(c=>(c.relationships||[]).forEach(r=>{if(chars.find(x=>x.id===r.targetId))links.push({source:c.id,target:r.targetId,label:r.type,lt:"rel"});}));
    chaps.forEach(c=>(c.characters||[]).forEach(cid=>{if(chars.find(x=>x.id===cid))links.push({source:cid,target:c.id,label:"",lt:"app"});}));
    const svg=d3.select(ref.current);svg.selectAll("*").remove();
    const g=svg.append("g");svg.call(d3.zoom().scaleExtent([0.1,5]).on("zoom",ev=>g.attr("transform",ev.transform)));
    const defs=svg.append("defs");
    [["rel","#c89830"],["app","#8b5060"]].forEach(([id,col])=>{defs.append("marker").attr("id","arr_"+id).attr("viewBox","0 -4 10 8").attr("refX",30).attr("refY",0).attr("markerWidth",6).attr("markerHeight",6).attr("orient","auto").append("path").attr("d","M0,-4L10,0L0,4").attr("fill",col+"80");});
    const d3l=links.map(l=>({source:l.source,target:l.target,label:l.label,lt:l.lt}));
    const sim=d3.forceSimulation(nodes).force("link",d3.forceLink(d3l).id(d=>d.id).distance(170)).force("charge",d3.forceManyBody().strength(-600)).force("center",d3.forceCenter(W/2,H/2)).force("collide",d3.forceCollide(60));
    const COL={char:"#c89830",chap:"#8b5060",theme:"#4a7c4e"};const R=d=>d.t==="char"?26:d.t==="chap"?20:14;
    const line=g.append("g").selectAll("line").data(d3l).join("line").attr("stroke",d=>d.lt==="rel"?"#c8983040":"#8b506040").attr("stroke-width",1.5).attr("stroke-dasharray",d=>d.lt==="app"?"5,3":null).attr("marker-end",d=>`url(#arr_${d.lt})`);
    const edgeTxt=g.append("g").selectAll("text").data(d3l.filter(l=>l.label)).join("text").attr("font-size",9).attr("fill","#54473a").attr("text-anchor","middle").attr("font-family","Lora,serif").attr("font-style","italic").text(d=>d.label);
    const ng=g.append("g").selectAll("g").data(nodes).join("g").style("cursor","grab").call(d3.drag().on("start",(ev,d)=>{if(!ev.active)sim.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;}).on("drag",(ev,d)=>{d.fx=ev.x;d.fy=ev.y;}).on("end",(ev,d)=>{if(!ev.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}));
    ng.append("circle").attr("r",R).attr("fill",d=>COL[d.t]+"18").attr("stroke",d=>COL[d.t]).attr("stroke-width",d=>d.t==="char"?2:1.5);
    ng.append("text").attr("text-anchor","middle").attr("dy","0.35em").attr("font-size",d=>d.t==="char"?14:10).attr("fill",d=>COL[d.t]).attr("font-family","Lora,serif").text(d=>d.icon||"●");
    ng.append("text").attr("text-anchor","middle").attr("dy",d=>R(d)+16).attr("font-size",11).attr("fill",d=>COL[d.t]).attr("font-family",'"Playfair Display",serif').text(d=>d.label.length>16?d.label.slice(0,16)+"…":d.label);
    ng.append("text").attr("text-anchor","middle").attr("dy",d=>R(d)+28).attr("font-size",9).attr("fill","#54473a").attr("font-family","Lora,serif").attr("font-style","italic").text(d=>(d.sub||"").slice(0,18));
    sim.on("tick",()=>{line.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y).attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);edgeTxt.attr("x",d=>(d.source.x+d.target.x)/2).attr("y",d=>(d.source.y+d.target.y)/2);ng.attr("transform",d=>`translate(${d.x},${d.y})`);});
    return()=>sim.stop();
  },[chars,chaps,world]);
  const total=chars.length+chaps.length+(world.themes||[]).filter(Boolean).length;
  return (
    <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
      <PageHdr title="Story Map" sub="The web of connections in your story">
        <div style={{display:"flex",gap:16,alignItems:"center"}}>{[["#c89830","Characters"],["#8b5060","Chapters"],["#4a7c4e","Themes"]].map(([col,l])=>(<div key={l} style={{display:"flex",alignItems:"center",gap:6,fontSize:11,color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic"}}><div style={{width:9,height:9,borderRadius:"50%",background:col+"25",border:`1.5px solid ${col}`}}/>{l}</div>))}</div>
      </PageHdr>
      {total===0?(<div style={{flex:1,display:"flex",alignItems:"center",justifyContent:"center",flexDirection:"column",gap:14,color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic"}}><div style={{fontSize:40,color:C.border}}>◎</div><div style={{fontSize:14,textAlign:"center",lineHeight:1.8}}>Add characters and chapters.<br/>The map will build itself.</div></div>):(
        <svg ref={ref} style={{flex:1,background:C.bg,cursor:"grab"}} />
      )}
    </div>
  );
}

/* ── STORY CHECK ── */
function CheckTab({ chaps, chars, world, toast }) {
  const [sel,setSel]=useState(""); const [busy,setBusy]=useState(false); const [res,setRes]=useState(null);
  const run=async()=>{const chap=chaps.find(c=>c.id===sel);if(!chap?.content?.trim()){toast("This chapter has no content yet","error");return;}setBusy(true);setRes(null);try{const sys=`You are a meticulous novel continuity editor. Return ONLY valid JSON:\n{"issues":[{"type":"CHARACTER|WORLD|LOGIC|TIMELINE|TONE","desc":"specific description","sev":"HIGH|MEDIUM|LOW"}],"praise":["what works well"]}\n\n${buildCtx(world,chars,chaps)}`;const txt=await callAI(sys,`Review this chapter:\n\nTitle: ${chap.title}\n\n${chap.content}`);try{setRes(JSON.parse(txt.replace(/```json|```/g,"").trim()));}catch{setRes({raw:txt,issues:[],praise:[]});}}catch(e){toast("Error: "+e.message,"error");}setBusy(false);};
  const sev={HIGH:{bg:C.redFaint,border:C.red,color:C.red,label:"Needs attention"},MEDIUM:{bg:`${C.gold}12`,border:C.gold,color:C.gold,label:"Worth a look"},LOW:{bg:"#1a1a2a",border:"#7a7acd",color:"#7a7acd",label:"Minor note"}};
  return (
    <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>
      <PageHdr title="Story Check" sub="Let the AI read your work against the full story bible" />
      <div style={{flex:1,overflowY:"auto",padding:"28px 30px"}}>
        <Card title="Choose a chapter to review" icon="◇" style={{marginBottom:24}}>
          <p style={{fontSize:12,color:C.text3,marginBottom:14,fontFamily:"Lora,serif",fontStyle:"italic",lineHeight:1.8}}>The AI will compare the chapter against your world bible, every character profile, and all previous chapters — and surface everything that doesn't add up.</p>
          <div style={{display:"flex",gap:12,alignItems:"flex-end"}}><div style={{flex:1}}><label style={lblSt}>Chapter</label><Sel val={sel} set={setSel}><option value="">— Select a chapter —</option>{chaps.map(c=><option key={c.id} value={c.id}>Chapter {c.number}: {c.title}</option>)}</Sel></div><Btn primary onClick={run} disabled={busy||!sel} style={{whiteSpace:"nowrap"}}>{busy?"Reading...":"◇ Run Check"}</Btn></div>
        </Card>
        {res&&(
          <>
            {res.raw&&<div style={{background:C.ink,border:`1px solid ${C.border}`,borderRadius:10,padding:16,fontSize:12,color:C.text2,lineHeight:1.7,marginBottom:20,fontFamily:"Lora,serif",whiteSpace:"pre-wrap"}}>{res.raw}</div>}
            <Card icon={res.issues?.length?"⚠":"✓"} title={res.issues?.length?`${res.issues.length} issue${res.issues.length!==1?"s":""} found`:"All clear"} style={{marginBottom:16,borderColor:res.issues?.length?`${C.red}40`:`${C.green}40`}}>
              {res.issues?.length===0&&<p style={{fontSize:13,color:"#5a9960",fontFamily:"Lora,serif",fontStyle:"italic",lineHeight:1.7}}>The chapter holds up. Nothing contradicts the world or the characters you've built.</p>}
              {(res.issues||[]).map((issue,i)=>{const s=sev[issue.sev]||sev.LOW;return(<div key={i} style={{padding:"13px 16px",borderRadius:10,marginBottom:8,borderLeft:`3px solid ${s.border}`,background:s.bg}}><div style={{fontSize:10,fontFamily:"Lora,serif",fontStyle:"italic",color:s.color,marginBottom:5}}>{issue.type} — {s.label}</div><div style={{fontSize:13,color:C.text2,lineHeight:1.7,fontFamily:"Lora,serif"}}>{issue.desc}</div></div>);})}
            </Card>
            {res.praise?.length>0&&(<Card title="What's working well" icon="✦">{res.praise.map((p,i)=><div key={i} style={{fontSize:13,color:C.text2,padding:"8px 0",borderBottom:i<res.praise.length-1?`1px solid ${C.border}`:"none",lineHeight:1.7,fontFamily:"Lora,serif",fontStyle:"italic"}}>✦ {p}</div>)}</Card>)}
          </>
        )}
        {chaps.length===0&&<div style={{textAlign:"center",padding:"60px",color:C.text3,fontFamily:"Lora,serif",fontStyle:"italic",fontSize:14,lineHeight:1.8}}>Write your chapters first,<br/>then return here to check them.</div>}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════
   ROOT APP
═══════════════════════════════════════════ */
export default function App() {
  const [projects, setProjects] = useState([]);
  const [currentId, setCurrentId] = useState(null);
  const [tab, setTab] = useState("world");
  const [world, setWorld] = useState(defaultWorld());
  const [chars, setChars] = useState([]);
  const [chaps, setChaps] = useState([]);
  const [toast, setToastState] = useState(null);

  useEffect(() => { loadStudio().then(s => setProjects(s.projects||[])); }, []);

  const showToast = (msg, type="success") => { setToastState({msg,type}); setTimeout(()=>setToastState(null),3200); };

  const syncMeta = (id, w, cs, chs) => {
    const meta = { id, title:w.title||"Untitled", genre:w.genre||"", updatedAt:Date.now(), stats:{ words:chs.reduce((a,c)=>a+wc(c.content),0), chapters:chs.length, chars:cs.length } };
    return meta;
  };

  const handleCreate = (title, genre) => {
    const id = uid();
    const paletteIdx = ~~(Math.random() * COVER_PALETTES.length);
    const w = { ...defaultWorld(), title, genre };
    const proj = { id, title, genre, paletteIdx, createdAt:Date.now(), updatedAt:Date.now(), stats:{words:0,chapters:0,chars:0} };
    const updated = [...projects, proj];
    setProjects(updated);
    saveStudio({ projects: updated });
    saveProject(id, { world:w, chars:[], chaps:[] });
    setWorld(w); setChars([]); setChaps([]);
    setCurrentId(id); setTab("flow");
    showToast("Story created ✓");
  };

  const handleOpen = async (proj) => {
    const data = await loadProject(proj.id);
    setWorld(data?.world || { ...defaultWorld(), title:proj.title, genre:proj.genre });
    setChars(data?.chars || []);
    setChaps(data?.chaps || []);
    setCurrentId(proj.id); setTab("flow");
  };

  const handleDelete = async (id) => {
    await deleteProject(id);
    const updated = projects.filter(p => p.id !== id);
    setProjects(updated); saveStudio({ projects: updated });
    showToast("Story deleted");
  };

  const backToStudio = async () => {
    if (currentId) {
      await saveProject(currentId, { world, chars, chaps });
      const updated = projects.map(p => p.id===currentId ? { ...p, ...syncMeta(currentId,world,chars,chaps) } : p);
      setProjects(updated); saveStudio({ projects: updated });
    }
    setCurrentId(null);
  };

  // Save functions — persist to project store + update studio meta
  const saveWorld = async w => {
    setWorld(w); await saveProject(currentId, { world:w, chars, chaps });
    const updated = projects.map(p => p.id===currentId ? { ...p, title:w.title||p.title, genre:w.genre||p.genre, updatedAt:Date.now() } : p);
    setProjects(updated); saveStudio({ projects: updated });
  };
  const saveChars = async c => {
    setChars(c); await saveProject(currentId, { world, chars:c, chaps });
    const updated = projects.map(p => p.id===currentId ? { ...p, updatedAt:Date.now(), stats:{...p.stats, chars:c.length} } : p);
    setProjects(updated); saveStudio({ projects: updated });
  };
  const saveChaps = async c => {
    setChaps(c); await saveProject(currentId, { world, chars, chaps:c });
    const updated = projects.map(p => p.id===currentId ? { ...p, updatedAt:Date.now(), stats:{...p.stats, chapters:c.length, words:c.reduce((a,ch)=>a+wc(ch.content),0)} } : p);
    setProjects(updated); saveStudio({ projects: updated });
  };

  // Flow Writing integration — files polished prose + extracted elements everywhere
  const handleFlowIntegrate = async (data) => {
    let cs = [...chars]; const addedIds = [];
    (data.newCharacters||[]).forEach(nc => {
      if (!nc.name) return;
      if (cs.some(c => c.name.toLowerCase() === nc.name.toLowerCase())) return;
      const id = uid();
      cs.push({ id, name:nc.name, role:nc.role||"Supporting", icon:CICONS[~~(Math.random()*CICONS.length)], age:"", appearance:nc.appearance||"", personality:nc.personality||"", backstory:"", motivation:nc.motivation||"", flaw:nc.flaw||"", arc:"", status:nc.status||"alive", relationships:[] });
      addedIds.push(id);
    });
    const findId = n => cs.find(c => c.name.toLowerCase() === (n||"").toLowerCase())?.id;
    const povId = findId(data.povCharacter) || "";
    const involved = [...new Set([ ...(data.existingInvolved||[]).map(findId).filter(Boolean), ...addedIds ])];
    const summary = (data.summary||"") + ((data.events||[]).length ? `\n\nKey events: ${data.events.join("; ")}` : "");
    const chap = { id:uid(), number:chaps.length+1, title:data.suggestedTitle||`Chapter ${chaps.length+1}`, content:data.polishedProse||"", summary, pov:povId, location:(data.locations||[])[0]||"", characters:involved, seeds:"" };
    const chs = [...chaps, chap];
    const themes = [...(world.themes||[])];
    (data.themes||[]).forEach(t => { if (t && !themes.some(x=>x.toLowerCase()===t.toLowerCase())) themes.push(t); });
    const w = { ...world, themes };
    setChars(cs); setChaps(chs); setWorld(w);
    await saveProject(currentId, { world:w, chars:cs, chaps:chs });
    const updated = projects.map(p => p.id===currentId ? { ...p, updatedAt:Date.now(), stats:{ words:chs.reduce((a,c)=>a+wc(c.content),0), chapters:chs.length, chars:cs.length } } : p);
    setProjects(updated); saveStudio({ projects: updated });
  };

  const stats = { chars:chars.length, chaps:chaps.length, words:chaps.reduce((a,c)=>a+wc(c.content),0) };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&family=Lora:ital,wght@0,400;0,500;1,400;1,500&display=swap');
        * { box-sizing:border-box; margin:0; padding:0; }
        ::-webkit-scrollbar { width:4px; }
        ::-webkit-scrollbar-track { background:transparent; }
        ::-webkit-scrollbar-thumb { background:#2a2016; border-radius:4px; }
        select option { background:#151009; color:#e8dcc8; }
        @keyframes fadeUp { from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)} }
        @keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.2} }
      `}</style>

      {!currentId ? (
        <Studio projects={projects} onCreate={handleCreate} onOpen={handleOpen} onDelete={handleDelete} onImport={async (bundle)=>{ await importAllData(bundle); const s = await loadStudio(); setProjects(s.projects||[]); showToast(`Restored ${(s.projects||[]).length} project${(s.projects||[]).length!==1?"s":""} ✓`); }} toast={showToast} />
      ) : (
        <div style={{ display:"flex", height:"100vh", background:C.bg, color:C.text, overflow:"hidden", fontFamily:"Lora,Georgia,serif" }}>
          <Sidebar tab={tab} setTab={setTab} world={world} stats={stats} chars={chars} chaps={chaps} toast={showToast} onBackToStudio={backToStudio} />
          <main style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden" }}>
            {tab==="flow" && <FlowTab world={world} chars={chars} chaps={chaps} onIntegrate={handleFlowIntegrate} toast={showToast} />}
            {tab==="world" && <WorldTab world={world} onSave={saveWorld} toast={showToast} />}
            {tab==="chars" && <CharactersTab chars={chars} onSave={saveChars} toast={showToast} />}
            {tab==="write" && <WritingTab chaps={chaps} chars={chars} world={world} onSave={saveChaps} toast={showToast} />}
            {tab==="graph" && <GraphTab chars={chars} chaps={chaps} world={world} />}
            {tab==="check" && <CheckTab chaps={chaps} chars={chars} world={world} toast={showToast} />}
          </main>
        </div>
      )}

      {toast && (
        <div style={{ position:"fixed", bottom:26, right:26, padding:"12px 20px", borderRadius:10, fontSize:13, zIndex:999, background:C.surface2, border:`1px solid ${toast.type==="error"?C.red+"50":C.green+"50"}`, color:toast.type==="error"?C.red:"#5a9960", fontFamily:"Lora,serif", fontStyle:"italic", animation:"fadeUp .25s ease" }}>
          {toast.msg}
        </div>
      )}
    </>
  );
}
