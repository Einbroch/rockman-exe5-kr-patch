"""Render the four text BG layers of a Mesen snapshot (mode 0, 4bpp or 8bpp per BGxCNT bit 7, 32x32 maps)."""
import json
import struct
import sys
from PIL import Image


def render(snap: str, step: str, out: str) -> None:
    v = open("%s/step_%s_gbaVideoRam.bin" % (snap, step), "rb").read()
    pal = open("%s/step_%s_gbaPaletteRam.bin" % (snap, step), "rb").read()
    st = json.load(open("%s/step_%s_state.json" % (snap, step)))["state"]
    col = [((c & 31) << 3, (c >> 5 & 31) << 3, (c >> 10 & 31) << 3) for c in struct.unpack_from("<256H", pal)]
    sheet = Image.new("RGB", (240 * 4, 160))
    for b in range(4):
        tm = st["ppu.bgLayers[%d].tilemapAddr" % b]
        ts = st["ppu.bgLayers[%d].tilesetAddr" % b]
        sx = st.get("ppu.bgLayers[%d].scrollX" % b, 0)
        sy = st.get("ppu.bgLayers[%d].scrollY" % b, 0)
        bpp8 = st.get("ppu.bgLayers[%d].control" % b, 0) >> 7 & 1
        img = Image.new("RGB", (240, 160), (255, 0, 255))
        px = img.load()
        for y in range(160):
            for x in range(240):
                mx, my = (x + sx) % 256, (y + sy) % 256
                e = struct.unpack_from("<H", v, tm + ((my // 8) * 32 + mx // 8) * 2)[0]
                t, hf, vf, p = e & 1023, e >> 10 & 1, e >> 11 & 1, e >> 12
                cx, cy = mx % 8, my % 8
                if hf: cx = 7 - cx
                if vf: cy = 7 - cy
                if bpp8:
                    a = ts + t * 64 + cy * 8 + cx
                    if a >= 0x10000:
                        continue
                    if v[a]:
                        px[x, y] = col[v[a]]
                    continue
                a = ts + t * 32 + cy * 4 + cx // 2
                if a >= 0x10000:
                    continue
                c = v[a] >> 4 if cx & 1 else v[a] & 15
                if c:
                    px[x, y] = col[p * 16 + c]
        sheet.paste(img, (240 * b, 0))
    sheet.save(out)


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2], sys.argv[3])
