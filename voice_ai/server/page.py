"""Single-page demo UI — dark modern minimalist theme.

Design language: deep-zinc canvas with a soft violet glow, hairline
borders, a single accent color, Inter/system typography and quiet
micro-interactions (Linear/Vercel school). Every feature stays
self-explanatory: talk, type, or click an example; the result card says
plainly what was heard, understood and replied; the teach panel closes
the learning loop.

Audio is captured with AudioContext and encoded to 16 kHz mono PCM WAV
client-side — the server needs no ffmpeg. (The ScriptProcessorNode is
held in a module variable: browsers garbage-collect it mid-recording
otherwise, which silently kills the mic.)
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Voice AI Assistant</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#09090b;--card:#101014;--card2:#141419;--line:rgba(255,255,255,.08);
--line2:rgba(255,255,255,.14);--ink:#fafafa;--dim:#8f8f98;--dim2:#6b6b74;
--violet:#8b5cf6;--teal:#2dd4bf;--amber:#f59e0b;--rose:#fb7185;
--emerald:#34d399}
*{box-sizing:border-box}
::selection{background:rgba(139,92,246,.35)}
body{margin:0;color:var(--ink);background:var(--bg);
background-image:radial-gradient(640px 320px at 50% -60px,
rgba(139,92,246,.16),transparent 70%);
font:15px/1.6 Inter,"Segoe UI Variable","Segoe UI",system-ui,sans-serif;
-webkit-font-smoothing:antialiased;
display:flex;justify-content:center;min-height:100vh}
main{width:100%;max-width:640px;padding:28px 20px 48px;display:flex;
flex-direction:column;gap:14px}
.card{background:var(--card);border:1px solid var(--line);
border-radius:16px}

header{display:flex;justify-content:space-between;align-items:center;
padding:14px 18px}
header h1{font-size:15px;margin:0;font-weight:600;letter-spacing:-.01em;
display:flex;align-items:center;gap:9px}
header h1::before{content:"";width:8px;height:8px;border-radius:3px;
background:linear-gradient(135deg,var(--violet),#6366f1)}
#engine{font:11px/1 ui-monospace,Consolas,monospace;color:var(--dim);
border:1px solid var(--line);border-radius:999px;padding:5px 11px;
background:var(--card2)}

.steps{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
@media(max-width:560px){.steps{grid-template-columns:1fr}}
.step{padding:12px 14px}
.step b{display:flex;align-items:center;gap:7px;font-size:12px;
font-weight:600;letter-spacing:.02em;margin-bottom:3px}
.step b::before{content:"";width:6px;height:6px;border-radius:50%;
background:var(--dot)}
.step span{font-size:12.5px;color:var(--dim)}
.s1{--dot:var(--teal)}.s2{--dot:var(--violet)}.s3{--dot:var(--amber)}

.micwrap{text-align:center;padding:26px 0 6px}
#rec{width:132px;height:132px;border-radius:50%;border:0;cursor:pointer;
font-family:inherit;color:#fff;font-weight:600;font-size:14.5px;
letter-spacing:.02em;
background:linear-gradient(135deg,#8b5cf6,#6366f1);
box-shadow:inset 0 1px 0 rgba(255,255,255,.18),
0 20px 50px -16px rgba(139,92,246,.55);
transition:transform .18s ease,box-shadow .18s ease}
#rec:hover{transform:scale(1.03)}
#rec:active{transform:scale(.98)}
#rec.on{background:linear-gradient(135deg,#fb7185,#f43f5e);
animation:ring 1.5s ease-out infinite}
@keyframes ring{0%{box-shadow:inset 0 1px 0 rgba(255,255,255,.2),
0 0 0 0 rgba(244,63,94,.45)}100%{box-shadow:inset 0 1px 0
rgba(255,255,255,.2),0 0 0 22px rgba(244,63,94,0)}}
#hint{color:var(--dim2);font-size:12.5px;margin-top:14px}
#hint kbd{font:11px ui-monospace,Consolas,monospace;color:var(--dim);
background:var(--card2);border:1px solid var(--line2);border-radius:6px;
padding:2px 7px}
#status{min-height:20px;font-size:13px;text-align:center;color:var(--dim)}
#status.err{color:var(--rose)}

.label{font-size:10.5px;font-weight:600;letter-spacing:.14em;
text-transform:uppercase;color:var(--dim2);margin:0 0 9px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:8px;
border:1px solid var(--line);border-radius:999px;padding:7px 14px;
font-family:inherit;font-size:12.5px;color:var(--ink);cursor:pointer;
background:var(--card);transition:border-color .15s ease,transform .15s ease}
.chip::before{content:"";width:6px;height:6px;border-radius:50%;
background:var(--dot)}
.chip:hover{border-color:rgba(139,92,246,.5);transform:translateY(-1px)}
.c1{--dot:var(--rose)}.c2{--dot:var(--teal)}.c3{--dot:var(--amber)}
.c4{--dot:var(--violet)}.c5{--dot:#60a5fa}.c6{--dot:var(--emerald)}

.typerow{display:flex;gap:10px;padding:14px}
#typetext{flex:1;font-family:inherit;font-size:14px;color:var(--ink);
background:var(--bg);border:1px solid var(--line2);
border-radius:11px;padding:11px 14px;outline:none;
transition:border-color .15s ease,box-shadow .15s ease}
#typetext::placeholder{color:var(--dim2)}
#typetext:focus{border-color:rgba(139,92,246,.65);
box-shadow:0 0 0 3px rgba(139,92,246,.15)}
#typego{font-family:inherit;font-weight:600;font-size:13px;color:#fff;
background:linear-gradient(135deg,#8b5cf6,#6366f1);border:0;
border-radius:11px;padding:11px 20px;cursor:pointer;
box-shadow:0 8px 24px -10px rgba(139,92,246,.6);
transition:filter .15s ease,transform .15s ease}
#typego:hover{filter:brightness(1.1)}
#typego:active{transform:translateY(1px)}

.result{padding:20px;display:none}
.result .row{margin:13px 0}
.result .row:first-child{margin-top:0}
.result .who{font-size:10.5px;font-weight:600;letter-spacing:.14em;
text-transform:uppercase;color:var(--dim2);display:block;margin-bottom:4px}
.result .heard{font-size:16px}
.result .fixed{font-size:14px;color:var(--emerald);font-weight:500}
.result #intent{font-size:14px;color:var(--dim)}
.result .reply{font-size:16px;font-weight:500}
.result .meta{font-size:11.5px;color:var(--dim2);margin-top:14px}
#note{display:none;color:var(--amber);font-size:12.5px;margin-top:12px;
padding:10px 13px;border:1px solid rgba(245,158,11,.25);
background:rgba(245,158,11,.07);border-radius:10px}
#play{font-family:inherit;font-size:12.5px;font-weight:500;color:var(--ink);
background:var(--card2);border:1px solid var(--line2);border-radius:9px;
padding:7px 14px;cursor:pointer;margin-top:12px;
transition:border-color .15s ease}
#play:hover{border-color:rgba(139,92,246,.5)}

.teach{padding:18px 20px;display:none;flex-direction:column;gap:10px}
.teach .t{font-size:13px;font-weight:600}
.teach .t span{color:var(--dim);font-weight:400}
.teachrow{display:flex;gap:10px}
#fbtext{flex:1;font-family:inherit;font-size:14px;color:var(--ink);
background:var(--bg);border:1px solid var(--line2);
border-radius:11px;padding:11px 14px;outline:none;
transition:border-color .15s ease,box-shadow .15s ease}
#fbtext::placeholder{color:var(--dim2)}
#fbtext:focus{border-color:rgba(139,92,246,.65);
box-shadow:0 0 0 3px rgba(139,92,246,.15)}
#send{font-family:inherit;font-weight:600;font-size:13px;color:#fff;
background:linear-gradient(135deg,#8b5cf6,#6366f1);border:0;
border-radius:11px;padding:11px 20px;cursor:pointer;
box-shadow:0 8px 24px -10px rgba(139,92,246,.6);
transition:filter .15s ease,transform .15s ease}
#send:hover{filter:brightness(1.1)}
#send:active{transform:translateY(1px)}
#send:disabled{opacity:.5}
#fbres{font-size:12.5px;color:var(--dim);min-height:18px}

footer{margin-top:4px;text-align:center;color:var(--dim2);font-size:11.5px;
font-variant-numeric:tabular-nums}
</style></head><body>
<main>
  <header class="card">
    <h1>Voice AI Assistant</h1>
    <span id="engine">…</span>
  </header>

  <div class="steps">
    <div class="card step s1"><b>1 · Talk</b>
      <span>tap the mic, speak, tap again — or type below</span></div>
    <div class="card step s2"><b>2 · Understand</b>
      <span>it detects the language and fixes its known mistakes</span></div>
    <div class="card step s3"><b>3 · Teach</b>
      <span>correct it once and it never repeats the mistake</span></div>
  </div>

  <div class="micwrap">
    <button id="rec" aria-label="start recording">TAP TO TALK</button>
    <div id="hint">press <kbd>space</kbd> to start — press again to stop
      · no mic? type below</div>
  </div>
  <div id="status"></div>

  <section>
    <p class="label">Try saying — click one</p>
    <div class="chips">
      <button class="chip c1">what time is it</button>
      <button class="chip c2">what is twelve plus thirty</button>
      <button class="chip c3">set a timer for five minutes</button>
      <button class="chip c4">note buy milk tomorrow</button>
      <button class="chip c5">i will prepone the meeting</button>
      <button class="chip c1">नमस्ते आप कैसे हो</button>
      <button class="chip c6">এখন কয়টা বাজে</button>
    </div>
  </section>

  <section class="card">
    <div class="typerow">
      <input id="typetext" placeholder="Type a command — e.g. what time is it">
      <button id="typego">Go →</button>
    </div>
  </section>

  <div class="result card" id="result">
    <div class="row"><span class="who">You said</span>
      <div class="heard" id="heard"></div></div>
    <div class="row" id="fixedrow" style="display:none">
      <span class="who">✨ Learned fix</span>
      <div class="fixed" id="fixed"></div></div>
    <div class="row"><span class="who">Understood as</span>
      <div id="intent"></div></div>
    <div class="row"><span class="who">It replied</span>
      <div class="reply" id="reply"></div>
      <button id="play" style="display:none">▶ Hear it</button></div>
    <div class="meta" id="rmeta"></div>
    <div id="note"></div>
  </div>

  <div class="teach card" id="teach">
    <div class="t">Misheard? <span>Type what you actually said — it learns
      and won't repeat the mistake.</span></div>
    <div class="teachrow">
      <input id="fbtext" placeholder="what you really said…">
      <button id="send">Teach</button>
    </div>
    <div id="fbres"></div>
  </div>

  <footer id="stats">connecting…</footer>
</main>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",
">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const DEMO=new URLSearchParams(location.search); // ?demo=&teach= for captures
let last=null, recState="idle", stream=null, ctx=null, processor=null,
    chunks=[], tick=null, audio=null;

// ---- footer stats -------------------------------------------------- //
async function poll(){
  try{
    const s=await (await fetch("/api/state")).json();
    $("engine").textContent=s.engine.asr+" · "+s.engine.tts;
    const acc=(s.learning.accuracy||{}).accuracy;
    const st=s.stages||{}, tot=st["pipeline.total_ms"];
    let stats=s.utterances+" commands handled";
    if(acc!=null)stats+=" · "+(100*acc).toFixed(0)+"% accuracy";
    if(tot)stats+=" · answered in ~"+tot.p50.toFixed(0)+" ms";
    stats+=" · "+(s.learning.active||0)+" things learned";
    $("stats").textContent=stats;
  }catch(e){$("stats").textContent="server offline — is it running?"}
}
poll(); setInterval(poll,3000);

// ---- example chips fill the typer ---------------------------------- //
document.querySelectorAll(".chip").forEach(ch=>{
  ch.onclick=()=>{$("typetext").value=ch.textContent;
    $("typetext").focus();sendText()};
});

// ---- talk: click (or press space) to start, again to stop ---------- //
$("rec").onclick=toggle;
document.addEventListener("keydown",e=>{
  if(e.code!=="Space")return;
  if(document.activeElement===$("fbtext")
     ||document.activeElement===$("typetext"))return;
  e.preventDefault();
  if(e.repeat)return;              // holding space must not spam-toggle
  toggle();
});
async function toggle(){
  if(recState==="recording")return stop();
  if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){
    return err("mic needs a secure origin — open http://localhost:8080 (or type below)");
  }
  try{
    stream=await navigator.mediaDevices.getUserMedia({audio:true});
    ctx=new (window.AudioContext||window.webkitAudioContext)();
    const src=ctx.createMediaStreamSource(stream);
    processor=ctx.createScriptProcessor(4096,1,1);   // kept referenced!
    chunks=[];
    processor.onaudioprocess=e=>{
      if(recState==="recording")
        chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    };
    src.connect(processor);processor.connect(ctx.destination);
    recState="recording";
    $("rec").classList.add("on");$("rec").textContent="● LISTENING — TAP TO STOP";
    $("hint").textContent="speak now — tap the button when done";
    $("status").className="";$("status").textContent="";
    const t0=Date.now();tick=setInterval(()=>{
      $("status").textContent="recording… "+((Date.now()-t0)/1000).toFixed(1)+" s";
    },100);
  }catch(e){err("mic blocked: "+e.message+" — you can type instead ↓")}
}
async function stop(){
  recState="idle";clearInterval(tick);
  $("rec").classList.remove("on");$("rec").textContent="TAP TO TALK";
  $("hint").innerHTML='press <kbd>space</kbd> to start — press again to stop · no mic? type below';
  $("status").textContent="thinking…";
  try{stream&&stream.getTracks().forEach(t=>t.stop())}catch(e){}
  const rate=ctx?ctx.sampleRate:48000;
  try{processor&&processor.disconnect()}catch(e){}
  try{ctx&&ctx.close()}catch(e){}
  const total=chunks.reduce((a,c)=>a+c.length,0);
  if(total<8000){err("too short — speak a full sentence, then stop");return}
  const all=new Float32Array(total);let o=0;
  for(const c of chunks){all.set(c,o);o+=c.length}
  try{
    const r=await fetch("/transcribe?session=web&audio=1",
      {method:"POST",headers:{"Content-Type":"audio/wav"},body:wav16k(all,rate)});
    show(await r.json());
  }catch(e){err("server unreachable")}
}
function wav16k(buf,from){
  const ratio=from/16000,n=Math.floor(buf.length/ratio);
  const out=new Float32Array(n);
  for(let i=0;i<n;i++){const p=i*ratio,i0=Math.floor(p);
    const a=buf[i0]||0,b=buf[i0+1]||a;out[i]=a+(b-a)*(p-i0)}
  const v=new DataView(new ArrayBuffer(44+n*2));
  const ws=(o,s)=>{for(let i=0;i<s.length;i++)v.setUint8(o+i,s.charCodeAt(i))};
  ws(0,"RIFF");v.setUint32(4,36+n*2,true);ws(8,"WAVE");ws(12,"fmt ");
  v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);
  v.setUint32(24,16000,true);v.setUint32(28,32000,true);v.setUint16(32,2,true);
  v.setUint16(34,16,true);ws(36,"data");v.setUint32(40,n*2,true);
  for(let i=0;i<n;i++){const s=Math.max(-1,Math.min(1,out[i]));
    v.setInt16(44+i*2,s<0?s*32768:s*32767,true)}
  return new Blob([v],{type:"audio/wav"});
}

// ---- type mode ------------------------------------------------------ //
$("typego").onclick=sendText;
$("typetext").addEventListener("keydown",e=>{
  if(e.key==="Enter")sendText();
});
async function sendText(){
  const text=$("typetext").value.trim();
  if(!text){err("type a command first — or click an example above");return}
  $("status").className="";$("status").textContent="thinking…";
  try{
    const r=await fetch("/text",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({text,session:"web",
                           audio:DEMO.get("audio","1")})});
    show(await r.json());
  }catch(e){err("server unreachable")}
}

// ---- show any result ------------------------------------------------ //
function show(j){
  last=j;
  if(j.error){err(j.error==="no_speech"?"didn't catch that — try again":j.error);return}
  $("status").textContent="";
  $("heard").textContent='"'+j.transcript+'"';
  const fixed=j.rules_fired&&j.rules_fired.length;
  $("fixedrow").style.display=fixed?"block":"none";
  if(fixed)$("fixed").textContent=j.rules_fired.map(
    f=>f[0]+" → "+f[1]).join(", ");
  $("intent").textContent=j.intent+"   ("+j.language+")";
  $("reply").textContent="“"+j.reply+"”";
  if(j.note){$("note").style.display="block";$("note").textContent="⚠️ "+j.note}
  else{$("note").style.display="none"}
  const src=j.engine==="text"?"⌨️ typed":"🎙️ spoken";
  $("rmeta").textContent=src+" · answered in "+(j.total_ms/1000).toFixed(2)
    +" s · say it again and it may answer even smarter";
  $("result").style.display="block";
  $("teach").style.display="flex";$("fbres").textContent="";
  $("result").scrollIntoView({behavior:"smooth",block:"nearest"});
  if(j.audio_b64){
    audio=new Audio("data:audio/wav;base64,"+j.audio_b64);
    audio.play().catch(()=>{});
    $("play").style.display="inline-block";
  }
  const teach=DEMO.get("teach");   // capture hook: auto-submit a correction
  if(teach&&j.id&&!j.__taught){j.__taught=true;
    $("fbtext").value=teach;$("send").click();}
}
$("play").onclick=()=>{if(audio)audio.play().catch(()=>{})};
const demo=DEMO.get("demo");       // capture hook: auto-run a command
if(demo){
  // hidden <img> to /slow keeps the window load event pending until the
  // whole demo (incl. the teach round-trip) has settled — headless
  // captures shoot at load time (fetch() would NOT delay it)
  const hold=document.createElement("img");
  hold.src="/slow?ms=9000";hold.style.display="none";
  document.body.appendChild(hold);
  $("typetext").value=demo;sendText();
}

// ---- teach ---------------------------------------------------------- //
$("send").onclick=async()=>{
  if(!last){$("fbres").textContent="talk or type something first";return}
  const text=$("fbtext").value.trim();
  if(!text){$("fbres").textContent="type what you actually said";return}
  $("send").disabled=true;
  try{
    const r=await fetch("/feedback",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({utterance_id:last.id,text})});
    const j=await r.json();
    if(j.error){$("fbres").textContent="error: "+j.error}
    else{
      const what=(j.learned&&j.learned.length)
        ?("hear "+j.learned.map(p=>"'"+p[0]+"'").join(", ")
          +" → say "+j.learned.map(p=>"'"+p[1]+"'").join(", "))
        :"got it — noted for next time";
      $("fbres").textContent="✅ Learned! "+what+"  ·  "+j.rules_active
        +" rules known. Say it again and watch the ✨ line.";
    }
    $("fbtext").value="";
  }catch(e){$("fbres").textContent="server unreachable"}
  $("send").disabled=false;
};
function err(msg){$("status").className="err";$("status").textContent=msg}
</script></body></html>"""
