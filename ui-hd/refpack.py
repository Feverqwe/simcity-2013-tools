def refpack(data, expected):
    flags, magic = data[:2]
    width = 4 if flags & 128 else 3
    assert flags & 0x3e == 0x10 and magic == 0xfb
    assert int.from_bytes(data[2:2+width], 'big') == expected
    cursor = 2 + width * (2 if flags & 1 else 1)
    result = bytearray()
    while cursor < len(data):
        code = data[cursor]
        cursor += 1
        length = distance = 0
        if code < 0x80:
            length = ((code & 28) >> 2) + 3
            distance = ((code & 96) << 3) + data[cursor] + 1
            literal = code & 3
            cursor += 1
        elif code < 0xc0:
            first, second = data[cursor:cursor+2]
            length = (code & 63) + 4
            distance = ((first & 63) << 8) + second + 1
            literal = first >> 6
            cursor += 2
        elif code < 0xe0:
            first, second, third = data[cursor:cursor+3]
            length = ((code & 12) << 6) + third + 5
            distance = ((code & 16) << 12) + (first << 8) + second + 1
            literal = code & 3
            cursor += 3
        else:
            literal = (code & 31) * 4 + 4 if code < 0xfc else code & 3
        result.extend(data[cursor:cursor+literal])
        cursor += literal
        for _ in range(length):
            result.append(result[-distance])
        if code >= 0xfc:
            break
    assert len(result) == expected
    return result
