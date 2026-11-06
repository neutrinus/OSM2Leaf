/* sd_card.c - SD SPI-mode driver limited to init, status and CMD42.
 * See sd_card.h for the safety contract. */
#include "sd_card.h"
#include "sd_proto.h"

#include <string.h>

#define INIT_TIMEOUT_MS   1500u
#define TOKEN_TIMEOUT_MS   200u
#define BUSY_TIMEOUT_MS   3000u

static uint8_t rx(const sd_bus_t *b) { return b->xfer(b->ctx, 0xFF); }

static void sel(const sd_bus_t *b) { b->cs(b->ctx, 1); }

static void desel(const sd_bus_t *b)
{
    b->cs(b->ctx, 0);
    rx(b); /* 8 extra clocks so the card releases MISO */
}

/* Send one command (CS already asserted) and return R1 (0xFF = none). */
static uint8_t cmd(const sd_bus_t *b, uint8_t idx, uint32_t arg)
{
    uint8_t f[6];
    sdp_cmd_frame(idx, arg, f);
    rx(b);
    for (int i = 0; i < 6; i++)
        b->xfer(b->ctx, f[i]);
    for (int i = 0; i < 16; i++) { /* NCR is at most 8 bytes */
        uint8_t r = rx(b);
        if (!(r & 0x80u))
            return r;
    }
    return 0xFF;
}

/* A whole command with CS framing; for commands with a plain R1. */
static uint8_t cmd1(const sd_bus_t *b, uint8_t idx, uint32_t arg)
{
    sel(b);
    uint8_t r = cmd(b, idx, arg);
    desel(b);
    return r;
}

sd_err_t sd_init(const sd_bus_t *b, sd_card_t *c)
{
    uint8_t r = 0xFF;

    memset(c, 0, sizeof *c);
    b->set_fast(b->ctx, 0);

    /* >= 74 clocks with CS high (deselected) after power-up. */
    b->cs(b->ctx, 0);
    for (int i = 0; i < 10; i++)
        rx(b);

    /* CMD0 GO_IDLE_STATE with CS low enters SPI mode. */
    for (int tries = 0; tries < 20; tries++) {
        r = cmd1(b, 0, 0);
        if (r == SDP_R1_IDLE)
            break;
    }
    c->last_r1 = r;
    if (r == 0xFF)
        return SD_ERR_NO_RESPONSE;
    if (r != SDP_R1_IDLE)
        return SD_ERR_NOT_IDLE;

    /* CMD8 SEND_IF_COND: 2.7-3.6 V, check pattern 0xAA. */
    sel(b);
    r = cmd(b, 8, 0x000001AAu);
    c->last_r1 = r;
    if (r == 0xFF) {
        desel(b);
        return SD_ERR_NO_RESPONSE;
    }
    if (r & SDP_R1_ILLEGAL_CMD) {
        c->v2 = 0; /* SD v1.x: no CMD8 */
    } else {
        uint8_t r7[4];
        for (int i = 0; i < 4; i++)
            r7[i] = rx(b);
        if ((r7[2] & 0x0Fu) != 0x01u || r7[3] != 0xAAu) {
            desel(b);
            return SD_ERR_VOLTAGE;
        }
        c->v2 = 1;
    }
    desel(b);

    /* ACMD41 SD_SEND_OP_COND until the card leaves idle. */
    uint32_t t0 = b->millis(b->ctx);
    for (;;) {
        r = cmd1(b, 55, 0);
        if (r & (uint8_t)~SDP_R1_IDLE) {
            c->last_r1 = r;
            return r == 0xFF ? SD_ERR_NO_RESPONSE : SD_ERR_R1;
        }
        r = cmd1(b, 41, c->v2 ? 0x40000000u : 0u); /* HCS */
        c->last_r1 = r;
        if (r == 0)
            break;
        if (r & (uint8_t)~SDP_R1_IDLE)
            return SD_ERR_R1;
        if ((uint32_t)(b->millis(b->ctx) - t0) > INIT_TIMEOUT_MS)
            return SD_ERR_INIT_TIMEOUT;
    }

    /* CMD58 READ_OCR: CCS bit tells SDSC from SDHC/SDXC. */
    sel(b);
    r = cmd(b, 58, 0);
    c->last_r1 = r;
    if (r == 0) {
        for (int i = 0; i < 4; i++)
            c->ocr = (c->ocr << 8) | rx(b);
    }
    desel(b);
    if (r != 0)
        return SD_ERR_R1;
    c->high_capacity = c->v2 && (c->ocr & 0x40000000u);

    /* CMD9 SEND_CSD: a 16-byte data block; class 7 = lock card. */
    sel(b);
    r = cmd(b, 9, 0);
    c->last_r1 = r;
    if (r != 0) {
        desel(b);
        return SD_ERR_R1;
    }
    t0 = b->millis(b->ctx);
    for (;;) {
        uint8_t t = rx(b);
        if (t == SDP_TOKEN_START)
            break;
        if ((uint32_t)(b->millis(b->ctx) - t0) > TOKEN_TIMEOUT_MS) {
            desel(b);
            return SD_ERR_TOKEN_TIMEOUT;
        }
    }
    for (int i = 0; i < 16; i++)
        c->csd[i] = rx(b);
    rx(b); /* CRC16, unchecked */
    rx(b);
    desel(b);
    c->lock_class = sdp_csd_has_lock_class(c->csd);

    b->set_fast(b->ctx, 1);
    c->initialised = 1;
    return c->lock_class ? SD_OK : SD_ERR_NO_LOCK_CLASS;
}

