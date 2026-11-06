/*
 * Host self-test for sdlock: drives sd_card.c against a byte-level
 * simulated SD card in SPI mode.
 *
 *   cc -std=c99 -Wall -Wextra -I../src ../src/sd_proto.c ../src/sd_card.c \
 *      test_sdlock.c -o test_sdlock && ./test_sdlock
 *
 * (tools/sdlock_pico_check.py does exactly this.)
 *
 * The simulator implements CMD0/8/55/41/58/9/13/16/42 with the CMD42
 * semantics of the SD Physical Layer Simplified Spec 4.3.7: set, clear,
 * lock, unlock, combined set+lock, lock-at-power-up when a password is
 * set, LOCK_UNLOCK_FAILED on a wrong password, and forced erase.  The test
 * asserts the driver never sends a command outside its whitelist and never
 * a CMD42 block with the ERASE bit.  Passwords are dummies.
 */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sd_card.h"
#include "sd_proto.h"

/* ---------------------------------------------------------------- sim --- */

enum { S_IDLE, S_CMD, S_WAIT_TOKEN, S_DATA };

typedef struct {
    /* persistent ("flash") */
    uint8_t pwd[SDP_PWD_MAX];
    uint8_t pwd_len;
    int lock_class;      /* CCC bit 7 in CSD                              */
    int no_combined;     /* SET_PWD|LOCK stores but does not lock         */
    /* session */
    int powered, spi, ready, acmd, locked, acmd41_polls;
    uint8_t lk_failed;
    uint32_t blocklen;
    /* wire */
    int cs, state, nbuf;
    uint8_t buf[8], data[600];
    uint8_t q[64];
    int qh, qt;
    int cmd42_count;
    uint32_t ms;
} sim_t;

static sim_t S;
/* audit counters across all scenarios */
static int g_bad_cmd, g_crc_fail, g_erase_frames, g_erased;

static void q_push(uint8_t v) { S.q[S.qt++ % 64] = v; }

static void sim_power_cycle(void)
{
    S.powered = 1;
    S.spi = S.ready = S.acmd = 0;
    S.locked = S.pwd_len > 0; /* a card with a password powers up locked */
    S.lk_failed = 0;
    S.blocklen = 512;
    S.acmd41_polls = 0;
    S.state = S_IDLE;
    S.qh = S.qt = 0;
}

static void lk_process(const uint8_t *d, uint32_t n)
{
    uint8_t f = d[0], len = d[1];
    S.cmd42_count++;
    if (f & SDP_LK_ERASE) {
        g_erase_frames++;
        if (S.locked) {          /* forced erase: password and DATA gone */
            g_erased = 1;
            S.pwd_len = 0;
            S.locked = 0;
        } else {
            S.lk_failed = 1;
        }
        return;
    }
    if (n < 2u + len) { S.lk_failed = 1; return; }
    const uint8_t *p = d + 2;
    if (f & SDP_LK_CLR_PWD) {
        if (S.pwd_len && len == S.pwd_len && !memcmp(p, S.pwd, len)) {
            S.pwd_len = 0;
            S.locked = 0;
        } else {
            S.lk_failed = 1;
        }
        return;
    }
    if (f & SDP_LK_SET_PWD) {
        /* len = old + new; with no password set, old is empty */
        if (len > S.pwd_len + SDP_PWD_MAX || len <= S.pwd_len ||
            (S.pwd_len && memcmp(p, S.pwd, S.pwd_len))) {
            S.lk_failed = 1;
            return;
        }
        uint8_t nl = (uint8_t)(len - S.pwd_len);
        memmove(S.pwd, p + S.pwd_len, nl);
        S.pwd_len = nl;
        if ((f & SDP_LK_LOCK) && !S.no_combined)
            S.locked = 1;
        return;
    }
    /* plain lock / unlock */
    if (!S.pwd_len || len != S.pwd_len || memcmp(p, S.pwd, len)) {
        S.lk_failed = 1;
        return;
    }
    S.locked = (f & SDP_LK_LOCK) ? 1 : 0;
}

