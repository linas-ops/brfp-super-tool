"""Offline FETP v4 container writer, as serialized by FET 2.2.0.

This module never loads the editor or game. The template header is copied as
opaque bytes. Asset payloads must already contain valid game asset identities
and references: this writer does not rewrite EBX imports, RES internals, BRTs,
shader keys, mesh data, or resource identifiers inside payloads.

write_project(template, output, inherit=False, ebx=[...], resources=[...],
              chunks=[...], addedbundles=[...], shader_sources=[...]) starts a
clean project. The inherit choice is mandatory. True retains source records.
Each asset accepts raw=bytes (stored in CAS None blocks) or encoded=bytes plus
original_size (pre-encoded CAS bytes, retained exactly).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import tempfile
import uuid


def uint(value, width=1):
    return int(value).to_bytes(width, "little", signed=False)


def encode7(value):
    value = int(value)
    if value < 0 or value > 0x7fffffff:
        raise ValueError("7-bit encoded length must fit positive .NET Int32")
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def string(value):
    encoded = str(value).encode("utf8")
    return encode7(len(encoded)) + encoded


def guid(value):
    return uuid.UUID(str(value)).bytes_le


def hash20(value):
    result = bytes.fromhex(value) if isinstance(value, str) else bytes(value)
    if len(result) != 20:
        raise ValueError("Expected 20-byte SHA1")
    return result


def bytes16(value):
    result = bytes.fromhex(value) if isinstance(value, str) else bytes(value)
    if len(result) != 16:
        raise ValueError("Expected 16-byte RES metadata")
    return result


def bundles(values):
    return encode7(len(values)) + b"".join(uint(v, 8) for v in values)


def links(values):
    result = bytearray(encode7(len(values)))
    for entry in values:
        kind, value = entry["type"], entry["value"]
        if kind not in (0, 1, 2, 3):
            raise ValueError("Link type must be Ebx0, Res1, Chunk2, Legacy3")
        result += uint(kind)
        result += guid(value) if kind == 2 else uint(value, 8) if kind == 3 else string(value)
    return bytes(result)


def compress_none(data):
    """Frostbite CAS block framing, no compression, maximum 64 KiB per block."""
    data = bytes(data)
    return b"".join(struct.pack(">II", len(block), 0x00700000 | len(block)) + block
                    for block in (data[i:i + 65536] for i in range(0, len(data), 65536)))


def decompress_none(data):
    """Validate and decode only codec-0 CAS blocks; never load native libraries."""
    data = bytes(data)
    pos = 0
    result = bytearray()
    while pos < len(data):
        if len(data) - pos < 8:
            raise ValueError("Truncated CAS header")
        a, b = struct.unpack_from(">II", data, pos)
        pos += 8
        size, codec, length = a & 0xffffff, b >> 24, b & 0xfffff
        if a >> 24 or codec or ((b >> 20) & 15) != 7 or length != size:
            raise ValueError("Expected codec-0 uncompressed CAS block")
        if pos + length > len(data):
            raise ValueError("Truncated CAS payload")
        result += data[pos:pos + length]
        pos += length
    return bytes(result)


def payload(entry):
    if ("raw" in entry) == ("encoded" in entry):
        raise ValueError("Supply exactly one of raw or encoded")
    if "raw" in entry:
        raw = _byte_payload(entry["raw"])
        encoded = compress_none(raw)
        size, level = len(raw), 8
    else:
        encoded = _byte_payload(entry["encoded"])
        size, level = int(entry.get("original_size", cas_original_size(encoded))), int(entry.get("compression_level", 8))
        declared, codecs = _cas_frames(encoded)
        if declared != size:
            raise ValueError("CAS declared size does not match original_size")
        if level == 8 and any(codec != 0 for codec in codecs):
            raise ValueError("Compression level None requires codec-0 CAS blocks")
    if not encoded:
        raise ValueError("Empty asset payload is not supported")
    return encoded, size, level, hashlib.sha1(encoded).digest()


def _byte_payload(value):
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("Payload must be bytes, bytearray or memoryview")
    return bytes(value)


def _cas_frames(data):
    """Check every frame without decoding proprietary codecs; return size/codecs."""
    pos, size, codecs = 0, 0, set()
    while pos < len(data):
        if len(data) - pos < 8:
            raise ValueError("Truncated CAS header")
        a, b = struct.unpack_from(">II", data, pos)
        declared, codec, length = a & 0xffffff, b >> 24, b & 0xfffff
        if a >> 24 or ((b >> 20) & 15) != 7 or pos + 8 + length > len(data):
            raise ValueError("Invalid CAS block framing")
        if not declared or not length:
            raise ValueError("Empty CAS block is outside this profile")
        if codec == 0 and length != declared:
            raise ValueError("Codec-0 CAS stored size differs from declared size")
        codecs.add(codec)
        size += declared
        pos += 8 + length
    if not pos:
        raise ValueError("Empty asset payload is outside this profile")
    return size, codecs


def cas_original_size(data):
    """Sum declared CAS block sizes without decompressing or running a codec."""
    return _cas_frames(data)[0]


def write_chunk(entry, patch):
    encoded, _, level, digest = payload(entry)
    added = bool(entry.get("is_added", True))
    if not added and "original_sha1" not in entry:
        raise ValueError("Existing chunk requires original_sha1 from the native game asset")
    membership = entry.get("addedbundles", [])
    logical_offset, logical_size, h32 = (entry.get(n, 0) for n in ("logical_offset", "logical_size", "h32"))
    sbhash = entry.get("superbundlehash", 0)
    legacy = "legacyhash" in entry
    if added and entry.get("bundle_assignment_only"):
        raise ValueError("An added chunk cannot be bundle-assignment-only")
    if sbhash and not added:
        raise ValueError("Only added chunks can specify a superbundlehash")
    flags = int(added) | (2 if legacy else 0) | (4 if sbhash else 0)
    flags |= (8 if logical_offset else 0) | (16 if logical_size else 0) | (32 if h32 else 0)
    flags |= (64 if "legacyname" in entry else 0) | (128 if membership else 0)
    flags |= 256 if entry.get("bundle_assignment_only") else 0
    if "legacyname" in entry and not legacy:
        raise ValueError("legacyname requires legacyhash")
    result = bytearray(guid(entry["id"]) + uint(flags, 2) + digest)
    if logical_offset:
        result += encode7(logical_offset)
    if logical_size:
        result += encode7(logical_size)
    if h32:
        result += uint(h32, 8)
    result += encode7(len(encoded))
    if legacy:
        result += uint(entry["legacyhash"], 8)
        if "legacyname" in entry:
            result += string(entry["legacyname"])
    result += uint(entry.get("patch", patch), 3)
    if not added:
        result += hash20(entry["original_sha1"])
    if membership:
        result += bundles(membership)
    if sbhash:
        result += uint(sbhash, 4)
    result += uint(level) + encoded
    return bytes(result)


def write_res(entry, patch, shader_source_indices):
    added = bool(entry.get("is_added", True))
    direct = entry.get("direct", "raw" in entry or "encoded" in entry)
    membership, linked = entry.get("addedbundles", []), entry.get("links", [])
    meta = entry.get("resmeta")
    regs = entry.get("shader_registrations", [])
    if added and not direct:
        raise ValueError("An added RES must have payload")
    if not direct and ("raw" in entry or "encoded" in entry or meta is not None):
        raise ValueError("RES direct=False would discard payload or resmeta")
    if not added and ("restype" in entry or "resrid" in entry):
        raise ValueError("Existing RES cannot serialize restype/resrid; resolve these from the native index")
    if added and entry.get("bundle_assignment_only"):
        raise ValueError("An added RES cannot be bundle-assignment-only")
    if direct and not added and "original_sha1" not in entry:
        raise ValueError("Existing RES requires original_sha1 from the native game asset")
    if (membership or entry.get("bundle_assignment_only") or regs) and not direct:
        raise ValueError("RES membership/assignment/shader registrations require payload")
    if added and meta is None:
        raise ValueError("Added RES requires 16-byte resmeta")
    if regs and entry.get("bundle_assignment_only"):
        raise ValueError("Shader registration is incompatible with bundle_assignment_only")
    flags = int(added) | (2 if direct else 0) | (4 if meta is not None else 0)
    flags |= (8 if linked else 0) | (16 if membership else 0)
    flags |= (32 if entry.get("bundle_assignment_only") else 0) | (64 if regs else 0)
    result = bytearray(string(entry["name"]) + uint(flags))
    if direct:
        encoded, size, level, digest = payload(entry)
        if added:
            result += uint(entry["restype"], 4) + uint(entry["resrid"], 8)
        result += digest + encode7(size)
        if meta is not None:
            result += bytes16(meta)
        result += uint(entry.get("patch", patch), 3)
        if not added:
            result += hash20(entry["original_sha1"])
        if membership:
            result += bundles(membership)
        result += uint(level) + encode7(len(encoded)) + encoded
        if regs:
            result += encode7(len(regs))
            for registration in regs:
                new_key, source_key = registration
                result += uint(new_key, 8) + encode7(shader_source_indices[source_key])
    if linked:
        result += links(linked)
    return bytes(result)


def write_ebx(entry, patch):
    added = bool(entry.get("is_added", True))
    direct = entry.get("direct", "raw" in entry or "encoded" in entry)
    membership, linked = entry.get("addedbundles", []), entry.get("links", [])
    brthash = entry.get("brthash", 0)
    if added and not direct:
        raise ValueError("An added EBX must have payload")
    if not direct and ("raw" in entry or "encoded" in entry):
        raise ValueError("EBX direct=False would discard payload")
    if not added and ("type" in entry or "partition" in entry):
        raise ValueError("Existing EBX cannot serialize type/partition; resolve these from its payload/native index")
    if added and entry.get("bundle_assignment_only"):
        raise ValueError("An added EBX cannot be bundle-assignment-only")
    if direct and not added and "original_sha1" not in entry:
        raise ValueError("Existing EBX requires original_sha1 from the native game asset")
    if (membership or brthash or entry.get("bundle_assignment_only")) and not direct:
        raise ValueError("EBX membership/BRT/assignment requires payload")
    if (entry.get("parentbrtpath") is not None or entry.get("bundle_ref_only")) and not brthash:
        raise ValueError("Parent/ref-only BRT settings require brthash")
    flags = int(added) | (2 if direct else 0) | (4 if brthash else 0) | (8 if linked else 0)
    flags |= (16 if membership else 0) | (32 if entry.get("bundle_assignment_only") else 0)
    flags |= (64 if entry.get("parentbrtpath") is not None else 0) | (128 if entry.get("bundle_ref_only") else 0)
    result = bytearray(string(entry["name"]) + uint(flags))
    if direct:
        encoded, size, level, digest = payload(entry)
        if added:
            result += string(entry["type"]) + guid(entry["partition"])
        result += uint(entry.get("patch", patch), 3)
        if not added:
            result += hash20(entry["original_sha1"])
        if brthash:
            result += uint(brthash, 4) + string(entry["brtpath"])
            if entry.get("parentbrtpath") is not None:
                result += string(entry["parentbrtpath"])
        if membership:
            result += bundles(membership)
        result += digest + encode7(size) + uint(level) + encode7(len(encoded)) + encoded
    if linked:
        result += links(linked)
    return bytes(result)


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError(f"Read beyond file at {self.pos}, size {size}")
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def u(self, size=1):
        return int.from_bytes(self.take(size), "little")

    def seven(self):
        result = 0
        for shift in range(0, 35, 7):
            value = self.u()
            result |= (value & 127) << shift
            if not value & 128:
                if result > 0x7fffffff:
                    raise ValueError("Out-of-range 7-bit integer")
                return result
        raise ValueError("Invalid 7-bit integer")

    def string(self):
        return self.take(self.seven()).decode("utf8")

    def guid(self):
        return str(uuid.UUID(bytes_le=self.take(16)))

    def bundles(self):
        return [self.u(8) for _ in range(self.seven())]

    def links(self):
        result = []
        for _ in range(self.seven()):
            kind = self.u()
            if kind not in (0, 1, 2, 3):
                raise ValueError("Unknown linked asset kind")
            value = self.guid() if kind == 2 else self.u(8) if kind == 3 else self.string()
            result.append({"type": kind, "value": value})
        return result


def read_project(path):
    """Independent structural reader; accepts the empty texture-quality header."""
    return read_project_bytes(Path(path).read_bytes())


def read_project_bytes(data):
    """Read the same limited FETP-v4 profile from an immutable byte buffer."""
    data = _byte_payload(data)
    r = Reader(data)
    if r.take(5) != b"FETP\x04":
        raise ValueError("Expected FETP version 4")
    header = {"version": list(r.take(4)), "game": r.string(), "patch": r.u(3), "exe": r.u(4)}
    header.update(title=r.string(), author=r.string(), category=r.u(), subcategory=r.u())
    for name in ("customcategory", "secondcategory", "modversion", "description", "website", "discord", "patreon", "twitter", "youtube", "instagram", "facebook", "customlink"):
        header[name] = r.string()
    icon_length = r.seven()
    r.take(icon_length)
    if icon_length:
        r.take(8)
    for _ in range(r.seven()):
        r.take(r.seven())
    for _ in range(r.seven()):
        r.string(); r.string()
    for _ in range(r.seven()):
        r.string(); r.take(r.seven())
    for _ in range(r.seven()):
        r.string(); r.take(r.seven())
    for _ in range(r.seven()):
        r.string()
        for _ in range(r.seven()):
            r.string()
            for _ in range(r.seven()):
                r.string()
    if r.u() != 0:
        raise ValueError("Nonempty texture-quality header is not yet decoded")
    header["end"] = r.pos
    addedbundles = [{"name": r.string(), "superbundle": r.u(4), "type": r.u()} for _ in range(r.u(3))]
    chunks = []
    for _ in range(r.u(3)):
        e = {"kind": "chunk", "record_start": r.pos, "id": r.guid(), "flags": r.u(2)}
        flags = e["flags"]
        e["sha1"] = r.take(20).hex()
        for key, mask, width in (("logical_offset", 8, 0), ("logical_size", 16, 0), ("h32", 32, 8)):
            if flags & mask:
                e[key] = r.u(width) if width else r.seven()
        size = r.seven()
        if flags & 2:
            e["legacyhash"] = r.u(8)
            if flags & 64:
                e["legacyname"] = r.string()
        e["patch"] = r.u(3)
        if not flags & 1:
            e["original_sha1"] = r.take(20).hex()
        if flags & 128:
            e["addedbundles"] = r.bundles()
        if flags & 4:
            e["superbundlehash"] = r.u(4)
        e["compression_level"] = r.u()
        e["data_offset"], e["data_size"] = r.pos, size
        r.take(size)
        e["record_end"] = r.pos
        chunks.append(e)
    resources = []
    for _ in range(r.u(3)):
        e = {"kind": "res", "record_start": r.pos, "name": r.string(), "flags": r.u()}
        flags = e["flags"]
        if flags & 2:
            if flags & 1:
                e.update(restype=r.u(4), resrid=r.u(8))
            e.update(sha1=r.take(20).hex(), original_size=r.seven())
            if flags & 4:
                e["resmeta"] = r.take(16).hex()
            e["patch"] = r.u(3)
            if not flags & 1:
                e["original_sha1"] = r.take(20).hex()
            if flags & 16:
                e["addedbundles"] = r.bundles()
            e["compression_level"] = r.u()
            e["data_size"] = r.seven()
            e["data_offset"] = r.pos
            r.take(e["data_size"])
            if flags & 64:
                e["shader_registrations"] = [(r.u(8), r.seven()) for _ in range(r.seven())]
        if flags & 8:
            e["links"] = r.links()
        e["record_end"] = r.pos
        resources.append(e)
    shader_sources = [r.u(8) for _ in range(r.seven())]
    ebx = []
    for _ in range(r.u(3)):
        e = {"kind": "ebx", "record_start": r.pos, "name": r.string(), "flags": r.u()}
        flags = e["flags"]
        if flags & 2:
            if flags & 1:
                e.update(type=r.string(), partition=r.guid())
            e["patch"] = r.u(3)
            if not flags & 1:
                e["original_sha1"] = r.take(20).hex()
            if flags & 4:
                e.update(brthash=r.u(4), brtpath=r.string())
                if flags & 64:
                    e["parentbrtpath"] = r.string()
            if flags & 16:
                e["addedbundles"] = r.bundles()
            e.update(sha1=r.take(20).hex(), original_size=r.seven(), compression_level=r.u())
            e["data_size"] = r.seven()
            e["data_offset"] = r.pos
            r.take(e["data_size"])
        if flags & 8:
            e["links"] = r.links()
        e["record_end"] = r.pos
        ebx.append(e)
    if r.pos != len(data):
        raise ValueError(f"Unconsumed bytes at {r.pos}/{len(data)}")
    return {"header": header, "bytes": data, "addedbundles": addedbundles, "chunks": chunks,
            "resources": resources, "shadersources": shader_sources, "ebx": ebx,
            "sha256": hashlib.sha256(data).hexdigest()}


def audit_project(parsed):
    """Audit container identities/flags/CAS integrity, not EBX or game semantics.

    Compressed proprietary codecs are not decoded. Successful framing and size
    checks for those codecs are explicitly reported as a remaining limitation.
    The input must be the unmodified dictionary returned by read_project*().
    """
    errors, warnings = [], []
    data = parsed["bytes"]
    counts = {key: len(parsed[key]) for key in ("addedbundles", "chunks", "resources", "ebx")}
    decoded_codecs, payloads_checked = set(), 0

    def unique(values, label):
        seen = set()
        for value in values:
            if value in seen:
                errors.append(f"Duplicate {label}: {value}")
            seen.add(value)

    unique((entry["name"].lower() for entry in parsed["addedbundles"]), "bundle name")
    for entry in parsed["addedbundles"]:
        if not entry["name"] or "\0" in entry["name"]:
            errors.append("Empty/NUL-containing bundle name")
    source_keys = parsed["shadersources"]
    if len(set(source_keys)) != len(source_keys):
        warnings.append("Repeated shader source keys are retained at their existing indices")
    registered, legacy_hashes, partitions, resrids = [], [], [], []
    for kind, mask in (("chunks", 0x1ff), ("resources", 0x7f), ("ebx", 0xff)):
        entries = parsed[kind]
        key_name = "id" if kind == "chunks" else "name"
        unique((str(entry[key_name]).lower() for entry in entries), f"{kind} identity")
        for entry in entries:
            label = f"{kind}:{entry[key_name]}"
            flags = entry["flags"]
            direct = True if kind == "chunks" else bool(flags & 2)
            added = bool(flags & 1)
            assignment = bool(flags & (256 if kind == "chunks" else 32))
            if flags & ~mask:
                errors.append(f"{label}: unknown flags 0x{flags & ~mask:X}")
            if not str(entry[key_name]) or "\0" in str(entry[key_name]):
                errors.append(f"{label}: empty/NUL-containing identity")
            if added and not direct:
                errors.append(f"{label}: added asset has no direct payload")
            if added and assignment:
                errors.append(f"{label}: added asset cannot be bundle-assignment-only")
            if kind != "chunks" and not direct and flags & (16 | 32):
                errors.append(f"{label}: bundle membership/assignment requires a payload")
            if len(set(entry.get("addedbundles", []))) != len(entry.get("addedbundles", [])):
                errors.append(f"{label}: repeated added-bundle membership")
            if not 0 <= entry["record_start"] <= entry["record_end"] <= len(data):
                errors.append(f"{label}: record bounds are invalid")
            if kind == "chunks":
                if flags & 64 and not flags & 2:
                    errors.append(f"{label}: legacy-name flag requires legacy-file flag")
                if flags & 4 and not added:
                    errors.append(f"{label}: superbundle flag is only supported on added chunks")
                if "legacyhash" in entry:
                    legacy_hashes.append(entry["legacyhash"])
            elif kind == "resources":
                if not direct and flags & (4 | 64):
                    errors.append(f"{label}: resmeta/shader flags require a payload")
                if flags & 64 and assignment:
                    errors.append(f"{label}: shader registration and assignment-only are incompatible")
                if added and direct and not flags & 4:
                    errors.append(f"{label}: added RES requires resmeta")
                if "resrid" in entry:
                    resrids.append(entry["resrid"])
                for new_key, source_index in entry.get("shader_registrations", []):
                    registered.append(new_key)
                    if not 0 <= source_index < len(source_keys):
                        errors.append(f"{label}: shader source index {source_index} is out of bounds")
            elif kind == "ebx":
                if flags & (64 | 128) and not flags & 4:
                    errors.append(f"{label}: parent/ref-only BRT flags require a BRT")
                if flags & 4 and not direct:
                    errors.append(f"{label}: BRT requires a payload")
                if "partition" in entry:
                    partitions.append(entry["partition"].lower())
                if added and direct and not entry.get("type"):
                    errors.append(f"{label}: added EBX type is empty")
            for link in entry.get("links", []):
                if link["type"] not in (0, 1, 2, 3):
                    errors.append(f"{label}: unknown linked asset kind")
            if "data_offset" not in entry:
                if direct:
                    errors.append(f"{label}: missing direct payload location")
                continue
            offset, length = entry["data_offset"], entry["data_size"]
            if not entry["record_start"] <= offset <= offset + length <= entry["record_end"]:
                errors.append(f"{label}: payload bounds are invalid")
                continue
            encoded = data[offset:offset + length]
            payloads_checked += 1
            if hashlib.sha1(encoded).hexdigest() != entry.get("sha1"):
                errors.append(f"{label}: encoded payload SHA1 mismatch")
            if assignment and entry.get("sha1") != entry.get("original_sha1"):
                errors.append(f"{label}: assignment-only payload differs from the original native SHA1")
            try:
                declared, codecs = _cas_frames(encoded)
                if "original_size" in entry and declared != entry["original_size"]:
                    errors.append(f"{label}: CAS declared size differs from original_size")
                if entry.get("compression_level") == 8 and any(codec != 0 for codec in codecs):
                    errors.append(f"{label}: compression level None contains a compressed CAS codec")
                decoded_codecs.update(codecs - {0})
            except (ValueError, struct.error) as exc:
                errors.append(f"{label}: {exc}")
    unique(partitions, "added EBX partition GUID")
    unique(resrids, "added RES RID")
    unique(legacy_hashes, "legacy file hash")
    unique(registered, "global shader registration key")
    if decoded_codecs:
        warnings.append("CAS codec(s) " + ", ".join(map(str, sorted(decoded_codecs))) + " were not decompressed; only SHA1, framing and declared sizes were checked")
    if parsed["addedbundles"]:
        warnings.append("Bundle-name hashes and native-cache collisions require a separate target-version check")
    warnings.append("EBX/RES semantics, linked-asset resolution, editor export and game runtime were not validated by this container audit")
    return {"container_valid": not errors, "errors": errors, "warnings": warnings,
            "counts": counts, "payloads_checked": payloads_checked}


def publish_project_bytes(data, output, *, expected_header=None):
    """Validate first; publish a staged file atomically without replacing output.

    On Windows, same-directory os.rename is atomic and refuses an existing
    destination. On POSIX, use os.link for atomic create-if-absent publication;
    POSIX rename would replace a destination and is deliberately not used.
    """
    data = _byte_payload(data)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Refusing to overwrite output: {output}")
    parsed = read_project_bytes(data)
    report = audit_project(parsed)
    if not report["container_valid"]:
        raise ValueError("Container audit failed: " + "; ".join(report["errors"]))
    if expected_header is not None and data[:parsed["header"]["end"]] != _byte_payload(expected_header):
        raise ValueError("Template header was not preserved")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staging = tempfile.mkstemp(prefix="." + output.name + ".", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        staged = read_project(staging)
        staged_report = audit_project(staged)
        if not staged_report["container_valid"] or staged["bytes"] != data:
            raise ValueError("Staged project failed integrity verification")
        if os.name == "nt":
            os.rename(staging, output)
        else:
            os.link(staging, output)
    finally:
        try:
            os.unlink(staging)
        except FileNotFoundError:
            pass  # Windows rename consumed the staging path.
    return parsed


def asset_from_record(project, entry):
    """Translate a parsed record to writer input, retaining its encoded payload.

    A caller cloning this input must explicitly replace identity fields and
    payload imports. This function itself never creates new identifiers.
    """
    fields = ("name", "id", "type", "partition", "restype", "resrid", "resmeta",
              "patch", "original_sha1", "addedbundles", "links", "logical_offset",
              "logical_size", "h32", "superbundlehash", "legacyhash", "legacyname",
              "brthash", "brtpath", "parentbrtpath", "original_size", "compression_level")
    result = {key: entry[key] for key in fields if key in entry}
    flags, kind = entry["flags"], entry["kind"]
    result["is_added"] = bool(flags & 1)
    result["bundle_assignment_only"] = bool(flags & (256 if kind == "chunk" else 32))
    if kind != "chunk":
        result["direct"] = bool(flags & 2)
    if kind == "ebx":
        result["bundle_ref_only"] = bool(flags & 128)
    if "data_offset" in entry:
        offset = entry["data_offset"]
        result["encoded"] = project["bytes"][offset:offset + entry["data_size"]]
        if kind == "chunk" and "original_size" not in result:
            result["original_size"] = cas_original_size(result["encoded"])
    if "shader_registrations" in entry:
        result["shader_registrations"] = [(new_key, project["shadersources"][source_index])
                                           for new_key, source_index in entry["shader_registrations"]]
    return result


def remap_links(entries, *, names=None, chunk_ids=None, legacy_hashes=None):
    """Return remapped container link records only, never mutate payload bytes."""
    names, chunk_ids, legacy_hashes = names or {}, chunk_ids or {}, legacy_hashes or {}
    result = []
    for entry in entries:
        kind, value = entry["type"], entry["value"]
        replacement = (chunk_ids if kind == 2 else legacy_hashes if kind == 3 else names).get(value, value)
        result.append({"type": kind, "value": replacement})
    return result


def write_project(template, output, *, inherit, addedbundles=(), chunks=(), resources=(), ebx=(), shader_sources=()):
    """Write and structurally verify a new project; refuse source overwrite.

    addedbundles are dictionaries {name,superbundle:uint32,type:byte}.
    Membership in asset dictionaries uses bundle name hashes (uint64), not cache
    indexes. Legacy/shader/BRT metadata is optional but is serialized when given.
    inherit=False keeps only the source header. inherit=True preserves every
    source asset record byte-for-byte before appending the supplied assets.
    Shader registration tuples are (newKey,sourceKey), never source indexes.
    """
    if not isinstance(inherit, bool):
        raise TypeError("inherit must explicitly be True or False")
    template, output = Path(template).resolve(), Path(output).absolute()
    if output == template or (output.exists() and output.samefile(template)):
        raise ValueError("Refusing to overwrite template")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Refusing to overwrite output: {output}")
    addedbundles, chunks, resources, ebx = map(list, (addedbundles, chunks, resources, ebx))
    parsed = read_project(template)
    template_audit = audit_project(parsed)
    if not template_audit["container_valid"]:
        raise ValueError("Template audit failed: " + "; ".join(template_audit["errors"]))
    # Registrations add keys to the global expression-shader database. The same
    # key in two depots is an error even when both refer to the same source key.
    registered = set()
    if inherit:
        for entry in parsed['resources']:
            for new_key, _ in entry.get('shader_registrations', []):
                if new_key in registered:
                    raise ValueError(f'Duplicate global shader registration 0x{new_key:016X}')
                registered.add(new_key)
    for entry in resources:
        for new_key, _ in entry.get('shader_registrations', []):
            if new_key in registered:
                raise ValueError(f'Duplicate global shader registration 0x{new_key:016X}')
            registered.add(new_key)
    patch = parsed["header"]["patch"]
    source = parsed["bytes"]
    source_bundles = parsed["addedbundles"] if inherit else []
    bundle_list = list(source_bundles) + list(addedbundles)
    source_keys = list(parsed["shadersources"] if inherit else [])
    for key in shader_sources:
        if key not in source_keys:
            source_keys.append(key)
    for entry in resources:
        for _, key in entry.get("shader_registrations", []):
            if key not in source_keys:
                source_keys.append(key)
    shader_indices = {key: index for index, key in enumerate(source_keys)}
    result = bytearray(source[:parsed["header"]["end"]])
    names = [entry["name"].lower() for entry in bundle_list]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate bundle names")
    result += uint(len(bundle_list), 3)
    for entry in bundle_list:
        result += string(entry["name"]) + uint(entry["superbundle"], 4) + uint(entry["type"])
    for kind, entries, writer in (("chunks", chunks, write_chunk), ("resources", resources, write_res), ("ebx", ebx, write_ebx)):
        if kind == "ebx":
            result += bundles(source_keys)
        old = parsed[kind] if inherit else []
        key_name = "id" if kind == "chunks" else "name"
        identities = [str(entry[key_name]).lower() for entry in list(old) + list(entries)]
        if len(identities) != len(set(identities)):
            raise ValueError(f"Duplicate {kind} identities; replace rather than append")
        result += uint(len(old) + len(entries), 3)
        for entry in old:
            result += source[entry["record_start"]:entry["record_end"]]
        for entry in entries:
            result += writer(entry, patch, shader_indices) if kind == "resources" else writer(entry, patch)
    return publish_project_bytes(result, output, expected_header=source[:parsed["header"]["end"]])