sd_err_t sd_status(const sd_bus_t *b, sd_card_t *c, int *locked)
{
    if (!c->initialised)
        return SD_ERR_NOT_INIT;
    sel(b);
    uint8_t r = cmd(b, 13, 0);
    uint8_t r2 = rx(b);
    desel(b);
    c->last_r1 = r;
    if (r == 0xFF)
        return SD_ERR_NO_RESPONSE;
    c->last_r2 = r2;
    if (locked)
        *locked = (r2 & SDP_R2_LOCKED) ? 1 : 0;
    return SD_OK;
}

sd_err_t sd_cmd42(const sd_bus_t *b, sd_card_t *c, uint8_t flags,
                  const uint8_t *pwd, size_t pwd_len)
{
    uint8_t blk[SDP_LK_BLOCK_MAX];
    int n = sdp_lock_block(flags, pwd, pwd_len, blk);
    if (n < 0)
        return SD_ERR_BAD_ARG; /* includes every ERASE attempt */
    if (!c->initialised)
        return SD_ERR_NOT_INIT;
    if (!c->lock_class)
        return SD_ERR_NO_LOCK_CLASS;

    /* Read (and so clear) any stale LOCK_UNLOCK_FAILED bit first. */
    sd_err_t e = sd_status(b, c, NULL);
    if (e != SD_OK)
        return e;

    /* CMD16: block length = size of the lock data structure.  On SDHC/SDXC
     * CMD16 affects only CMD42. */
    uint8_t r = cmd1(b, 16, (uint32_t)n);
    c->last_r1 = r;
    if (r != 0)
        return r == 0xFF ? SD_ERR_NO_RESPONSE : SD_ERR_R1;

    sel(b);
    r = cmd(b, 42, 0);
    c->last_r1 = r;
    if (r != 0) {
        desel(b);
        cmd1(b, 16, 512);
        return r == 0xFF ? SD_ERR_NO_RESPONSE : SD_ERR_R1;
    }
    rx(b); /* NWR gap */
    b->xfer(b->ctx, SDP_TOKEN_START);
    for (int i = 0; i < n; i++)
        b->xfer(b->ctx, blk[i]);
    b->xfer(b->ctx, 0xFF); /* CRC16: CRC is off in SPI mode by default */
    b->xfer(b->ctx, 0xFF);
    uint8_t d = rx(b) & SDP_DRESP_MASK;
    c->last_dresp = d;
    sd_err_t result = SD_OK;
    if (d != SDP_DRESP_ACCEPTED) {
        result = SD_ERR_DATA_REJECTED;
    } else {
        uint32_t t0 = b->millis(b->ctx);
        while (rx(b) == 0x00) { /* busy: card holds MISO low */
            if ((uint32_t)(b->millis(b->ctx) - t0) > BUSY_TIMEOUT_MS) {
                result = SD_ERR_BUSY_TIMEOUT;
                break;
            }
        }
    }
    memset(blk, 0, sizeof blk);
    desel(b);

    cmd1(b, 16, 512); /* restore the default for SDSC cards */

    e = sd_status(b, c, NULL);
    if (result != SD_OK)
        return result;
    if (e != SD_OK)
        return e;
    if (c->last_r2 & SDP_R2_LK_FAILED)
        return SD_ERR_LOCK_FAILED;
    return SD_OK;
}

