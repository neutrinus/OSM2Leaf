/*
 * sdlock - SD card CMD42 lock/unlock tool for the Raspberry Pi Pico (RP2040).
 *
 * USB serial shell (115200 8N1 is ignored by USB CDC; any terminal works).
 * Wiring (SPI0): GP16 MISO, GP17 CS, GP18 SCK, GP19 MOSI, 3V3(OUT), GND.
 * See docs/hardware/sd-blocker-pico.md.
 *
 * Password: the built-in default PASS below (loaded into RAM at start-up),
 * or `pw ...` at run time.  PASS ships as the placeholder "Changeme", which
 * is never loaded.  Set the real value only in your local copy or at build
 * time (cmake -DSDLOCK_PASS=...); never commit it.
 */
#include <stdio.h>
#include <string.h>

#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "pico/stdlib.h"

#include "sd_card.h"
#include "sd_proto.h"

#define SDLOCK_VERSION "1.0"

#define SD_SPI     spi0
#define PIN_MISO   16
#define PIN_CS     17
#define PIN_SCK    18
#define PIN_MOSI   19
#define SLOW_HZ    400000u
#define FAST_HZ    4000000u /* plenty for CMD42; robust on jumper wires */

/* ---- bus binding ------------------------------------------------------- */

static uint8_t pico_xfer(void *ctx, uint8_t out)
{
    (void)ctx;
    uint8_t in = 0xFF;
    spi_write_read_blocking(SD_SPI, &out, &in, 1);
    return in;
}

static void pico_cs(void *ctx, int asserted)
{
    (void)ctx;
    gpio_put(PIN_CS, asserted ? 0 : 1);
}

static void pico_fast(void *ctx, int fast)
{
    (void)ctx;
    spi_set_baudrate(SD_SPI, fast ? FAST_HZ : SLOW_HZ);
}

static uint32_t pico_millis(void *ctx)
{
    (void)ctx;
    return to_ms_since_boot(get_absolute_time());
}

static const sd_bus_t bus = {pico_xfer, pico_cs, pico_fast, pico_millis, NULL};

/* ---- default password -------------------------------------------------- */

/*
 * PASS: the card password this build uses by default.
 * Format: the same tokens as the `pw` command, concatenated in order,
 *   "hex:<8 digits from the unit's SD PIN screen> ascii:<12-char suffix>"
 * or plain text without tokens.  At most 16 bytes.
 * Override at build time without editing this file:
 *   cmake -S . -B build -DSDLOCK_PASS="hex:... ascii:..."
 * "Changeme" is a placeholder and is ignored.  DO NOT COMMIT A REAL VALUE.
 */
#ifndef SDLOCK_PASS
#define SDLOCK_PASS SDP_PASS_PLACEHOLDER
#endif
static const char PASS[] = SDLOCK_PASS;

/* ---- state ------------------------------------------------------------- */

static sd_card_t card;
static uint8_t pwd[SDP_PWD_MAX];
static size_t pwd_len;

/* Load PASS into the RAM password buffer; print what happened. */
static void load_default_pass(void)
{
    uint8_t tmp[SDP_PWD_MAX];
    int n = sdp_parse_default_pass(PASS, tmp);
    if (n == -5) {
        printf("PASS is the placeholder \"%s\": no default password. "
               "Set PASS (or -DSDLOCK_PASS) or use pw.\n", SDP_PASS_PLACEHOLDER);
        return;
    }
    if (n < 0) {
        printf("PASS is invalid (error %d, max 16 bytes): ignored.\n", n);
        return;
    }
    memcpy(pwd, tmp, (size_t)n);
    memset(tmp, 0, sizeof tmp);
    pwd_len = (size_t)n;
    printf("password: %d bytes from PASS (not shown)\n", n);
}

static void led(int on)
{
#ifdef PICO_DEFAULT_LED_PIN
    gpio_put(PICO_DEFAULT_LED_PIN, on);
#else
    (void)on;
#endif
}

static void hw_init(void)
{
    spi_init(SD_SPI, SLOW_HZ);
    spi_set_format(SD_SPI, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);
    gpio_pull_up(PIN_MISO); /* DAT0 needs a pull-up; external 10k is better */
    gpio_init(PIN_CS);
    gpio_set_dir(PIN_CS, GPIO_OUT);
    gpio_put(PIN_CS, 1);
#ifdef PICO_DEFAULT_LED_PIN
    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);
#endif
}

/* ---- output helpers ---------------------------------------------------- */

static void print_detail(void)
{
    char b1[96], b2[128];
    printf("  R1=0x%02X (%s)  R2=0x%02X (%s)", card.last_r1,
           sdp_r1_str(card.last_r1, b1, sizeof b1), card.last_r2,
           sdp_r2_str(card.last_r2, b2, sizeof b2));
    if (card.last_dresp)
        printf("  data-resp=0x%02X", card.last_dresp);
    printf("\n");
}

static void report(const char *what, sd_err_t e)
{
    if (e == SD_OK)
        printf("%s: OK\n", what);
    else
        printf("%s: ERROR %d - %s\n", what, (int)e, sd_err_str(e));
    print_detail();
}

static void show_state(void)
{
    int locked = -1;
    sd_err_t e = sd_status(&bus, &card, &locked);
    if (e != SD_OK) {
        report("status", e);
        led(0);
        return;
    }
    printf("card state: %s\n", locked ? "LOCKED" : "unlocked");
    print_detail();
    led(locked);
}

