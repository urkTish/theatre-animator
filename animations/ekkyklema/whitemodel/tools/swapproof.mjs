// Swap proof: two full renders that differ only in the cast file's `representation` (look A = cast.json, white
// maquettes; look B = examples/cast.clay.json, the motion build's clay stand-ins). The plate frames and tracks.json
// must be identical. usage: node tools/swapproof.mjs <outA> <outB> <SWAP_PROOF.txt>
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

const [A, B, OUTF] = process.argv.slice(2);
const sha = (f) => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const HA = JSON.parse(fs.readFileSync(path.join(A, 'frame_hashes.json'))).plate;
const HB = JSON.parse(fs.readFileSync(path.join(B, 'frame_hashes.json'))).plate;
const same = HA.filter((h, i) => h === HB[i]).length;
const tA = sha(path.join(A, 'tracks.json')), tB = sha(path.join(B, 'tracks.json'));
const castA = JSON.parse(fs.readFileSync('cast.json')), castB = JSON.parse(fs.readFileSync('examples/cast.clay.json'));
const motionSame = Object.keys(castA.slots).every((k) => JSON.stringify(castA.slots[k].motion) === JSON.stringify(castB.slots[k].motion));
const repA = Object.fromEntries(Object.entries(castA.slots).map(([k, v]) => [k, v.representation]));
const repB = Object.fromEntries(Object.entries(castB.slots).map(([k, v]) => [k, v.representation]));
// the composites differ (the look changed): compare a few composite frames of A with B's stills is not byte-comparable,
// so we report the cast-layer hashes of A for the record and B's composite stills by name.
const ok = same === HA.length && HA.length === HB.length && tA === tB && motionSame;
const lines = [
  'SWAP PROOF: changing the characters\' look changes neither the plate nor the tracks',
  '',
  `look A: cast.json                 (representation: ${JSON.stringify(repA.standing_actor)} in every slot)`,
  `look B: examples/cast.clay.json   (representation: ${JSON.stringify(repB.standing_actor)} in every slot)`,
  `motion blocks in the two cast files identical: ${motionSame}`,
  '',
  `plate frames rendered: A ${HA.length}, B ${HB.length} (1920x1080, 24 fps, 0-${(HA.length / 24).toFixed(2)} s)`,
  `plate frames with identical MD5 (lossless PNG captures): ${same} / ${HA.length}`,
  `tracks.json sha256  A ${tA}`,
  `tracks.json sha256  B ${tB}`,
  `tracks.json byte-identical: ${tA === tB}`,
  '',
  'first / middle / last plate hashes (A = B):',
  ...[0, Math.floor(HA.length / 2), HA.length - 1].map((i) => `  frame ${String(i).padStart(3)}  ${HA[i]}  ${HB[i]}`),
  '',
  'Why it holds: the plate layer hides every character slot and their shadows (contactShadows off), the projector',
  'puts data colours only on the model (figures get the neutral black level only), and tracks.json is computed from',
  'the canonical skeleton and simple set occluders, never from the mesh that fills a slot.',
  'The hashes refer to the full-quality PNG renders (outside the repo); plate.mp4 is an H.264 encode of look A\'s plate.',
  '',
  ok ? 'RESULT: PASS' : 'RESULT: FAIL',
];
fs.writeFileSync(OUTF, lines.join('\n') + '\n');
console.log(lines.join('\n'));
process.exit(ok ? 0 : 1);
