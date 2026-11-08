#!/usr/bin/env python3
"""Bounded, dependency-free parser for 64-bit little-endian Mach-O files."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
LC_DYSYMTAB = 0xB
LC_UNIXTHREAD = 0x5
LC_MAIN = 0x80000028
LC_DYLD_INFO_ONLY = 0x80000022
LC_FUNCTION_STARTS = 0x26
LC_DATA_IN_CODE = 0x29
LC_CODE_SIGNATURE = 0x1D
LC_DYLD_EXPORTS_TRIE = 0x80000033
LC_DYLD_CHAINED_FIXUPS = 0x80000034
LC_UUID = 0x1B
LC_SOURCE_VERSION = 0x2A
LC_BUILD_VERSION = 0x32

COMMAND_NAMES = {
    LC_SEGMENT_64: "LC_SEGMENT_64", LC_SYMTAB: "LC_SYMTAB",
    LC_DYSYMTAB: "LC_DYSYMTAB", LC_UNIXTHREAD: "LC_UNIXTHREAD",
    LC_MAIN: "LC_MAIN", LC_DYLD_INFO_ONLY: "LC_DYLD_INFO_ONLY",
    LC_FUNCTION_STARTS: "LC_FUNCTION_STARTS", LC_DATA_IN_CODE: "LC_DATA_IN_CODE",
    LC_CODE_SIGNATURE: "LC_CODE_SIGNATURE", LC_DYLD_EXPORTS_TRIE: "LC_DYLD_EXPORTS_TRIE",
    LC_DYLD_CHAINED_FIXUPS: "LC_DYLD_CHAINED_FIXUPS",
    LC_UUID: "LC_UUID", LC_SOURCE_VERSION: "LC_SOURCE_VERSION", LC_BUILD_VERSION: "LC_BUILD_VERSION",
}
FILE_TYPES = {1: "MH_OBJECT", 2: "MH_EXECUTE", 6: "MH_DYLIB", 11: "MH_KEXT_BUNDLE"}


class MachOError(ValueError):
    pass


def _range(size, offset, length, label):
    if offset < 0 or length < 0 or offset > size or length > size - offset:
        raise MachOError(f"{label} exceeds file bounds")


def _name(raw):
    return raw.split(b"\0", 1)[0].decode("ascii", "replace")


def inspect(path, max_symbols=200000):
    data = Path(path).read_bytes()
    _range(len(data), 0, 32, "Mach-O header")
    magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags, reserved = struct.unpack_from("<IiiIIIII", data)
    if magic != MH_MAGIC_64:
        raise MachOError("not a little-endian 64-bit Mach-O")
    if ncmds > 65535:
        raise MachOError("unreasonable load-command count")
    _range(len(data), 32, sizeofcmds, "load-command region")
    out = {
        "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
        "header": {"magic": "0xfeedfacf", "cputype": cputype,
                   "architecture": "arm64" if cputype == CPU_TYPE_ARM64 else "unknown",
                   "cpusubtype": cpusubtype, "filetype": filetype,
                   "filetype_name": FILE_TYPES.get(filetype, "UNKNOWN"), "ncmds": ncmds,
                   "sizeofcmds": sizeofcmds, "flags": f"0x{flags:08x}", "reserved": reserved},
        "load_commands": [], "segments": [], "entry": None, "symbol_table": None,
        "relocations": {"section_total": 0, "external": 0, "local": 0}, "fixups": [],
    }
    off = 32
    symtab = None
    for index in range(ncmds):
        _range(len(data), off, 8, f"load command {index}")
        cmd, cmdsize = struct.unpack_from("<II", data, off)
        if cmdsize < 8 or off + cmdsize > 32 + sizeofcmds:
            raise MachOError(f"invalid load command {index} size")
        item = {"index": index, "cmd": f"0x{cmd:08x}", "name": COMMAND_NAMES.get(cmd, "UNKNOWN"), "size": cmdsize}
        if cmd == LC_SEGMENT_64:
            if cmdsize < 72:
                raise MachOError("short LC_SEGMENT_64")
            vals = struct.unpack_from("<II16sQQQQiiII", data, off)
            _, _, rawname, vmaddr, vmsize, fileoff, filesize, maxprot, initprot, nsects, segflags = vals
            if cmdsize != 72 + nsects * 80:
                raise MachOError("LC_SEGMENT_64 section count/size mismatch")
            _range(len(data), fileoff, filesize, f"segment {_name(rawname)}")
            seg = {"name": _name(rawname), "vmaddr": vmaddr, "vmsize": vmsize,
                   "vm_end": vmaddr + vmsize, "fileoff": fileoff, "filesize": filesize,
                   "maxprot": maxprot, "initprot": initprot, "flags": segflags, "sections": []}
            so = off + 72
            for section_index in range(nsects):
                fields = struct.unpack_from("<16s16sQQIIIIIIII", data, so)
                sectname, segname, addr, size, offset, align, reloff, nreloc, sflags, r1, r2, r3 = fields
                if size and offset:
                    _range(len(data), offset, size, f"section {_name(segname)},{_name(sectname)}")
                if nreloc:
                    _range(len(data), reloff, nreloc * 8, f"relocations {_name(sectname)}")
                out["relocations"]["section_total"] += nreloc
                seg["sections"].append({"name": _name(sectname), "segment": _name(segname),
                    "addr": addr, "size": size, "offset": offset, "align": align,
                    "reloff": reloff, "nreloc": nreloc, "flags": f"0x{sflags:08x}"})
                so += 80
            out["segments"].append(seg)
            item["segment"] = seg["name"]
        elif cmd == LC_SYMTAB:
            if cmdsize < 24:
                raise MachOError("short LC_SYMTAB")
            _, _, symoff, nsyms, stroff, strsize = struct.unpack_from("<IIIIII", data, off)
            if nsyms > max_symbols:
                raise MachOError("symbol count exceeds configured bound")
            _range(len(data), symoff, nsyms * 16, "symbol table")
            _range(len(data), stroff, strsize, "string table")
            symtab = (symoff, nsyms, stroff, strsize)
            item.update({"symoff": symoff, "nsyms": nsyms, "stroff": stroff, "strsize": strsize})
        elif cmd == LC_DYSYMTAB:
            if cmdsize < 80:
                raise MachOError("short LC_DYSYMTAB")
            words = struct.unpack_from("<20I", data, off)
            extreloff, nextrel, locreloff, nlocrel = words[16:20]
            if nextrel: _range(len(data), extreloff, nextrel * 8, "external relocations")
            if nlocrel: _range(len(data), locreloff, nlocrel * 8, "local relocations")
            out["relocations"].update({"external": nextrel, "local": nlocrel})
            item.update({"external_relocations": nextrel, "local_relocations": nlocrel})
        elif cmd == LC_MAIN:
            if cmdsize < 24: raise MachOError("short LC_MAIN")
            _, _, entryoff, stacksize = struct.unpack_from("<IIQQ", data, off)
            out["entry"] = {"kind": "LC_MAIN", "file_offset": entryoff, "stacksize": stacksize}
            item.update(out["entry"])
        elif cmd == LC_UNIXTHREAD:
            if cmdsize >= 16:
                flavor, count = struct.unpack_from("<II", data, off + 8)
                item.update({"flavor": flavor, "count": count})
                if cputype == CPU_TYPE_ARM64 and count >= 68 and cmdsize >= 16 + 272:
                    state = struct.unpack_from("<33QII", data, off + 16)
                    pc = state[32]
                    out["entry"] = {"kind": "LC_UNIXTHREAD", "pc": pc, "sp": state[31], "cpsr": state[33]}
                    item.update(out["entry"])
        elif cmd == LC_DYLD_INFO_ONLY:
            if cmdsize < 48: raise MachOError("short LC_DYLD_INFO_ONLY")
            words = struct.unpack_from("<12I", data, off)
            labels = ("rebase", "bind", "weak_bind", "lazy_bind", "export")
            for pos, label in enumerate(labels, 2):
                bloboff, blobsize = words[pos * 2 - 2:pos * 2]
                if blobsize: _range(len(data), bloboff, blobsize, label)
                if blobsize: out["fixups"].append({"kind": label, "offset": bloboff, "size": blobsize})
        elif cmd in (LC_FUNCTION_STARTS, LC_DATA_IN_CODE, LC_CODE_SIGNATURE, LC_DYLD_EXPORTS_TRIE, LC_DYLD_CHAINED_FIXUPS):
            if cmdsize < 16: raise MachOError("short linkedit_data_command")
            _, _, dataoff, datasize = struct.unpack_from("<IIII", data, off)
            if datasize: _range(len(data), dataoff, datasize, item["name"])
            item.update({"dataoff": dataoff, "datasize": datasize})
            if cmd == LC_DYLD_CHAINED_FIXUPS and datasize:
                out["fixups"].append({"kind": "chained", "offset": dataoff, "size": datasize})
        elif cmd == LC_UUID:
            if cmdsize < 24: raise MachOError("short LC_UUID")
            raw = data[off + 8:off + 24].hex()
            item["uuid"] = f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
        elif cmd == LC_SOURCE_VERSION:
            if cmdsize < 16: raise MachOError("short LC_SOURCE_VERSION")
            version = struct.unpack_from("<Q", data, off + 8)[0]
            item["version_raw"] = version
        elif cmd == LC_BUILD_VERSION:
            if cmdsize < 24: raise MachOError("short LC_BUILD_VERSION")
            platform, minos, sdk, ntools = struct.unpack_from("<IIII", data, off + 8)
            if cmdsize != 24 + ntools * 8: raise MachOError("LC_BUILD_VERSION tool count/size mismatch")
            item.update({"platform": platform, "minos": minos, "sdk": sdk, "ntools": ntools})
        out["load_commands"].append(item)
        off += cmdsize
    if off != 32 + sizeofcmds:
        raise MachOError("load commands do not consume sizeofcmds")
    if symtab:
        symoff, nsyms, stroff, strsize = symtab
        names = []
        valued = []
        for i in range(nsyms):
            strx, n_type, n_sect, n_desc, value = struct.unpack_from("<IBBHQ", data, symoff + i * 16)
            if strx >= strsize: raise MachOError("symbol string index out of bounds")
            end = data.find(b"\0", stroff + strx, stroff + strsize)
            if end < 0: raise MachOError("unterminated symbol name")
            names.append(data[stroff + strx:end].decode("utf-8", "replace"))
            if value and names[-1]: valued.append((value, names[-1]))
        out["symbol_table"] = {"count": nsyms, "named": sum(bool(x) for x in names), "names": names}
        if out["entry"] and "pc" in out["entry"]:
            before = [pair for pair in valued if pair[0] <= out["entry"]["pc"]]
            if before:
                value, name = max(before)
                out["entry"]["nearest_symbol"] = name
                out["entry"]["symbol_address"] = value
                out["entry"]["symbol_offset"] = out["entry"]["pc"] - value
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = inspect(args.file)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output: args.output.write_text(rendered)
    else: print(rendered, end="")


if __name__ == "__main__":
    main()
