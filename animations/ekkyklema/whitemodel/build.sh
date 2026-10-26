#!/bin/sh
# One-command build of the white-model sample.
#   sh build.sh                 # everything: render (3 workers) -> merge -> encode -> sound -> mux -> swap proof -> sheet
#   STAGE=render|assemble|sound|swap|sheet sh build.sh   # one stage
# Env: OUT (work folder, default ./out), WORKERS (3), LIB (lemo-opuscar clone, for sfx.py/sampler.py/mux.sh/sheet.py)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${OUT:-$HERE/out}
WORKERS=${WORKERS:-3}
LIB=${LIB:-$HOME/lemo-opuscar}
PY=${PY:-$LIB/.venv/bin/python}
SAMPLE=$HERE/sample
STAGE=${STAGE:-all}
DUR=15.0
FPS=24
cd "$HERE"

render_look() {   # $1 = out dir, $2 = cast file, $3 = layers
  mkdir -p "$1"
  n=$(python3 -c "print(round($DUR*$FPS))")
  i=0; pids=""
  while [ $i -lt "$WORKERS" ]; do
    a=$(python3 -c "print($i*$n//$WORKERS/$FPS)"); b=$(python3 -c "print(($i+1)*$n//$WORKERS/$FPS)")
    node render.mjs --png --tracks --cast "$2" --layers "$3" --start "$a" --end "$b" --out "$1" > "$1/worker_$i.log" 2>&1 &
    pids="$pids $!"; i=$((i+1))
  done
  for p in $pids; do wait "$p"; done
  node render.mjs --events --stills 0 --layers plate --out "$1/ev" > /dev/null 2>&1   # window.EV -> events.json
}

merge_json() {    # merge the per-worker tracks / hashes / stats in $1
  node -e '
    const fs=require("fs"),p=require("path"),d=process.argv[1];
    const ls=(pre)=>fs.readdirSync(d).filter(f=>f.startsWith(pre+"_")&&f.endsWith(".json")).sort();
    const T=ls("tracks").map(f=>JSON.parse(fs.readFileSync(p.join(d,f))));
    fs.writeFileSync(p.join(d,"tracks.json"),JSON.stringify({fps:T[0].fps,width:T[0].width,height:T[0].height,frames:T.flatMap(t=>t.frames)},null,1));
    const H={},cr=require("crypto"),NM={all:"composite",plate:"plate",cast:"cast_rgba"};   // md5 of every PNG on disk
    for(const[k,dir]of Object.entries(NM)){const q=p.join(d,dir);if(!fs.existsSync(q))continue;H[k]=fs.readdirSync(q).filter(f=>f.endsWith(".png")).sort().map(f=>cr.createHash("md5").update(fs.readFileSync(p.join(q,f))).digest("hex"));}
    fs.writeFileSync(p.join(d,"frame_hashes.json"),JSON.stringify(H));
    const S=ls("render_stats").map(f=>JSON.parse(fs.readFileSync(p.join(d,f))));
    const L={};for(const s of S)for(const[k,v]of Object.entries(s.layers)){const o=(L[k]||={frames:0,render_ms:0,capture_ms:0});o.frames+=v.frames;o.render_ms+=v.render_ms;o.capture_ms+=v.capture_ms;}
    for(const o of Object.values(L)){o.render_s_per_frame=+(o.render_ms/o.frames/1000).toFixed(2);o.capture_s_per_frame=+(o.capture_ms/o.frames/1000).toFixed(2);}
    fs.writeFileSync(p.join(d,"render_stats.json"),JSON.stringify({workers:S.length,wall_s_per_worker:S.map(s=>s.total_s),frames:S.reduce((a,s)=>a+s.frames,0),layers:L},null,1));
  ' "$1"
}

enc() {  # $1 = png pattern dir, $2 = out mp4, $3 = crf, $4 = extra vf
  ffmpeg -hide_banner -loglevel error -y -framerate $FPS -i "$1/%04d.png" ${4:+-vf "$4"} -c:v libx264 -preset slow -crf "$3" -pix_fmt yuv420p -movflags +faststart "$2"
}

if [ "$STAGE" = all ] || [ "$STAGE" = render ]; then
  render_look "$OUT/white" cast.json all,plate,cast
fi
if [ "$STAGE" = all ] || [ "$STAGE" = assemble ]; then
  merge_json "$OUT/white"
  mkdir -p "$SAMPLE"
  enc "$OUT/white/composite" "$OUT/video.mp4" 16
  enc "$OUT/white/plate" "$SAMPLE/plate.mp4" 22
  enc "$OUT/white/cast_rgba" "$SAMPLE/matte.mp4" 20 "alphaextract,format=yuv420p"
  ffmpeg -hide_banner -loglevel error -y -framerate $FPS -i "$OUT/white/cast_rgba/%04d.png" -c:v prores_ks -profile:v 4444 -pix_fmt yuva444p10le -alpha_bits 16 -vendor apl0 "$OUT/cast_rgba.mov"
  node -e 'const fs=require("fs");const t=JSON.parse(fs.readFileSync(process.argv[1]));fs.writeFileSync(process.argv[2],JSON.stringify(t))' "$OUT/white/tracks.json" "$SAMPLE/tracks.json"
fi
if [ "$STAGE" = all ] || [ "$STAGE" = sound ]; then
  LIB="$LIB" "$PY" mix.py "$OUT/white/ev/events.json" "$OUT/mix.wav"
  CRF=${CRF:-21} sh tools/mux.sh "$OUT/video.mp4" "$OUT/mix.wav" "$SAMPLE/composite.mp4" $FPS 1
fi
if [ "$STAGE" = all ] || [ "$STAGE" = swap ]; then
  render_look "$OUT/clay" examples/cast.clay.json plate
  merge_json "$OUT/clay"
  node render.mjs --cast examples/cast.clay.json --stills 3.5,8.0,11.5,14.5 --layers all --out "$OUT/clay_stills" > /dev/null 2>&1
  node tools/swapproof.mjs "$OUT/white" "$OUT/clay" "$SAMPLE/SWAP_PROOF.txt"
fi
if [ "$STAGE" = all ] || [ "$STAGE" = sheet ]; then
  "$PY" tools/sheet.py "$OUT" "$SAMPLE/contact_sheet.jpg"
fi
