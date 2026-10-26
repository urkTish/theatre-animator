// looks.js: what fills a character slot (colours, mask, costume pattern). Swapping a look changes only how a slot is
// painted, never where it is or how it moves (that is the motion track in cast/cast.js). Add a look here and name it
// in the cast file.
//
// Masked actors: look.mask (whole-head mask: skin, shading, hair, beard, iris, lips, fillet, style 'prime' | 'elder'),
// look.robe (the long-sleeved chiton poikilos: colour, shadow, bands [{ y, h, col, pat, fg }] in metres up from the hem,
// belt, cuff), look.mantle (himation over the left shoulder), boots, skin (the actor's own hands).
// Stagehands: look.head (their own face, no mask), look.tunic (a plain short belted tunic), skin.
// Band patterns: wave (running spiral), meander, dots, tri (dogtooth), palmette, zig.
const LOOKS = {
  // ---------------- look set A: madder, saffron, woad and undyed wool; tanned ochre masks (Pronomos Vase, c. 400 BC)
  dikaiopolis: {
    skin: '#B97F58', skinDk: '#8A5638', boots: '#6B4A33',
    mask: { style: 'prime', skin: '#C98B5B', shade: '#9A5E3B', sheen: '#F4CFA2', white: '#F3E6CF', iris: '#4A2E1E', lip: '#A0453F',
            hair: '#2F2420', hairDk: '#140E0E', beard: '#2F2420', beardDk: '#140E0E', fillet: '#B8463A' },
    robe: { col: '#A3482F', dk: '#6E2A1F', belt: '#3E2A22', cuff: '#3F5F8C', cuffFg: '#F1E2C2',
            bands: [{ y: .07, h: .11, col: '#3F5F8C', pat: 'wave', fg: '#F1E2C2' }, { y: .27, h: .07, col: '#EEDDBA', pat: 'tri', fg: '#5A2A20' },
                    { y: .46, h: .05, col: '#D9A443', pat: 'dots', fg: '#6E281E' }, { y: 1.16, h: .07, col: '#3F5F8C', pat: 'meander', fg: '#F1E2C2' }] },
    mantle: { col: '#D9A043', dk: '#A87428', border: '#6E2A1F' },
  },
  euripides: {
    skin: '#B98660', skinDk: '#875A3C', boots: '#5E4330',
    mask: { style: 'elder', skin: '#C4906A', shade: '#8E5E42', sheen: '#F3D3B0', white: '#EFE4D0', iris: '#3E3A36', lip: '#94564F',
            hair: '#BDB5A8', hairDk: '#6F675D', beard: '#C9C1B4', beardDk: '#7A7266', fillet: null },
    robe: { col: '#D8AC5C', dk: '#A47B36', belt: '#5A3A26', cuff: '#9E4A35', cuffFg: '#F1E2C2',
            bands: [{ y: .07, h: .1, col: '#9E4A35', pat: 'wave', fg: '#F1E2C2' }, { y: 1.12, h: .06, col: '#9E4A35', pat: 'wave', fg: '#F1E2C2' }, { y: 1.27, h: .04, col: '#4E6A92', pat: 'dots', fg: '#F1E2C2' }] },
    mantle: { col: '#4E6A92', dk: '#33496B', border: '#E8D9B5' },
  },
  stagehand_a: {
    skin: '#B07650', skinDk: '#7E5034',
    head: { skin: '#B57A52', shade: '#8A5638', hair: '#2B201C', hairDk: '#120C0B', stubble: '#5A4436' },
    tunic: { col: '#E2D2AE', dk: '#B8A47C', belt: '#7A5A3A' },
  },
  stagehand_b: {
    skin: '#A86E48', skinDk: '#77482E',
    head: { skin: '#AC7049', shade: '#7E4E31', hair: '#3A2A22', hairDk: '#1A1210', stubble: '#5E4636' },
    tunic: { col: '#C9B48C', dk: '#9E8A64', belt: '#6B4A30' },
  },
  // ---------------- look set B: the same slots in other colourings (used to prove the swap)
  dikaiopolis_B: {
    skin: '#C08A64', skinDk: '#8E5E40', boots: '#3E2E26',
    mask: { style: 'prime', skin: '#DDB088', shade: '#A9775A', sheen: '#FBE3C2', white: '#F6ECDA', iris: '#2E4A3A', lip: '#B0524C',
            hair: '#7A3E22', hairDk: '#3E1C10', beard: '#7A3E22', beardDk: '#3E1C10', fillet: '#5E7F4A' },
    robe: { col: '#3D5C8A', dk: '#26395A', belt: '#D9A443', cuff: '#E2A83C', cuffFg: '#3D2A20',
            bands: [{ y: .07, h: .11, col: '#E2A83C', pat: 'meander', fg: '#3D2A20' }, { y: .27, h: .07, col: '#EEDDBA', pat: 'zig', fg: '#7A2E24' },
                    { y: .46, h: .05, col: '#A9432F', pat: 'dots', fg: '#F1E2C2' }, { y: 1.16, h: .07, col: '#E2A83C', pat: 'wave', fg: '#3D2A20' }] },
    mantle: { col: '#EBDDBB', dk: '#C2AF88', border: '#A9432F' },
  },
  euripides_B: {
    skin: '#C2906A', skinDk: '#8E6044', boots: '#3E2E26',
    mask: { style: 'elder', skin: '#D6A984', shade: '#9E7458', sheen: '#FBE6CC', white: '#F4EBDC', iris: '#3A4A5A', lip: '#A2625A',
            hair: '#E4DFD6', hairDk: '#9A948A', beard: '#ECE7DE', beardDk: '#A39C92', fillet: '#5E7F4A' },
    robe: { col: '#6F8B4F', dk: '#4A6234', belt: '#3E2A22', cuff: '#E2A83C', cuffFg: '#3D2A20',
            bands: [{ y: .07, h: .1, col: '#E2A83C', pat: 'palmette', fg: '#6E281E' }, { y: 1.12, h: .06, col: '#E2A83C', pat: 'meander', fg: '#3D2A20' }, { y: 1.27, h: .04, col: '#A9432F', pat: 'dots', fg: '#F1E2C2' }] },
    mantle: { col: '#6C4A7E', dk: '#48304F', border: '#E2A83C' },
  },
  stagehand_a_B: {
    skin: '#9E6A46', skinDk: '#6E452C',
    head: { skin: '#A56C46', shade: '#764A2E', hair: '#5A3A26', hairDk: '#2A1A10', stubble: '#5A4030' },
    tunic: { col: '#9C7F5A', dk: '#75603F', belt: '#E2D2AE' },
  },
  stagehand_b_B: {
    skin: '#B8825C', skinDk: '#86583A',
    head: { skin: '#BC865E', shade: '#8E5E40', hair: '#1E1612', hairDk: '#0A0606', stubble: '#4A3A30' },
    tunic: { col: '#8E9A7A', dk: '#6A7658', belt: '#4A3424' },
  },
};