static sd_err_t expect_locked(const sd_bus_t *b, sd_card_t *c, int want)
{
    int locked = -1;
    sd_err_t e = sd_status(b, c, &locked);
    if (e != SD_OK)
        return e;
    return locked == want ? SD_OK : SD_ERR_STATE;
}

sd_err_t sd_op_set_and_lock(const sd_bus_t *b, sd_card_t *c,
                            const uint8_t *pwd, size_t len)
{
    int locked = 0;
    sd_err_t e = sd_status(b, c, &locked);
    if (e != SD_OK)
        return e;
    if (locked)
        return SD_ERR_STATE; /* already has a password: unlock/clear first */
    e = sd_cmd42(b, c, SDP_LK_SET_PWD | SDP_LK_LOCK, pwd, len);
    if (e != SD_OK)
        return e;
    if (expect_locked(b, c, 1) == SD_OK)
        return SD_OK;
    /* Some cards store the password but do not lock in the same
     * transaction: lock explicitly with the password just set. */
    e = sd_cmd42(b, c, SDP_LK_LOCK, pwd, len);
    if (e != SD_OK)
        return e;
    return expect_locked(b, c, 1);
}

sd_err_t sd_op_lock(const sd_bus_t *b, sd_card_t *c,
                    const uint8_t *pwd, size_t len)
{
    int locked = 0;
    sd_err_t e = sd_status(b, c, &locked);
    if (e != SD_OK)
        return e;
    if (locked)
        return SD_OK;
    e = sd_cmd42(b, c, SDP_LK_LOCK, pwd, len);
    if (e != SD_OK)
        return e;
    return expect_locked(b, c, 1);
}

sd_err_t sd_op_unlock(const sd_bus_t *b, sd_card_t *c,
                      const uint8_t *pwd, size_t len)
{
    int locked = 0;
    sd_err_t e = sd_status(b, c, &locked);
    if (e != SD_OK)
        return e;
    if (!locked)
        return SD_OK;
    e = sd_cmd42(b, c, 0, pwd, len); /* LOCK_UNLOCK = 0: unlock */
    if (e != SD_OK)
        return e;
    return expect_locked(b, c, 0);
}

sd_err_t sd_op_clear(const sd_bus_t *b, sd_card_t *c,
                     const uint8_t *pwd, size_t len)
{
    sd_err_t e = sd_op_unlock(b, c, pwd, len);
    if (e != SD_OK)
        return e;
    e = sd_cmd42(b, c, SDP_LK_CLR_PWD, pwd, len);
    if (e != SD_OK)
        return e;
    return expect_locked(b, c, 0);
}

sd_err_t sd_op_verify(const sd_bus_t *b, sd_card_t *c,
                      const uint8_t *pwd, size_t len)
{
    sd_err_t e = expect_locked(b, c, 1);
    if (e != SD_OK)
        return e;
    e = sd_cmd42(b, c, 0, pwd, len);
    if (e != SD_OK)
        return e;
    e = sd_cmd42(b, c, SDP_LK_LOCK, pwd, len);
    if (e != SD_OK)
        return e;
    return expect_locked(b, c, 1);
}

const char *sd_err_str(sd_err_t e)
{
    switch (e) {
    case SD_OK:                return "OK";
    case SD_ERR_NO_RESPONSE:   return "no response (no card? wiring? power?)";
    case SD_ERR_NOT_IDLE:      return "CMD0 did not return idle (R1=0x01)";
    case SD_ERR_VOLTAGE:       return "CMD8 voltage/check-pattern mismatch";
    case SD_ERR_INIT_TIMEOUT:  return "ACMD41 init timeout";
    case SD_ERR_R1:            return "command error in R1";
    case SD_ERR_TOKEN_TIMEOUT: return "no data token (CSD)";
    case SD_ERR_NO_LOCK_CLASS: return "card does not support CMD42 (CCC class 7 clear)";
    case SD_ERR_DATA_REJECTED: return "CMD42 data block rejected";
    case SD_ERR_BUSY_TIMEOUT:  return "card busy timeout after CMD42";
    case SD_ERR_LOCK_FAILED:   return "LOCK_UNLOCK_FAILED: wrong password or state";
    case SD_ERR_BAD_ARG:       return "refused locally (ERASE bit or bad password length)";
    case SD_ERR_STATE:         return "unexpected lock state after the operation";
    case SD_ERR_NOT_INIT:      return "card not initialised: run 'init'";
    }
    return "?";
}