static void sim_command(const uint8_t *c)
{
    uint8_t idx = c[0] & 0x3F;
    uint32_t arg = ((uint32_t)c[1] << 24) | ((uint32_t)c[2] << 16) |
                   ((uint32_t)c[3] << 8) | c[4];
    int acmd = S.acmd;
    S.acmd = 0;

    if ((idx == 0 || idx == 8) && sdp_crc7_byte(c, 5) != c[5]) {
        g_crc_fail++;
        q_push(0xFF);
        q_push(SDP_R1_CRC_ERR | (S.ready ? 0 : SDP_R1_IDLE));
        return;
    }
    uint8_t idle = S.ready ? 0 : SDP_R1_IDLE;
    q_push(0xFF); /* NCR = 1 byte */

    if (acmd) {
        if (idx == 41) {
            if (++S.acmd41_polls >= 3)
                S.ready = 1;
            q_push(S.ready ? 0 : SDP_R1_IDLE);
        } else {
            g_bad_cmd++;
            q_push(idle | SDP_R1_ILLEGAL_CMD);
        }
        return;
    }
    switch (idx) {
    case 0:
        S.spi = 1;
        S.ready = 0;
        S.acmd41_polls = 0;
        q_push(SDP_R1_IDLE);
        break;
    case 8:
        q_push(idle);
        q_push(0); q_push(0); q_push((uint8_t)((arg >> 8) & 0x0F));
        q_push((uint8_t)arg);
        break;
    case 55:
        S.acmd = 1;
        q_push(idle);
        break;
    case 58:
        q_push(idle);
        q_push(0xC0); q_push(0xFF); q_push(0x80); q_push(0x00); /* CCS */
        break;
    case 9: {
        uint8_t csd[16] = {0x40, 0x0E, 0x00, 0x32, 0x5B, 0x59, 0x00, 0x00,
                           0x3B, 0x37, 0x7F, 0x80, 0x0A, 0x40, 0x00, 0x01};
        if (!S.lock_class) {          /* clear CCC bit 7 = CSD bit 91 */
            csd[4] &= (uint8_t)~0x08u;
        }
        q_push(idle);
        q_push(0xFF);
        q_push(SDP_TOKEN_START);
        for (int i = 0; i < 16; i++) q_push(csd[i]);
        q_push(0x00); q_push(0x00);
        break;
    }
    case 13: {
        uint8_t r2 = (uint8_t)((S.locked ? SDP_R2_LOCKED : 0) |
                               (S.lk_failed ? SDP_R2_LK_FAILED : 0));
        S.lk_failed = 0; /* clear-on-read */
        q_push(idle);
        q_push(r2);
        break;
    }
    case 16:
        S.blocklen = arg;
        q_push(arg == 0 || arg > 512 ? (uint8_t)(idle | SDP_R1_PARAM_ERR) : idle);
        break;
    case 42:
        if (!S.ready || !S.lock_class) {
            q_push(idle | SDP_R1_ILLEGAL_CMD);
            break;
        }
        q_push(0);
        S.state = S_WAIT_TOKEN;
        break;
    default: /* anything else (read/write/erase...) is a driver bug here */
        g_bad_cmd++;
        q_push(idle | SDP_R1_ILLEGAL_CMD);
    }
}

