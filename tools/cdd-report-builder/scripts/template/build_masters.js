// Maintainer script: builds the slide masters/layouts of the DiligenceIQ CDD template.
// Output: a base deck with three layouts (DIQ_COVER, DIQ_DIVIDER, DIQ_CONTENT) that
// build_template.py then populates with the fixed 48-slide sequence and named shapes.
// Usage: node build_masters.js <out.pptx>
const pptxgen = require("pptxgenjs");
const B = require("./brand.json");
const out = process.argv[2] || "base.pptx";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in (same canvas as the reference report)
pres.author = "DiligenceIQ";
pres.company = "DiligenceIQ";
pres.title = "Commercial Due Diligence Report";

const C = B.colors;
pres.defineSlideMaster({
  title: "DIQ_CONTENT",
  background: { color: C.white },
  objects: [
    { rect: { x: 0, y: 0, w: 13.333, h: 1.55, fill: { color: C.ink } } },
    { text: { text: "DiligenceIQ", options: { x: 10.9, y: 0.1, w: 2.0, h: 0.34, fontFace: B.fonts.head, fontSize: 13, bold: true, color: C.white, align: "right", margin: 0 } } },
    { rect: { x: 0, y: 7.08, w: 13.333, h: 0.42, fill: { color: C.tint } } },
    { text: { text: "[Project name]", options: { x: 0.45, y: 7.12, w: 4.5, h: 0.32, fontFace: B.fonts.body, fontSize: 8, color: C.slate, margin: 0, valign: "middle" } } },
    { text: { text: "DiligenceIQ  |  Strictly private & confidential", options: { x: 4.4, y: 7.12, w: 4.5, h: 0.32, fontFace: B.fonts.body, fontSize: 8, color: C.slate, align: "center", margin: 0, valign: "middle" } } },
  ],
  slideNumber: { x: 12.3, y: 7.14, w: 0.6, h: 0.28, fontFace: B.fonts.body, fontSize: 8, color: C.slate, align: "right" },
});

pres.defineSlideMaster({
  title: "DIQ_DIVIDER",
  background: { color: C.ink },
  objects: [
    { text: { text: "DiligenceIQ", options: { x: 0.6, y: 6.7, w: 3, h: 0.4, fontFace: B.fonts.head, fontSize: 14, bold: true, color: C.white, margin: 0 } } },
    { text: { text: "[Project name]", options: { x: 8.3, y: 6.75, w: 4.6, h: 0.32, fontFace: B.fonts.body, fontSize: 9, color: C.mist, align: "right", margin: 0 } } },
  ],
  slideNumber: { x: 12.3, y: 7.1, w: 0.6, h: 0.28, fontFace: B.fonts.body, fontSize: 8, color: C.mist, align: "right" },
});

pres.defineSlideMaster({
  title: "DIQ_COVER",
  background: { color: C.white },
  objects: [
    { rect: { x: 0, y: 0, w: 5.1, h: 7.5, fill: { color: C.ink } } },
  ],
});

// one throwaway slide per layout so every layout part is written
["DIQ_COVER", "DIQ_DIVIDER", "DIQ_CONTENT"].forEach((m) => pres.addSlide({ masterName: m }));
pres.writeFile({ fileName: out }).then(() => console.log("wrote", out));
