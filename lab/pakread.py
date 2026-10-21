"""Read Arma Reforger .pak files (FORM/PAC1: HEAD, DATA, FILE chunks).

    python lab/pakread.py <data.pak> --list [filter]          # paths containing filter
    python lab/pakread.py <data.pak> --extract <filter> <out>  # files containing filter, into <out>/<path>

The FILE chunk is a tree: an entry is a type byte (0 directory, 1 file), a name length byte and the name; a
directory then has a little-endian child count, a file its offset, stored size, original size, two flags
words and a timestamp (6 x uint32). Stored files differing from their original size are zlib-compressed.
Used to read a map mod's mission worlds and layers (Yunakivka, 21 Oct).
"""
import struct
import sys
import zlib
from pathlib import Path


def chunks(f):
    f.seek(12)
    out = {}
    while True:
        head = f.read(8)
        if len(head) < 8:
            break
        cid, size = head[:4].decode(errors="replace"), struct.unpack(">I", head[4:])[0]
        out[cid] = (f.tell(), size)
        f.seek(size, 1)
    return out


def tree(buf):
    files = []

    def entry(pos, prefix):
        kind = buf[pos]
        n = buf[pos + 1]
        name = buf[pos + 2:pos + 2 + n].decode("utf-8", errors="replace")
        pos += 2 + n
        path = f"{prefix}/{name}" if prefix and name else (name or prefix)
        if kind == 0:
            count = struct.unpack("<I", buf[pos:pos + 4])[0]
            pos += 4
            for _ in range(count):
                pos = entry(pos, path)
        else:
            offset, stored, original, a, b, stamp = struct.unpack("<6I", buf[pos:pos + 24])
            pos += 24
            files.append((path, offset, stored, original, b))
        return pos

    entry(0, "")
    return files


def read_file(f, offset, stored, original):
    f.seek(offset)
    data = f.read(stored)
    if stored != original:
        try:
            data = zlib.decompress(data)
        except zlib.error:
            try:
                data = zlib.decompress(data, -15)
            except zlib.error:
                pass
    return data


def main():
    pak = Path(sys.argv[1])
    with open(pak, "rb") as f:
        c = chunks(f)
        start, size = c["FILE"]
        f.seek(start)
        files = tree(f.read(size))
        if "--list" in sys.argv:
            flt = sys.argv[sys.argv.index("--list") + 1] if len(sys.argv) > sys.argv.index("--list") + 1 else ""
            for path, off, st, orig, flag in files:
                if flt.lower() in path.lower():
                    print(f"{orig:>10} {path}")
        if "--extract" in sys.argv:
            i = sys.argv.index("--extract")
            flt, out = sys.argv[i + 1], Path(sys.argv[i + 2])
            for path, off, st, orig, flag in files:
                if flt.lower() in path.lower():
                    target = out / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(read_file(f, off, st, orig))
                    print("extracted", target)


if __name__ == "__main__":
    main()