static uint8_t sim_xfer(void *ctx, uint8_t out)
{
    (void)ctx;
    S.ms++;
    if (!S.cs)
        return 0xFF;
    uint8_t in = 0xFF;
    if (S.qh != S.qt)
        in = S.q[S.qh++ % 64];

    switch (S.state) {
    case S_IDLE:
        if ((out & 0xC0) == 0x40) {
            S.buf[0] = out;
            S.nbuf = 1;
            S.state = S_CMD;
        }
        break;
    case S_CMD:
        S.buf[S.nbuf++] = out;
        if (S.nbuf == 6) {
            S.state = S_IDLE;
            sim_command(S.buf);
        }
        break;
    case S_WAIT_TOKEN:
        if (out == SDP_TOKEN_START) {
            S.nbuf = 0;
            S.state = S_DATA;
        }
        break;
    case S_DATA:
        S.data[S.nbuf++] = out;
        if ((uint32_t)S.nbuf == S.blocklen + 2) { /* + CRC16 */
            S.state = S_IDLE;
            lk_process(S.data, S.blocklen);
            q_push(SDP_DRESP_ACCEPTED | 0xE0);
            q_push(0x00); q_push(0x00); q_push(0x00); /* busy */
        }
        break;
    }
    return in;
}

static void sim_cs(void *ctx, int a)
{
    (void)ctx;
    S.cs = a;
    if (!a) {
        S.state = S_IDLE;
        S.qh = S.qt = 0;
    }
}

static void sim_fast(void *ctx, int f) { (void)ctx; (void)f; }
static uint32_t sim_ms(void *ctx) { (void)ctx; return S.ms / 50; }

static const sd_bus_t BUS = {sim_xfer, sim_cs, sim_fast, sim_ms, NULL};

/* --------------------------------------------------------------- test --- */

static int fails, checks;

static void check(int ok, const char *fmt, ...)
{
    va_list ap;
    checks++;
    if (ok)
        return;
    fails++;
    printf("FAIL: ");
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    printf("\n");
}

#define EXPECT(expr, want) do { sd_err_t e_ = (expr); \
    check(e_ == (want), "%s -> %d (%s), want %d", #expr, e_, sd_err_str(e_), want); \
} while (0)

static void fresh(int lock_class)
{
    memset(&S, 0, sizeof S);
    S.lock_class = lock_class;
    sim_power_cycle();
}

static void test_proto(void)
{
    uint8_t f[6], blk[SDP_LK_BLOCK_MAX], pw[SDP_PWD_MAX];

    sdp_cmd_frame(0, 0, f);
    check(f[0] == 0x40 && f[5] == 0x95, "CMD0 frame crc 0x%02X", f[5]);
    sdp_cmd_frame(8, 0x1AA, f);
    check(f[5] == 0x87, "CMD8 frame crc 0x%02X", f[5]);
    sdp_cmd_frame(17, 0, f);
    check(f[5] == 0x55, "CMD17 frame crc 0x%02X", f[5]);

    /* Every one of the 256 flag values: only allowed subsets pass. */
    uint8_t one = 0x11;
    int passed = 0;
    for (int fl = 0; fl < 256; fl++) {
        int n = sdp_lock_block((uint8_t)fl, &one, 1, blk);
        if (n >= 0) {
            passed++;
            check(!(blk[0] & SDP_LK_ERASE), "ERASE escaped with flags 0x%02X", fl);
            check((fl & ~SDP_LK_ALLOWED) == 0, "flags 0x%02X accepted", fl);
        } else {
            check((fl & ~SDP_LK_ALLOWED) != 0, "allowed flags 0x%02X refused", fl);
        }
    }
    check(passed == 8, "allowed flag combinations = %d, want 8", passed);
    check(sdp_lock_block(SDP_LK_LOCK, pw, 0, blk) == -2, "empty pwd accepted");
    check(sdp_lock_block(SDP_LK_LOCK, pw, 17, blk) == -2, "17-byte pwd accepted");
    check(sdp_lock_block(SDP_LK_LOCK, pw, 16, blk) == 18, "16-byte pwd refused");

    /* Password spec parser (dummy values). */
    int n = sdp_parse_password("hex:DEADBEEF ascii:TestSuffix12", pw);
    check(n == 16 && pw[0] == 0xDE && pw[3] == 0xEF && pw[4] == 'T' &&
          pw[15] == '2', "parse hex+ascii -> %d", n);
    check(sdp_parse_password("ascii:12345678 ascii:TestSuffix12", pw) == -3,
          "20 bytes must be refused (SD max 16)");
    check(sdp_parse_password("hex:ABC", pw) == -2, "odd hex accepted");
    check(sdp_parse_password("hex:zz", pw) == -2, "bad hex accepted");
    check(sdp_parse_password("foo:1", pw) == -1, "unknown token accepted");
    check(sdp_parse_password("   ", pw) == -4, "empty spec accepted");
    check(sdp_parse_password("hex:00", pw) == 1 && pw[0] == 0, "hex:00");

    /* Built-in default password PASS. */
    check(sdp_parse_default_pass("Changeme", pw) == -5, "placeholder loaded");
    check(sdp_parse_default_pass(SDP_PASS_PLACEHOLDER, pw) == -5, "placeholder");
    check(sdp_parse_default_pass(NULL, pw) == -5, "NULL pass");
    n = sdp_parse_default_pass("hex:DEADBEEF ascii:TestSuffix12", pw);
    check(n == 16 && pw[0] == 0xDE && pw[15] == '2', "PASS tokens -> %d", n);
    n = sdp_parse_default_pass("test1234", pw);
    check(n == 8 && pw[0] == 't' && pw[7] == '4', "PASS plain -> %d", n);
    check(sdp_parse_default_pass("12345678901234567", pw) == -3, "PASS 17 bytes");
    check(sdp_parse_default_pass("", pw) == -4, "PASS empty");
    check(sdp_parse_default_pass("has space", pw) == -1, "PASS with space");

    uint8_t csd[16] = {0};
    csd[4] = 0x08; /* CCC bit 7 */
    check(sdp_csd_has_lock_class(csd) == 1, "lock class bit");
    csd[4] = 0xF7;
    csd[5] = 0xF0;
    check(sdp_csd_has_lock_class(csd) == 0, "lock class bit clear");
}