static void cmd_init(void)
{
    sd_err_t e = sd_init(&bus, &card);
    report("init", e);
    if (!card.initialised)
        return;
    printf("  type=%s  OCR=0x%08lX  CMD42 (CCC class 7)=%s\n",
           card.high_capacity ? "SDHC/SDXC" : (card.v2 ? "SDSC v2" : "SDSC v1"),
           (unsigned long)card.ocr, card.lock_class ? "yes" : "NO");
    printf("  CSD=");
    for (int i = 0; i < 16; i++)
        printf("%02X", card.csd[i]);
    printf("\n");
    show_state();
}

static int need_pwd(void)
{
    if (pwd_len == 0) {
        printf("no password set: use  pw hex:<digits> ascii:<text>\n");
        return 0;
    }
    return 1;
}

static int confirmed(const char *arg, const char *what)
{
    if (strcmp(arg, "YES") == 0)
        return 1;
    printf("%s changes the card's password. Type '%s YES' to confirm.\n",
           what, what);
    return 0;
}

static void help(void)
{
    printf(
        "sdlock " SDLOCK_VERSION " - SD CMD42 lock tool (SPI0: GP16 MISO, GP17 CS, "
        "GP18 SCK, GP19 MOSI)\n"
        "  init                 power-up sequence, CSD, lock state\n"
        "  status               CMD13: locked / unlocked\n"
        "  pw <tokens>          set password in RAM, tokens concatenated:\n"
        "                         hex:<hex digits>  ascii:<text>  (max 16 bytes)\n"
        "  pw                   show password length\n"
        "  pwforget             wipe password from RAM\n"
        "  pwdefault            reload the built-in PASS\n"
        "  setlock YES          SET_PWD + LOCK on a card WITHOUT a password\n"
        "  lock                 LOCK a card that already has this password\n"
        "  unlock               temporary unlock (card re-locks at power-up)\n"
        "  verify               locked card: unlock + lock again (checks pwd)\n"
        "  clear YES            remove the password for good (card stays\n"
        "                       unlocked at power-up; for writing in a PC)\n"
        "There is no erase command. Forced erase (CMD42 ERASE bit) is refused.\n");
}

static void dispatch(char *line)
{
    char *arg = strchr(line, ' ');
    if (arg) {
        *arg++ = '\0';
        while (*arg == ' ')
            arg++;
    } else {
        arg = line + strlen(line);
    }

    if (line[0] == '\0') {
        return;
    } else if (!strcmp(line, "help") || !strcmp(line, "?")) {
        help();
    } else if (!strcmp(line, "init")) {
        cmd_init();
    } else if (!strcmp(line, "status")) {
        show_state();
    } else if (!strcmp(line, "pw")) {
        if (*arg == '\0') {
            printf("password: %u bytes in RAM\n", (unsigned)pwd_len);
            return;
        }
        uint8_t tmp[SDP_PWD_MAX];
        int n = sdp_parse_password(arg, tmp);
        if (n < 0) {
            static const char *const why[] = {
                "", "unknown token (use hex:... / ascii:...)", "bad hex",
                "longer than 16 bytes (SD limit)", "empty"};
            printf("pw: ERROR - %s\n", why[-n]);
            return;
        }
        memcpy(pwd, tmp, (size_t)n);
        memset(tmp, 0, sizeof tmp);
        pwd_len = (size_t)n;
        printf("password: %d bytes in RAM (not shown)\n", n);
    } else if (!strcmp(line, "pwdefault")) {
        load_default_pass();
    } else if (!strcmp(line, "pwforget")) {
        memset(pwd, 0, sizeof pwd);
        pwd_len = 0;
        printf("password wiped\n");
    } else if (!strcmp(line, "setlock")) {
        if (need_pwd() && confirmed(arg, "setlock")) {
            report("setlock", sd_op_set_and_lock(&bus, &card, pwd, pwd_len));
            show_state();
        }
    } else if (!strcmp(line, "lock")) {
        if (need_pwd()) {
            report("lock", sd_op_lock(&bus, &card, pwd, pwd_len));
            show_state();
        }
    } else if (!strcmp(line, "unlock")) {
        if (need_pwd()) {
            report("unlock", sd_op_unlock(&bus, &card, pwd, pwd_len));
            show_state();
        }
    } else if (!strcmp(line, "verify")) {
        if (need_pwd()) {
            report("verify", sd_op_verify(&bus, &card, pwd, pwd_len));
            show_state();
        }
    } else if (!strcmp(line, "clear")) {
        if (need_pwd() && confirmed(arg, "clear")) {
            report("clear", sd_op_clear(&bus, &card, pwd, pwd_len));
            show_state();
        }
    } else {
        printf("unknown command '%s' (try help)\n", line);
    }
}

int main(void)
{
    stdio_init_all();
    hw_init();

    char line[96];
    size_t len = 0;
    int was_connected = 0;
    int last_cr = 0;

    for (;;) {
        int connected = stdio_usb_connected();
        if (connected && !was_connected) {
            sleep_ms(200);
            printf("\n");
            help();
            if (pwd_len == 0)
                load_default_pass();
            printf("> ");
        }
        was_connected = connected;

        int ch = getchar_timeout_us(100000);
        if (ch == PICO_ERROR_TIMEOUT)
            continue;
        if (ch == '\n' && last_cr) { /* CR LF from the terminal */
            last_cr = 0;
            continue;
        }
        last_cr = (ch == '\r');
        if (ch == '\r' || ch == '\n') {
            printf("\n");
            line[len] = '\0';
            dispatch(line);
            memset(line, 0, sizeof line);
            len = 0;
            printf("> ");
        } else if (ch == 0x08 || ch == 0x7F) {
            if (len) {
                len--;
                printf("\b \b");
            }
        } else if (ch >= 0x20 && ch < 0x7F && len + 1 < sizeof line) {
            line[len++] = (char)ch;
            putchar(ch);
        }
    }
}
