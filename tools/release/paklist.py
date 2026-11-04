"""List the files inside an Enfusion data.pak (FORM/PAC1: a FILE chunk with the tree - entry: u8 type (0 dir, 1 file),
u8 name length, name; a dir: u32 child count; a file: u32 offset, u32 size, u32 original size, u32, u16, u8, u8, u32).
    python tools/release/paklist.py D:/work/release/packed/*/data.pak
"""
import struct
import sys


def entries(data: bytes):
    i = data.find(b"FILE")
    size = struct.unpack(">I", data[i + 4:i + 8])[0]
    pos, end = i + 8, i + 8 + size
    out = []

    def walk(prefix: str, count: int):
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
                pos += 12 + 4 + 2 + 1 + 1 + 4
                out.append((prefix + name, orig))
    kind, n = data[pos], data[pos + 1]
    pos += 2 + n
    (k,) = struct.unpack("<I", data[pos:pos + 4])
    pos += 4
    walk("", k)
    return out


for path in sys.argv[1:]:
    files = entries(open(path, "rb").read())
    print(f"== {path}: {len(files)} files")
    for name, sz in files:
        print(f"   {sz:>9}  {name}")
