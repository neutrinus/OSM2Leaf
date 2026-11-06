/*
 * sd_proto.h - pure SD SPI-mode protocol helpers (no hardware access).
 *
 * Everything here is plain C99 with no Pico SDK dependency, so the same code
 * is compiled into the firmware and into the host self-test
 * (test/test_sdlock.c).
 *
 * Reference: SD Specifications Part 1, Physical Layer Simplified
 * Specification, sections 4.3.7 (card lock/unlock), 7.3 (SPI mode:
 * commands, R1/R2 responses, data tokens).
 */
#ifndef SD_PROTO_H
#define SD_PROTO_H

#include <stddef.h>
#include <stdint.h>

/* ---- CMD42 LOCK_UNLOCK data structure, byte 0 ------------------------- */
#define SDP_LK_SET_PWD    0x01u /* bit 0: set (or replace) the password   */
#define SDP_LK_CLR_PWD    0x02u /* bit 1: clear the password              */
#define SDP_LK_LOCK       0x04u /* bit 2: 1 = lock, 0 = unlock            */
#define SDP_LK_ERASE      0x08u /* bit 3: FORCED ERASE - never sent here  */
/* Bits 4..7 are reserved (bit 4 is COP in newer specs) and must be 0.
 * Only these bits may ever leave this tool: */
#define SDP_LK_ALLOWED    (SDP_LK_SET_PWD | SDP_LK_CLR_PWD | SDP_LK_LOCK)

#define SDP_PWD_MAX       16u   /* PWD_LEN limit for one password (spec)   */
#define SDP_LK_BLOCK_MAX  (2u + SDP_PWD_MAX)

/* ---- R1 bits (SPI mode) ------------------------------------------------ */
#define SDP_R1_IDLE         0x01u
#define SDP_R1_ERASE_RESET  0x02u
#define SDP_R1_ILLEGAL_CMD  0x04u
#define SDP_R1_CRC_ERR      0x08u
#define SDP_R1_ERASE_SEQ    0x10u
#define SDP_R1_ADDR_ERR     0x20u
#define SDP_R1_PARAM_ERR    0x40u

/* ---- R2 second byte (SPI mode, CMD13 SEND_STATUS) ---------------------- */
#define SDP_R2_LOCKED       0x01u /* card is locked                        */
#define SDP_R2_LK_FAILED    0x02u /* WP erase skip | lock/unlock cmd failed */
#define SDP_R2_ERROR        0x04u
#define SDP_R2_CC_ERROR     0x08u
#define SDP_R2_ECC_FAILED   0x10u
#define SDP_R2_WP_VIOLATION 0x20u
#define SDP_R2_ERASE_PARAM  0x40u
#define SDP_R2_OUT_OF_RANGE 0x80u /* out of range | CSD overwrite          */

/* ---- data tokens ------------------------------------------------------- */
#define SDP_TOKEN_START     0xFEu /* single-block read/write start token   */
#define SDP_DRESP_MASK      0x1Fu
#define SDP_DRESP_ACCEPTED  0x05u /* xxx0 010 1 */
#define SDP_DRESP_CRC_ERR   0x0Bu /* xxx0 101 1 */
#define SDP_DRESP_WRITE_ERR 0x0Du /* xxx0 110 1 */

/* CRC7 over a command's first five bytes, returned as the full last byte
 * ((crc7 << 1) | 1). */
uint8_t sdp_crc7_byte(const uint8_t *buf, size_t len);

/* Build the 6-byte SPI command frame for CMDidx with a valid CRC7. */
void sdp_cmd_frame(uint8_t idx, uint32_t arg, uint8_t out[6]);

/*
 * Build the CMD42 data block.  Returns the block length (2 + pwd_len) or a
 * negative value if the request is not allowed:
 *   -1  flags contain ERASE or a reserved bit (forced erase is refused)
 *   -2  password empty or longer than SDP_PWD_MAX
 * This is the only function that produces CMD42 payloads; the SPI driver
 * calls nothing else.
 */
int sdp_lock_block(uint8_t flags, const uint8_t *pwd, size_t pwd_len,
                   uint8_t out[SDP_LK_BLOCK_MAX]);

/*
 * Parse a password spec made of space-separated tokens, concatenated in
 * order:
 *   hex:<even number of hex digits>   raw bytes
 *   ascii:<printable text, no spaces> bytes as typed
 * Example (dummy): "hex:DEADBEEF ascii:TestSuffix12" -> 16 bytes.
 * Returns the byte count, or a negative error:
 *   -1 unknown token prefix, -2 bad hex, -3 longer than SDP_PWD_MAX,
 *   -4 empty.
 */
int sdp_parse_password(const char *spec, uint8_t out[SDP_PWD_MAX]);

/* Command class bit 7 ("lock card") from a 16-byte CSD (CCC = CSD[95:84]). */
int sdp_csd_has_lock_class(const uint8_t csd[16]);

/* Human-readable names for R1 / R2 bits; write into buf, return buf. */
const char *sdp_r1_str(uint8_t r1, char *buf, size_t n);
const char *sdp_r2_str(uint8_t r2, char *buf, size_t n);

#endif /* SD_PROTO_H */
