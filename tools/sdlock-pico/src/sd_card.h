/*
 * sd_card.h - SD card SPI-mode driver: init, status, CMD42 operations.
 *
 * Hardware-independent: the caller supplies a bus (byte exchange, chip
 * select, clock speed, millisecond clock).  The firmware binds it to the
 * RP2040 SPI block (main.c); the host self-test binds it to a simulated card.
 *
 * The driver never reads or writes data blocks (no CMD17/CMD24/CMD25), never
 * erases (no CMD32/33/38) and cannot send CMD42 with the ERASE bit: every
 * CMD42 payload comes from sdp_lock_block(), which refuses it.
 */
#ifndef SD_CARD_H
#define SD_CARD_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint8_t (*xfer)(void *ctx, uint8_t out); /* full-duplex one byte    */
    void (*cs)(void *ctx, int asserted);      /* 1 = CS low (selected)   */
    void (*set_fast)(void *ctx, int fast);    /* 0 = <=400 kHz, 1 = fast  */
    uint32_t (*millis)(void *ctx);            /* monotonic milliseconds  */
    void *ctx;
} sd_bus_t;

typedef enum {
    SD_OK = 0,
    SD_ERR_NO_RESPONSE,   /* no R1 at all: no card, wiring, power        */
    SD_ERR_NOT_IDLE,      /* CMD0 answered but never with R1 = 0x01      */
    SD_ERR_VOLTAGE,       /* CMD8 echo/voltage mismatch                  */
    SD_ERR_INIT_TIMEOUT,  /* ACMD41 never left idle                      */
    SD_ERR_R1,            /* a command returned an error bit in R1       */
    SD_ERR_TOKEN_TIMEOUT, /* no data start token (CSD read)              */
    SD_ERR_NO_LOCK_CLASS, /* CSD CCC bit 7 clear: card has no CMD42      */
    SD_ERR_DATA_REJECTED, /* CMD42 data block not accepted               */
    SD_ERR_BUSY_TIMEOUT,  /* card stayed busy after CMD42                */
    SD_ERR_LOCK_FAILED,   /* R2 "lock/unlock failed": wrong pwd/state    */
    SD_ERR_BAD_ARG,       /* refused locally (ERASE bit, pwd length)     */
    SD_ERR_STATE,         /* card state after the op is not the expected */
    SD_ERR_NOT_INIT       /* sd_init() has not succeeded                 */
} sd_err_t;

typedef struct {
    int initialised;
    int v2;               /* answered CMD8 (SD v2+)                      */
    int high_capacity;    /* OCR CCS: SDHC/SDXC                          */
    uint32_t ocr;
    uint8_t csd[16];
    int lock_class;       /* CSD CCC bit 7                               */
    uint8_t last_r1;      /* R1 of the last command                      */
    uint8_t last_r2;      /* second status byte of the last CMD13        */
    uint8_t last_dresp;   /* last data response token (CMD42)            */
} sd_card_t;

/* Power-up sequence, CMD0/CMD8/ACMD41/CMD58, CSD read and lock-class
 * check.  Works on a locked card (those commands are allowed when locked). */
sd_err_t sd_init(const sd_bus_t *bus, sd_card_t *card);

/* CMD13; sets card->last_r1/last_r2 and *locked. */
sd_err_t sd_status(const sd_bus_t *bus, sd_card_t *card, int *locked);

/* One raw CMD42 transaction (CMD16, CMD42, data block, busy, CMD16 512,
 * CMD13).  flags must be a subset of SDP_LK_ALLOWED. */
sd_err_t sd_cmd42(const sd_bus_t *bus, sd_card_t *card, uint8_t flags,
                  const uint8_t *pwd, size_t pwd_len);

/* High-level operations; each one checks the resulting lock state. */
sd_err_t sd_op_set_and_lock(const sd_bus_t *, sd_card_t *, const uint8_t *, size_t);
sd_err_t sd_op_lock(const sd_bus_t *, sd_card_t *, const uint8_t *, size_t);
sd_err_t sd_op_unlock(const sd_bus_t *, sd_card_t *, const uint8_t *, size_t);
sd_err_t sd_op_clear(const sd_bus_t *, sd_card_t *, const uint8_t *, size_t);
/* Locked card only: unlock with pwd, then lock again.  Proves the password
 * without leaving the card unlocked. */
sd_err_t sd_op_verify(const sd_bus_t *, sd_card_t *, const uint8_t *, size_t);

const char *sd_err_str(sd_err_t e);

#endif /* SD_CARD_H */
