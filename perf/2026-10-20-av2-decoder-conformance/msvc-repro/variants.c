#include <stdint.h>
#include <stdio.h>
#define P(name, a, b) printf("%-44s [0]=%#llx [1]=%#llx %s\n", name, (unsigned long long)(a), (unsigned long long)(b), ((a) == 5 && (b) == 7) ? "ok" : "WRONG")

typedef union { struct { int32_t x, y; }; uint64_t n; } U_anon;      /* dav2d's union mv */
typedef union { struct { int32_t x, y; } s; uint64_t n; } U_named;
typedef union { uint64_t n; struct { int32_t x, y; }; } U_n_first;
typedef union { uint64_t n; uint32_t w[2]; } U_noStruct;
typedef struct { uint64_t n; } S_plain;

struct A { U_anon m[2]; };
struct B { U_named m[2]; };
struct C { U_n_first m[2]; };
struct D { U_noStruct m[2]; };
struct E { S_plain m[2]; };
struct F { uint64_t m[2]; };

int main(void) {
    struct A a = { .m[0].n = 5, .m[1].n = 7 };  P("union{anon struct; u64 n}  .m[i].n", a.m[0].n, a.m[1].n);
    struct B b = { .m[0].n = 5, .m[1].n = 7 };  P("union{named struct; u64 n} .m[i].n", b.m[0].n, b.m[1].n);
    struct C c = { .m[0].n = 5, .m[1].n = 7 };  P("union{u64 n; anon struct}  .m[i].n", c.m[0].n, c.m[1].n);
    struct D d = { .m[0].n = 5, .m[1].n = 7 };  P("union{u64 n; u32 w[2]}     .m[i].n", d.m[0].n, d.m[1].n);
    struct E e = { .m[0].n = 5, .m[1].n = 7 };  P("struct{u64 n}              .m[i].n", e.m[0].n, e.m[1].n);
    struct F f = { .m[0] = 5, .m[1] = 7 };      P("u64                        .m[i]", f.m[0], f.m[1]);
    U_anon g[2] = { [0].n = 5, [1].n = 7 };     P("bare array of union{anon}  [i].n", g[0].n, g[1].n);
    struct A h = { .m = { [0].n = 5, [1].n = 7 } }; P("union{anon} .m = {[i].n}", h.m[0].n, h.m[1].n);
    struct A k; k.m[0].n = 5; k.m[1].n = 7;      P("union{anon} assignment", k.m[0].n, k.m[1].n);
    return 0;
}
