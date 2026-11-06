/* sd_proto.c - see sd_proto.h. Pure C99, shared by firmware and host test. */
#include "sd_proto.h"

#include <string.h>

uint8_t sdp_crc7_byte(const uint8_t *buf, size_t len)
{
    uint8_t crc = 0;
    for (size_t i = 0; i < len; i++) {
        uint8_t d = buf[i];
        for (int b = 0; b < 8; b++) {
            crc <<= 1;
            if ((d ^ crc) & 0x80u)
                crc ^= 0x09u;
            d <<= 1;
        }
    }
    return (uint8_t)(((crc & 0x7Fu) << 1) | 1u);
}

void sdp_cmd_frame(uint8_t idx, uint32_t arg, uint8_t out[6])
{
    out[0] = (uint8_t)(0x40u | (idx & 0x3Fu));
    out[1] = (uint8_t)(arg >> 24);
    out[2] = (uint8_t)(arg >> 16);
    out[3] = (uint8_t)(arg >> 8);
    out[4] = (uint8_t)arg;
    out[5] = sdp_crc7_byte(out, 5);
}

int sdp_lock_block(uint8_t flags, const uint8_t *pwd, size_t pwd_len,
                   uint8_t out[SDP_LK_BLOCK_MAX])
{
    /* Refuse forced erase and every reserved bit, whatever the caller. */
    if (flags & (uint8_t)~SDP_LK_ALLOWED)
        return -1;
    if (pwd == NULL || pwd_len == 0 || pwd_len > SDP_PWD_MAX)
        return -2;
    memset(out, 0, SDP_LK_BLOCK_MAX);
    out[0] = flags;
    out[1] = (uint8_t)pwd_len;
    memcpy(out + 2, pwd, pwd_len);
    return (int)(2 + pwd_len);
}

static int hexval(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

int sdp_parse_password(const char *spec, uint8_t out[SDP_PWD_MAX])
{
    size_t n = 0;
    const char *p = spec;

    for (;;) {
        while (*p == ' ' || *p == '\t')
            p++;
        if (*p == '\0')
            break;
        const char *end = p;
        while (*end && *end != ' ' && *end != '\t')
            end++;

        if (strncmp(p, "hex:", 4) == 0) {
            const char *h = p + 4;
            size_t digits = (size_t)(end - h);
            if (digits == 0 || (digits & 1u))
                return -2;
            for (size_t i = 0; i < digits; i += 2) {
                int hi = hexval(h[i]), lo = hexval(h[i + 1]);
                if (hi < 0 || lo < 0)
                    return -2;
                if (n >= SDP_PWD_MAX)
                    return -3;
                out[n++] = (uint8_t)((hi << 4) | lo);
            }
        } else if (strncmp(p, "ascii:", 6) == 0) {
            const char *a = p + 6;
            if (a == end)
                return -1;
            for (; a < end; a++) {
                if ((unsigned char)*a < 0x21 || (unsigned char)*a > 0x7E)
                    return -1;
                if (n >= SDP_PWD_MAX)
                    return -3;
                out[n++] = (uint8_t)*a;
            }
        } else {
            return -1;
        }
        p = end;
    }
    return n == 0 ? -4 : (int)n;
}

int sdp_csd_has_lock_class(const uint8_t csd[16])
{
    /* CSD bits [95:84] = CCC.  Byte 4 holds bits 95..88, byte 5 high
     * nibble holds bits 87..84. */
    unsigned ccc = ((unsigned)csd[4] << 4) | ((unsigned)csd[5] >> 4);
    return (ccc >> 7) & 1u;
}

static const char *bits_str(uint8_t v, const char *const names[8],
                            char *buf, size_t n)
{
    size_t used = 0;
    if (n == 0)
        return buf;
    buf[0] = '\0';
    for (int b = 0; b < 8; b++) {
        if (!(v & (1u << b)) || names[b] == NULL)
            continue;
        size_t l = strlen(names[b]);
        if (used + l + 2 >= n)
            break;
        if (used) buf[used++] = ',';
        memcpy(buf + used, names[b], l);
        used += l;
        buf[used] = '\0';
    }
    if (used == 0 && n > 2) {
        buf[0] = 'o';
        buf[1] = 'k';
        buf[2] = '\0';
    }
    return buf;
}

const char *sdp_r1_str(uint8_t r1, char *buf, size_t n)
{
    static const char *const names[8] = {
        "idle", "erase_reset", "illegal_cmd", "crc_err",
        "erase_seq_err", "addr_err", "param_err", "invalid(b7)"};
    return bits_str(r1, names, buf, n);
}

const char *sdp_r2_str(uint8_t r2, char *buf, size_t n)
{
    static const char *const names[8] = {
        "LOCKED", "lock_unlock_failed", "error", "cc_error",
        "ecc_failed", "wp_violation", "erase_param", "out_of_range"};
    return bits_str(r2, names, buf, n);
}
