"""Prepare a new hook for an existing seed without regenerating its static pack.

Usage: python -m src.patcher.update_hook OLD_HOOK OUTPUT_HOOK
The seed table and fingerprint are retained; only supported capabilities change.
"""
import re
import struct
import sys
from pathlib import Path

from .core import ROOT
from botw_static.protocol import PROTOCOL as P


def upgrade_hook(source: str) -> str:
    begin = source.index('_AP_Mailbox_Base:\n')
    end = source.index('_AP_Is_Injecting:', begin)
    block = source[begin:end]
    words = re.findall(r'0x[0-9A-F]{8}', block)
    data = bytearray(struct.pack(f'>{len(words)}I', *(int(word, 16) for word in words)))
    if (len(data) != P['mailbox_size'] or data[:8] != b'APMBBOTW'
            or data[P['extension_offset']:P['extension_offset']+4] != b'APV2'
            or struct.unpack_from('>I', data, P['version_offset'])[0] != P['version']
            or struct.unpack_from('>I', data, P['configured_offset'])[0] != 1):
        raise ValueError('A configured protocol v2 seed hook is required')
    # Keep every seed-bound byte, including the legacy starting-state identity.
    index = P['capabilities_offset'] // 4
    capability = int(words[index], 16) | sum(P['capabilities'].values())
    matches = list(re.finditer(r'0x[0-9A-F]{8}', block))
    span = matches[index].span()
    block = block[:span[0]] + f'0x{capability:08X}' + block[span[1]:]
    template = (ROOT / 'src/hook/patch_Archipelago.asm').read_text()
    start, stop = template.index('_AP_Mailbox_Base:\n'), template.index('_AP_Is_Injecting:')
    return template[:start] + block + template[stop:]


def main():
    source, output = map(Path, sys.argv[1:])
    if source.resolve() == output.resolve():
        raise ValueError('Write to a separate output file for review before installation')
    output.write_text(upgrade_hook(source.read_text()))
    print(f'Prepared updated seed hook: {output}')


if __name__ == '__main__':
    main()
