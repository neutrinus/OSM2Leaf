/*
 * ze0_cov.c - out-of-tree TCG plugin: executed-basic-block coverage for -M ze0.
 *
 * Records the guest virtual address of each translated block and the number
 * of times it executes, then prints one "VA,COUNT" line per block at exit.
 * Built against the pinned QEMU 11.1.3 plugin API (QEMU_PLUGIN_VERSION 7).
 * Output is visible with QEMU's -d plugin (see tools/ze0_cov.py).
 *
 * No QEMU source patch. GPL-2.0-or-later, like the stock plugins.
 */
#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <glib.h>

#include <qemu-plugin.h>

QEMU_PLUGIN_EXPORT int qemu_plugin_version = QEMU_PLUGIN_VERSION;

/* One entry per (block VA, instruction count). The count distinguishes two
 * blocks that share a start VA but differ in length (same shape as QEMU's
 * contrib/plugins/hotblocks.c). */
typedef struct {
    uint64_t start_addr;
    size_t insns;
    struct qemu_plugin_scoreboard *exec_count;
} Block;

static GMutex lock;
static GHashTable *blocks;

static guint64 period = 1;       /* sample every Nth translated block */
static guint64 tb_seen = 0;      /* total translations (for --period) */
static guint64 tb_recorded = 0;  /* blocks actually counted */

static gint cmp_blocks(gconstpointer a, gconstpointer b, gpointer unused)
{
    const Block *ba = (const Block *)a;
    const Block *bb = (const Block *)b;
    (void)unused;
    if (ba->start_addr < bb->start_addr) {
        return -1;
    }
    if (ba->start_addr > bb->start_addr) {
        return 1;
    }
    return 0;
}

static guint block_hash(gconstpointer v)
{
    const Block *b = (const Block *)v;
    return (guint)(b->start_addr ^ (uint64_t)b->insns);
}

static gboolean block_equal(gconstpointer v1, gconstpointer v2)
{
    const Block *b1 = (const Block *)v1;
    const Block *b2 = (const Block *)v2;
    return b1->start_addr == b2->start_addr && b1->insns == b2->insns;
}

static void block_free(gpointer key, gpointer value, gpointer user_data)
{
    Block *b = (Block *)value;
    (void)key;
    (void)user_data;
    qemu_plugin_scoreboard_free(b->exec_count);
    g_free(b);
}

static void count_block(unsigned int cpu_index, void *udata)
{
    Block *b = (Block *)udata;
    qemu_plugin_u64_add(qemu_plugin_scoreboard_u64(b->exec_count),
                        cpu_index, 1);
}

static void vcpu_tb_trans(struct qemu_plugin_tb *tb, void *userdata)
{
    uint64_t pc = qemu_plugin_tb_vaddr(tb);
    size_t insns = qemu_plugin_tb_n_insns(tb);
    Block key = { .start_addr = pc, .insns = insns };
    Block *b;

    (void)userdata;

    g_mutex_lock(&lock);
    tb_seen++;
    if (period > 1 && (tb_seen % period) != 0) {
        g_mutex_unlock(&lock);
        return;
    }
    b = (Block *)g_hash_table_lookup(blocks, &key);
    if (b == NULL) {
        b = g_new0(Block, 1);
        b->start_addr = pc;
        b->insns = insns;
        b->exec_count = qemu_plugin_scoreboard_new(sizeof(uint64_t));
        g_hash_table_insert(blocks, b, b);
        tb_recorded++;
    }
    g_mutex_unlock(&lock);

    qemu_plugin_register_vcpu_tb_exec_cb(tb, count_block,
                                         QEMU_PLUGIN_CB_NO_REGS, (void *)b);
}

static void plugin_exit(void *p)
{
    GString *out = g_string_new(NULL);
    GList *vals, *sorted, *it;

    (void)p;

    g_mutex_lock(&lock);
    g_string_append_printf(out,
        "ze0_cov: period=%" PRIu64 " translated=%" PRIu64
        " recorded=%" PRIu64 " entries=%u\n",
        period, tb_seen, tb_recorded, g_hash_table_size(blocks));
    g_mutex_unlock(&lock);

    g_string_append(out, "ze0_cov: VA,COUNT\n");
    vals = g_hash_table_get_values(blocks);
    sorted = g_list_sort_with_data(vals, cmp_blocks, NULL);
    for (it = sorted; it != NULL; it = it->next) {
        Block *b = (Block *)it->data;
        g_string_append_printf(out, "0x%016" PRIx64 ",%" PRIu64 "\n",
            b->start_addr,
            qemu_plugin_u64_sum(qemu_plugin_scoreboard_u64(b->exec_count)));
    }
    g_list_free(sorted);
    qemu_plugin_outs(out->str);
    g_string_free(out, TRUE);

    g_hash_table_foreach(blocks, block_free, NULL);
    g_hash_table_destroy(blocks);
}

QEMU_PLUGIN_EXPORT
int qemu_plugin_install(qemu_plugin_id_t id, const qemu_info_t *info,
                        int argc, char **argv)
{
    int i;

    (void)info;

    for (i = 0; i < argc; i++) {
        char *opt = argv[i];
        g_auto(GStrv) tokens = g_strsplit(opt, "=", 2);
        if (g_strcmp0(tokens[0], "period") == 0) {
            char *endptr = NULL;
            period = g_ascii_strtoull(tokens[1], &endptr, 10);
            if (endptr == tokens[1] || *endptr != '\0' || period == 0) {
                fprintf(stderr, "ze0_cov: bad period '%s'\n", tokens[1]);
                return -1;
            }
        } else {
            fprintf(stderr, "ze0_cov: unknown option '%s'\n", opt);
            return -1;
        }
    }

    blocks = g_hash_table_new(block_hash, block_equal);
    qemu_plugin_register_vcpu_tb_trans_cb(id, vcpu_tb_trans, NULL);
    qemu_plugin_register_atexit_cb(id, plugin_exit, NULL);
    return 0;
}