static void test_flows(void)
{
    static const uint8_t PW[16] = {0xDE, 0xAD, 0xBE, 0xEF, 'T', 'e', 's', 't',
                                   'S', 'u', 'f', 'f', 'i', 'x', '1', '2'};
    static const uint8_t BAD[16] = {0xEF, 0xBE, 0xAD, 0xDE, 'T', 'e', 's', 't',
                                    'S', 'u', 'f', 'f', 'i', 'x', '1', '2'};
    sd_card_t c;
    int locked = -1;

    /* 1. Fresh card: init, set+lock, power cycle -> locked. */
    fresh(1);
    EXPECT(sd_init(&BUS, &c), SD_OK);
    check(c.high_capacity && c.v2 && c.lock_class, "card info");
    EXPECT(sd_status(&BUS, &c, &locked), SD_OK);
    check(locked == 0, "fresh card unlocked");
    EXPECT(sd_op_lock(&BUS, &c, PW, 16), SD_ERR_LOCK_FAILED); /* no pwd yet */
    EXPECT(sd_op_set_and_lock(&BUS, &c, PW, 16), SD_OK);
    check(S.locked && S.pwd_len == 16 && !memcmp(S.pwd, PW, 16), "pwd stored");
    EXPECT(sd_op_set_and_lock(&BUS, &c, PW, 16), SD_ERR_STATE); /* locked */

    sim_power_cycle();
    EXPECT(sd_init(&BUS, &c), SD_OK); /* init works on a locked card */
    EXPECT(sd_status(&BUS, &c, &locked), SD_OK);
    check(locked == 1, "locked after power cycle");

    /* 2. Wrong password (e.g. swapped byte order) fails, state unchanged. */
    EXPECT(sd_op_unlock(&BUS, &c, BAD, 16), SD_ERR_LOCK_FAILED);
    check(S.locked, "still locked after wrong pwd");
    EXPECT(sd_op_verify(&BUS, &c, BAD, 16), SD_ERR_LOCK_FAILED);
    EXPECT(sd_op_unlock(&BUS, &c, PW, 15), SD_ERR_LOCK_FAILED); /* length */

    /* 3. verify: unlock + relock, ends locked. */
    EXPECT(sd_op_verify(&BUS, &c, PW, 16), SD_OK);
    check(S.locked, "locked after verify");

    /* 4. Temporary unlock, then power cycle locks again. */
    EXPECT(sd_op_unlock(&BUS, &c, PW, 16), SD_OK);
    check(!S.locked && S.pwd_len == 16, "unlocked, pwd kept");
    EXPECT(sd_op_lock(&BUS, &c, PW, 16), SD_OK);
    check(S.locked, "re-locked");
    EXPECT(sd_op_unlock(&BUS, &c, PW, 16), SD_OK);
    sim_power_cycle();
    EXPECT(sd_init(&BUS, &c), SD_OK);
    check(S.locked, "power cycle re-locks a card with a password");

    /* 5. Clear (from locked) removes the password for good. */
    EXPECT(sd_op_clear(&BUS, &c, BAD, 16), SD_ERR_LOCK_FAILED);
    check(S.pwd_len == 16, "wrong clear keeps pwd");
    EXPECT(sd_op_clear(&BUS, &c, PW, 16), SD_OK);
    check(S.pwd_len == 0 && !S.locked, "pwd cleared");
    sim_power_cycle();
    EXPECT(sd_init(&BUS, &c), SD_OK);
    check(!S.locked, "unlocked after power cycle when cleared");

    /* 6. Card that stores but does not lock in the combined command. */
    fresh(1);
    S.no_combined = 1;
    EXPECT(sd_init(&BUS, &c), SD_OK);
    EXPECT(sd_op_set_and_lock(&BUS, &c, PW, 16), SD_OK);
    check(S.locked && S.pwd_len == 16, "fallback lock");

    /* 7. Card without CMD42 support: refuse before sending anything. */
    fresh(0);
    EXPECT(sd_init(&BUS, &c), SD_ERR_NO_LOCK_CLASS);
    int before = S.cmd42_count;
    EXPECT(sd_op_set_and_lock(&BUS, &c, PW, 16), SD_ERR_NO_LOCK_CLASS);
    check(S.cmd42_count == before, "no CMD42 on a card without class 7");

    /* 8. Forced erase is unreachable through the driver. */
    fresh(1);
    EXPECT(sd_init(&BUS, &c), SD_OK);
    EXPECT(sd_op_set_and_lock(&BUS, &c, PW, 16), SD_OK);
    for (int fl = 0; fl < 256; fl++)
        if (fl & ~SDP_LK_ALLOWED)
            EXPECT(sd_cmd42(&BUS, &c, (uint8_t)fl, PW, 16), SD_ERR_BAD_ARG);
    check(S.locked && S.pwd_len == 16, "card intact after refused flags");

    /* 9. Not initialised / no card. */
    sd_card_t z;
    memset(&z, 0, sizeof z);
    EXPECT(sd_op_lock(&BUS, &z, PW, 16), SD_ERR_NOT_INIT);
}

static uint8_t dead_xfer(void *ctx, uint8_t out) { (void)ctx; (void)out; S.ms++; return 0xFF; }

static void test_no_card(void)
{
    sd_bus_t dead = BUS;
    sd_card_t c;
    dead.xfer = dead_xfer;
    EXPECT(sd_init(&dead, &c), SD_ERR_NO_RESPONSE);
}

int main(void)
{
    test_proto();
    test_flows();
    test_no_card();

    check(!g_erased && g_erase_frames == 0, "a forced-erase frame reached the card");
    check(g_bad_cmd == 0, "driver sent %d non-whitelisted commands", g_bad_cmd);
    check(g_crc_fail == 0, "%d CRC failures on CMD0/CMD8", g_crc_fail);

    printf("sdlock host test: %d checks, %d failed\n", checks, fails);
    return fails ? 1 : 0;
}
