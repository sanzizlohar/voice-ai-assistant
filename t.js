const s={utterances:1}, acc=0.9, tot={p50:1}, learning={active:2};
const x =
  s.utterances+" utterances · "+
  (acc!=null?(100*acc).toFixed(0)+"% accuracy · ":'')+
  (tot?("p50 "+tot.p50.toFixed(0)+" ms · ":''))+
  (learning.active||0)+" learned rules";
console.log("OK:", x);
