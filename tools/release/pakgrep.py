"""Which files of an Enfusion data.pak contain a text (files are zlib-compressed when their sizes differ).
    python tools/release/pakgrep.py <text> <data.pak>...
"""
import struct
import sys
import zlib


def files(data: bytes):
    i = data.find(b"FILE")
    pos = i + 8
    out = []

    def walk(prefix, count):
        nonlocal pos
        for _ in range(count):
            kind, n = data[pos], data[pos + 1]
            name = data[pos + 2:pos + 2 + n].decode("utf-8", "replace")
            pos += 2 + n
            if kind == 0:
                (k,) = struct.unpack("<I", data[pos:pos + 4])
                pos += 4
                walk(prefix + name + "/", k)
            else:
                off, sz, orig = struct.unpack("<III", data[pos:pos + 12])
                pos += 24
                out.append((prefix + name, off, sz, orig))
    pos += 2 + data[pos + 1]
    (k,) = struct.unpack("<I", data[pos:pos + 4])
    pos += 4
    walk("", k)
    return out


text = sys.argv[1].encode()
for path in sys.argv[2:]:
    data = open(path, "rb").read()
    for name, off, sz, orig in files(data):
        raw = data[off:off + sz]
        if sz != orig:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                continue
        if text in raw:
            print(f"{path}: {name}")
