"""Preview the logo subtitle: logo_preview.py '<json cfg>' out.png
cfg: {"boxes": [[x0,y0,x1,y1,"YRW"]...], "plates": [[x0,y0,x1,y1,shear,border]...] (optional),
      "words": [[text,size,shear,x,y,"yellow"|"red"]...]}"""
import json,struct,sys
sys.path.insert(0,"tools")
import logo_subtitle as L
from PIL import Image
cfg0=json.loads(sys.argv[1]); ver=cfg0.get("version","blues"); L.set_style(ver)
idx=json.load(open("runtime/logo_idx.json" if ver=="blues" else "runtime/logo_idx_colonel.json"))
pal=open("runtime/title_snap/step_005_gbaPaletteRam.bin" if ver=="blues" else "runtime/title_snap_col/step_005_gbaPaletteRam.bin","rb").read()
P=[((c&31)<<3,(c>>5&31)<<3,(c>>10&31)<<3) for c in struct.unpack_from("<256H",pal)]
cfg=json.loads(sys.argv[1])
if cfg.get("plates"):
    img,mask,left=L.compose_plate(idx,P,[tuple(b) for b in cfg["boxes"]],[tuple(p) for p in cfg["plates"]],[tuple(w) for w in cfg["words"]])
    print("uncovered mask pixels",len(left))
else:
    img,mask=L.compose(idx,P,[tuple(b) for b in cfg["boxes"]],[tuple(w) for w in cfg["words"]])
def draw(g):
    im=Image.new("RGB",(240,160))
    for y in range(160):
        for x in range(240): im.putpixel((x,y),P[g[y][x]])
    return im
a=draw(idx).crop((10,50,200,120)); b=draw(img).crop((10,50,200,120))
s=Image.new("RGB",(190,140)); s.paste(a,(0,0)); s.paste(b,(0,70)); s.resize((760,560),0).save(sys.argv[2])
