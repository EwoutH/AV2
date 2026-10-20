#include <stdint.h>
#include <stdio.h>
typedef union { struct { int32_t x, y; }; uint64_t n; } mv;
struct A { mv m[2]; int16_t pair; };
int main(int argc, char **argv) {
    (void) argv;
    mv src = { .n = 0x500000003ull };
    struct A a = { .pair = -1, .m[0] = src, .m[1].n = 7 };
    printf(".m[0] = union, .m[1].n      [0]=%#llx [1]=%#llx %s\n", (unsigned long long) a.m[0].n, (unsigned long long) a.m[1].n, a.m[0].n == src.n && a.m[1].n == 7 ? "ok" : "WRONG");
    struct A b = { .m[0].y = argc + 1, .m[0].x = argc + 2 };
    printf(".m[0].y, .m[0].x            y=%d x=%d %s\n", b.m[0].y, b.m[0].x, b.m[0].y == argc + 1 && b.m[0].x == argc + 2 ? "ok" : "WRONG");
    struct A c = { .m[0].x = 3, .m[1].x = 4 };
    printf(".m[0].x, .m[1].x            [0].x=%d [1].x=%d %s\n", c.m[0].x, c.m[1].x, c.m[0].x == 3 && c.m[1].x == 4 ? "ok" : "WRONG");
    struct A d = { .m[1].n = 7, .m[0] = src };
    printf(".m[1].n, .m[0] = union      [0]=%#llx [1]=%#llx %s\n", (unsigned long long) d.m[0].n, (unsigned long long) d.m[1].n, d.m[0].n == src.n && d.m[1].n == 7 ? "ok" : "WRONG");
    return 0;
}
