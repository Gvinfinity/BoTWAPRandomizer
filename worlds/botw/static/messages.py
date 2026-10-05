"""Read label/text pairs from BotW MSBT for game-to-reference name binding."""
from __future__ import annotations

import struct


def read_msbt(data: bytes) -> dict[str, str]:
    if data[:8] != b"MsgStdBn":
        raise ValueError("Not an MSBT file")
    endian = ">" if data[8:10] == b"\xfe\xff" else "<"
    if data[12] != 1:
        raise ValueError("Only UTF-16 BotW messages are supported")
    sections, offset = {}, 32
    while offset < len(data):
        size = struct.unpack_from(endian + "I", data, offset + 4)[0]
        sections[data[offset:offset + 4]] = data[offset + 16:offset + 16 + size]
        offset = (offset + 16 + size + 15) & ~15
    labels, label_data = {}, sections[b"LBL1"]
    count = struct.unpack_from(endian + "I", label_data)[0]
    for group in range(count):
        entries, offset = struct.unpack_from(endian + "II", label_data, 4 + group * 8)
        for _ in range(entries):
            length = label_data[offset]
            label = label_data[offset + 1:offset + length + 1].decode("utf-8")
            index = struct.unpack_from(endian + "I", label_data, offset + length + 1)[0]
            labels[index] = label
            offset += length + 5
    texts = sections[b"TXT2"]
    count = struct.unpack_from(endian + "I", texts)[0]
    offsets = list(struct.unpack_from(endian + f"{count}I", texts, 4)) + [len(texts)]
    encoding = "utf-16-be" if endian == ">" else "utf-16-le"
    return {labels[index]: texts[offsets[index]:offsets[index + 1]].decode(encoding).rstrip("\0")
            for index in range(count) if index in labels}


def add_messages(original: bytes, additions: dict[str, str]) -> bytes:
    """Extend the Item table, retaining existing text and fixed ATR1 records."""
    endian = ">" if original[8:10] == b"\xfe\xff" else "<"
    encoding = "utf-16-be" if endian == ">" else "utf-16-le"
    entries = read_msbt(original)
    if set(entries) & set(additions):
        raise ValueError("AP message label already exists")
    sections, offset = {}, 32
    while offset < len(original):
        size = struct.unpack_from(endian + "I", original, offset + 4)[0]
        sections[original[offset:offset + 4]] = original[offset + 16:offset + 16 + size]
        offset = (offset + 16 + size + 15) & ~15
    if set(sections) != {b"LBL1", b"ATR1", b"TXT2"}:
        raise ValueError("Unsupported MSBT sections; preserve instead of guessing metadata")
    original_count, attribute_size = struct.unpack_from(endian + "II", sections[b"ATR1"])
    if original_count != len(entries) or len(sections[b"ATR1"]) != 8 + attribute_size * original_count:
        raise ValueError("Unsupported variable MSBT attribute layout")
    entries.update(additions)
    count = len(entries)
    group_count = struct.unpack_from(endian + "I", sections[b"LBL1"])[0]
    groups = [[] for _ in range(group_count)]
    texts, offsets = bytearray(), []
    for index, (label, text) in enumerate(entries.items()):
        label_bytes = label.encode("utf-8")
        if len(label_bytes) > 255:
            raise ValueError("MSBT label too long")
        crc = 0
        for value in label_bytes:
            crc = (crc * 0x492 + value) & 0xFFFFFFFF
        groups[crc % group_count].append(bytes([len(label_bytes)]) + label_bytes + struct.pack(endian + "I", index))
        offsets.append(4 + count * 4 + len(texts))
        texts.extend((text + "\0").encode(encoding))
    label_header = bytearray(struct.pack(endian + "I", group_count))
    label_body = bytearray()
    for group in groups:
        label_header.extend(struct.pack(endian + "II", len(group), 4 + group_count * 8 + len(label_body)))
        label_body.extend(b"".join(group))
    sections[b"LBL1"] = bytes(label_header + label_body)
    sections[b"TXT2"] = struct.pack(endian + "I", count) + struct.pack(endian + f"{count}I", *offsets) + texts
    # Item attributes in BotW v208 are empty. Nonempty fixed records get neutral
    # records for added names, while every existing attribute is kept verbatim.
    sections[b"ATR1"] = (struct.pack(endian + "II", count, attribute_size)
                          + sections[b"ATR1"][8:] + bytes(attribute_size * len(additions)))
    result = bytearray(original[:32])
    for tag, payload in sections.items():
        result.extend(tag + struct.pack(endian + "I", len(payload)) + bytes(8) + payload)
        result.extend(bytes([0xAB]) * ((-len(result)) % 16))
    struct.pack_into(endian + "I", result, 18, len(result))
    return bytes(result)
