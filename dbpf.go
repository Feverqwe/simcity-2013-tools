package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"sort"
)

type resourceID struct{ kind, group, instance uint32 }
type resources map[resourceID][]byte

var le = binary.LittleEndian
var be = binary.BigEndian

func readPackage(path string, selectID func(resourceID) bool) (resources, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	var header [96]byte
	if _, err := io.ReadFull(file, header[:]); err != nil {
		return nil, err
	}
	if string(header[:4]) != "DBPF" || le.Uint32(header[4:]) != 3 {
		return nil, fmt.Errorf("unsupported DBPF version")
	}
	count, size, offset := le.Uint32(header[36:]), le.Uint32(header[44:]), le.Uint32(header[64:])
	info, err := file.Stat()
	if err != nil {
		return nil, err
	}
	if offset < 96 || size < 4 || uint64(offset)+uint64(size) > uint64(info.Size()) || size > 64<<20 {
		return nil, fmt.Errorf("invalid DBPF index bounds")
	}
	index := make([]byte, size)
	if _, err := file.ReadAt(index, int64(offset)); err != nil {
		return nil, err
	}
	flags := le.Uint32(index)
	if flags < 4 || flags > 7 {
		return nil, fmt.Errorf("unsupported DBPF index flags")
	}
	var shared [3]uint32
	cursor, recordSize := 4, 32
	for field := range shared {
		if flags&(1<<field) != 0 {
			if cursor+4 > len(index) {
				return nil, io.ErrUnexpectedEOF
			}
			shared[field] = le.Uint32(index[cursor:])
			cursor += 4
			recordSize -= 4
		}
	}
	if uint64(cursor)+uint64(count)*uint64(recordSize) != uint64(size) {
		return nil, fmt.Errorf("invalid DBPF index length")
	}
	result := make(resources)
	for range count {
		fields := shared
		for field := range fields {
			if flags&(1<<field) == 0 {
				fields[field] = le.Uint32(index[cursor:])
				cursor += 4
			}
		}
		record := index[cursor : cursor+20]
		cursor += 20
		id := resourceID{fields[0], fields[1], le.Uint32(record)}
		if !selectID(id) {
			continue
		}
		position := le.Uint32(record[4:])
		stored := le.Uint32(record[8:]) & 0x7fffffff
		expanded := le.Uint32(record[12:])
		if _, exists := result[id]; exists || position < 96 ||
			uint64(position)+uint64(stored) > uint64(info.Size()) ||
			stored > 16<<20 || expanded > 16<<20 {
			return nil, fmt.Errorf("invalid resource %08x:%08x:%08x", id.kind, id.group, id.instance)
		}
		raw := make([]byte, stored)
		if _, err := file.ReadAt(raw, int64(position)); err != nil {
			return nil, err
		}
		switch le.Uint16(record[16:]) {
		case 0xffff:
			raw, err = refpack(raw, int(expanded))
			if err != nil {
				return nil, err
			}
		case 0:
		default:
			return nil, fmt.Errorf("unsupported resource compression")
		}
		if len(raw) != int(expanded) {
			return nil, fmt.Errorf("unexpected resource size")
		}
		result[id] = raw
	}
	return result, nil
}

