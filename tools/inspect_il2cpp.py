"""Inspect Il2CppDumper outputs without executing the game."""
import argparse
import bisect
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUMP = ROOT / "analysis/il2cpp-arm64"
LIB = ROOT / "analysis/xapk_1.4.1/apk/lib/arm64-v8a/libil2cpp.so"


def types(pattern, fields_only=False):
    text = (DUMP / "dump.cs").read_text(encoding="utf-8-sig")
    for block in re.split(r"(?=// Namespace:)", text):
        header = re.search(r"^(?:public|private|internal|protected).*?\b(?:class|struct|enum) (.+?) // TypeDefIndex", block, re.M)
        if header and re.search(pattern, header[1]):
            if fields_only:
                block = block.split("\t// Methods")[0] + "}\n"
            print(block)


def disassemble(pattern, limit):
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
    from elftools.elf.elffile import ELFFile
    data = json.loads((DUMP / "script.json").read_text(encoding="utf-8-sig"))
    methods = sorted(data["ScriptMethod"], key=lambda x: x["Address"])
    by_addr = {x["Address"]: x["Name"] for x in methods}
    addresses = sorted(by_addr)
    names = {}
    for key in ("ScriptString", "ScriptMetadata", "ScriptMetadataMethod"):
        for x in data.get(key, []):
            names[x["Address"]] = x.get("Name", x.get("Value", ""))
    with LIB.open("rb") as f:
        elf = ELFFile(f)
        segments = [s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
        relocations = {}
        for section in elf.iter_sections():
            if section["sh_type"] == "SHT_RELA":
                for relocation in section.iter_relocations():
                    if relocation["r_info_type"] == 1027:
                        relocations[relocation["r_offset"]] = relocation["r_addend"]

        def read(va, size):
            for s in segments:
                if s["p_vaddr"] <= va < s["p_vaddr"] + s["p_filesz"]:
                    f.seek(s["p_offset"] + va - s["p_vaddr"])
                    return f.read(size)
            return b""

        engine = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
        for m in methods:
            if not re.search(pattern, m["Name"]):
                continue
            start = m["Address"]
            idx = bisect.bisect_right(addresses, start)
            end = addresses[idx] if idx < len(addresses) else start + limit
            print(f"\n{m['Name']} @ {start:#x} ({end-start} bytes)")
            regs = {}
            for ins in engine.disasm(read(start, min(end-start, limit)), start):
                note = ""
                if ins.mnemonic in ("bl", "b") and ins.op_str.startswith("#"):
                    note = by_addr.get(int(ins.op_str[1:], 16), "")
                p = re.fullmatch(r"(x\d+), #0x([0-9a-f]+)", ins.op_str)
                if ins.mnemonic == "adrp" and p:
                    regs[p[1]] = int(p[2], 16)
                p = re.fullmatch(r"(x\d+), \[(x\d+)(?:, #0x([0-9a-f]+))?\]", ins.op_str)
                if ins.mnemonic == "ldr" and p and p[2] in regs:
                    addr = regs[p[2]] + int(p[3] or "0", 16)
                    note = names.get(addr, f"memory {addr:#x}")
                    raw = read(addr, 8)
                    value = relocations.get(addr, struct.unpack("<Q", raw)[0] if len(raw) == 8 else 0)
                    regs[p[1]] = value
                    if value in names:
                        note = names[value]
                p = re.fullmatch(r"(x\d+), (x\d+), #0x([0-9a-f]+)", ins.op_str)
                if ins.mnemonic == "add" and p and p[2] in regs:
                    regs[p[1]] = regs[p[2]] + int(p[3], 16)
                    note = names.get(regs[p[1]], "")
                if note and len(note) > 180:
                    note = note[:180] + "..."
                print(f" {ins.address:08x}  {ins.mnemonic:8} {ins.op_str:42} {note}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["types", "asm"])
    parser.add_argument("pattern")
    parser.add_argument("--fields", action="store_true")
    parser.add_argument("--limit", type=int, default=2000)
    args = parser.parse_args()
    if args.mode == "types":
        types(args.pattern, args.fields)
    else:
        disassemble(args.pattern, args.limit)
