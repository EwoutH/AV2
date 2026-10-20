#include <stdint.h>
#include <stdio.h>

typedef union mv {
    struct { int32_t x, y; };
    uint64_t n;
} mv;

typedef struct blk {
    mv mv[2];
    int16_t pair;
    uint8_t bs;
} blk;

#define INVALID_MV 0x200000

int main(int argc, char **argv) {
    (void) argv;
    blk a = (blk) { .pair = -1, .mv[0].n = INVALID_MV, .mv[1].n = INVALID_MV, .bs = (uint8_t) argc };
    blk b = { .pair = -1, .mv[0].n = INVALID_MV, .mv[1].n = INVALID_MV, .bs = (uint8_t) argc };
    blk c = { .mv[0] = { .n = INVALID_MV }, .mv[1] = { .n = INVALID_MV } };
    blk d = { .mv[1].n = INVALID_MV, .mv[0].n = INVALID_MV };
    mv  e[2] = { [0].n = INVALID_MV, [1].n = INVALID_MV };
    printf("compound literal   mv[0].n=%#llx mv[1].n=%#llx\n", (unsigned long long) a.mv[0].n, (unsigned long long) a.mv[1].n);
    printf("initializer        mv[0].n=%#llx mv[1].n=%#llx\n", (unsigned long long) b.mv[0].n, (unsigned long long) b.mv[1].n);
    printf("braced members     mv[0].n=%#llx mv[1].n=%#llx\n", (unsigned long long) c.mv[0].n, (unsigned long long) c.mv[1].n);
    printf("reversed order     mv[0].n=%#llx mv[1].n=%#llx\n", (unsigned long long) d.mv[0].n, (unsigned long long) d.mv[1].n);
    printf("plain array        e[0].n=%#llx  e[1].n=%#llx\n", (unsigned long long) e[0].n, (unsigned long long) e[1].n);
    return 0;
}