func refpack(data []byte, expected int) ([]byte, error) {
	if len(data) < 2 || data[0]&0x3e != 0x10 || data[1] != 0xfb {
		return nil, fmt.Errorf("invalid RefPack header")
	}
	width := 3
	if data[0]&0x80 != 0 {
		width = 4
	}
	cursor := 2 + width
	if data[0]&1 != 0 {
		cursor += width
	}
	if cursor > len(data) {
		return nil, io.ErrUnexpectedEOF
	}
	size := uint32(0)
	for _, value := range data[2 : 2+width] {
		size = size<<8 | uint32(value)
	}
	if size != uint32(expected) {
		return nil, fmt.Errorf("RefPack header size mismatch")
	}
	result := make([]byte, 0, expected)
	for cursor < len(data) {
		code := int(data[cursor])
		cursor++
		extra, literal, length, distance := 0, 0, 0, 0
		switch {
		case code < 0x80:
			extra = 1
		case code < 0xc0:
			extra = 2
		case code < 0xe0:
			extra = 3
		case code < 0xfc:
			literal = (code&31 + 1) * 4
		default:
			literal = code & 3
		}
		if cursor+extra > len(data) {
			return nil, io.ErrUnexpectedEOF
		}
		switch extra {
		case 1:
			literal = code & 3
			length = (code&28)>>2 + 3
			distance = (code&96)<<3 + int(data[cursor]) + 1
		case 2:
			first, second := int(data[cursor]), int(data[cursor+1])
			literal = first >> 6
			length = code&63 + 4
			distance = (first&63)<<8 + second + 1
		case 3:
			first, second, third := int(data[cursor]), int(data[cursor+1]), int(data[cursor+2])
			literal = code & 3
			length = (code&12)<<6 + third + 5
			distance = (code&16)<<12 + first<<8 + second + 1
		}
		cursor += extra
		if cursor+literal > len(data) || len(result)+literal+length > expected || distance > len(result)+literal {
			return nil, fmt.Errorf("invalid RefPack command")
		}
		result = append(result, data[cursor:cursor+literal]...)
		cursor += literal
		for range length {
			result = append(result, result[len(result)-distance])
		}
		if code >= 0xfc {
			break
		}
	}
	if len(result) != expected {
		return nil, fmt.Errorf("RefPack output size mismatch")
	}
	return result, nil
}

func writePackage(records resources) []byte {
	ids := make([]resourceID, 0, len(records))
	for id := range records {
		ids = append(ids, id)
	}
	sort.Slice(ids, func(i, j int) bool {
		a, b := ids[i], ids[j]
		if a.kind != b.kind {
			return a.kind < b.kind
		}
		if a.group != b.group {
			return a.group < b.group
		}
		return a.instance < b.instance
	})
	const headerSize = 96
	indexSize := 8 + 28*len(ids)
	output := make([]byte, headerSize+indexSize)
	copy(output, "DBPF")
	le.PutUint32(output[4:], 3)
	le.PutUint32(output[36:], uint32(len(ids)))
	le.PutUint32(output[44:], uint32(indexSize))
	le.PutUint32(output[60:], 3)
	le.PutUint32(output[64:], headerSize)
	le.PutUint32(output[headerSize:], 4)
	for i, id := range ids {
		raw := records[id]
		fields := [...]uint32{id.kind, id.group, id.instance, uint32(len(output)),
			uint32(len(raw)) | 0x80000000, uint32(len(raw)), 0}
		index := output[headerSize+8+i*28:]
		for field, value := range fields {
			le.PutUint32(index[field*4:], value)
		}
		output = append(output, raw...)
	}
	return output
}

func withoutCategory(raw []byte) ([]byte, error) {
	marker := []byte{0x0d, 0xb9, 0xfc, 0x63, 0x00, 0x20}
	at := bytes.Index(raw, marker)
	if at < 0 {
		return raw, nil
	}
	if at+16 > len(raw) || bytes.Contains(raw[at+1:], marker) {
		return nil, fmt.Errorf("unexpected construction menu category")
	}
	flags := be.Uint16(raw[at+6:])
	count, width := be.Uint32(raw[at+8:]), be.Uint32(raw[at+12:])
	start := at + 16
	if flags&0x30 == 0 || flags&0x40 != 0 || width != 12 || uint64(count)*12 > uint64(len(raw)-start) {
		return nil, fmt.Errorf("unexpected construction menu category format")
	}
	if count == 0 {
		return raw, nil
	}
	end := start + int(count)*12
	updated := make([]byte, len(raw)-(end-start))
	copy(updated, raw[:start])
	be.PutUint32(updated[at+8:], 0)
	copy(updated[start:], raw[end:])
	return updated, nil
}
