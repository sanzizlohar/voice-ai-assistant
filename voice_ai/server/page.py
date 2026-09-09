"""Single-page demo UI — colorful hand-drawn "sketchbook" theme.

Design goals (user-requested): eye-catchy, playful sketch look, and zero
ambiguity — every section says in plain words what to do and what
happened. Three ways in: talk (mic), type (no mic needed), or click an
example chip. Audio is captured with AudioContext and encoded to 16 kHz
mono PCM WAV client-side — the server needs no ffmpeg. (The
ScriptProcessorNode is held in a module variable: browsers garbage-collect
it mid-recording otherwise, which silently kills the mic.)
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Voice AI Assistant</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--paper:#fdf6e3;--ink:#33322e;--coral:#ff5252;--teal:#00b8a0;
--amber:#ffb300;--violet:#7c4dff;--blue:#2f7bff;--green:#00b85a;
--pink:#ff5c95;--soft:#fffdf7;--dim:#6b675c}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);
background:var(--paper);
background-image:radial-gradient(rgba(51,50,46,.08) 1.2px,transparent 1.3px);
background-size:24px 24px;
font-family:'Segoe Print','Comic Sans MS','Chalkboard SE',cursive;
display:flex;justify-content:center;min-height:100vh;
-webkit-font-smoothing:antialiased}
main{width:100%;max-width:620px;padding:26px 18px 46px;display:flex;
flex-direction:column;gap:16px}
.sk{background:var(--soft);border:2.5px solid var(--ink);
border-radius:255px 15px 225px 15px/15px 225px 15px 255px;
box-shadow:4px 4px 0 rgba(51,50,46,.8)}
header{display:flex;justify-content:space-between;align-items:center;
gap:10px;padding:14px 20px;transform:rotate(-.6deg)}
header h1{font-size:21px;margin:0;font-weight:700}
header .badge{font-size:11px;background:var(--amber);border:2px solid var(--ink);
border-radius:12px 4px 10px 5px;padding:3px 9px;box-shadow:2px 2px 0 var(--ink);
font-weight:700}

.steps{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
@media(max-width:520px){.steps{grid-template-columns:1fr}}
.step{padding:10px 12px;font-size:12.5px;line-height:1.5;transition:all .18s ease}
.step:hover{transform:translateY(-2px) rotate(0deg)!important}
.step b{display:block;font-size:13.5px}
.s1{transform:rotate(-1deg);background:#ccf3ec;border-color:#00806e}
.s1 b{color:#00795f}
.s2{transform:rotate(.8deg);background:#e9dcff;border-color:#6a3fd8}
.s2 b{color:#5b2fd4}
.s3{transform:rotate(-.5deg);background:#ffedb0;border-color:#d19400}
.s3 b{color:#9a6b00}

.micwrap{text-align:center;padding:20px 0 4px}
#rec{width:150px;height:150px;border-radius:50% 46% 52% 48%/47% 52% 46% 53%;
border:3px solid var(--ink);cursor:pointer;font-family:inherit;
background:var(--coral);color:#fff;font-weight:700;font-size:17px;
box-shadow:5px 6px 0 rgba(51,50,46,.55),0 10px 22px rgba(255,82,82,.35);
transition:transform .16s ease,box-shadow .16s ease}
#rec:hover{transform:scale(1.05) rotate(-1.5deg);
box-shadow:6px 8px 0 rgba(51,50,46,.5),0 14px 28px rgba(255,82,82,.45)}
#rec.on{background:var(--pink);color:#fff;animation:wiggle .5s infinite}
@keyframes wiggle{0%,100%{transform:rotate(-1.6deg) scale(1.03)}
50%{transform:rotate(1.6deg) scale(1.03)}}
#hint{color:var(--dim);font-size:13px;margin-top:12px}
#hint kbd{background:#fff;border:2px solid var(--ink);border-radius:8px 3px 9px 4px;
padding:1px 7px;font-size:11px;box-shadow:2px 2px 0 rgba(51,50,46,.6)}
#status{min-height:22px;font-size:14px;text-align:center;color:var(--dim)}
#status.err{color:var(--coral);font-weight:700}

h2{font-size:14px;margin:0 0 8px;transform:rotate(-.8deg)}
h2 .tag{display:inline-block;background:var(--teal);color:#fff;
border:2px solid var(--ink);border-radius:10px 4px 12px 5px;padding:2px 10px;
box-shadow:3px 3px 0 rgba(51,50,46,.6);font-weight:700}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{border:2px solid var(--ink);border-radius:14px 5px 12px 6px;
padding:5px 11px;font-size:12.5px;cursor:pointer;font-family:inherit;
box-shadow:3px 3px 0 rgba(51,50,46,.5);font-weight:700;color:#33322e;
transition:all .15s ease}
.chip:hover{transform:translate(-1px,-2px) rotate(-.8deg);
box-shadow:4px 6px 0 rgba(51,50,46,.4)}
.c1{background:#ffd0d0}.c2{background:#b8f0e6}.c3{background:#ffe089}
.c4{background:#e4ccff}.c5{background:#c7ddff}.c6{background:#b2f0cf}

.typerow{display:flex;gap:8px;padding:12px}
#typetext{flex:1;font-family:inherit;font-size:15px;color:var(--ink);
background:#fff;border:2px solid var(--ink);
border-radius:12px 5px 14px 6px;padding:10px 12px;outline:none;
transition:border-color .15s ease,box-shadow .15s ease}
#typetext:focus{border-color:var(--violet);
box-shadow:0 0 0 3px rgba(124,77,255,.18)}
#typego{font-family:inherit;font-weight:700;font-size:14px;color:#fff;
background:var(--violet);border:2px solid var(--ink);
border-radius:14px 6px 12px 5px;padding:10px 18px;cursor:pointer;
box-shadow:3px 3px 0 rgba(51,50,46,.55);transition:all .15s ease}
#typego:hover{transform:translateY(-1px)}
#typego:active{transform:translate(2px,2px);box-shadow:1px 1px 0 rgba(51,50,46,.5)}

.result{padding:16px 18px;display:none;transform:rotate(.4deg);
background:#fff}
.result .row{margin:9px 0}
.result .who{font-size:11px;letter-spacing:.5px;font-weight:700;
text-transform:uppercase;border-radius:8px 3px 9px 4px;display:inline-block;
padding:1px 8px;border:2px solid var(--ink);margin-bottom:3px;
box-shadow:2px 2px 0 rgba(51,50,46,.5)}
.w-said{background:#ffd0d0}.w-knew{background:#e4ccff}
.w-reply{background:#b8f0e6}.w-fix{background:#ffe089}
.result .heard{font-size:17px}
.result .fixed{font-size:16px;color:#00875a;font-weight:700}
.result .reply{font-size:17px}
.result .meta{font-size:12px;color:var(--dim);margin-top:10px}
#play{font-family:inherit;font-weight:700;
background:#b8f0e6;border:2px solid var(--ink);
border-radius:10px 4px 12px 5px;padding:6px 13px;font-size:13px;cursor:pointer;
box-shadow:3px 3px 0 rgba(51,50,46,.5);margin-top:8px;transition:all .15s ease}
#play:hover{transform:translateY(-1px)}
#play:active{transform:translate(2px,2px);box-shadow:1px 1px 0 rgba(51,50,46,.4)}

.teach{padding:14px 16px;display:none;flex-direction:column;gap:9px;
transform:rotate(-.5deg);background:#ffecad}
.teachrow{display:flex;gap:8px}
#fbtext{flex:1;font-family:inherit;font-size:15px;color:var(--ink);
background:#fff;border:2px solid var(--ink);
border-radius:12px 5px 14px 6px;padding:10px 12px;outline:none;
transition:border-color .15s ease,box-shadow .15s ease}
#fbtext:focus{border-color:var(--amber);box-shadow:0 0 0 3px rgba(255,179,0,.2)}
#send{font-family:inherit;font-weight:700;font-size:14px;color:#3d2e00;
background:var(--amber);border:2px solid var(--ink);
border-radius:14px 6px 12px 5px;padding:10px 16px;cursor:pointer;
box-shadow:3px 3px 0 rgba(51,50,46,.55);transition:all .15s ease}
#send:hover{transform:translateY(-1px)}
#send:active{transform:translate(2px,2px);box-shadow:1px 1px 0 rgba(51,50,46,.4)}
#fbres{font-size:13px;color:var(--dim);min-height:18px}

footer{margin-top:6px;text-align:center;color:var(--dim);font-size:12.5px;
transform:rotate(.4deg)}
</style></head><body>
<main>
  <header class="sk">
    <h1>🎙️ Voice AI Assistant</h1>
    <span class="badge" id="engine">…</span>
  </header>

  <div class="steps">
    <div class="sk step s1"><b>1 · 🎙️ Talk</b>
      click the mic, speak, click again</div>
    <div class="sk step s2"><b>2 · 🧠 Understand</b>
      it hears you, then fixes its known mistakes</div>
    <div class="sk step s3"><b>3 · ✏️ Teach</b>
      wrong word? correct it once — it learns</div>
  </div>

  <div class="micwrap">
    <button id="rec" aria-label="start recording">🎙️ TAP TO<br>TALK</button>
    <div id="hint">press <kbd>space</kbd> to start — press again to stop
      · no mic? type below</div>
  </div>
  <div id="status"></div>

  <section>
    <h2><span class="tag">TRY SAYING — click one</span></h2>
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

  <section class="sk">
    <div class="typerow">
      <input id="typetext" placeholder="no mic? type a command here…">
      <button id="typego">Go →</button>
    </div>
  </section>

  <div class="result sk" id="result">
    <div class="row"><span class="who w-said">🗣️ you said</span>
      <div class="heard" id="heard"></div></div>
    <div class="row" id="fixedrow" style="display:none">
      <span class="who w-fix">✨ learned fix</span>
      <div class="fixed" id="fixed"></div></div>
    <div class="row"><span class="who w-knew">🧠 understood as</span>
      <div id="intent"></div></div>
    <div class="row"><span class="who w-reply">💬 it replied</span>
      <div class="reply" id="reply"></div>
      <button id="play" style="display:none">▶ hear it</button></div>
    <div class="meta" id="rmeta"></div>
    <div id="note" style="display:none;color:#9a6b00;font-size:12.5px;
      margin-top:8px"></div>
  </div>

  <div class="teach sk" id="teach">
    <div><b>✏️ Misheard?</b> Type what you actually said — it learns and
      won't repeat the mistake:</div>
    <div class="teachrow">
      <input id="fbtext" placeholder="what you really said…">
      <button id="send">teach</button>
    </div>
    <div id="fbres"></div>
  </div>

  <footer id="stats">connecting…</footer>
</main>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",
">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
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
    $("rec").classList.add("on");$("rec").innerHTML="● LISTENING…<br>tap to stop";
    $("hint").textContent="speak now — click the button when done";
    $("status").className="";$("status").textContent="";
    const t0=Date.now();tick=setInterval(()=>{
      $("status").textContent="🎙️ recording… "+((Date.now()-t0)/1000).toFixed(1)+" s";
    },100);
  }catch(e){err("mic blocked: "+e.message+" — you can type instead ↓")}
}
async function stop(){
  recState="idle";clearInterval(tick);
  $("rec").classList.remove("on");$("rec").innerHTML="🎙️ TAP TO<br>TALK";
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
      body:JSON.stringify({text,session:"web"})});
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
}
$("play").onclick=()=>{if(audio)audio.play().catch(()=>{})};

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
