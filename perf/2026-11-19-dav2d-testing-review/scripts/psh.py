import ctypes, struct, sys
L = ctypes.CDLL(sys.argv[1]); buf = ctypes.create_string_buffer(4096)
d = open(sys.argv[2], "rb").read(); p = 32; i = 0; ok = 0
while p + 12 <= len(d):
    sz = struct.unpack("<I", d[p:p+4])[0]; fr = d[p+12:p+12+sz]; p += 12 + sz
    r = L.dav2d_parse_sequence_header(buf, fr, ctypes.c_size_t(len(fr)))
    if i < 3 or r == 0: print("TU", i, "size", sz, "ret", r, "first bytes", fr[:6].hex())
    ok += r == 0; i += 1
print(i, "TUs,", ok, "with a parsable sequence header")
